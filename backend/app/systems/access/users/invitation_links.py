"""Invitation links to copy and send by any channel (DEC-0042, AC-L1 and AC-L2).

Auth makes the one-time invitation without an email. The link goes back once to the
administrator who asked for it; it is never stored, logged or put in an event. A new link
for the same person ends the earlier link or emailed invitation, and completion refuses a
link more than 24 hours old (``invitation_provider.INVITATION_LIFETIME``).
"""

from uuid import UUID

from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import require_fresh_exact_admin
from app.core.base_model import utc_now
from app.core.config import get_settings
from app.core.database.organization_scope import session_organization
from app.core.integrations.supabase_admin_accounts import generate_invitation_link
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    ProviderUser,
    SupabaseAuthClient,
    SupabaseAuthUnavailable,
    get_supabase_auth_client,
)
from app.systems.access.users import invitation_provider, service
from app.systems.access.users.coordination import (
    InvitationConflict,
    InvitationError,
    InvitationNotFound,
    get_user,
)
from app.systems.access.users.membership import bound_organization
from app.systems.access.users.models import Membership, User, UserStatus
from app.systems.access.users.schemas import InvitationCreate, InvitationResponse
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.audit.security_events import append_security_event


def invitation_url(hashed_token: str) -> str:
    """The completion page that the invitation email also opens (``invite.html``)."""

    return f"{get_settings().public_origin}/auth/setup#token_hash={hashed_token}&type=invite"


def created_invitation_response(result: InvitationResponse) -> InvitationResponse | Response:
    """A new invitation's answer; one with a link is a credential and is never cached."""

    if result.invitation_url is None:
        return result
    return JSONResponse(
        status_code=201, content=jsonable_encoder(result), headers={"Cache-Control": "no-store"}
    )


class _LinkSender:
    """Takes the place of the invitation email in ``invite_user`` and keeps the link."""

    def __init__(self) -> None:
        self.url: str | None = None

    def __call__(self, provider: SupabaseAuthClient, email: str) -> ProviderUser:
        link = generate_invitation_link(provider, email)
        self.url = invitation_url(link.hashed_token)
        return link.user


def invite_with_link(
    db: Session, payload: InvitationCreate, *, actor_id: UUID
) -> tuple[User, str | None]:
    """``invite_user`` with a link in place of the email; email setup is not needed.

    A person who already has an account accepts in the app, so they get no link.
    """

    sender = _LinkSender()
    user = service.invite_user(db, payload, actor_id=actor_id, send=sender)
    return user, sender.url if user.status == UserStatus.PENDING.value else None


def new_invitation_link(
    db: Session, user_id: UUID, *, actor_id: UUID, client: SupabaseAuthClient | None = None
) -> tuple[User, str]:
    """Replace the person's invitation with a new link; it also reopens a cancelled one."""

    operation_id = uuid7()
    provider = client or get_supabase_auth_client()
    try:
        require_fresh_exact_admin(db, actor_id)
        profile = service._lock_profile(db, user_id)
        membership = db.scalars(select(Membership).where(
            Membership.user_id == user_id, Membership.status == UserStatus.PENDING.value,
            Membership.org_id == bound_organization(db), Membership.is_deleted.is_(False),
        ).with_for_update()).one_or_none()
        if profile is None or profile.is_deleted or membership is None:
            raise InvitationNotFound("Invitation does not exist")
        if (
            profile.status != UserStatus.PENDING.value
            or membership.invitation_accepted_at is not None
            or membership.provider_invitation_operation_id is None
        ):
            raise InvitationConflict("Invitation is not pending")
        provider_user = invitation_provider.prepare_invitation_user(
            provider, profile, membership, email=False
        )
        link = generate_invitation_link(provider, profile.email)
        if link.user.id != provider_user.id:
            raise InvitationError("Provider invitation does not match")
        profile.supabase_user_id = provider_user.id
        membership.invitation_sent_at = utc_now()
        append_security_event(db, SecurityEventIngestRequest(
            event_type="user.invitation_link", outcome=SecurityEventOutcome.SUCCESS,
            source="users.invitation_links", operation_id=operation_id,
            actor_id=actor_id, subject_id=profile.id,
        ))
        db.commit()
        return get_user(db, profile.id), invitation_url(link.hashed_token)
    except (InvalidProviderCredentials, SupabaseAuthUnavailable, SQLAlchemyError) as error:
        db.rollback()
        _failed(operation_id, actor_id, user_id, db)
        raise InvitationError("Unable to create invitation link") from error
    except (InvitationError, HTTPException):
        db.rollback()
        _failed(operation_id, actor_id, user_id, db)
        raise


def _failed(operation_id: UUID, actor_id: UUID, user_id: UUID, db: Session) -> None:
    service._record_invitation_failure(
        operation_id, actor_id, event_type="user.invitation_link", subject_id=user_id,
        org_id=session_organization(db),
    )
