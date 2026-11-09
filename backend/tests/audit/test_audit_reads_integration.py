"""The five audit reads return the same rows before and after the organization chokepoint (P6).

Every expected id comes from this file's own inserts. A shared `request_id` bounds the list,
so rows that the fixture builders write do not count.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import get_current_user
from app.core.database.organization_scope import scope_session
from app.core.database.session import get_db
from app.main import create_app
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User, UserRole
from app.systems.manage.audit.models import AuditAction, AuditLog
from app.systems.sandbox.records.models import Record
from tests.conftest import create_member, create_organization
from tests.organization_scope_support import bind_test_organization, scoped_override
from tests.rbac.support import (
    add_department,
    add_module,
    add_user,
    make_group_access,
    organization,
)

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 1, 9, tzinfo=UTC)


@dataclass
class _Reads:
    db: Session
    client: TestClient
    reader: list[User]
    admin: User
    manager: User
    member: User
    request_id: UUID
    department: UUID
    record: UUID
    department_rows: list[str]
    other_department_row: str
    shared_account_row: str
    record_rows: list[str]
    hidden_rows: list[str]
    hidden_actor: UUID

    def get(self, user: User, path: str, **params: Any) -> Any:
        self.reader[:] = [user]
        response = self.client.get(path, params=params)
        assert response.status_code == 200, response.text
        return response


def _row(
    db: Session, minute: int, *, action: AuditAction = AuditAction.UPDATE, **values: Any
) -> str:
    identity = uuid7()
    db.connection().execute(AuditLog.__table__.insert().values(
        id=identity, created_at=START + timedelta(minutes=minute), action=action,
        after={"marker": identity.hex}, **values,
    ))
    return str(identity)


@pytest.fixture
def reads(integration_db: Session) -> Iterator[_Reads]:
    db = integration_db
    admin = add_user(db, role=UserRole.ADMIN)
    manager, member = add_user(db), add_user(db)
    department, other_department = add_department(db), add_department(db)
    module = add_module(db, department)
    make_group_access(db, [manager], department, level=AccessLevel.MANAGE)
    make_group_access(db, [member], department, module, level=AccessLevel.READ)
    record = Record(org_id=department.org_id, module_id=module.id, data={})
    db.add(record)
    db.flush()
    home = organization(db)
    shared, _ = create_member(db, home)
    foreign_organization = create_organization(db)
    create_member(db, foreign_organization, user=shared)
    foreign, _ = create_member(db, foreign_organization)
    # Creating the other organization bound the session to it; bind it back to home.
    scope_session(db, home.id)
    bind_test_organization(home.id)
    request_id = uuid7()
    bounded = {"request_id": request_id}
    department_rows = [
        _row(db, minute, org_id=home.id, department_id=department.id, entity_type="reports",
             entity_id=uuid7(), performed_by=admin.id, **bounded)
        for minute in (1, 2, 3, 4, 5)
    ]
    other_department_row = _row(
        db, 6, org_id=home.id, department_id=other_department.id, entity_type="dashboards",
        entity_id=uuid7(), performed_by=manager.id, **bounded,
    )
    shared_account_row = _row(
        db, 7, org_id=None, entity_type="users", entity_id=shared.id, performed_by=shared.id,
        **bounded,
    )
    record_rows = [
        _row(db, minute, org_id=home.id, department_id=department.id, entity_type="records",
             entity_id=record.id, action=AuditAction.CREATE, **bounded)
        for minute in (8, 9)
    ]
    hidden_rows = [
        _row(db, 10, org_id=None, entity_type="users", entity_id=foreign.id,
             performed_by=foreign.id, **bounded),
        _row(db, 11, org_id=None, entity_type="platform_settings", entity_id=uuid7(),
             performed_by=foreign.id, **bounded),
    ]
    organization_id = home.id
    db.commit()
    current: list[User] = [admin]
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_current_user] = scoped_override(
        lambda: current[0], org_id=organization_id
    )
    with TestClient(application) as client:
        yield _Reads(
            db, client, current, admin, manager, member, request_id, department.id, record.id,
            department_rows, other_department_row, shared_account_row, record_rows,
            hidden_rows, foreign.id,
        )


def _walk(world: _Reads, user: User, **filters: Any) -> list[str]:
    """Every page of the list, two rows at a time, newest first."""

    ids: list[str] = []
    while True:
        page = world.get(user, "/api/audit-logs", limit=2, offset=len(ids), **filters).json()
        ids += [row["id"] for row in page["items"]]
        if not page["pagination"]["has_more"]:
            return ids


def test_each_audit_read_returns_the_expected_rows_in_order_p6(reads: _Reads) -> None:
    world = reads
    bounded = {"request_id": str(world.request_id)}
    admin_rows = [
        *reversed(world.record_rows), world.shared_account_row,
        world.other_department_row, *reversed(world.department_rows),
    ]
    manager_rows = [*reversed(world.record_rows), *reversed(world.department_rows)]

    assert _walk(world, world.admin, **bounded) == admin_rows
    assert _walk(world, world.manager, department_id=str(world.department), **bounded) == (
        manager_rows
    )
    history = world.get(
        world.member, "/api/audit-logs", entity_id=str(world.record), limit=50, **bounded
    )
    assert [row["id"] for row in history.json()["items"]] == list(reversed(world.record_rows))

    exported = world.get(world.admin, "/api/audit-logs/export", **bounded)
    assert exported.headers["x-audit-export-count"] == str(len(admin_rows))
    for identity in admin_rows:
        assert f"Marker: {UUID(identity).hex}" in exported.text
    for identity in world.hidden_rows:
        assert f"Marker: {UUID(identity).hex}" not in exported.text

    for identity in admin_rows:
        assert world.get(world.admin, f"/api/audit-logs/{identity}").json()["id"] == identity
    world.reader[:] = [world.admin]
    for identity in world.hidden_rows:
        assert world.client.get(f"/api/audit-logs/{identity}").status_code == 404

    admin_options = world.get(world.admin, "/api/audit-logs/options").json()
    assert {"reports", "dashboards", "users", "records"} <= set(admin_options["entity_types"])
    assert "platform_settings" not in admin_options["entity_types"]
    admin_actors = {row["performed_by"] for row in admin_options["actors"]}
    assert {str(world.admin.id), str(world.manager.id)} <= admin_actors
    assert str(world.hidden_actor) not in admin_actors

    manager_options = world.get(
        world.manager, "/api/audit-logs/options", department_id=str(world.department)
    ).json()
    assert {"reports", "records"} <= set(manager_options["entity_types"])
    assert not {"dashboards", "users", "platform_settings"} & set(
        manager_options["entity_types"]
    )
    manager_actors = {row["performed_by"] for row in manager_options["actors"]}
    assert str(world.admin.id) in manager_actors
    assert not {str(world.manager.id), str(world.hidden_actor)} & manager_actors


ORGANIZATION_ROWS = "audit_logs.org_id = nullif(current_setting("
ACCOUNT_ROWS = "audit_logs.org_id IS NULL"


@contextmanager
def _audit_statements(db: Session) -> Iterator[list[str]]:
    """The statements that read `audit_logs`, as the application sends them."""

    seen: list[str] = []

    def record(_connection, _cursor, statement, _parameters, _context, _many) -> None:
        if "FROM audit_logs" in statement:
            seen.append(statement)

    engine = db.connection().engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_each_audit_statement_states_the_organization_condition_once_g2(reads: _Reads) -> None:
    # H1: the chokepoint gives each read its condition exactly once; twice costs a Sort,
    # none shows other organizations' account rows and install-wide rows.
    world = reads
    bounded = {"request_id": str(world.request_id)}
    reads_by_route = {
        "admin list": (world.admin, "/api/audit-logs", bounded),
        "manager list": (
            world.manager, "/api/audit-logs", {"department_id": str(world.department)},
        ),
        "admin options": (world.admin, "/api/audit-logs/options", {}),
        "manager options": (
            world.manager, "/api/audit-logs/options", {"department_id": str(world.department)},
        ),
        "record history": (world.member, "/api/audit-logs", {"entity_id": str(world.record)}),
        "export": (world.admin, "/api/audit-logs/export", bounded),
        "detail": (world.admin, f"/api/audit-logs/{world.department_rows[0]}", {}),
    }
    counts = {}
    for name, (user, path, params) in reads_by_route.items():
        with _audit_statements(world.db) as seen:
            world.get(user, path, **params)
        counts[name] = [
            (statement.count(ORGANIZATION_ROWS), statement.count(ACCOUNT_ROWS))
            for statement in seen
        ]

    assert counts == {
        "admin list": [(1, 1), (1, 1)],
        "manager list": [(1, 1), (1, 1)],
        "admin options": [(1, 1), (1, 1)],
        "manager options": [(1, 1), (1, 1)],
        "record history": [(1, 1), (1, 1)],
        "export": [(1, 1)],
        "detail": [(1, 1)],
    }
