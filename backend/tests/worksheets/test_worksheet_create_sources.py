"""Route 3 sources: New sheet from this structure, Make a copy, template import.

D9.5, D9.2; L6, X6, X7; SH-17, SH-33, SH-34, SH-70 (template import). A copy or structure
gets new column keys, never the source's shares; a template creates nothing when it is
refused.
"""

import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.access.users.models import User
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.models import (
    Worksheet,
    WorksheetRow,
    WorksheetRowLink,
    WorksheetRowRevision,
    WorksheetShare,
)
from tests.conftest import membership_of
from tests.rbac.support import _client, add_module
from tests.worksheets.support import SheetWorld, Students, add_students, sheet_world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


class World:
    """The world's sheet with keys c1, c3, c5 (c2 and c4 were removed), rows and links."""

    def __init__(self, application: FastAPI, db: Session) -> None:
        self.application, self.db = application, db
        self.world: SheetWorld = sheet_world(db)
        world = self.world
        self.students: Students = add_students(db, world, [world.owner, world.editor,
                                                            world.peer, world.viewer])
        world.sheet.structure = {
            "structureVersion": 1, "nextColumnSeq": 8,
            "columns": [
                {"key": "c1", "name": "Student", "type": "link",
                 "link": {"moduleId": str(self.students.module.id)}},
                {"key": "c3", "name": "Score", "type": "lookup",
                 "lookup": {"linkKey": "c1", "fieldId": str(self.students.score.id)}},
                {"key": "c5", "name": "Quiz", "type": "int"},
                {"key": "c7", "name": "Total", "type": "computed",
                 "computed": {"expression": "{c3} + {c5}"}},
            ],
            "groups": [{"name": "Marks", "keys": ["c5", "c7"]}],
            "totals": {"c7": "average", "c1": "count"},
        }
        db.flush()
        self.rows = []
        for position, (data, target) in enumerate([
            ({"c5": 7, "c2": "stale"}, self.students.alice),
            ({"c1": {"unlinked": "Carol"}, "c5": 3}, None),
        ], start=1):
            row = WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id,
                               position=position * 1024, data=data, data_bytes=40)
            db.add(row)
            db.flush()
            if target is not None:
                db.add(WorksheetRowLink(org_id=row.org_id, worksheet_id=row.worksheet_id,
                                        row_id=row.id, column_key="c1",
                                        target_record_id=target.id))
            self.rows.append(row)
        world.sheet.live_row_count = 2
        db.flush()

    def create(self, person: User, source: dict[str, Any], **anchor: Any) -> Any:
        target = anchor or {"record_id": str(self.world.record.id)}
        return _client(self.application, person, self.db).post(
            "/api/worksheets", json={**target, "title": "Second", "source": source},
        )

    def sheets(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Worksheet)) or 0)


@pytest.fixture
def world(application: FastAPI, integration_db: Session) -> World:
    return World(application, integration_db)


EXPECTED_COLUMNS = [
    {"key": "c1", "name": "Student", "type": "link"},
    {"key": "c2", "name": "Score", "type": "lookup"},
    {"key": "c3", "name": "Quiz", "type": "int"},
    {"key": "c4", "name": "Total", "type": "computed"},
]


def _shape(structure: dict[str, Any]) -> list[dict[str, Any]]:
    return [{key: column[key] for key in ("key", "name", "type")}
            for column in structure["columns"]]


def test_new_sheet_from_this_structure_has_new_keys_and_no_rows_or_shares(
    world: World,
) -> None:
    """SH-34, X7: a View recipient makes a structure copy on a module they can create on."""

    viewer = world.world.viewer
    created = world.create(
        viewer, {"kind": "structure", "worksheet_id": str(world.world.sheet.id)},
        module_id=str(world.world.module.id),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    structure = body["structure"]
    assert _shape(structure) == EXPECTED_COLUMNS
    assert structure["columns"][1]["lookup"]["linkKey"] == "c1"
    assert structure["columns"][3]["computed"]["expression"] == "{c2} + {c3}"
    assert structure["groups"] == [{"name": "Marks", "keys": ["c3", "c4"]}]
    assert structure["totals"] == {"c4": "average", "c1": "count"}
    assert structure["nextColumnSeq"] == 5
    assert (body["owner"]["id"], body["state"], body["live_row_count"]) == (
        str(viewer.id), "private", 0,
    )
    assert world.db.scalar(select(func.count()).select_from(WorksheetShare).where(
        WorksheetShare.worksheet_id == body["id"])) == 0


def test_a_hidden_source_answers_like_a_missing_one(world: World) -> None:
    for source_id in (world.world.sheet.id, uuid7()):
        for kind in ("structure", "copy"):
            refused = world.create(world.world.peer,
                                   {"kind": kind, "worksheet_id": str(source_id)})
            assert (refused.status_code, refused.json()["detail"]["code"]) == (
                404, "worksheet_not_found",
            )


def test_the_owner_makes_a_copy_with_rows_links_and_one_create_revision_each(
    world: World,
) -> None:
    """L6: same columns, rows, links and unlinked text; no shares, no other history."""

    created = world.create(world.world.owner,
                           {"kind": "copy", "worksheet_id": str(world.world.sheet.id)})
    assert created.status_code == 201, created.text
    copy_id = created.json()["id"]
    assert _shape(created.json()["structure"]) == EXPECTED_COLUMNS
    assert created.json()["live_row_count"] == 2
    rows = _client(world.application, world.world.owner, world.db).post(
        f"/api/worksheets/{copy_id}/rows/query", json={},
    ).json()["items"]
    alice = world.students.alice
    assert [row["cells"]["c1"] for row in rows] == [
        {"link": {"record_id": str(alice.id), "label": "Alice"}}, {"unlinked": "Carol"},
    ]
    assert [row["cells"]["c3"] for row in rows] == [{"value": 7}, {"value": 3}]
    assert [row["cells"]["c4"] for row in rows] == [{"value": "97"}, {"value": None}]
    stored = world.db.scalars(select(WorksheetRow).where(
        WorksheetRow.worksheet_id == copy_id)).all()
    assert all("c2" not in row.data for row in stored)  # the stale key is not copied
    revisions = world.db.scalars(select(WorksheetRowRevision).where(
        WorksheetRowRevision.worksheet_id == copy_id)).all()
    assert sorted((item.revision, item.action) for item in revisions) == [(1, "create")] * 2
    assert world.db.scalar(select(func.count()).select_from(WorksheetShare).where(
        WorksheetShare.worksheet_id == copy_id)) == 0


def test_a_reader_of_an_open_sheet_copies_it_and_others_cannot(world: World) -> None:
    """SH-17: Decision 3a. A recipient of a private sheet and a guest cannot copy."""

    source = {"kind": "copy", "worksheet_id": str(world.world.sheet.id)}
    editor = world.create(world.world.editor, source)
    assert (editor.status_code, editor.json()["detail"]["code"]) == (
        403, "worksheet_copy_forbidden",
    )
    membership_of(world.db, world.world.owner.id).worksheets_released_at = (
        world.world.sheet.created_at + timedelta(seconds=1)
    )
    world.db.flush()
    copied = world.create(world.world.peer, source)
    assert copied.status_code == 201, copied.text
    assert copied.json()["owner"]["id"] == str(world.world.peer.id)
    assert world.create(world.world.guest, source).status_code == 403
    elsewhere = world.create(world.world.peer, source, module_id=str(world.world.module.id))
    assert (elsewhere.status_code, elsewhere.json()["detail"]["code"]) == (
        422, "copy_anchor_mismatch",
    )


def _template(students: Students, **changes: Any) -> dict[str, Any]:
    template: dict[str, Any] = {
        "kind": "slateops-worksheet-template", "schemaVersion": 1, "title": "Class",
        "columns": [
            {"key": "c1", "name": "Student", "type": "link",
             "link": {"moduleName": "Student List", "departmentName": "Anything"}},
            {"key": "c2", "name": "Points", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldName": "Score"}},
            {"key": "c3", "name": "Quiz 1", "type": "decimal",
             "decimal": {"places": 2, "currency": False}},
            {"key": "c4", "name": "Quiz 2", "type": "int"},
            {"key": "c5", "name": "Total", "type": "computed",
             "computed": {"expression": "SUM({c3}, {c4}) + {c2}"}},
            {"key": "c6", "name": "Teacher", "type": "link",
             "link": {"moduleName": "Staff", "departmentName": "Anything"}},
            {"key": "c7", "name": "Teacher score", "type": "lookup",
             "lookup": {"linkKey": "c6", "fieldName": "Score"}},
            {"key": "c8", "name": "Missing", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldName": "Nowhere"}},
        ],
        "groups": [{"name": "Quizzes", "keys": ["c3", "c4"]}],
        "totals": {"c5": "average", "c8": "sum"},
    }
    template.update(changes)
    return template


def test_a_template_maps_its_link_columns_and_turns_the_rest_into_text(world: World) -> None:
    """SH-33, X6: computed text arrives in stored form, here in a comma-decimal org."""

    world.db.get(WorkspaceProfile, world.world.sheet.org_id).locale = "de-DE"
    world.db.flush()
    created = world.create(world.world.owner, {
        "kind": "template", "template": _template(world.students),
        "module_mapping": {"c1": str(world.students.module.id), "c6": None},
    })
    assert created.status_code == 201, created.text
    structure = created.json()["structure"]
    assert [(column["key"], column["type"]) for column in structure["columns"]] == [
        ("c1", "link"), ("c2", "lookup"), ("c3", "decimal"), ("c4", "int"),
        ("c5", "computed"), ("c6", "text"), ("c7", "text"), ("c8", "text"),
    ]
    assert structure["columns"][0]["link"]["moduleId"] == str(world.students.module.id)
    assert structure["columns"][1]["lookup"]["fieldId"] == str(world.students.score.id)
    assert structure["columns"][4]["computed"]["expression"] == "SUM({c3}, {c4}) + {c2}"
    assert structure["totals"] == {"c5": "average"}
    assert created.json()["live_row_count"] == 0


@pytest.mark.parametrize(("change", "status", "code"), [
    ("version 2", 422, "template_unsupported_version"),
    ("From another sheet column", 422, "template_sheet_lookup"),
    ("unreadable mapped module", 404, "module_not_found"),
    ("missing mapped module", 404, "module_not_found"),
])
def test_a_template_that_is_refused_creates_nothing(
    world: World, change: str, status: int, code: str,
) -> None:
    template = _template(world.students)
    mapping: dict[str, Any] = {"c1": str(world.students.module.id)}
    if change == "version 2":
        template["schemaVersion"] = 2
    elif change == "From another sheet column":
        template["columns"].append({"key": "c9", "name": "Elsewhere", "type": "sheet_lookup",
                                    "sheet_lookup": {"linkKey": "c1"}})
    elif change == "unreadable mapped module":
        mapping["c1"] = str(add_module(world.db, world.world.department, "Hidden").id)
    else:
        mapping["c1"] = str(uuid7())
    before = world.sheets()
    refused = world.create(world.world.owner, {"kind": "template", "template": template,
                                               "module_mapping": mapping})
    assert refused.status_code == status, refused.text
    detail = refused.json()["detail"]
    found = detail["code"] if isinstance(detail, dict) else detail[0]["type"]
    assert found == code
    assert world.sheets() == before


def test_a_full_sheet_copies_in_one_request(world: World) -> None:
    """D8: a sheet at its 10,000-row limit copies in one request (time reported in TASK-0103)."""

    world.db.connection().execute(WorksheetRow.__table__.insert(), [
        {"id": uuid7(), "org_id": world.world.sheet.org_id,
         "worksheet_id": world.world.sheet.id, "position": (index + 3) * 1024,
         "data": {"c5": index}, "data_bytes": 9} for index in range(9_998)
    ])
    world.world.sheet.live_row_count = 10_000
    world.db.flush()
    started = time.perf_counter()
    created = world.create(world.world.owner,
                           {"kind": "copy", "worksheet_id": str(world.world.sheet.id)})
    elapsed = time.perf_counter() - started
    assert created.status_code == 201, created.text
    assert created.json()["live_row_count"] == 10_000, elapsed
