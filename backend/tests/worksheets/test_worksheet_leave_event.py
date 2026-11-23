"""An account-wide leave opens the sheets of every organization; the event names one (SH-60).

This test keeps the real security-event writer: committed rows in two organizations, the
installation owner disables the shared account in the first one, and the event table is read.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from uuid6 import uuid7

import app.systems.access.users.account_operations as account_operations
from app.core.database.organization_scope import scope_session
from app.core.database.session import AuditSession
from app.systems.access.users.models import Membership, PlatformOperator, User
from app.systems.access.users.schemas import UserUpdate
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.access import worksheet_present_clause
from app.systems.openview.worksheets.models import Worksheet
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from operations.reset.models import DELETE_ORDER
from tests.conftest import guarded_create_engine
from tests.worksheets.committed_support import TEXT, CommittedSheet
from tests.worksheets.committed_support import committed_sheet as committed_sheet

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class SecondOrganization:
    org_id: UUID
    sheet_id: UUID


@pytest.fixture
def second_organization(committed_sheet: CommittedSheet) -> Iterator[SecondOrganization]:
    world, engine = committed_sheet, committed_sheet.owner_engine
    org_id, department_id, module_id, record_id, sheet_id = (uuid7() for _ in range(5))
    with engine.begin() as connection:
        connection.execute(WorkspaceProfile.__table__.insert().values(
            id=org_id, slug=f"race-two-{org_id}", display_name="Two", timezone="UTC",
            locale="en-US",
        ))
        connection.execute(Membership.__table__.insert().values(
            id=uuid7(), org_id=org_id, user_id=world.owner_id, role="member",
            status="active", invitation_accepted_at=text("now()"),
        ))
        connection.execute(Department.__table__.insert().values(
            id=department_id, org_id=org_id, department_name="Two",
        ))
        connection.execute(Module.__table__.insert().values(
            id=module_id, org_id=org_id, department_id=department_id, module_name="Two",
        ))
        connection.execute(Record.__table__.insert().values(
            id=record_id, org_id=org_id, module_id=module_id, data={},
        ))
        connection.execute(Worksheet.__table__.insert().values(
            id=sheet_id, org_id=org_id, record_id=record_id, owner_id=world.owner_id,
            title="Two", structure=TEXT,
        ))
        connection.execute(PlatformOperator.__table__.insert().values(
            id=uuid7(), user_id=world.admin_id,
        ))
    try:
        yield SecondOrganization(org_id, sheet_id)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM public.platform_operators WHERE user_id = :id"),
                               {"id": world.admin_id})
            scoped = set(connection.scalars(text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'org_id'"
            )))
            for table in DELETE_ORDER:
                if table in scoped:
                    connection.execute(text(f"DELETE FROM public.{table} WHERE org_id = :org"),
                                       {"org": org_id})
            connection.execute(text("DELETE FROM public.organizations WHERE id = :org"),
                               {"org": org_id})


def _present(engine: Engine, org_id: UUID, sheet_id: UUID) -> bool:
    with AuditSession(engine) as db:
        scope_session(db, org_id)
        return bool(db.scalar(select(worksheet_present_clause()).select_from(Worksheet).where(
            Worksheet.id == sheet_id
        )))


def test_an_account_disable_opens_both_organizations_and_records_one_event(
    committed_sheet: CommittedSheet, second_organization: SecondOrganization,
) -> None:
    world, other = committed_sheet, second_organization
    runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        assert _present(runtime, world.org_id, world.sheet_id)
        with AuditSession(runtime) as db:
            scope_session(db, world.org_id)
            db.info[AUDIT_CONTEXT_KEY] = AuditContext(
                request_id=uuid7(), request_method="PATCH", request_path="/api/users",
            )
            admin = db.get(User, world.admin_id)
            account_operations.update_user(
                world.owner_id, UserUpdate(status="disabled"), admin, db,
            )
        assert not _present(runtime, world.org_id, world.sheet_id)
        assert not _present(runtime, other.org_id, other.sheet_id)
    finally:
        runtime.dispose()
    with world.owner_engine.connect() as connection:
        events = connection.execute(text(
            "SELECT org_id, metadata FROM public.security_events "
            "WHERE event_type = 'worksheets.opened_on_leave' AND subject_id = :owner"
        ), {"owner": world.owner_id}).all()
    assert [(row.org_id, row.metadata) for row in events] == [
        (world.org_id, {"opened_count": 1, "path": "account_disabled"}),
    ]
