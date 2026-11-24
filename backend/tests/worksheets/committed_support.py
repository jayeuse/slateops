"""A committed organization with a shared sheet, for tests that race two real sessions.

Rows are written with the owner role so every connection sees them, and every row of the
organization is removed afterwards, child tables first (the guarded reset's order).
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import Connection, Engine, text
from uuid6 import uuid7

from app.systems.access.policy.models import Group, GroupAccess, GroupMember
from app.systems.access.users.models import Membership, User
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetShare
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from operations.reset.models import DELETE_ORDER
from tests.conftest import guarded_create_engine
from tests.worksheets.support import STRUCTURE

TEXT = {**STRUCTURE, "nextColumnSeq": 4,
        "columns": [{"key": "c3", "name": "Note", "type": "text"}]}


@dataclass(frozen=True)
class CommittedSheet:
    owner_engine: Engine
    org_id: UUID
    admin_id: UUID
    owner_id: UUID
    editor_id: UUID
    sheet_id: UUID
    row_id: UUID
    share_id: UUID


def _person(connection: Connection, org_id: UUID, role: str) -> UUID:
    user_id = uuid7()
    connection.execute(User.__table__.insert().values(
        id=user_id, email=f"race-{user_id}@example.test", username=f"race-{user_id}",
        status="active",
    ))
    connection.execute(Membership.__table__.insert().values(
        id=uuid7(), org_id=org_id, user_id=user_id, role=role, status="active",
        invitation_accepted_at=datetime.now(UTC),
    ))
    return user_id


@pytest.fixture
def committed_sheet() -> Iterator[CommittedSheet]:
    owner_engine = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"])
    org_id, department_id, module_id, record_id, group_id = (uuid7() for _ in range(5))
    sheet_id, row_id, share_id = uuid7(), uuid7(), uuid7()
    with owner_engine.begin() as connection:
        connection.execute(WorkspaceProfile.__table__.insert().values(
            id=org_id, slug=f"race-{org_id}", display_name="Race", timezone="UTC",
            locale="en-US",
        ))
        admin_id = _person(connection, org_id, "admin")
        owner_id = _person(connection, org_id, "member")
        editor_id = _person(connection, org_id, "member")
        connection.execute(Department.__table__.insert().values(
            id=department_id, org_id=org_id, department_name="Race",
        ))
        connection.execute(Module.__table__.insert().values(
            id=module_id, org_id=org_id, department_id=department_id, module_name="Race",
        ))
        connection.execute(Group.__table__.insert().values(
            id=group_id, org_id=org_id, name="Race readers",
        ))
        for person in (owner_id, editor_id):
            connection.execute(GroupMember.__table__.insert().values(
                id=uuid7(), org_id=org_id, group_id=group_id, user_id=person,
            ))
        connection.execute(GroupAccess.__table__.insert().values(
            id=uuid7(), org_id=org_id, group_id=group_id, department_id=department_id,
            module_id=None, level="read",
        ))
        connection.execute(Record.__table__.insert().values(
            id=record_id, org_id=org_id, module_id=module_id, data={},
        ))
        connection.execute(Worksheet.__table__.insert().values(
            id=sheet_id, org_id=org_id, record_id=record_id, owner_id=owner_id,
            title="Race", structure=TEXT, live_row_count=1, data_bytes=10,
        ))
        connection.execute(WorksheetRow.__table__.insert().values(
            id=row_id, org_id=org_id, worksheet_id=sheet_id, position=1024,
            data={"c3": "x"}, data_bytes=10,
        ))
        connection.execute(WorksheetShare.__table__.insert().values(
            id=share_id, org_id=org_id, worksheet_id=sheet_id, subject="user",
            user_id=editor_id, level="edit", created_by=owner_id,
        ))
    people = [admin_id, owner_id, editor_id]
    try:
        yield CommittedSheet(owner_engine, org_id, admin_id, owner_id, editor_id, sheet_id,
                             row_id, share_id)
    finally:
        with owner_engine.begin() as connection:
            scoped = set(connection.scalars(text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'org_id'"
            )))
            for table in DELETE_ORDER:
                if table in scoped:
                    connection.execute(text(f"DELETE FROM public.{table} WHERE org_id = :org"),
                                       {"org": org_id})
            connection.execute(text("DELETE FROM public.security_events WHERE subject_id = ANY("
                                    ":people) OR actor_id = ANY(:people)"), {"people": people})
            connection.execute(text("DELETE FROM public.identity_sessions "
                                    "WHERE user_id = ANY(:people)"), {"people": people})
            connection.execute(text("DELETE FROM public.users WHERE id = ANY(:people)"),
                               {"people": people})
            connection.execute(text("DELETE FROM public.organizations WHERE id = :org"),
                               {"org": org_id})
        owner_engine.dispose()
