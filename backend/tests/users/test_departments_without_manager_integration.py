"""The user summary lists the open departments that no active member manages (BE-SD8, R13).

SD-C33 (a non-administrator gets 403) is owned by
``tests/access/test_people_monitoring_integration.py::
test_recorded_history_endpoints_retain_exact_admin_admission``.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.common.dependencies.auth import get_current_user
from app.core.database import get_db
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User, UserRole, UserStatus
from app.systems.access.users.router import router as users_router
from app.systems.sandbox.departments.models import Department
from tests.organization_scope_support import scoped_override
from tests.rbac.support import add_department, add_module, add_user, make_group_access

pytestmark = pytest.mark.integration


@pytest.fixture
def summary_client(integration_owner_db: Session) -> Iterator[tuple[Session, User, TestClient]]:
    db = integration_owner_db
    admin = add_user(db, "summary-admin", role=UserRole.ADMIN)
    app = FastAPI()
    app.include_router(users_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = scoped_override(lambda: admin)
    with TestClient(app) as client:
        yield db, admin, client


def _managed_by(db: Session, people: list[User], *, level: str = AccessLevel.MANAGE,
                module: bool = False) -> Department:
    department = add_department(db)
    make_group_access(
        db, people, department, add_module(db, department) if module else None, level=level
    )
    return department


def test_summary_lists_open_departments_without_an_active_non_admin_manager(summary_client):
    db, admin, client = summary_client
    manager = add_user(db, "summary-manager")
    managed = _managed_by(db, [manager])
    module_only = _managed_by(db, [add_user(db, "summary-module")], module=True)
    write_only = _managed_by(db, [add_user(db, "summary-writer")], level=AccessLevel.WRITE)
    guest_manager = _managed_by(db, [add_user(db, "summary-guest", role=UserRole.GUEST)])
    admin_manager = _managed_by(db, [admin])
    disabled_manager = _managed_by(
        db, [add_user(db, "summary-disabled", status=UserStatus.DISABLED)]
    )
    empty = add_department(db)
    closed = add_department(db)
    closed.is_deleted, closed.deleted_at = True, datetime.now(UTC)
    db.flush()

    response = client.get("/api/users/summary")

    assert response.status_code == 200, response.text
    listed = [UUID(identity) for identity in response.json()["departments_without_manager"]]
    assert len(listed) == len(set(listed))
    assert set(listed) == {
        module_only.id,
        write_only.id,
        guest_manager.id,
        admin_manager.id,
        disabled_manager.id,
        empty.id,
    }
    assert managed.id not in listed and closed.id not in listed
