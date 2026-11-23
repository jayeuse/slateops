"""Computed columns on a real sheet (spec K3-K6, K8, D7.2, D7.3; SH-21-SH-23, SH-25, SH-58).

Columns are saved through route 6 in the editor form (names in braces), rows through
route 10, and values read through route 9 and the export builder: the grid, the sort, the
totals and the export show the same computed value.
"""

import csv
import io
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.openview.worksheets.export import build_export
from tests.rbac.support import _client
from tests.worksheets.support import SheetWorld, Students, add_students, sheet_world

pytestmark = pytest.mark.integration
NAMES = ["Student", "Score", "Quiz 1", "Quiz 2", "Total", "Stats", "Ratio", "Ratio plus",
         "Most", "Least", "Sum"]


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _columns(students: Students) -> list[dict[str, Any]]:
    def computed(key: str, name: str, expression: str) -> dict[str, Any]:
        return {"key": key, "name": name, "type": "computed",
                "computed": {"expression": expression, "places": 2}}

    return [
        {"key": "c1", "name": "Student", "type": "link",
         "link": {"moduleId": str(students.module.id)}},
        {"key": "c2", "name": "Score", "type": "lookup",
         "lookup": {"linkKey": "c1", "fieldId": str(students.score.id)}},
        {"key": "c3", "name": "Quiz 1", "type": "decimal", "decimal": {"places": 2}},
        {"key": "c4", "name": "Quiz 2", "type": "int"},
        computed("c5", "Total", "{Quiz 1} + {Quiz 2}"),
        computed("c6", "Stats", "ROUND(AVERAGE({Quiz 1}, {Quiz 2}, {Score}), 1)"),
        computed("c7", "Ratio", "{Quiz 1} / {Quiz 2}"),
        computed("c8", "Ratio plus", "{Ratio} + 1"),
        computed("c9", "Most", "MAX({Quiz 1}, {Quiz 2})"),
        computed("c10", "Least", "MIN({Quiz 1}, {Quiz 2})"),
        computed("c11", "Sum", "SUM({Quiz 1}, {Quiz 2})"),
    ]


class Sheet:
    def __init__(self, application: FastAPI, db: Session, world: SheetWorld,
                 students: Students) -> None:
        self.application, self.db, self.world, self.students = application, db, world, students
        self.base = f"/api/worksheets/{world.sheet.id}"
        self.revision = 1

    def save(self, columns: list[dict[str, Any]], **extra: Any) -> Any:
        response = _client(self.application, self.world.owner, self.db).put(
            f"{self.base}/structure",
            json={"columns": columns, "groups": [], "totals": {}, **extra},
            headers={"If-Match": f'"{self.world.sheet.id}:{self.revision}"'},
        )
        if response.status_code == 200:
            self.revision += 1
        return response

    def add(self, cells: dict[str, Any]) -> str:
        created = _client(self.application, self.world.owner, self.db).post(
            f"{self.base}/rows", json={"cells": cells},
        )
        assert created.status_code == 201, created.text
        return str(created.json()["id"])

    def query(self, person: User, **request: Any) -> Any:
        response = _client(self.application, person, self.db).post(
            f"{self.base}/rows/query", json=request,
        )
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def sheet(application: FastAPI, integration_db: Session) -> Sheet:
    """Four rows: a linked student, a division by zero, a blank operand, all blank."""

    world = sheet_world(integration_db)
    students = add_students(integration_db, world, [world.owner, world.editor])
    found = Sheet(application, integration_db, world, students)
    saved = found.save(
        _columns(students),
        groups=[{"name": "Period 1", "keys": ["c3"]}, {"name": "Period 2", "keys": ["c4"]}],
        totals={"c5": "sum", "c7": "sum", "c6": "count"},
    )
    assert saved.status_code == 200, saved.text
    found.add({"c1": {"record_id": str(students.alice.id)}, "c3": "12.5", "c4": 10})
    found.add({"c3": "4", "c4": 0})
    found.add({"c4": 3})
    found.add({})
    return found


def _cells(page: dict[str, Any], key: str) -> list[Any]:
    return [row["cells"][key] for row in page["items"]]


DIVIDED = {"value": None, "error": "division_by_zero"}
BLANK = {"value": None}


def test_route_six_stores_keys_and_the_grid_shows_each_value(sheet: Sheet) -> None:
    """SH-21, SH-23 (blanks and the division mark), SH-25 (columns of two groups)."""

    detail = _client(sheet.application, sheet.world.owner, sheet.db).get(sheet.base).json()
    expressions = {column["key"]: column["computed"]["expression"]
                   for column in detail["structure"]["columns"] if column["type"] == "computed"}
    assert expressions["c5"] == "{c3} + {c4}"
    assert expressions["c6"] == "ROUND(AVERAGE({c3}, {c4}, {c2}), 1)"
    page = sheet.query(sheet.world.owner)
    assert _cells(page, "c5") == [{"value": "22.5"}, {"value": "4"}, BLANK, BLANK]
    assert _cells(page, "c6") == [{"value": "37.5"}, {"value": "2"}, {"value": "3"}, BLANK]
    assert _cells(page, "c7") == [{"value": "1.25"}, DIVIDED, BLANK, BLANK]
    assert _cells(page, "c8") == [{"value": "2.25"}, DIVIDED, BLANK, BLANK]
    assert _cells(page, "c9") == [{"value": "12.5"}, {"value": "4"}, {"value": "3"}, BLANK]
    assert _cells(page, "c10") == [{"value": "10"}, {"value": "0"}, {"value": "3"}, BLANK]
    assert _cells(page, "c11") == [{"value": "22.5"}, {"value": "4"}, {"value": "3"}, BLANK]


def test_the_sort_the_totals_and_the_export_show_the_grid_value(sheet: Sheet) -> None:
    """SH-23: one compiled value for every read."""

    owner = sheet.world.owner
    by_total = sheet.query(owner, sort={"key": "c5", "order": "desc"})
    assert _cells(by_total, "c5") == [{"value": "22.5"}, {"value": "4"}, BLANK, BLANK]
    assert by_total["totals"] == {
        "c5": {"fn": "sum", "value": "26.5", "hidden_count": 0},
        "c7": {"fn": "sum", "value": "1.25", "hidden_count": 0},
        "c6": {"fn": "count", "value": 3, "hidden_count": 0},
    }
    assert _cells(sheet.query(owner, search="37.5"), "c6") == [{"value": "37.5"}]
    exported = build_export(sheet.db, reader_id=owner.id, worksheet_id=sheet.world.sheet.id,
                            format="csv")
    rows = list(csv.reader(io.StringIO(exported.content.decode())))
    assert rows[0] == NAMES
    assert [row[4:8] for row in rows[1:]] == [
        ["22.5", "37.5", "1.25", "2.25"],
        ["4", "2", "Division by zero", "Division by zero"],
        ["", "3", "", ""],
        ["", "", "", ""],
    ]


def test_a_reader_without_the_lookup_module_gets_no_access_in_computed_cells(
    sheet: Sheet,
) -> None:
    """SH-58: masked like the lookup it reads, in the grid, sort, search, totals, export."""

    viewer = sheet.world.viewer
    page = sheet.query(viewer)
    assert _cells(page, "c6") == [{"state": "no_access"}] * 4
    assert _cells(page, "c5")[0] == {"value": "22.5"}  # Total reads no lookup
    assert page["totals"]["c6"] == {"fn": "count", "value": 0, "hidden_count": 4}
    sorted_page = sheet.query(viewer, sort={"key": "c6", "order": "desc"})
    assert [row["id"] for row in sorted_page["items"]] == [row["id"] for row in page["items"]]
    assert sheet.query(viewer, search="37.5")["items"] == []
    exported = build_export(sheet.db, reader_id=viewer.id, worksheet_id=sheet.world.sheet.id,
                            format="csv")
    rows = list(csv.reader(io.StringIO(exported.content.decode())))
    assert [row[5] for row in rows[1:]] == ["No access"] * 4
    assert b"37.5" not in exported.content


def test_a_renamed_column_keeps_every_expression_working(sheet: Sheet) -> None:
    """SH-22: the expressions store keys; the stored text is saved back unchanged."""

    detail = _client(sheet.application, sheet.world.owner, sheet.db).get(sheet.base).json()
    columns = detail["structure"]["columns"]
    columns[2]["name"] = "Quiz A"
    saved = sheet.save(columns)
    assert saved.status_code == 200, saved.text
    stored = {column["key"]: column for column in saved.json()["structure"]["columns"]}
    assert stored["c3"]["name"] == "Quiz A"
    assert stored["c5"]["computed"]["expression"] == "{c3} + {c4}"
    assert _cells(sheet.query(sheet.world.owner), "c5")[0] == {"value": "22.5"}


@pytest.mark.parametrize(("expression", "reason", "named"), [
    ("{Ratio plus} + 1", "loop", ["Ratio", "Ratio plus"]),
    ("B2 * 2", "cell_reference", ["B2"]),
    ("{Nobody} + 1", "unknown_column", ["Nobody"]),
    ("{Student} + 1", "not_numeric", ["Student"]),
])
def test_route_six_refuses_an_expression_with_its_reason_and_keeps_the_sheet(
    sheet: Sheet, expression: str, reason: str, named: list[str],
) -> None:
    """SH-21: the reason names the problem; nothing is saved."""

    columns = _columns(sheet.students)
    columns[6]["computed"]["expression"] = expression  # Ratio
    refused = sheet.save(columns)
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert (detail["code"], detail["reason"], detail["key"]) == (
        "expression_invalid", reason, "c7",
    )
    for name in named:
        assert name in detail["message"]
    assert sheet.revision == 2
