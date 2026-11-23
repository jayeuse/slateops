"""Route 6: saving a sheet's columns (K1, K2, F4; SH-20)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import WorksheetRow, WorksheetRowLink
from tests.rbac.support import _client, add_module
from tests.worksheets.support import (
    SheetWorld,
    Students,
    add_students,
    editable_structure,
    sheet_world,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def world(integration_db: Session) -> SheetWorld:
    return sheet_world(integration_db)


@pytest.fixture
def students(integration_db: Session, world: SheetWorld) -> Students:
    return add_students(integration_db, world, [world.owner, world.editor])


def _save(application: FastAPI, db: Session, person: User, world: SheetWorld,
          structure: dict[str, Any], revision: int | None = 1) -> Any:
    client: TestClient = _client(application, person, db)
    headers = {} if revision is None else {"If-Match": f'"{world.sheet.id}:{revision}"'}
    body = {key: structure[key] for key in ("columns", "groups", "totals")}
    return client.put(f"/api/worksheets/{world.sheet.id}/structure", json=body, headers=headers)


def _code(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]


def test_the_owner_saves_every_column_kind_and_the_revision_moves(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    structure = editable_structure(students)
    structure["columns"][4]["decimal"]["currency"] = True  # K2: a display option
    saved = _save(application, integration_db, world.owner, world, structure)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["revision"], saved.headers["ETag"]) == (2, f'"{world.sheet.id}:2"')
    assert [column["type"] for column in body["structure"]["columns"]] == [
        "link", "lookup", "text", "int", "decimal", "select", "user", "boolean", "date",
    ]
    assert body["structure"]["columns"][4]["decimal"] == {"places": 2, "currency": True}
    assert body["structure"]["nextColumnSeq"] == 10


def test_an_edit_recipient_saves_and_others_are_refused_or_not_found(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    db = integration_db
    structure = editable_structure(students)
    assert _save(application, db, world.editor, world, structure).status_code == 200
    assert _code(_save(application, db, world.viewer, world, structure, 2)) == (
        403, "worksheet_read_only"
    )
    assert _code(_save(application, db, world.peer, world, structure, 2)) == (
        404, "worksheet_not_found"
    )
    assert _save(application, db, world.owner, world, structure, None).status_code == 428
    assert _code(_save(application, db, world.owner, world, structure, 1)) == (
        412, "worksheet_changed"
    )


def test_a_relationship_column_is_refused(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    structure = editable_structure(students)
    structure["columns"].append({"key": "c10", "name": "Rel", "type": "relationship"})
    assert _save(application, integration_db, world.owner, world, structure).status_code == 422


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("unreadable link module", "link_module_invalid"),
        ("lookup of another module", "lookup_field_invalid"),
        ("non-adjacent group", "structure_invalid"),
        ("From another sheet reading itself", "sheet_lookup_invalid"),
    ],
)
def test_a_structure_that_breaks_a_column_rule_is_refused(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
    change: str, code: str,
) -> None:
    db = integration_db
    structure = editable_structure(students)
    columns = structure["columns"]
    if change == "unreadable link module":
        hidden = add_module(db, world.department, "Hidden")
        columns[0]["link"]["moduleId"] = str(hidden.id)
    elif change == "lookup of another module":
        other = add_students(db, world, [world.owner], "Staff List")
        columns[1]["lookup"]["fieldId"] = str(other.name.id)
    elif change == "non-adjacent group":
        structure["groups"] = [{"name": "Gap", "keys": ["c3", "c5"]}]
    else:
        columns.append({"key": "c10", "name": "Elsewhere", "type": "sheet_lookup",
                        "sheet_lookup": {"sourceWorksheetId": str(world.sheet.id),
                                         "sourceColumnKey": "c3", "linkKey": "c1",
                                         "sourceLinkKey": "c1"}})
    assert _code(_save(application, db, world.owner, world, structure)) == (422, code)


def test_a_key_below_the_next_sequence_cannot_come_back(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    db = integration_db
    structure = editable_structure(students)
    assert _save(application, db, world.owner, world, structure).status_code == 200
    without = {**structure, "columns": structure["columns"][:-1]}  # c9 removed
    assert _save(application, db, world.owner, world, without, 2).status_code == 200
    again = {**structure}  # c9 comes back
    assert _code(_save(application, db, world.owner, world, again, 3)) == (
        422, "column_key_reused"
    )


def test_a_type_change_on_a_column_with_values_is_refused(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    db = integration_db
    structure = editable_structure(students)
    assert _save(application, db, world.owner, world, structure).status_code == 200
    db.add(WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id,
                        position=1024, data={"c3": "kept"}, data_bytes=12))
    db.flush()
    changed = editable_structure(students)
    changed["columns"][2] = {"key": "c3", "name": "Note", "type": "int"}
    assert _code(_save(application, db, world.owner, world, changed, 2)) == (
        409, "column_has_values"
    )
    empty = editable_structure(students)
    empty["columns"][3] = {"key": "c4", "name": "Points", "type": "number"}
    assert _save(application, db, world.owner, world, empty, 2).status_code == 200


def _link_row(db: Session, world: SheetWorld, target: object) -> WorksheetRowLink:
    row = WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id,
                       position=1024, data={}, data_bytes=2)
    db.add(row)
    db.flush()
    link = WorksheetRowLink(org_id=row.org_id, worksheet_id=row.worksheet_id, row_id=row.id,
                            column_key="c1", target_record_id=target)
    db.add(link)
    db.flush()
    return link


def test_a_link_column_with_links_keeps_its_module(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    db = integration_db
    structure = editable_structure(students)
    assert _save(application, db, world.owner, world, structure).status_code == 200
    _link_row(db, world, students.alice.id)
    staff = add_students(db, world, [world.owner], "Staff List")
    moved = editable_structure(students)
    moved["columns"][0]["link"]["moduleId"] = str(staff.module.id)
    moved["columns"][1]["lookup"]["fieldId"] = str(staff.name.id)
    assert _code(_save(application, db, world.owner, world, moved, 2)) == (
        409, "column_has_values"
    )


def test_a_removed_link_column_takes_its_links_along(
    application: FastAPI, integration_db: Session, world: SheetWorld, students: Students,
) -> None:
    db = integration_db
    structure = editable_structure(students)
    assert _save(application, db, world.owner, world, structure).status_code == 200
    link = _link_row(db, world, students.alice.id)
    without = {**structure, "columns": structure["columns"][2:]}  # the link and its lookup
    assert _save(application, db, world.owner, world, without, 2).status_code == 200
    db.refresh(link)
    assert link.is_deleted is True


def test_a_lookup_through_a_module_the_saver_cannot_read_is_refused(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    private = add_students(db, world, [world.owner], "Private List")
    structure = editable_structure(private)
    structure["columns"] = structure["columns"][:1] + structure["columns"][2:]  # no lookup
    assert _save(application, db, world.owner, world, structure).status_code == 200
    lookup = {"key": "c10", "name": "Name", "type": "lookup",
              "lookup": {"linkKey": "c1", "fieldId": str(private.name.id)}}
    added = {**structure, "columns": [*structure["columns"], lookup]}
    assert _code(_save(application, db, world.editor, world, added, 2)) == (
        422, "lookup_field_invalid"
    )
