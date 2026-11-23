"""A sheet write that waits on a held lock past its bound answers 503 (D3.3).

Another connection holds the sheet row ``FOR UPDATE``; the rename waits its 2 s lock bound,
then answers 503 ``worksheet_busy`` and changes nothing. The rows are committed with the
owner role so both connections see them, and removed afterwards.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.main import create_app
from app.systems.access.users.models import Membership, User
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.models import Worksheet
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from tests.conftest import guarded_create_engine
from tests.rbac.support import _client
from tests.worksheets.support import STRUCTURE

pytestmark = pytest.mark.integration
_TABLES = ("worksheets", "records", "modules", "departments", "memberships")


@dataclass(frozen=True)
class Committed:
    owner_engine: Engine
    org_id: UUID
    user_id: UUID
    sheet_id: UUID


@pytest.fixture
def committed(integration_db: Session) -> Iterator[Committed]:
    owner_engine = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"])
    org_id, user_id, department_id, module_id, record_id, sheet_id = (
        uuid7() for _ in range(6)
    )
    with owner_engine.begin() as connection:
        connection.execute(WorkspaceProfile.__table__.insert().values(
            id=org_id, slug=f"lock-{org_id}", display_name="Lock", timezone="UTC",
            locale="en-US",
        ))
        connection.execute(User.__table__.insert().values(
            id=user_id, email=f"lock-{user_id}@example.test", username=f"lock-{user_id}",
            status="active",
        ))
        connection.execute(Membership.__table__.insert().values(
            id=uuid7(), org_id=org_id, user_id=user_id, role="admin", status="active",
            invitation_accepted_at=datetime.now(UTC),
        ))
        connection.execute(Department.__table__.insert().values(
            id=department_id, org_id=org_id, department_name="Lock",
        ))
        connection.execute(Module.__table__.insert().values(
            id=module_id, org_id=org_id, department_id=department_id, module_name="Lock",
        ))
        connection.execute(Record.__table__.insert().values(
            id=record_id, org_id=org_id, module_id=module_id, data={},
        ))
        connection.execute(Worksheet.__table__.insert().values(
            id=sheet_id, org_id=org_id, record_id=record_id, owner_id=user_id,
            title="Held", structure=STRUCTURE,
        ))
    try:
        yield Committed(owner_engine, org_id, user_id, sheet_id)
    finally:
        integration_db.rollback()
        integration_db.connection().rollback()
        with owner_engine.begin() as connection:
            for table in _TABLES:
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE org_id = :org"), {"org": org_id}
                )
            connection.execute(text("DELETE FROM public.audit_logs WHERE org_id = :org"),
                               {"org": org_id})
            connection.execute(text("DELETE FROM public.users WHERE id = :id"), {"id": user_id})
            connection.execute(text("DELETE FROM public.organizations WHERE id = :id"),
                               {"id": org_id})
        owner_engine.dispose()


def test_a_rename_behind_a_held_sheet_lock_answers_busy_and_changes_nothing(
    integration_db: Session, committed: Committed,
) -> None:
    owner = integration_db.get(User, committed.user_id)
    assert owner is not None
    client = _client(create_app(), owner, integration_db)
    path = f"/api/worksheets/{committed.sheet_id}"
    with committed.owner_engine.connect() as holder:
        holder.execute(text("SELECT id FROM public.worksheets WHERE id = :id FOR UPDATE"),
                       {"id": committed.sheet_id})
        refused = client.patch(path, json={"title": "Changed"},
                               headers={"If-Match": f'"{committed.sheet_id}:1"'})
        holder.rollback()
    assert (refused.status_code, refused.json()["detail"]["code"]) == (503, "worksheet_busy")
    with committed.owner_engine.connect() as reader:
        title = reader.scalar(text("SELECT title FROM public.worksheets WHERE id = :id"),
                              {"id": committed.sheet_id})
    assert title == "Held"
