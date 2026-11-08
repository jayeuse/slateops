"""One access resolution for each transaction: what clears it, drops it and seeds it (step 3.4).

A3: the real writers change each input in one transaction, and the next resolution sees it.
A7: each lock or fresh read drops the stored resolution, with the reload backup removed.
A8: a rebound transaction never answers from another organization's resolution.
A9: ``Session.close()`` leaves no resolution behind.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

import app.systems.access.policy.delegation as delegation
import app.systems.access.policy.service as policy_service
import app.systems.access.users.account_operations as account_operations
from app.common.dependencies.auth import require_fresh_exact_admin
from app.core.database.organization_scope import scope_session
from app.systems.access.identity.models import IdentitySession
from app.systems.access.policy import transaction_access
from app.systems.access.policy.checks import _lock_authority, require_fresh_module_access
from app.systems.access.policy.models import AccessLevel, Group
from app.systems.access.policy.schemas import GroupAccessEntry
from app.systems.access.policy.scope import effective_levels
from app.systems.access.users.membership import organization_membership
from app.systems.access.users.models import Membership, User, UserRole, UserStatus
from app.systems.access.users.schemas import UserUpdate
from app.systems.comms.access import fresh_membership
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.publications.executor import _apply_modules
from tests.conftest import create_member, create_organization
from tests.rbac.support import add_department, add_module, add_user, make_group_access

pytestmark = pytest.mark.integration

READ, WRITE, MANAGE = AccessLevel.READ, AccessLevel.WRITE, AccessLevel.MANAGE


def _statements(db: Session, action: Callable[[], Any]) -> tuple[Any, int]:
    seen: list[str] = []

    def count(*_arguments: Any) -> None:
        seen.append("statement")

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", count)
    try:
        return action(), len(seen)
    finally:
        event.remove(connection, "before_cursor_execute", count)


@pytest.fixture
def one_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real writers commit at their end; here they flush, so all stays in one transaction."""

    for module in (policy_service, delegation, account_operations):
        monkeypatch.setattr(module, "commit", lambda db, _message: db.flush())
    monkeypatch.setattr(account_operations, "_record_outcome", lambda *_args, **_kwargs: None)


def _etag(db: Session, group_id: Any) -> str:
    group = db.get(Group, group_id)
    assert group is not None
    return policy_service.group_etag(group)


def _move(db: Session, module: Any, department: Department, actor: User) -> None:
    """The Sandbox publish's own module writer moves the module to ``department``."""

    desired = SimpleNamespace(
        id="ledger", department_id="target", name=module.module_name, closed=False
    )
    _apply_modules(
        db,
        SimpleNamespace(design=SimpleNamespace(modules=[desired])),
        {"module": {"ledger": SimpleNamespace(module_id=module.id)}},
        {"target": department},
        actor.id,
    )


def test_each_real_writer_of_an_input_clears_the_resolution(
    integration_db: Session, one_transaction: None
) -> None:
    db = integration_db
    admin = add_user(db, role=UserRole.ADMIN)
    member = add_user(db)
    sales, other = add_department(db), add_department(db)
    ledger = add_module(db, sales)
    group_id = make_group_access(db, [member], sales, level=READ).group_id
    empty_id = make_group_access(db, [], other, level=READ).group_id

    def level() -> AccessLevel | None:
        return effective_levels(db, member).module_level(ledger.id)

    def members(user_ids: list[Any]) -> None:
        delegation.replace_members(db, group_id, user_ids, _etag(db, group_id), admin)

    def update(**changes: Any) -> None:
        account_operations.update_user(member.id, UserUpdate(**changes), admin, db)

    assert level() is READ
    policy_service.replace_group_access(
        db, group_id, [GroupAccessEntry(department_id=sales.id, level=WRITE)],
        _etag(db, group_id), admin.id,
    )
    assert level() is WRITE
    members([])
    assert level() is None
    members([member.id])
    assert level() is WRITE
    _move(db, ledger, other, admin)
    assert level() is None
    _move(db, ledger, sales, admin)
    assert level() is WRITE
    # The service refuses a group with members, so a deletion changes no level here.
    policy_service.delete_group(db, empty_id, _etag(db, empty_id), admin.id)
    assert level() is WRITE
    update(role=UserRole.ADMIN)
    assert level() is MANAGE
    update(role=UserRole.MEMBER)  # promotion took the person out of every group
    assert level() is None
    members([member.id])
    assert level() is WRITE
    update(status=UserStatus.DISABLED)
    assert level() is None


def test_a_savepoint_rollback_resolves_the_access_again(
    integration_db: Session, one_transaction: None
) -> None:
    db = integration_db
    admin = add_user(db, role=UserRole.ADMIN)
    member = add_user(db)
    sales = add_department(db)
    group_id = make_group_access(db, [member], sales, level=READ).group_id
    assert effective_levels(db, member).department_level(sales.id) is READ

    savepoint = db.begin_nested()
    policy_service.replace_group_access(
        db, group_id, [GroupAccessEntry(department_id=sales.id, level=MANAGE)],
        _etag(db, group_id), admin.id,
    )
    assert effective_levels(db, member).department_level(sales.id) is MANAGE
    savepoint.rollback()

    assert effective_levels(db, member).department_level(sales.id) is READ


@pytest.fixture
def without_reload_backup() -> Iterator[None]:
    """Remove the load and reload drop, so each helper must drop the resolution itself."""

    pairs = [(model, name) for model in (User, Membership) for name in ("load", "refresh")]
    for model, name in pairs:
        event.remove(model, name, transaction_access._forget_reloaded)
    try:
        yield
    finally:
        for model, name in pairs:
            event.listen(model, name, transaction_access._forget_reloaded)


def _lock_manager(db: Session, user: User) -> object:
    return delegation._lock_manager_authority(db, user.id)


@pytest.mark.parametrize(
    "drop",
    [
        pytest.param(lambda db, user: _lock_authority(db, user.id), id="lock_authority"),
        pytest.param(_lock_manager, id="lock_manager_authority"),
        pytest.param(
            lambda db, user: organization_membership(db, user.id, fresh=True),
            id="organization_membership_fresh",
        ),
        pytest.param(fresh_membership, id="comms_fresh_membership"),
        pytest.param(
            lambda db, user: require_fresh_exact_admin(db, user.id), id="require_fresh_exact_admin"
        ),
    ],
)
def test_each_lock_and_fresh_read_drops_the_stored_resolution(
    integration_db: Session, without_reload_backup: None, drop: Callable[[Session, User], object]
) -> None:
    db = integration_db
    member = add_user(db)
    sales = add_department(db)
    make_group_access(db, [member], sales, level=WRITE)
    assert effective_levels(db, member).unrestricted is False
    # Another transaction promotes the person, unseen by this one's stored resolution.
    db.connection().execute(
        text("UPDATE public.memberships SET role = 'admin' WHERE user_id = :user_id"),
        {"user_id": member.id},
    )
    assert effective_levels(db, member).unrestricted is False

    drop(db, member)

    assert effective_levels(db, member).unrestricted is True


def test_the_fresh_module_check_overwrites_an_earlier_resolution(
    integration_db: Session, without_reload_backup: None
) -> None:
    db = integration_db
    member = add_user(db)
    sales = add_department(db)
    ledger = add_module(db, sales)
    grant = make_group_access(db, [member], sales, level=WRITE)
    session = IdentitySession(
        user_id=member.id, refresh_token_digest=uuid7().hex * 2,
        csrf_token_digest=uuid7().hex * 2, expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(session)
    db.flush()
    assert effective_levels(db, member).module_level(ledger.id) is WRITE
    db.connection().execute(
        text("UPDATE public.group_access SET level = 'read' WHERE id = :id"), {"id": grant.id}
    )

    require_fresh_module_access(
        db, actor_id=member.id, session_id=session.id, module_id=ledger.id, level=READ
    )
    # As charts/service.py:106-107 do after the lock: the seeded result, with no read.
    access, statements = _statements(db, lambda: effective_levels(db, member))

    assert access.module_level(ledger.id) is READ
    assert statements == 0


def test_a_rebound_transaction_resolves_in_its_new_organization(integration_db: Session) -> None:
    db = integration_db
    member = add_user(db)
    first = db.info["rbac_organization"].id
    sales = add_department(db)
    make_group_access(db, [member], sales, level=WRITE)
    second = create_organization(db)
    create_member(db, second, user=member)
    stock = Department(org_id=second.id, department_name=f"Stock {uuid7().hex}")
    db.add(stock)
    db.flush()
    make_group_access(db, [member], stock, level=READ)

    scope_session(db, first)
    in_first = effective_levels(db, member)
    scope_session(db, second.id)
    in_second = effective_levels(db, member)

    assert (in_first.department_level(sales.id), in_first.department_level(stock.id)) == (
        WRITE, None,
    )
    assert (in_second.department_level(sales.id), in_second.department_level(stock.id)) == (
        None, READ,
    )


def test_closing_the_session_leaves_no_resolution_and_the_next_transaction_resolves_again(
    integration_db: Session,
) -> None:
    db = integration_db
    member = add_user(db)
    sales = add_department(db)
    make_group_access(db, [member], sales, level=WRITE)
    db.commit()
    assert effective_levels(db, member).department_level(sales.id) is WRITE
    assert transaction_access.STORE_KEY in db.info

    db.close()

    assert transaction_access.STORE_KEY not in db.info
    access, statements = _statements(db, lambda: effective_levels(db, member))
    assert access.department_level(sales.id) is WRITE
    assert statements > 0
