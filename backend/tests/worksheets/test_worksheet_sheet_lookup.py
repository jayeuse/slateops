"""From another sheet columns (spec K9, D7.3a, D14 S1 and S3; SH-69, SH-70).

A summary sheet takes a column of a class sheet for each linked student: rows match
through the record both link columns point to. The value is computed per viewer and never
stored; the grid, the sort, the totals, the export and computed columns read the same one.
"""

import csv
import io
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.openview.worksheets.export import build_export
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetRowLink
from tests.rbac.support import _client
from tests.worksheets.support import SheetWorld, Students, add_sheet, add_students, sheet_world

pytestmark = pytest.mark.integration
BLANK = {"value": None}
NO_ACCESS = {"state": "no_access"}


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _link(students: Students, key: str = "c1", name: str = "Student") -> dict[str, Any]:
    return {"key": key, "name": name, "type": "link", "link": {"moduleId": str(students.module.id)}}


def _from(key: str, name: str, source: Worksheet, column: str) -> dict[str, Any]:
    return {"key": key, "name": name, "type": "sheet_lookup", "sheet_lookup": {
        "sourceWorksheetId": str(source.id), "sourceColumnKey": column,
        "linkKey": "c1", "sourceLinkKey": "c1"}}


def _row(db: Session, sheet: Worksheet, data: dict[str, Any], target: Any, position: int) -> None:
    row = WorksheetRow(org_id=sheet.org_id, worksheet_id=sheet.id, position=position * 1024,
                       data=data, data_bytes=64)
    db.add(row)
    db.flush()
    if target is not None:
        db.add(WorksheetRowLink(org_id=sheet.org_id, worksheet_id=sheet.id, row_id=row.id,
                                column_key="c1", target_record_id=target.id))
        db.flush()


class Summary:
    """The world's sheet as the summary; Class 1A is the owner's source sheet."""

    def __init__(self, application: FastAPI, db: Session) -> None:
        self.application, self.db = application, db
        self.world: SheetWorld = sheet_world(db)
        world = self.world
        self.students = add_students(db, world, [world.owner, world.editor, world.viewer])
        source = add_sheet(db, world.owner, record=world.record)
        source.title = "Class 1A"
        source.structure = {
            "structureVersion": 1, "nextColumnSeq": 6, "groups": [], "totals": {},
            "columns": [
                _link(self.students),
                {"key": "c2", "name": "Grade", "type": "decimal", "decimal": {"places": 1}},
                {"key": "c3", "name": "Points", "type": "int"},
                {"key": "c4", "name": "Double", "type": "computed",
                 "computed": {"expression": "{c3} * 2"}},
                {"key": "c5", "name": "Note", "type": "text"},
            ],
        }
        db.flush()
        alice, bob = self.students.alice, self.students.bob
        _row(db, source, {"c2": "88.5", "c3": 4, "c5": "=1+1"}, alice, 1)
        _row(db, source, {"c2": "70", "c3": 1}, bob, 2)
        _row(db, source, {"c2": "71", "c3": 2}, bob, 3)  # bob matches twice
        self.source = source
        self.revision = 1

    def save(self, columns: list[dict[str, Any]], person: Any = None, **extra: Any) -> Any:
        response = _client(self.application, person or self.world.owner, self.db).put(
            f"/api/worksheets/{self.world.sheet.id}/structure",
            json={"columns": columns, "groups": [], "totals": {}, **extra},
            headers={"If-Match": f'"{self.world.sheet.id}:{self.revision}"'},
        )
        if response.status_code == 200:
            self.revision += 1
        return response

    def columns(self) -> list[dict[str, Any]]:
        return [
            _link(self.students),
            _from("c2", "Final", self.source, "c2"),
            _from("c3", "Twice", self.source, "c4"),
            {"key": "c4", "name": "Bonus", "type": "computed",
             "computed": {"expression": "{Final} + 1"}},
            _from("c5", "Remark", self.source, "c5"),
        ]

    def query(self, person: Any, **request: Any) -> Any:
        response = _client(self.application, person, self.db).post(
            f"/api/worksheets/{self.world.sheet.id}/rows/query", json=request,
        )
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def summary(application: FastAPI, integration_db: Session) -> Summary:
    found = Summary(application, integration_db)
    saved = found.save(found.columns(), totals={"c2": "sum"})
    assert saved.status_code == 200, saved.text
    sheet = found.world.sheet
    _row(integration_db, sheet, {}, found.students.alice, 1)
    _row(integration_db, sheet, {}, found.students.bob, 2)
    _row(integration_db, sheet, {"c1": {"unlinked": "Carol"}}, None, 3)
    return found


def _cells(page: dict[str, Any], key: str) -> list[Any]:
    return [row["cells"][key] for row in page["items"]]


def test_each_row_takes_the_source_value_of_its_linked_record(summary: Summary) -> None:
    """SH-69: one match shows the value (a computed source too), two show the count."""

    page = summary.query(summary.world.owner)
    twice = {"state": "multiple_matches", "count": 2}
    assert _cells(page, "c2") == [{"value": "88.5"}, twice, BLANK]
    assert _cells(page, "c3") == [{"value": "8"}, twice, BLANK]
    assert _cells(page, "c4") == [{"value": "89.5"}, BLANK, BLANK]  # computed reads it
    assert page["totals"]["c2"] == {"fn": "sum", "value": "88.5", "hidden_count": 0}
    by_final = summary.query(summary.world.owner, sort={"key": "c2", "order": "asc"})
    assert _cells(by_final, "c2")[0] == {"value": "88.5"}
    assert _cells(summary.query(summary.world.owner, search="88.5"), "c2") == [
        {"value": "88.5"},
    ]
    exported = build_export(summary.db, reader_id=summary.world.owner.id,
                            worksheet_id=summary.world.sheet.id, format="csv")
    rows = list(csv.reader(io.StringIO(exported.content.decode())))
    assert [row[1:] for row in rows] == [
        ["Final", "Twice", "Bonus", "Remark"],
        ["88.5", "8", "89.5", "'=1+1"],
        ["2 matches", "2 matches", "", "2 matches"],
        ["", "", "", ""],
    ]


def test_a_viewer_who_cannot_see_the_source_gets_no_access_and_no_source_id(
    summary: Summary,
) -> None:
    """SH-69, SH-70: the column and every computed cell reading it are No access."""

    viewer = summary.world.viewer  # View on the summary, nothing on Class 1A
    page = summary.query(viewer)
    assert _cells(page, "c2") == [NO_ACCESS] * 3
    assert _cells(page, "c4") == [NO_ACCESS] * 3
    assert page["totals"]["c2"] == {"fn": "sum", "value": None, "hidden_count": 3}
    detail = _client(summary.application, viewer, summary.db).get(
        f"/api/worksheets/{summary.world.sheet.id}",
    )
    assert str(summary.source.id) not in detail.text
    exported = build_export(summary.db, reader_id=viewer.id,
                            worksheet_id=summary.world.sheet.id, format="csv")
    assert b"88.5" not in exported.content and b"No access" in exported.content


def test_a_removed_source_column_reads_column_removed(
    integration_db: Session, summary: Summary,
) -> None:
    structure = dict(summary.source.structure)
    structure["columns"] = [c for c in structure["columns"] if c["key"] != "c2"]
    summary.source.structure = structure
    integration_db.flush()
    page = summary.query(summary.world.owner)
    assert _cells(page, "c2") == [{"state": "column_removed"}] * 3
    assert _cells(page, "c3")[0] == {"value": "8"}


def _without_request_id(response: Any) -> Any:
    body = response.json()
    body.pop("request_id", None)
    return response.status_code, body


def test_a_hidden_source_and_a_missing_source_are_refused_alike(
    application: FastAPI, integration_db: Session,
) -> None:
    """D14 S1: the answer never tells whether a sheet the saver cannot see exists."""

    found = Summary(application, integration_db)
    hidden = add_sheet(integration_db, found.world.editor, record=found.world.record)
    hidden.structure = dict(found.source.structure)
    integration_db.flush()
    refusals = []
    for source_id in (hidden.id, uuid7()):
        column = _from("c2", "Final", found.source, "c2")
        column["sheet_lookup"]["sourceWorksheetId"] = str(source_id)
        refusals.append(_without_request_id(found.save([_link(found.students), column])))
    assert refusals[0] == refusals[1]
    assert refusals[0][0] == 422
    assert refusals[0][1]["detail"]["code"] == "sheet_lookup_invalid"


@pytest.mark.parametrize(("change", "message"), [
    ("unknown source column", "Final"),
    ("source link column on another module", "Final"),
])
def test_a_source_column_or_link_that_does_not_fit_is_refused(
    application: FastAPI, integration_db: Session, change: str, message: str,
) -> None:
    found = Summary(application, integration_db)
    column = _from("c2", "Final", found.source, "c2")
    if change == "unknown source column":
        column["sheet_lookup"]["sourceColumnKey"] = "c9"
    else:
        column["sheet_lookup"]["sourceLinkKey"] = "c2"  # Grade is not a link column
    refused = found.save([_link(found.students), column])
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "sheet_lookup_invalid"
    assert message in refused.json()["detail"]["message"]


def test_a_loop_through_another_sheet_is_refused(
    integration_db: Session, summary: Summary,
) -> None:
    """D7.4: Class 1A reads the summary's new column, which reads Class 1A back."""

    structure = dict(summary.source.structure)
    structure["columns"] = [*structure["columns"],
                            _from("c6", "Back", summary.world.sheet, "c6")]
    structure["nextColumnSeq"] = 7
    summary.source.structure = structure
    integration_db.flush()
    refused = summary.save([*summary.columns(), _from("c6", "Again", summary.source, "c6")])
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert (detail["code"], detail["reason"]) == ("expression_invalid", "loop")
    assert "Again" in detail["message"]


def test_the_expanded_budget_counts_the_steps_through_another_sheet(
    integration_db: Session, summary: Summary,
) -> None:
    """D14 S3: a source column that expands to 1,999 parts leaves no room for more."""

    structure = dict(summary.source.structure)
    wide = " + ".join(["{c3}"] * 50)  # 99 parts
    structure["columns"] = [*structure["columns"],
                            {"key": "c6", "name": "Wide", "type": "computed",
                             "computed": {"expression": wide}},
                            {"key": "c7", "name": "Wider", "type": "computed",
                             "computed": {"expression": " + ".join(["{c6}"] * 20)}}]
    structure["nextColumnSeq"] = 8
    summary.source.structure = structure
    integration_db.flush()
    columns = [*summary.columns(), _from("c6", "Big", summary.source, "c7")]
    assert summary.save(columns).status_code == 200  # 1 + 1,999 = 2,000 parts
    columns.append({"key": "c7", "name": "Bigger", "type": "computed",
                    "computed": {"expression": "{Big} + 1"}})
    refused = summary.save(columns)
    assert refused.status_code == 422, refused.text
    assert (refused.json()["detail"]["reason"], refused.json()["detail"]["key"]) == (
        "too_large", "c7",
    )
