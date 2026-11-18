"""Bootstrap the first organization, administrator and installation operator.

By default the administrator gets an emailed invitation (development, through Mailpit). The
installer passes ``--password-stdin`` (DEC-0041): the administrator's Auth account is created
confirmed with the password read from standard input, so no email is needed. The password is
never an argument, an environment value or output.
"""

import json
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

# Keep the documented ``python operations/bootstrap_admin.py`` invocation working
# without requiring callers to manage PYTHONPATH.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_admin_settings, get_settings
from app.core.config.environment import environment_inputs
from app.core.config.instance import (
    assert_database_url,
    assert_instance_target,
    instance_target_for_process,
)
from app.core.config.provider_instance import assert_provider_instance
from app.core.config.settings import DOTENV_PATH
from app.core.database import model_registry  # noqa: F401
from app.core.database.session import AuditSession, get_engine
from app.core.integrations import supabase_admin_accounts as admin_accounts
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    get_supabase_auth_client,
)
from app.systems.access.users.coordination import InvitationError
from app.systems.access.users.models import Membership, PlatformOperator, User, UserRole, UserStatus
from app.systems.access.users.schemas import InvitationCreate
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.manage.workspace.models import PlatformSettings, WorkspaceProfile
from operations.create_organization import provision, validate_identity
from operations.install.joblog import RefusalParser, log_line

LOCAL_ENVIRONMENTS = frozenset({"development", "dev", "local"})
# The product's shortest password (PasswordChangeRequest) and the pinned GoTrue's longest
# (72, counted in bytes); the install engine checks the same rule before step 1.
PASSWORD_MIN_CHARACTERS, PASSWORD_MAX_BYTES = 12, 72


class BootstrapError(RuntimeError):
    """A safe operational error raised while provisioning an administrator."""


class BootstrapFailure(BootstrapError):
    """The final commit or provider delivery failed; a rerun can complete it."""


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    user_id: UUID
    email: str
    username: str
    status: str
    org_id: UUID
    slug: str


def _parser() -> RefusalParser:
    parser = RefusalParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm first-administrator provisioning outside development/local environments",
    )
    parser.add_argument("--name", default="Slate Operations")
    parser.add_argument("--slug", default="slateops")
    parser.add_argument("--provider-user-id", type=UUID,
                        help="explicitly link a surviving confirmed provider identity")
    parser.add_argument("--time-zone", default="UTC",
                        help="IANA time zone of a new organization (never changes an existing one)")
    parser.add_argument("--json", action="store_true",
                        help="print one line of safe JSON for the install engine")
    parser.add_argument("--password-stdin", action="store_true",
                        help="create a confirmed account with the password on standard input; "
                             "no invitation (installer)")
    return parser


def _validate_confirmation(settings: Settings, confirmed: bool) -> None:
    if settings.environment.strip().casefold() not in LOCAL_ENVIRONMENTS and not confirmed:
        raise BootstrapError(
            "Administrator bootstrap requires --confirm outside development/local environments"
        )


def _time_zone(name: str) -> str:
    """Accept only an IANA name that fits the organization's time zone column."""
    try:
        if not name or len(name) > 64:
            raise ValueError
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise BootstrapError("The time zone must be an IANA time zone name") from None
    return name


def _invitation(email: str, username: str) -> InvitationCreate:
    try:
        return InvitationCreate(email=email, username=username)
    except ValueError:
        raise BootstrapError("ADMIN_EMAIL and ADMIN_USERNAME must be valid") from None


def _validate_schema(db: AuditSession) -> None:
    """Touch the account and membership schema before provisioning."""
    db.scalar(select(User.id, Membership.role).join(
        Membership, Membership.user_id == User.id,
    ).limit(1))


def _matching_profile(db: AuditSession, invitation: InvitationCreate) -> User | None:
    email_profile = db.scalar(select(User).where(User.email == invitation.email))
    username_profile = db.scalar(select(User).where(User.username == invitation.username))
    if email_profile is None and username_profile is None:
        return None
    if email_profile is not None and username_profile is not None:
        if email_profile.id != username_profile.id:
            raise BootstrapError("Email and username belong to different profiles")
        return email_profile
    return email_profile or username_profile


def _admin_assignment_count(db: AuditSession, *, excluded_user_id: UUID | None = None) -> int:
    statement = (
        select(func.count())
        .select_from(User)
        .join(Membership, Membership.user_id == User.id)
        .where(User.is_deleted.is_(False), Membership.is_deleted.is_(False),
               Membership.role == UserRole.ADMIN.value)
    )
    if excluded_user_id is not None:
        statement = statement.where(User.id != excluded_user_id)
    return int(db.scalar(statement) or 0)


def _is_exact_admin_reservation(db: AuditSession, user: User, invitation: InvitationCreate) -> bool:
    membership = db.scalars(select(Membership).where(
        Membership.user_id == user.id, Membership.status == UserStatus.PENDING.value,
        Membership.is_deleted.is_(False),
    ).limit(2)).all()
    if len(membership) != 1:
        return False
    reservation = membership[0]
    return bool(
        reservation.role == UserRole.ADMIN.value
        and user.status == UserStatus.PENDING.value
        and not user.is_deleted
        and reservation.provider_invitation_operation_id is not None
        and reservation.invitation_accepted_at is None
        and user.email == invitation.email
        and user.username == invitation.username
    )


def _provision(
    settings: Settings, invitation: InvitationCreate, *, provider_user_id: UUID | None = None,
    name: str = "Slate Operations", slug: str = "slateops", time_zone: str = "UTC",
) -> BootstrapResult:
    # Provider I/O precedes the short serialized installation transaction.
    confirmed_provider = (
        get_supabase_auth_client().get_admin_user(provider_user_id) if provider_user_id else None
    )
    with AuditSession(get_engine()) as db:
        db.info[AUDIT_CONTEXT_KEY] = AuditContext()
        _validate_schema(db)
        # The installation singleton orders concurrent first-operator bootstraps.
        db.scalar(select(PlatformSettings).with_for_update())
        existing_profile = _matching_profile(db, invitation)
        try:
            org = db.scalar(select(WorkspaceProfile).where(WorkspaceProfile.slug == slug))
            if org is not None:
                if existing_profile is None or (
                    existing_profile.email != invitation.email
                    or existing_profile.username != invitation.username
                ):
                    raise BootstrapError("Organization bootstrap identity does not match")
                membership = db.scalar(select(Membership).where(
                    Membership.org_id == org.id, Membership.user_id == existing_profile.id,
                    Membership.role == "admin", Membership.is_deleted.is_(False),
                ))
                if membership is None:
                    raise BootstrapError("Organization bootstrap identity does not match")
                if _is_exact_admin_reservation(db, existing_profile, invitation):
                    org = provision(db, name=name, slug=slug, invitation=invitation,
                                    provider_user_id=provider_user_id)
                elif (existing_profile.status != "active" or existing_profile.is_deleted
                      or membership.status != "active"
                      or existing_profile.supabase_user_id is None
                      or (provider_user_id is not None
                          and existing_profile.supabase_user_id != provider_user_id)):
                    raise BootstrapError("Bootstrap reservation is unavailable")
                user = existing_profile
            else:
                if db.scalar(select(PlatformOperator.id).limit(1)) or _admin_assignment_count(db):
                    raise BootstrapError("An administrator reservation already exists")
                if existing_profile is not None and provider_user_id is None:
                    raise BootstrapError("Existing account requires explicit provider identity")
                org = provision(db, name=name, slug=slug,
                                invitation=invitation.model_copy(update={"role": UserRole.ADMIN}),
                                provider_user_id=provider_user_id,
                                confirmed_provider=confirmed_provider, timezone=time_zone)
                created_user = db.scalar(select(User).where(User.email == invitation.email))
                assert created_user is not None
                user = created_user
            if not db.scalar(select(PlatformOperator.id).where(
                PlatformOperator.user_id == user.id
            )):
                db.add(PlatformOperator(user_id=user.id))
            db.commit()
            return BootstrapResult(
                user.id, user.email, user.username, user.status, org.id, org.slug
            )
        except (InvitationError, SQLAlchemyError, ValueError) as error:
            db.rollback()
            raise BootstrapFailure("Unable to finalize administrator profile") from error


def _read_password(stream: TextIO) -> str:
    """One line of standard input; the trailing newline is not part of the password."""
    text = stream.read(4 * PASSWORD_MAX_BYTES)
    text = text[:-1] if text.endswith("\n") else text
    if (
        len(text) < PASSWORD_MIN_CHARACTERS
        or len(text.encode("utf-8")) > PASSWORD_MAX_BYTES
        or "".join(text.splitlines()) != text
        or any(unicodedata.category(character) == "Cc" for character in text)
    ):
        raise BootstrapError("The administrator password does not meet the password rule")
    return text


def _active_provider_id(invitation: InvitationCreate) -> UUID | None:
    """The bound Auth account of an active profile with this email (a rerun), else None."""
    with AuditSession(get_engine()) as db:
        db.info[AUDIT_CONTEXT_KEY] = AuditContext()
        return db.scalar(select(User.supabase_user_id).where(
            User.email == invitation.email, User.status == UserStatus.ACTIVE.value,
            User.is_deleted.is_(False),
        ))


def _password_account(invitation: InvitationCreate, password: str) -> tuple[UUID, bool]:
    """The confirmed Auth account of the first administrator and whether this run made it.

    A rerun after an interrupted run finds the account that run marked and sets the password
    again; an account with this email and no marker belongs to someone else.
    """
    bound = _active_provider_id(invitation)
    if bound is not None:
        return bound, False
    client = get_supabase_auth_client()
    try:
        try:
            account = admin_accounts.create_confirmed_user(client, invitation.email, password)
        except admin_accounts.ProviderEmailTaken:
            found = admin_accounts.find_first_administrator(client, invitation.email)
            if found is None:
                raise BootstrapError("The email belongs to another sign-in account") from None
            account = admin_accounts.set_password(client, found, password)
    except InvalidProviderCredentials:
        raise BootstrapError("Auth refused the administrator account") from None
    return account.id, True


def _engine_output(level: str, value: dict[str, str]) -> None:
    log_line("bootstrap", level, next(iter(value.values())))
    print(json.dumps(value, separators=(",", ":")))


def main(argv: Sequence[str] | None = None) -> None:
    parser = _parser()
    arguments = sys.argv[1:] if argv is None else list(argv)
    # Without --json, argparse keeps its usage message and exit 2.
    parser.refuse = "--json" in arguments
    try:
        args = parser.parse_args(arguments)
    except ValueError:
        _engine_output("error", {"code": "bootstrap_refused"})
        raise SystemExit(2) from None

    try:
        if args.password_stdin and args.provider_user_id is not None:
            raise BootstrapError("--password-stdin creates the account; it takes no provider ID")
        password = _read_password(sys.stdin) if args.password_stdin else None
        time_zone = _time_zone(args.time_zone)
        try:
            validate_identity(args.name, args.slug)
        except ValueError:
            raise BootstrapError("Organization name or slug is invalid") from None
        settings = get_settings()
        admin = get_admin_settings()
        target = instance_target_for_process(settings.database_url, "slateops_runtime")
        if target is not None:
            assert_database_url(settings.database_url, target, expected_user="slateops_runtime")
            with get_engine().connect() as connection:
                assert_instance_target(connection, target, expected_user="slateops_runtime")
        invitation = _invitation(admin.admin_email, admin.admin_username)
        _validate_confirmation(settings, args.confirm)
        assert_provider_instance(
            environment_inputs(DOTENV_PATH), database_url=settings.database_url,
            expected_user="slateops_runtime",
        )
        provider_user_id, created = args.provider_user_id, False
        if password is not None:
            provider_user_id, created = _password_account(invitation, password)
        result = _provision(settings, invitation, provider_user_id=provider_user_id,
                            name=args.name, slug=args.slug, time_zone=time_zone)
    except SystemExit:
        raise
    except Exception as error:
        # Keep database, Auth, and configuration details out of command output.
        if args.json:
            refused = isinstance(error, BootstrapError) and not isinstance(
                error, BootstrapFailure
            )
            code = "bootstrap_refused" if refused else "bootstrap_failed"
            _engine_output("error", {"code": code})
            raise SystemExit(2 if refused else 3) from None
        raise SystemExit("Unable to provision administrator") from None

    if args.json:
        # The email and user name stay out of engine output and logs (plan 10.1 item 7).
        if password is not None:
            _engine_output("info", {"result": "created" if created else "already_active"})
            return
        sent = result.status == UserStatus.PENDING.value
        _engine_output("info", {"result": "sent" if sent else "already_active"})
        return
    print(
        f"user_id={result.user_id} email={result.email} "
        f"username={result.username} status={result.status} "
        f"org_id={result.org_id} slug={result.slug}"
    )
    if result.status == UserStatus.PENDING.value:
        print("Complete the emailed invitation to activate the administrator account.")


if __name__ == "__main__":
    main()
