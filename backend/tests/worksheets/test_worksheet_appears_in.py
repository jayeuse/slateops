"""Route 23, Appears in: the rows that link to a record, in sheets the viewer can see (N5, V7;
SH-28, SH-6, SH-41). Cells are masked for the viewer, with one read budget per request."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.openview.worksheets import from_sheet
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetRowLink
from tests.conftest import membership_of
from tests.rbac.support import _client, add_module
from tests.worksheets.support import SheetWorld, Students, add_sheet, add_students, sheet_world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


class World:
    """Alice is linked from the owner's sheet (shared View with the viewer) twice, and from
    the editor's private sheet once."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.world: SheetWorld = sheet_world(db)
        world = self.world
        self.students: Students = add_students(
            db, world, [world.owner, world.viewer, world.editor, world.peer],
        )
        self.hidden = add_module(db, world.department, "Hidden")
        structure = {
            "structureVersion": 1, "nextColumnSeq": 4, "groups": [], "totals": {},
            "columns": [
                {"key": "c1", "name": "Student", "type": "link",
                 "link": {"moduleId": str(self.students.module.id)}},
                {"key": "c2", "name": "Mark", "type": "int"},
                {"key": "c3", "name": "Mentor", "type": "link",
                 "link": {"moduleId": str(self.hidden.id)}},
            ],
        }
        world.sheet.title = "Class 1A"
        world.sheet.structure = structure
        self.private = add_sheet(db, world.editor, record=world.record)
        self.private.title = "Editor notes"
        self.private.structure = structure
        db.flush()
        self.rows = [
            self.row(world.sheet, 1, {"c2": 90}), self.row(world.sheet, 2, {"c2": 70}),
            self.row(self.private, 1, {"c2": 5}),
        ]

    def row(self, sheet: Worksheet, position: int, data: dict[str, Any]) -> WorksheetRow:
        row = WorksheetRow(org_id=sheet.org_id, worksheet_id=sheet.id, position=position * 1024,
                           data=data, data_bytes=16)
        self.db.add(row)
        self.db.flush()
        self.db.add(WorksheetRowLink(org_id=sheet.org_id, worksheet_id=sheet.id, row_id=row.id,
                                     column_key="c1", target_record_id=self.students.alice.id))
        self.db.flush()
        return row


@pytest.fixture
def found(integration_db: Session) -> World:
    return World(integration_db)


def _appears(application: FastAPI, found: World, person: Any, record: Any = None,
             **params: Any) -> Any:
    record_id = (record or found.students.alice).id
    return _client(application, person, found.db).get(
        f"/api/records/{record_id}/worksheet-rows", params=params,
    )


def test_each_viewer_sees_the_rows_of_the_sheets_they_can_see(
    application: FastAPI, found: World,
) -> None:
    """SH-28, SH-6: the owner and the View recipient see two rows; the peer sees none."""

    world = found.world
    owner = _appears(application, found, world.owner)
    assert owner.status_code == 200, owner.text
    assert owner.headers["cache-control"] == "no-store"
    body = owner.json()
    assert body["pagination"]["total"] == 2
    first = body["items"][0]
    assert {key: first[key] for key in ("worksheet_id", "worksheet_title", "row_id",
                                        "row_number", "column_key", "column_name")} == {
        "worksheet_id": str(world.sheet.id), "worksheet_title": "Class 1A",
        "row_id": str(found.rows[0].id), "row_number": 1, "column_key": "c1",
        "column_name": "Student",
    }
    assert first["owner"]["id"] == str(world.owner.id)
    assert first["columns"] == [{"key": "c1", "name": "Student", "type": "link"},
                                {"key": "c2", "name": "Mark", "type": "int"},
                                {"key": "c3", "name": "Mentor", "type": "link"}]
    assert first["cells"]["c2"] == {"value": 90}
    assert first["cells"]["c3"] == {"state": "no_access"}  # nobody reads Hidden
    assert [item["row_number"] for item in body["items"]] == [1, 2]
    assert _appears(application, found, world.viewer).json()["pagination"]["total"] == 2
    editor = _appears(application, found, world.editor).json()
    assert [item["worksheet_title"] for item in editor["items"]] == [
        "Class 1A", "Class 1A", "Editor notes",
    ]
    assert _appears(application, found, world.peer).json()["items"] == []


def test_a_deleted_sheet_or_row_leaves_appears_in_and_an_open_sheet_joins_it(
    application: FastAPI, found: World,
) -> None:
    """SH-41, F3; L1: the editor's sheet opens to every reader when its owner leaves."""

    db, world = found.db, found.world
    found.rows[1].is_deleted, found.rows[1].deleted_at = True, utc_now()
    world.sheet.is_deleted, world.sheet.deleted_at = True, utc_now()
    db.flush()
    assert _appears(application, found, world.viewer).json()["items"] == []
    membership_of(db, world.editor.id).worksheets_released_at = (
        found.private.created_at + timedelta(seconds=1)
    )
    db.flush()
    peer = _appears(application, found, world.peer).json()
    assert [item["worksheet_title"] for item in peer["items"]] == ["Editor notes"]


def test_an_unreadable_record_answers_like_a_missing_one(
    application: FastAPI, found: World,
) -> None:
    world = found.world
    outsider = _appears(application, found, world.outsider)
    missing = _client(application, world.owner, found.db).get(
        f"/api/records/{world.sheet.id}/worksheet-rows",
    )
    for response in (outsider, missing):
        assert (response.status_code, response.json()["detail"]) == (
            404, {"code": "record_not_found", "message": "Record not found"},
        )


def test_pages_keep_the_exact_total(application: FastAPI, found: World) -> None:
    page = _appears(application, found, found.world.editor, limit=2, offset=2).json()
    assert [item["worksheet_title"] for item in page["items"]] == ["Editor notes"]
    assert (page["pagination"]["total"], page["pagination"]["has_more"]) == (3, False)


def test_one_read_budget_serves_every_sheet_of_the_page(
    application: FastAPI, found: World, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-11 note for B14: the budget is per request, not per row or sheet."""

    db, world = found.db, found.world
    source = add_sheet(db, world.editor, record=world.record)  # the editor sees it
    source.structure = {"structureVersion": 1, "nextColumnSeq": 3, "groups": [], "totals": {},
                        "columns": [dict(world.sheet.structure["columns"][0]),
                                    {"key": "c2", "name": "Grade", "type": "int"}]}
    found.row(source, 1, {"c2": 4})
    reading = {"key": "c4", "name": "Grade", "type": "sheet_lookup", "sheet_lookup": {
        "sourceWorksheetId": str(source.id), "sourceColumnKey": "c2", "linkKey": "c1",
        "sourceLinkKey": "c1"}}
    for sheet in (world.sheet, found.private):
        structure = dict(sheet.structure)
        structure["columns"] = [*structure["columns"], reading]
        structure["nextColumnSeq"] = 5
        sheet.structure = structure
    db.flush()
    monkeypatch.setattr(from_sheet, "READ_BUDGET", 3)  # one sheet's read: 1 + 2 columns
    items = _appears(application, found, world.editor).json()["items"]
    grades = [(item["worksheet_title"], item["cells"]["c4"]) for item in items
              if item["worksheet_id"] != str(source.id)]
    assert grades[0] == ("Class 1A", {"value": 4})
    assert grades[-1] == ("Editor notes", {"value": None, "error": "too_complex"})
