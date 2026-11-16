"""The bootstrap reserves the first administrator only on an installation without one.

``operations/bootstrap_admin.py`` counts the administrators before it takes the
administrator lock, so two runs that start together both pass that count. The count
under the lock decides: the second run waits for the first and is then refused. The
reconcile path of a bootstrap re-sends only the sole pending administrator.

A first-administrator bootstrap happens only on an installation without a live
administrator, and the shared test database holds administrators from other tests.
These tests therefore hide every live administrator for their own duration: the race
commits the hiding and restores each row afterwards; the reconcile rows hide them in
their rolled-back transaction.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, time
from threading import Event, Thread
from typing import Any
from unittest.mock import Mock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from uuid6 import uuid7

import app.systems.access.users.service as user_service
from app.core.config import get_settings
from app.core.integrations.supabase_auth import ProviderUser
from app.systems.access.users.coordination import InvitationError
from app.systems.access.users.models import Membership, PlatformOperator, User, UserRole, UserStatus
from app.systems.access.users.schemas import InvitationCreate
from app.systems.boards.models import Board
from app.systems.manage.audit.models import AuditLog, SecurityEvent
from app.systems.manage.backups.models import BackupPolicy
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.sandbox.designs.models import SandboxDocument
from operations import backup_state
from operations import bootstrap_admin as bootstrap
from tests.backups.bridge_support import bridge_session, on_fresh_thread
from tests.conftest import guarded_create_engine
from tests.organization_scope_support import in_context
from tests.race_support import WAIT, backend_pid, wait_until_waiting
from tests.rbac.support import add_user, organization

pytestmark = pytest.mark.integration


def _live_administrators() -> Any:
    return select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.role == UserRole.ADMIN.value,
        Membership.is_deleted.is_(False), User.is_deleted.is_(False),
    ).distinct()


def _provider() -> Mock:
    """A provider that creates a new identity for each invited email."""

    provider = Mock()
    created: dict[str, UUID] = {}
    identities: dict[UUID, ProviderUser] = {}

    def create(email: str, local_id: UUID, operation_id: UUID) -> ProviderUser:
        created[email] = uuid7()
        identities[created[email]] = ProviderUser(
            created[email],
            None,
            email,
            {
                "slateops_user_id": str(local_id),
                "slateops_invitation_operation_id": str(operation_id),
            },
        )
        return identities[created[email]]

    provider.find_invitation_user.return_value = None
    provider.admin_create_invitation_user.side_effect = create
    # A resend reads the still unconfirmed identity that the first invitation created.
    provider.get_admin_user.side_effect = lambda provider_id: identities[provider_id]
    provider.admin_send_invitation.side_effect = lambda email: ProviderUser(
        created[email], None, email
    )
    return provider


@pytest.fixture
def empty_installation(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, list[str]]]:
    """Hide every live administrator, then restore each one and remove the invited ones."""

    owner = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"])
    try:
        runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
        try:
            monkeypatch.setattr(bootstrap, "get_engine", lambda: runtime)
            invited: list[str] = []
            hidden: dict[UUID, datetime | None] = {}
            org_id = None
            try:
                with Session(owner) as db:
                    org_id = organization(db).id
                    hidden = {
                        row.id: row.deleted_at for row in db.scalars(_live_administrators()).all()
                    }
                    if hidden:
                        db.execute(
                            update(User)
                            .where(User.id.in_(hidden))
                            .values(is_deleted=True, deleted_at=datetime.now(UTC))
                        )
                    db.commit()
                    assert db.scalars(_live_administrators()).all() == []
                yield owner, invited
            finally:
                with Session(owner) as db:
                    if invited:
                        invited_ids = select(User.id).where(User.email.in_(invited))
                        # A successful bootstrap commits its own organization with the
                        # administrator's membership; remove that organization too.
                        bootstrapped = set(db.scalars(select(Membership.org_id).where(
                            Membership.user_id.in_(invited_ids), Membership.org_id != org_id,
                        )))
                        db.execute(delete(Membership).where(Membership.user_id.in_(invited_ids)))
                        for model in (Board, SandboxDocument, AuditLog, SecurityEvent):
                            db.execute(delete(model).where(model.org_id.in_(bootstrapped)))
                        db.execute(
                            delete(WorkspaceProfile).where(WorkspaceProfile.id.in_(bootstrapped))
                        )
                        # Bootstrap also records its administrator as a platform operator.
                        db.execute(
                            delete(PlatformOperator).where(PlatformOperator.user_id.in_(invited_ids))
                        )
                        db.execute(delete(User).where(User.email.in_(invited)))
                    if org_id is not None:
                        db.execute(delete(AuditLog).where(AuditLog.org_id == org_id))
                        db.execute(delete(WorkspaceProfile).where(WorkspaceProfile.id == org_id))
                    for user_id, deleted_at in hidden.items():
                        db.execute(
                            update(User)
                            .where(User.id == user_id)
                            .values(is_deleted=False, deleted_at=deleted_at)
                        )
                    db.commit()
        finally:
            runtime.dispose()
    finally:
        owner.dispose()


def test_two_bootstraps_that_start_together_reserve_one_administrator(
    empty_installation: tuple[Engine, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, invited = empty_installation
    # Different people: the same email or username would be refused by its unique index.
    first, second = (
        InvitationCreate(
            email=f"{name}-{uuid7().hex}@example.com", username=f"{name}_{uuid7().hex}"
        )
        for name in ("first", "second")
    )
    invited.extend([first.email, second.email])
    monkeypatch.setattr(user_service, "get_supabase_auth_client", _provider)

    first_counted, release_first = Event(), Event()
    second_pid: list[int] = []
    original_exists = user_service._other_administrator_exists

    def pause_first_under_the_lock(db: Session, excluded_user_id: UUID, org_id: UUID) -> bool:
        found = original_exists(db, excluded_user_id, org_id)
        if not first_counted.is_set():
            first_counted.set()
            assert release_first.wait(WAIT)
        return found

    original_validate = bootstrap._validate_schema

    def note_second_connection(db: Session) -> None:
        # Bootstraps serialize on the installation settings row, taken right after this
        # check; record the second connection before it can wait there.
        if first_counted.is_set() and not second_pid:
            second_pid.append(backend_pid(db))
        original_validate(db)

    monkeypatch.setattr(user_service, "_other_administrator_exists", pause_first_under_the_lock)
    monkeypatch.setattr(bootstrap, "_validate_schema", note_second_connection)
    results: dict[str, object] = {}

    def run(invitation: InvitationCreate) -> None:
        try:
            results[invitation.email] = bootstrap._provision(get_settings(), invitation)
        except bootstrap.BootstrapError as error:
            results[invitation.email] = error

    runs = [
        Thread(target=in_context(run), args=(first,)),
        Thread(target=in_context(run), args=(second,)),
    ]
    try:
        runs[0].start()
        assert first_counted.wait(WAIT)
        runs[1].start()
        # Only a synchronization: the second run either waits for the first's lock or,
        # without that lock, finishes on its own before the first is released.
        wait_until_waiting(owner, second_pid, while_running=runs[1])
    finally:
        release_first.set()
        for thread in runs:
            thread.join(WAIT)
    assert not any(thread.is_alive() for thread in runs), "a bootstrap hung"

    assert isinstance(results[first.email], bootstrap.BootstrapResult), results
    assert isinstance(results[second.email], bootstrap.BootstrapError), results
    with Session(owner) as db:
        reserved = db.scalars(
            select(User.email).join(Membership, Membership.user_id == User.id).where(
                User.email.in_(invited),
                Membership.role == UserRole.ADMIN.value,
                Membership.is_deleted.is_(False),
                User.is_deleted.is_(False),
            )
        ).all()
        assert reserved == [first.email]
        assert db.scalar(select(func.count()).select_from(_live_administrators().subquery())) == 1


@pytest.mark.parametrize(
    ("other_administrator", "reconciled"),
    [
        pytest.param(False, True, id="sole-pending-administrator"),
        pytest.param(True, False, id="another-live-administrator"),
    ],
)
def test_a_bootstrap_reconcile_resends_only_the_sole_pending_administrator(
    integration_owner_db: Session, other_administrator: bool, reconciled: bool
) -> None:
    db = integration_owner_db
    for administrator in db.scalars(_live_administrators()).all():
        administrator.is_deleted = True
        administrator.deleted_at = datetime.now(UTC)
    # Neither a deleted administrator nor a member stops the first administrator.
    deleted = add_user(db, "deleted-admin", role=UserRole.ADMIN)
    deleted.is_deleted = True
    deleted.deleted_at = datetime.now(UTC)
    add_user(db, "member")
    if other_administrator:
        add_user(db, "other-admin", role=UserRole.ADMIN)
    pending = add_user(db, "pending-admin", role=UserRole.ADMIN, status=UserStatus.PENDING)
    pending_membership = db.scalars(select(Membership).where(
        Membership.user_id == pending.id, Membership.org_id == organization(db).id,
        Membership.status == UserStatus.PENDING.value,
    )).one()
    pending_membership.provider_invitation_operation_id = uuid7()
    db.commit()
    stored_profile = select(User.supabase_user_id, Membership.invitation_sent_at).join(
        Membership, Membership.user_id == User.id,
    ).where(User.id == pending.id, Membership.id == pending_membership.id)

    if reconciled:
        user_service.reconcile_invitation(
            db, pending.id, actor_id=None, bootstrap=True, client=_provider()
        )
        result = db.execute(stored_profile).one()
        assert result.supabase_user_id is not None
        assert result.invitation_sent_at is not None
    else:
        with pytest.raises(InvitationError):
            user_service.reconcile_invitation(
                db, pending.id, actor_id=None, bootstrap=True, client=_provider()
            )
        stored = db.execute(stored_profile).one_or_none()
        assert stored is not None
        assert (stored.supabase_user_id, stored.invitation_sent_at) == (None, None)


def _footprint(owner: Engine, user_id: UUID, org_id: UUID) -> dict[str, object]:
    """Row versions and append-only rows of one installation's first administrator."""
    keys = {"user": user_id, "org": org_id}
    queries = {
        "users": "SELECT xmin::text FROM users WHERE id = :user",
        "memberships": "SELECT id::text || xmin::text FROM memberships WHERE user_id = :user",
        "operators": "SELECT user_id::text FROM platform_operators WHERE user_id = :user",
        "operator_versions": "SELECT xmin::text FROM platform_operators WHERE user_id = :user",
        "organizations": f"SELECT xmin::text FROM {WorkspaceProfile.__tablename__} WHERE id = :org",
        "audit": "SELECT count(*)::text FROM audit_logs WHERE org_id = :org "
                 "OR entity_id IN (:user, :org) OR entity_id IN "
                 "(SELECT id FROM platform_operators WHERE user_id = :user) OR entity_id IN "
                 "(SELECT id FROM memberships WHERE user_id = :user)",
        "security_events": "SELECT count(*)::text FROM security_events "
                           "WHERE org_id = :org OR subject_id = :user",
    }
    with owner.connect() as connection:
        return {name: sorted(connection.scalars(text(query), keys).all())
                for name, query in queries.items()}


@pytest.mark.parametrize("operator_row", [
    pytest.param(True, id="operator-row-present"),
    pytest.param(False, id="operator-row-absent"),
])
def test_w5a_4_rerun_on_an_active_administrator_writes_no_row(
    empty_installation: tuple[Engine, list[str]], monkeypatch: pytest.MonkeyPatch,
    operator_row: bool,
) -> None:
    owner, invited = empty_installation
    invitation = InvitationCreate(
        email=f"first-{uuid7().hex}@example.com", username=f"first_{uuid7().hex}"
    )
    invited.append(invitation.email)
    monkeypatch.setattr(user_service, "get_supabase_auth_client", _provider)
    slug = f"w5a-{uuid7().hex[-12:]}"
    first = bootstrap._provision(get_settings(), invitation, name="Harbor Supply", slug=slug)
    assert first.status == UserStatus.PENDING.value
    with Session(owner) as db:
        # The administrator completes the emailed invitation.
        user = db.get(User, first.user_id)
        assert user is not None and user.supabase_user_id is not None
        user.status = UserStatus.ACTIVE.value
        membership = db.scalars(select(Membership).where(Membership.user_id == user.id)).one()
        membership.status = UserStatus.ACTIVE.value
        membership.invitation_accepted_at = datetime.now(UTC)
        if not operator_row:
            db.execute(delete(PlatformOperator).where(PlatformOperator.user_id == user.id))
        db.commit()
    before = _footprint(owner, first.user_id, first.org_id)

    again = bootstrap._provision(get_settings(), invitation, name="Harbor Supply", slug=slug)

    assert (again.status, again.org_id) == (UserStatus.ACTIVE.value, first.org_id)
    after = _footprint(owner, first.user_id, first.org_id)
    if operator_row:
        assert after == before
    else:
        # `_provision` in bootstrap_admin.py restores a missing operator row: one insert and
        # one audit row.
        assert after["operators"] == [str(first.user_id)] and before["operators"] == []
        assert int(after["audit"][0]) == int(before["audit"][0]) + 1
        unchanged = {"users", "memberships", "organizations", "security_events"}
        assert {key: after[key] for key in unchanged} == {key: before[key] for key in unchanged}
    with Session(owner) as db:
        assert db.scalar(select(func.count()).select_from(WorkspaceProfile).where(
            WorkspaceProfile.slug == slug)) == 1


@pytest.mark.parametrize("owner_status", [
    pytest.param(UserStatus.PENDING.value, id="owner-invitation-pending"),
    pytest.param(UserStatus.ACTIVE.value, id="owner-active"),
])
def test_d4_fresh_bootstrap_time_zone_gives_the_default_policy_at_0200_local(
    empty_installation: tuple[Engine, list[str]], monkeypatch: pytest.MonkeyPatch,
    owner_status: str,
) -> None:
    owner, invited = empty_installation
    invitation = InvitationCreate(
        email=f"first-{uuid7().hex}@example.com", username=f"first_{uuid7().hex}"
    )
    invited.append(invitation.email)
    provider = _provider()
    monkeypatch.setattr(user_service, "get_supabase_auth_client", lambda: provider)
    slug = f"d4-{uuid7().hex[-12:]}"
    first = bootstrap._provision(get_settings(), invitation, name="Harbor Supply", slug=slug,
                                 time_zone="Asia/Manila")
    if owner_status == UserStatus.ACTIVE.value:
        with Session(owner) as db:
            user = db.get(User, first.user_id)
            assert user is not None
            user.status = UserStatus.ACTIVE.value
            membership = db.scalars(select(Membership).where(Membership.user_id == user.id)).one()
            membership.status = UserStatus.ACTIVE.value
            membership.invitation_accepted_at = datetime.now(UTC)
            db.commit()

    # A pending owner's rerun resends the invitation through the resume path of `provision`.
    again = bootstrap._provision(get_settings(), invitation, name="Harbor Supply", slug=slug,
                                 time_zone="Europe/Berlin")

    assert (again.org_id, again.status) == (first.org_id, owner_status)
    with Session(owner) as db:
        organization_row = db.get(WorkspaceProfile, first.org_id)
        assert organization_row is not None and organization_row.timezone == "Asia/Manila"
        # On an installation this is the only organization; in the shared test database
        # make it the oldest one that an installation owner owns (the D-5 rule).
        organization_row.created_at = datetime(2000, 1, 1, tzinfo=UTC)
        db.commit()

    def default_policy() -> tuple[dict[str, Any], datetime | None]:
        with bridge_session() as bridge:
            instance = bridge.connection().scalar(text("SELECT current_setting('cluster_name')"))
            result = backup_state.execute(bridge, backup_state.COMMAND_ADAPTER.validate_python(
                {"op": "policy_default", "installation_id": instance, "project": "harbor-install"}
            ))
            return result, bridge.scalars(select(BackupPolicy)).one().next_due_at

    result, next_due_at = on_fresh_thread(default_policy)

    assert (result["written"], result["policy"]["schedule"], result["policy"]["timezone"]) == (
        True, "daily", "Asia/Manila"
    )
    assert next_due_at is not None
    assert next_due_at.astimezone(ZoneInfo("Asia/Manila")).time() == time(2)
