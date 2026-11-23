"""Reads of From another sheet and computed columns stay bounded (security review S-11).

Each From another sheet column projects only the source column it reads and the columns
that one needs, inside one budget per read; past the budget a cell reads
``{"value": null, "error": "too_complex"}``. Computed columns read each operand once per
row by column name, so a wide sheet never copies an operand's SQL into every reference.
Small shapes only: at most 4 columns per level and 4 levels.
"""

from typing import Any

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Join, Lateral

from app.systems.access.users.models import User
from app.systems.openview.worksheets import from_sheet
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.projection import project_rows
from app.systems.openview.worksheets.query import projected_rows, query_rows
from app.systems.openview.worksheets.schemas import SheetRowsQuery
from app.systems.openview.worksheets.structure import WorksheetStructure
from tests.worksheets.support import Students, add_sheet, add_students, sheet_world

pytestmark = pytest.mark.integration


def _link(students: Students) -> dict[str, Any]:
    return {"key": "c1", "name": "Student", "type": "link",
            "link": {"moduleId": str(students.module.id)}}


def _level(db: Session, owner: User, students: Students, record: Any, source: Worksheet,
           reads: list[str]) -> Worksheet:
    """A sheet with one From another sheet column per entry of ``reads``, and one row."""

    sheet = add_sheet(db, owner, record=record)
    sheet.structure = {
        "structureVersion": 1, "nextColumnSeq": 2 + len(reads), "groups": [], "totals": {},
        "columns": [_link(students), *[
            {"key": f"c{index}", "name": f"Read {index}", "type": "sheet_lookup",
             "sheet_lookup": {"sourceWorksheetId": str(source.id), "sourceColumnKey": key,
                              "linkKey": "c1", "sourceLinkKey": "c1"}}
            for index, key in enumerate(reads, start=2)]],
    }
    _row(db, sheet, students.alice, {})
    return sheet


def _row(db: Session, sheet: Worksheet, target: Any, data: dict[str, Any]) -> None:
    row = WorksheetRow(org_id=sheet.org_id, worksheet_id=sheet.id, position=1024, data=data,
                       data_bytes=16)
    db.add(row)
    db.flush()
    db.add(WorksheetRowLink(org_id=sheet.org_id, worksheet_id=sheet.id, row_id=row.id,
                            column_key="c1", target_record_id=target.id))
    db.flush()


def _laterals(node: Any) -> list[Lateral]:
    if isinstance(node, Join):
        return _laterals(node.left) + _laterals(node.right)
    return [node] if isinstance(node, Lateral) else []


def _chain(db: Session) -> tuple[User, Worksheet]:
    """T has one value; S reads it 4 times; R reads each S column; Q reads each R column."""

    world = sheet_world(db)
    students = add_students(db, world, [world.owner])
    t = add_sheet(db, world.owner, record=world.record)
    t.structure = {"structureVersion": 1, "nextColumnSeq": 3, "groups": [], "totals": {},
                   "columns": [_link(students), {"key": "c2", "name": "Mark", "type": "int"}]}
    _row(db, t, students.alice, {"c2": 7})
    reads = ["c2", "c3", "c4", "c5"]
    s = _level(db, world.owner, students, world.record, t, ["c2"] * 4)
    r = _level(db, world.owner, students, world.record, s, reads)
    q = _level(db, world.owner, students, world.record, r, reads)
    return world.owner, q


def _page(db: Session, user: User, sheet: Worksheet) -> Select[Any]:
    projection = project_rows(db, user, WorksheetStructure.model_validate(sheet.structure))
    return projected_rows(projection, sheet)


def test_a_chain_of_sheets_projects_only_the_columns_it_reads(
    integration_db: Session,
) -> None:
    """Four columns over three levels: 12 source reads, not 84 whole-sheet projections."""

    user, q = _chain(integration_db)
    sql = str(_page(integration_db, user, q).compile(dialect=postgresql.dialect()))
    assert sql.count(" AS from_sheet_") == 12
    cells = query_rows(integration_db, user, q, SheetRowsQuery()).items[0].cells
    assert [cells[key].model_dump() for key in ("c2", "c3", "c4", "c5")] == [
        {"value": 7}] * 4


def test_reads_past_the_budget_are_too_complex(
    integration_db: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each Q column costs 8 (three source reads: R and S give the column and its link
    column, T the value); a budget of 9 lets the first through and marks the others."""

    monkeypatch.setattr(from_sheet, "READ_BUDGET", 9)
    user, q = _chain(integration_db)
    cells = query_rows(integration_db, user, q, SheetRowsQuery()).items[0].cells
    too_complex = {"value": None, "error": "too_complex"}
    assert [cells[key].model_dump() for key in ("c2", "c3", "c4", "c5")] == [
        {"value": 7}, too_complex, too_complex, too_complex,
    ]


def test_many_references_to_one_lookup_do_not_copy_its_sql(integration_db: Session) -> None:
    """Twenty computed columns, each reading a lookup 50 times (99 parts, inside S3)."""

    world = sheet_world(integration_db)
    students = add_students(integration_db, world, [world.owner])
    keys = [f"c{index}" for index in range(3, 23)]
    world.sheet.structure = {
        "structureVersion": 1, "nextColumnSeq": 23, "groups": [], "totals": {},
        "columns": [_link(students),
                    {"key": "c2", "name": "Score", "type": "lookup",
                     "lookup": {"linkKey": "c1", "fieldId": str(students.score.id)}},
                    *[{"key": key, "name": f"Wide {key}", "type": "computed",
                       "computed": {"expression": " + ".join(["{c2}"] * 50)}}
                      for key in keys]],
    }
    _row(integration_db, world.sheet, students.alice, {})
    compiled = _page(integration_db, world.owner, world.sheet).compile(
        dialect=postgresql.dialect(),
    )
    assert len(compiled.params) < 1_000, len(compiled.params)
    assert len(str(compiled)) < 200_000, len(str(compiled))
    cells = query_rows(integration_db, world.owner, world.sheet, SheetRowsQuery()).items[0]
    assert cells.cells["c22"].model_dump() == {"value": "4500"}  # 50 times Alice's 90


def test_every_computed_subquery_is_fenced(integration_db: Session) -> None:
    """PostgreSQL never pulls a computed column's subquery into the row query (B10)."""

    world = sheet_world(integration_db)
    world.sheet.structure = {
        "structureVersion": 1, "nextColumnSeq": 5, "groups": [], "totals": {},
        "columns": [{"key": "c1", "name": "A", "type": "int"},
                    {"key": "c2", "name": "B", "type": "computed",
                     "computed": {"expression": "{c1} * 2"}},
                    {"key": "c3", "name": "C", "type": "computed",
                     "computed": {"expression": "SUM({c2}, {c1})"}},
                    {"key": "c4", "name": "D", "type": "computed",
                     "computed": {"expression": "{c3} / {c2}"}}],
    }
    projection = project_rows(integration_db, world.owner,
                              WorksheetStructure.model_validate(world.sheet.structure))
    computed = [item for item in _laterals(projection.source)
                if item.name.startswith("computed_")]
    assert len(computed) == 3
    for item in computed:
        sql = str(item.element.compile(dialect=postgresql.dialect()))
        assert "OFFSET" in sql, sql


def test_route_six_refuses_columns_whose_reads_exceed_the_budget(
    integration_db: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-11 item 3: the same count at save; the second column would pass the budget."""

    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.systems.openview.worksheets import sheet_lookup_cost
    from tests.rbac.support import _client

    monkeypatch.setattr(sheet_lookup_cost, "READ_BUDGET", 9)
    user, q = _chain(integration_db)
    r_id = q.structure["columns"][1]["sheet_lookup"]["sourceWorksheetId"]
    columns = [dict(q.structure["columns"][0]), *[
        {"key": key, "name": f"Again {key}", "type": "sheet_lookup",
         "sheet_lookup": {"sourceWorksheetId": r_id, "sourceColumnKey": key,
                          "linkKey": "c1", "sourceLinkKey": "c1"}} for key in ("c2", "c3")]]
    client: TestClient = _client(create_app(), user, integration_db)
    refused = client.put(f"/api/worksheets/{q.id}/structure",
                         json={"columns": columns, "groups": [], "totals": {}},
                         headers={"If-Match": f'"{q.id}:1"'})
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert (detail["code"], detail["reason"], detail["key"]) == (
        "expression_invalid", "too_complex", "c3",
    )
