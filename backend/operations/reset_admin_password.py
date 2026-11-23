"""Set the installation's first administrator's password from the server PC (DEC-0042).

The install engine's ``admin-password`` job runs ``python operations/reset_admin_password.py
--confirm --json --password-stdin`` in a one-shot server-image container, with the stored
administrator email in ``ADMIN_EMAIL`` and the new password on standard input only (never an
argument, an environment value, output or a log line). The person must be an active
administrator whose Auth account setup created (``supabase_admin_accounts`` marker). The job
sets the password in Auth, ends every Slate Operations session of that person, clears the
person's "must choose a new password" mark (``password_change_required_at``) and writes the
security event ``identity.local_admin_password_reset``. Output is one line of safe JSON:
``{"result": "reset"}`` (exit 0), ``{"code": "invalid_input"}`` or
``{"code": "admin_missing"}`` (exit 2), or ``{"code": "reset_failed"}`` (exit 3).
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from uuid6 import uuid7

# Keep the documented ``python operations/reset_admin_password.py`` invocation working.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.normalization import normalize_email
from app.core.base_model import utc_now
from app.core.config import get_admin_settings, get_settings
from app.core.config.environment import environment_inputs
from app.core.config.instance import (
    assert_database_url,
    assert_instance_target,
    instance_target_for_process,
)
from app.core.config.provider_instance import assert_provider_instance
from app.core.config.settings import DOTENV_PATH
from app.core.database import model_registry  # noqa: F401
from app.core.database.organization_scope import scope_session
from app.core.database.session import AuditSession, get_engine
from app.core.integrations import supabase_admin_accounts as admin_accounts
from app.core.integrations.supabase_auth import ProviderUserNotFound, get_supabase_auth_client
from app.systems.access.identity.admin_recovery import (
    OrganizationChoiceRequired,
    administered_membership,
)
from app.systems.access.identity.session_revocation import revoke_user_sessions
from app.systems.access.users.eligibility import is_active_account
from app.systems.access.users.models import Membership, User, UserStatus
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.audit.security_events import append_security_event
from operations.bootstrap_admin import BootstrapError, _read_password
from operations.install.joblog import RefusalParser, log_line

EVENT_TYPE = "identity.local_admin_password_reset"


class AdminMissing(RuntimeError):
    """No active first administrator with an Auth account that setup created."""


def _membership(db: AuditSession, user: User) -> Membership | None:
    """An active administrator membership; the first organization when there are several."""
    try:
        return administered_membership(db, user.id)
    except OrganizationChoiceRequired as choice:
        return administered_membership(db, user.id, choice.slugs[0])


def reset_admin_password(email: str, password: str) -> UUID:
    """Set the password in Auth, end the person's sessions and record it; return the user."""
    timestamp = utc_now()
    with AuditSession(get_engine()) as db:
        db.info[AUDIT_CONTEXT_KEY] = AuditContext()
        user = db.scalar(select(User).where(User.email == email).with_for_update(of=User))
        membership = None if user is None else _membership(db, user)
        if (
            user is None
            or membership is None
            or user.is_deleted
            or user.status != UserStatus.ACTIVE.value
            or user.supabase_user_id is None
            or not is_active_account(db, user, now=timestamp)
        ):
            db.rollback()
            raise AdminMissing("No active first administrator")
        # The security event belongs to that organization (as local recovery does).
        scope_session(db, membership.org_id)
        provider = get_supabase_auth_client()
        try:
            account = provider.get_admin_user(user.supabase_user_id)
        except ProviderUserNotFound:
            db.rollback()
            raise AdminMissing("The administrator has no Auth account") from None
        if (
            account.id != user.supabase_user_id
            or account.email != user.email
            or account.app_metadata.get(admin_accounts.FIRST_ADMIN_MARKER) is not True
        ):
            db.rollback()
            raise AdminMissing("The Auth account is not the one that setup created")
        admin_accounts.set_password(provider, account, password)
        revoke_user_sessions(db, user.id, except_session_id=None, now=timestamp)
        # DEC-0042: the administrator chose this password at the server PC, so the "must
        # choose a new password" mark of a temporary password no longer applies.
        user.password_change_required_at = None
        append_security_event(
            db,
            SecurityEventIngestRequest(
                event_type=EVENT_TYPE,
                outcome=SecurityEventOutcome.SUCCESS,
                source="operations.reset_admin_password",
                operation_id=uuid7(),
                subject_id=user.id,
                reason="administrator password set on the server PC",
            ),
            org_id=membership.org_id,
        )
        db.commit()
        return user.id


def _output(level: str, value: dict[str, str], exit_code: int = 0) -> None:
    log_line("reset_admin_password", level, next(iter(value.values())))
    print(json.dumps(value, separators=(",", ":")), flush=True)
    if exit_code:
        raise SystemExit(exit_code)


def main(argv: Sequence[str] | None = None) -> None:
    parser = RefusalParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--password-stdin", action="store_true")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
        if not (args.confirm and args.json and args.password_stdin):
            raise ValueError("--confirm, --json and --password-stdin are required")
        password = _read_password(sys.stdin)
    except (ValueError, BootstrapError):
        _output("error", {"code": "invalid_input"}, 2)
        return
    try:
        settings = get_settings()
        target = instance_target_for_process(settings.database_url, "slateops_runtime")
        if target is not None:
            assert_database_url(settings.database_url, target, expected_user="slateops_runtime")
            with get_engine().connect() as connection:
                assert_instance_target(connection, target, expected_user="slateops_runtime")
        assert_provider_instance(
            environment_inputs(DOTENV_PATH), database_url=settings.database_url,
            expected_user="slateops_runtime",
        )
        reset_admin_password(normalize_email(get_admin_settings().admin_email), password)
    except AdminMissing:
        _output("error", {"code": "admin_missing"}, 2)
        return
    except Exception:
        # Keep database, Auth and configuration details out of the output.
        _output("error", {"code": "reset_failed"}, 3)
        return
    _output("info", {"result": "reset"})


if __name__ == "__main__":
    main()
