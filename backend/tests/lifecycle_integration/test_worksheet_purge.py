"""Sheets follow their record or module through the lifecycle (D4, F1, F2, N6).

SH-29, SH-40, SH-56, SH-68.
"""

from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.policy.models import AccessLevel
from app.systems.openview.worksheets.access import worksheet_level
from app.systems.openview.worksheets.models import (
    Worksheet,
    WorksheetRow,
    WorksheetRowLink,
    WorksheetRowRevision,
    WorksheetShare,
)
from app.systems.openview.worksheets.query import read_row
from app.systems.sandbox.fields.models import Field
from app.systems.sandbox.lifecycle.exceptions import LifecyclePlanDriftError
from app.systems.sandbox.lifecycle.planner import LifecyclePlan, plan_lifecycle
from app.systems.sandbox.lifecycle.schemas import LifecycleTargetType
from app.systems.sandbox.lifecycle.service import (
    close_lifecycle,
    purge_lifecycle,
    reopen_lifecycle,
)
from tests.lifecycle_integration.lifecycle_integration_support import close_rows
from tests.rbac.support import (
    _client,
    add_department,
    add_module,
    make_group_access,
    organization,
)
from tests.sandbox_designs.fixtures import create_document
from tests.worksheets.support import (
    STRUCTURE,
    SheetWorld,
    add_sheet,
    add_students,
    sheet_world,
)

pytestmark = pytest.mark.integration
LINKED = {**STRUCTURE, "nextColumnSeq": 2,
          "columns": [{"key": "c1", "name": "Student", "type": "link",
                       "link": {"moduleId": "00000000-0000-7000-8000-000000000000"}}]}


def _row_with_link(db: Session, sheet: Worksheet, target: object,
                   *, deleted: bool = False) -> tuple[WorksheetRow, WorksheetRowLink]:
    row = WorksheetRow(org_id=sheet.org_id, worksheet_id=sheet.id, position=1024,
                       data={}, data_bytes=2)
    db.add(row)
    db.flush()
    link = WorksheetRowLink(org_id=row.org_id, worksheet_id=sheet.id, row_id=row.id,
                            column_key="c1", target_record_id=target,
                            target_removed=target is None)
    if deleted:
        link.is_deleted, link.deleted_at = True, utc_now()
    db.add(link)
    db.add(WorksheetRowRevision(org_id=row.org_id, worksheet_id=sheet.id, row_id=row.id,
                                revision=1, action="create", data={}, changed_keys=[]))
    db.flush()
    return row, link


def _world(db: Session, anchor: str = "record") -> SheetWorld:
    """A sheet world in an organization with its Sandbox document, as lifecycle needs."""

    world = sheet_world(db, "module" if anchor == "module" else "record")
    create_document(db, organization(db))
    db.add(Field(org_id=world.module.org_id, module_id=world.module.id, name="Name",
                 type="text", position=0, config={}))  # a module schema needs a field
    db.flush()
    return world


def _purge_plan(db: Session, target_type: LifecycleTargetType, target_id: UUID) -> LifecyclePlan:
    return plan_lifecycle(db, target_type, target_id, "purge", None)


def _gone(db: Session, sheet_id: object) -> dict[str, int]:
    counts = {}
    for model in (Worksheet, WorksheetRow, WorksheetShare, WorksheetRowLink,
                  WorksheetRowRevision):
        column = model.id if model is Worksheet else model.worksheet_id
        counts[model.__tablename__] = len(db.scalars(select(model.id).where(
            column == sheet_id
        )).all())
    return counts


NOTHING = dict.fromkeys(
    ("worksheets", "worksheet_rows", "worksheet_shares", "worksheet_row_links",
     "worksheet_row_revisions"), 0,
)


def test_a_record_delete_hides_its_sheets_and_a_restore_returns_them_with_shares(
    integration_db: Session,
) -> None:
    world = _world(integration_db)
    close_rows(world.record)
    integration_db.flush()
    assert worksheet_level(integration_db, world.editor, world.sheet) is None
    world.record.is_deleted, world.record.deleted_at = False, None
    integration_db.flush()
    assert worksheet_level(integration_db, world.editor, world.sheet) == "edit"


def test_a_module_close_hides_module_sheets_and_a_reopen_returns_them(
    integration_db: Session,
) -> None:
    world = _world(integration_db, "module")
    integration_db.commit()
    close_lifecycle(integration_db, LifecycleTargetType.MODULE, world.module.id, None)
    assert worksheet_level(integration_db, world.owner, world.sheet) is None
    reopen_lifecycle(integration_db, LifecycleTargetType.MODULE, world.module.id, None)
    assert worksheet_level(integration_db, world.owner, world.sheet) == "owner"
    assert worksheet_level(integration_db, world.editor, world.sheet) == "edit"


def _linked_elsewhere(db: Session, world: SheetWorld) -> tuple[Worksheet, WorksheetRowLink,
                                                                WorksheetRowLink]:
    """Another sheet whose links (one live, one deleted) point at the world's record."""

    students = add_students(db, world, [world.owner])
    other = add_sheet(db, world.owner, module=students.module)
    other.structure = {**LINKED, "columns": [{**LINKED["columns"][0],
                                              "link": {"moduleId": str(world.module.id)}}]}
    _row, live = _row_with_link(db, other, world.record.id)
    _row, gone = _row_with_link(db, other, world.record.id, deleted=True)
    return other, live, gone


def test_a_record_purge_removes_its_sheets_and_marks_links_elsewhere_removed(
    integration_db: Session,
) -> None:
    db = integration_db
    world = _world(db)
    _row_with_link(db, world.sheet, None)
    other, live, gone = _linked_elsewhere(db, world)
    close_rows(world.record)
    db.commit()
    plan = _purge_plan(db, LifecycleTargetType.RECORD, world.record.id)
    response = plan.response().model_dump(mode="json")
    assert response["worksheet_count"] == 1
    assert world.sheet.title not in str(response)
    purge_lifecycle(db, LifecycleTargetType.RECORD, world.record.id, None, plan=plan)
    assert _gone(db, world.sheet.id) == NOTHING
    for link in (live, gone):
        db.refresh(link)
        assert (link.target_record_id, link.target_removed) == (None, True)
    cell = read_row(db, world.owner, other, live.row_id)
    assert cell is not None and cell.cells["c1"].model_dump() == {"state": "removed"}


def test_a_module_purge_removes_module_sheets_and_sheets_of_its_records(
    integration_db: Session,
) -> None:
    db = integration_db
    world = _world(db, "module")
    on_record = add_sheet(db, world.owner, record=world.record)
    _row_with_link(db, world.sheet, None)
    db.commit()
    close_lifecycle(db, LifecycleTargetType.MODULE, world.module.id, None)
    plan = _purge_plan(db, LifecycleTargetType.MODULE, world.module.id)
    assert plan.response().worksheet_count == 2
    purge_lifecycle(db, LifecycleTargetType.MODULE, world.module.id, None, plan=plan)
    assert _gone(db, world.sheet.id) == NOTHING
    assert _gone(db, on_record.id) == NOTHING


def test_a_department_purge_removes_the_sheets_of_its_modules(
    integration_db: Session,
) -> None:
    db = integration_db
    world = _world(db, "module")
    on_record = add_sheet(db, world.owner, record=world.record)
    db.commit()
    close_lifecycle(db, LifecycleTargetType.DEPARTMENT, world.department.id, None)
    plan = _purge_plan(db, LifecycleTargetType.DEPARTMENT, world.department.id)
    assert plan.response().worksheet_count == 2
    purge_lifecycle(db, LifecycleTargetType.DEPARTMENT, world.department.id, None, plan=plan)
    assert _gone(db, world.sheet.id) == NOTHING
    assert _gone(db, on_record.id) == NOTHING


def test_a_sheet_made_after_the_preview_stops_the_purge(integration_db: Session) -> None:
    db = integration_db
    world = _world(db)
    close_rows(world.record)
    db.commit()
    plan = _purge_plan(db, LifecycleTargetType.RECORD, world.record.id)
    late = add_sheet(db, world.owner, record=world.record)
    db.commit()
    with pytest.raises(LifecyclePlanDriftError, match="Lifecycle impact changed after planning"):
        purge_lifecycle(db, LifecycleTargetType.RECORD, world.record.id, None, plan=plan)
    assert db.get(Worksheet, world.sheet.id) is not None
    assert db.get(Worksheet, late.id) is not None


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _sheet_linking_into(db: Session, world: SheetWorld) -> tuple[Worksheet, UUID, UUID]:
    """A sheet in another department whose link column points into the world's module."""

    department = add_department(db)
    module = add_module(db, department)
    make_group_access(db, [world.owner], department, module, level=AccessLevel.READ)
    other = add_sheet(db, world.owner, module=module)
    other.structure = {**LINKED, "columns": [{**LINKED["columns"][0],
                                              "link": {"moduleId": str(world.module.id)}}]}
    linked, _link = _row_with_link(db, other, world.record.id)
    unlinked = WorksheetRow(org_id=other.org_id, worksheet_id=other.id, position=2048,
                            data={"c1": {"unlinked": "Carol"}}, data_bytes=26)
    db.add(unlinked)
    db.flush()
    return other, linked.id, unlinked.id


@pytest.mark.parametrize("target", [LifecycleTargetType.MODULE, LifecycleTargetType.DEPARTMENT])
def test_links_into_a_purged_module_read_removed_and_can_be_cleared(
    integration_db: Session, application: FastAPI, target: LifecycleTargetType,
) -> None:
    """B8-B1 (N6, SH-29): the target module row is gone, so the column is not hidden."""

    db = integration_db
    world = _world(db)
    other, linked_id, unlinked_id = _sheet_linking_into(db, world)
    db.commit()
    target_id = world.module.id if target is LifecycleTargetType.MODULE else world.department.id
    close_lifecycle(db, target, target_id, None)
    purge_lifecycle(db, target, target_id, None, plan=_purge_plan(db, target, target_id))
    linked = read_row(db, world.owner, other, linked_id)
    unlinked = read_row(db, world.owner, other, unlinked_id)
    assert linked is not None and linked.cells["c1"].model_dump() == {"state": "removed"}
    assert unlinked is not None and unlinked.cells["c1"].model_dump() == {"unlinked": "Carol"}
    response = _client(application, world.owner, db).patch(
        f"/api/worksheets/{other.id}/rows/{linked_id}",
        json={"cells": {"c1": {"value": None, "expected": {"state": "removed"}}}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cells"]["c1"] == {"value": None}
