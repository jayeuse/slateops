"""Temporary passwords set by an administrator (DEC-0042, AC-T1 to AC-T3).

The administrator gives a person a password by any channel; no email is needed. The person's
sessions end and ``users.password_change_required_at`` is set in one commit, before Auth
gets the password, so a failed provider call never leaves a new password with live sessions.
Until the person chooses a password of their own (``provider_actions.change_password`` or
email recovery clears the mark), their sessions reach only their identity, the password
change, MFA completion and sign-out (``common/dependencies/auth.py``).
"""

import secrets
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.dependencies.auth import CurrentIdentity, require_fresh_exact_admin
from app.core.base_model import utc_now
from app.core.integrations.supabase_admin_accounts import set_password_by_administrator
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    SupabaseAuthUnavailable,
    get_supabase_auth_client,
)
from app.systems.access.identity.session_revocation import revoke_user_sessions
from app.systems.access.users.coordination import advance_token_cutoff
from app.systems.access.users.membership import bound_organization, is_platform_operator
from app.systems.access.users.models import User
from app.systems.access.users.schemas import TemporaryPasswordResponse
from app.systems.access.users.security import (
    Binding,
    Operation,
    admit_operation,
    commit_event,
    failed_operation,
    refusal,
    require_visible_target,
)
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.workspace.models import PlatformSettings, WorkspaceProfile
from app.systems.manage.workspace.security_policy import (
    PasswordPolicyViolation,
    load_platform_policy,
    validate_password,
)

# The pinned GoTrue's longest password, counted in bytes (also ``operations/bootstrap_admin``).
MAX_PASSWORD_BYTES = 72
GENERATED_LENGTH = 16
# Letters and digits without look-alikes (0 O 1 l I), so the password survives being read out.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
_ATTEMPTS = 64


def check_temporary_password(policy: PlatformSettings, password: str) -> None:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordPolicyViolation(f"Use a password of at most {MAX_PASSWORD_BYTES} bytes")
    validate_password(policy, password)


def generate_temporary_password(policy: PlatformSettings) -> str:
    length = max(GENERATED_LENGTH, policy.password_min_length)
    if length > MAX_PASSWORD_BYTES:
        raise PasswordPolicyViolation(
            f"The password policy asks for more than {MAX_PASSWORD_BYTES} characters"
        )
    for _ in range(_ATTEMPTS):
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        try:
            validate_password(policy, candidate)
        except PasswordPolicyViolation:
            continue  # A random draw can miss a required kind of character.
        return candidate
    raise PasswordPolicyViolation("A password could not be chosen. Try again.")


@dataclass
class TemporaryPasswordOperation(Operation):
    chosen_by: str = "server"

    def payload(self, outcome: SecurityEventOutcome) -> SecurityEventIngestRequest:
        # Who, for whom and when (``occurred_at``); never the password (AC-T3).
        return SecurityEventIngestRequest(
            event_type="identity.temporary_password",
            outcome=outcome,
            source="access.users",
            operation_id=self.id,
            actor_id=self.actor.user_id,
            subject_id=self.binding.user_id,
            metadata={
                "chosen_by": self.chosen_by,
                "local_revocation": self.local_revocation,
                "revoked_sessions": self.revoked_sessions,
            },
        )


def _refuse_owner(db: Session, target_id: UUID) -> None:
    owner_id = db.scalar(
        select(WorkspaceProfile.owner_user_id).where(WorkspaceProfile.id == bound_organization(db))
    )
    if target_id == owner_id or is_platform_operator(db, target_id):
        raise refusal(409, "security_target_owner", "An owner's password cannot be set here.")


def _end_sessions_and_mark(db: Session, operation: TemporaryPasswordOperation) -> None:
    """Lock the person, end every session, move the token cutoff and set the mark."""

    target = db.get(User, operation.binding.user_id, with_for_update=True,
                    populate_existing=True)
    if (
        target is None
        or target.supabase_user_id is None
        or Binding(target.id, target.supabase_user_id, target.email) != operation.binding
    ):
        raise refusal(409, "security_binding_changed",
                      "This person's sign-in identity changed. Reload before continuing.")
    operation.revoked_sessions += revoke_user_sessions(db, target.id, except_session_id=None)
    advance_token_cutoff(target)
    target.password_change_required_at = utc_now()


def set_temporary_password(
    db: Session, identity: CurrentIdentity, request: Request, target_id: UUID,
    password: str | None,
) -> TemporaryPasswordResponse:
    require_fresh_exact_admin(db, identity.user.id)
    require_visible_target(db, target_id)
    if target_id == identity.user.id:
        raise refusal(409, "security_target_self", "Use Change password for your own account.")
    _refuse_owner(db, target_id)
    policy = load_platform_policy(db)
    try:
        chosen = generate_temporary_password(policy) if password is None else password
        check_temporary_password(policy, chosen)
    except PasswordPolicyViolation as error:
        raise refusal(422, "password_policy_violation", str(error)) from error
    try:
        admitted = admit_operation(db, identity, request, target_id, "temporary_password")
    except (SQLAlchemyError, SupabaseAuthUnavailable) as error:
        db.rollback()
        raise refusal(
            503, "user_security_unavailable", "Security is unavailable. Try again."
        ) from error
    operation = TemporaryPasswordOperation(
        admitted.actor, admitted.binding, admitted.kind,
        chosen_by="server" if password is None else "administrator",
    )
    try:
        # The last admission checkpoint holds the administrator lock and both user rows.
        _refuse_owner(db, target_id)
        _end_sessions_and_mark(db, operation)
        operation.local_revocation = "unconfirmed"
        commit_event(db, operation, SecurityEventOutcome.ATTEMPT)
        operation.local_revocation = "committed"
        set_password_by_administrator(
            get_supabase_auth_client(), operation.binding.provider_id, chosen
        )
        # The old password still signed in until Auth changed it; a session made then, and
        # a password change it made, end here too (as ``reset_person_mfa`` does).
        _end_sessions_and_mark(db, operation)
        commit_event(db, operation, SecurityEventOutcome.SUCCESS)
    except HTTPException as error:
        if operation.local_revocation == "not_requested":
            db.rollback()  # Nothing changed yet.
            raise
        raise failed_operation(db, operation) from error
    except (SQLAlchemyError, SupabaseAuthUnavailable, InvalidProviderCredentials) as error:
        raise failed_operation(db, operation) from error
    return TemporaryPasswordResponse(
        operation_id=operation.id,
        user_id=target_id,
        temporary_password=chosen if password is None else None,
        revoked_sessions=operation.revoked_sessions,
    )
