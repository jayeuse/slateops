"""The cost of the sheet reads does not grow with sheets or rows the reader never sees.

B2 review N-2: the SSE snapshot (`visible_worksheet_ids`) runs for every subscriber on every
event, and route 9 runs for every grid page. Each test measures the pages one statement
reads (``EXPLAIN (ANALYZE, BUFFERS)``) at a small and at a sample-pack size and asserts the
difference stays far below one page per added row. Buffers count each page visit, warm or
cold, so the measure does not depend on the cache; no test asserts on time.
"""

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Select, event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.openview.worksheets.access import (
    visible_worksheet_ids,
    visible_worksheet_statement,
)
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.projection import project_rows
from app.systems.openview.worksheets.query import _rows, query_rows
from app.systems.openview.worksheets.schemas import SheetRowsQuery
from app.systems.openview.worksheets.structure import WorksheetStructure
from tests.worksheets.support import STRUCTURE, sheet_world

pytestmark = pytest.mark.integration
SMALL, LARGE = 20, 2000


def _pages(db: Session, statement: Select[Any]) -> int:
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    connection = db.connection()
    connection.exec_driver_sql("SET LOCAL max_parallel_workers_per_gather = 0")
    plan = connection.exec_driver_sql(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled), compiled.params
    ).scalar()
    assert isinstance(plan, list)
    top = plan[0]["Plan"]
    return int(top["Shared Hit Blocks"]) + int(top["Shared Read Blocks"])


def _add_sheets(db: Session, org_id: UUID, record_id: UUID, owner_id: UUID, count: int) -> None:
    db.connection().execute(Worksheet.__table__.insert(), [
        {"id": uuid7(), "org_id": org_id, "record_id": record_id, "owner_id": owner_id,
         "title": f"Private {index}", "structure": STRUCTURE}
        for index in range(count)
    ])
    db.connection().execute(text("ANALYZE public.worksheets"))


def test_the_sse_sheet_snapshot_does_not_read_other_peoples_private_sheets(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    world = sheet_world(db)
    org_id = world.sheet.org_id

    def snapshot_pages() -> int:
        return _pages(db, visible_worksheet_statement(db, world.peer, org_id))

    _add_sheets(db, org_id, world.record.id, world.editor.id, SMALL)
    at_small = snapshot_pages()
    _add_sheets(db, org_id, world.record.id, world.editor.id, LARGE - SMALL)
    at_large = snapshot_pages()
    assert visible_worksheet_ids(db, world.peer, org_id) == frozenset()
    assert at_large - at_small < (LARGE - SMALL) // 10, (at_small, at_large)


def test_a_grid_page_does_not_read_the_rows_of_other_sheets(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    world = sheet_world(db)
    other = Worksheet(org_id=world.sheet.org_id, record_id=world.record.id,
                      owner_id=world.owner.id, title="Big", structure=dict(STRUCTURE))
    db.add(other)
    db.flush()

    def add_rows(sheet: Worksheet, count: int, start: int) -> None:
        db.connection().execute(WorksheetRow.__table__.insert(), [
            {"id": uuid7(), "org_id": sheet.org_id, "worksheet_id": sheet.id,
             "position": (start + index) * 1024, "data": {"c1": index}, "data_bytes": 16}
            for index in range(count)
        ])
        db.connection().execute(text("ANALYZE public.worksheet_rows"))

    add_rows(world.sheet, 50, 0)
    projection = project_rows(db, world.owner, WorksheetStructure.model_validate(STRUCTURE))

    def page_pages() -> int:
        statement = _rows(projection, world.sheet)
        return _pages(db, statement.order_by(WorksheetRow.position, WorksheetRow.id).limit(201))

    add_rows(other, SMALL, 0)
    at_small = page_pages()
    add_rows(other, LARGE - SMALL, SMALL)
    at_large = page_pages()
    assert at_large - at_small < (LARGE - SMALL) // 10, (at_small, at_large)


def test_the_sse_snapshot_finds_a_sheet_opened_by_a_release_cutoff(
    integration_owner_db: Session,
) -> None:
    from datetime import timedelta

    from tests.conftest import membership_of

    db = integration_owner_db
    world = sheet_world(db)
    org_id = world.sheet.org_id
    assert world.sheet.id not in visible_worksheet_ids(db, world.peer, org_id)
    membership_of(db, world.owner.id).worksheets_released_at = (
        world.sheet.created_at + timedelta(seconds=1)
    )
    db.flush()
    assert world.sheet.id in visible_worksheet_ids(db, world.peer, org_id)


def _two_link_sheet(db: Session, world: Any) -> tuple[list[Any], list[Any]]:
    """The world's sheet with two link columns, a lookup and three totals (B4 review)."""

    from tests.worksheets.support import add_students

    students = add_students(db, world, [world.owner])
    teachers = add_students(db, world, [world.owner], "Teachers")
    world.sheet.structure = {
        "structureVersion": 1, "nextColumnSeq": 5,
        "columns": [
            {"key": "c1", "name": "Student", "type": "link",
             "link": {"moduleId": str(students.module.id)}},
            {"key": "c2", "name": "Teacher", "type": "link",
             "link": {"moduleId": str(teachers.module.id)}},
            {"key": "c3", "name": "Score", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(students.score.id)}},
            {"key": "c4", "name": "Points", "type": "int"},
        ],
        "groups": [], "totals": {"c1": "count", "c3": "sum", "c4": "sum"},
    }
    db.flush()
    return [students.alice, students.bob], [teachers.alice, teachers.bob]


def _linked_rows(db: Session, sheet: Worksheet, targets: tuple[list[Any], list[Any]],
                 start: int, count: int) -> None:
    rows, links = [], []
    for index in range(start, start + count):
        row_id = uuid7()
        rows.append({"id": row_id, "org_id": sheet.org_id, "worksheet_id": sheet.id,
                     "position": (index + 1) * 1024, "data": {"c4": index}, "data_bytes": 9})
        for key, records in zip(("c1", "c2"), targets, strict=True):
            links.append({"id": uuid7(), "org_id": sheet.org_id, "worksheet_id": sheet.id,
                          "row_id": row_id, "column_key": key,
                          "target_record_id": records[index % len(records)].id})
    db.connection().execute(WorksheetRow.__table__.insert(), rows)
    db.connection().execute(WorksheetRowLink.__table__.insert(), links)
    db.connection().execute(text("ANALYZE public.worksheet_rows"))
    db.connection().execute(text("ANALYZE public.worksheet_row_links"))


def _route_nine_pages(db: Session, user: Any, sheet: Worksheet,
                      request: SheetRowsQuery) -> list[int]:
    """The pages of each statement route 9 runs (count, page, totals), replayed by EXPLAIN."""

    connection = db.connection()
    captured: list[tuple[str, Any]] = []

    def capture(_conn: Any, _cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        if "worksheet_rows" in statement:
            captured.append((statement, parameters))

    event.listen(connection, "before_cursor_execute", capture)
    try:
        query_rows(db, user, sheet, request)
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    connection.exec_driver_sql("SET LOCAL max_parallel_workers_per_gather = 0")
    pages = []
    for statement, parameters in captured:
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
        ).scalar()
        top = plan[0]["Plan"]
        pages.append(int(top["Shared Hit Blocks"]) + int(top["Shared Read Blocks"]))
    return pages


def test_a_full_sheet_with_two_link_columns_reads_a_bounded_number_of_pages(
    integration_owner_db: Session,
) -> None:
    """At 10,000 rows (D8) the grid page does not grow with the rows, and the count, the
    totals and a sort by a link column grow by far less than one page per row: they join
    the links of all rows at once, never a per-row link probe (B4 review, deferred to B9).
    The page itself reads the two links of each of its 201 rows, a constant cost.

    Measured on 2026-11-24 with one sheet in the tables and the owner role (no RLS): about
    0.09 pages per added row for the count, the totals and the link sort, and a constant
    3,625 pages for the page. Rows of other sheets are covered by the test above.
    """

    db = integration_owner_db
    world = sheet_world(db)
    targets = _two_link_sheet(db, world)
    requests = {
        "page": SheetRowsQuery(limit=200),
        "link sort": SheetRowsQuery.model_validate(
            {"limit": 200, "sort": {"key": "c1", "order": "asc"}}
        ),
    }
    _linked_rows(db, world.sheet, targets, 0, 1_000)
    small = {name: _route_nine_pages(db, world.owner, world.sheet, request)
             for name, request in requests.items()}
    _linked_rows(db, world.sheet, targets, 1_000, 9_000)
    large = {name: _route_nine_pages(db, world.owner, world.sheet, request)
             for name, request in requests.items()}
    count, page, totals = (later - earlier for earlier, later
                           in zip(small["page"], large["page"], strict=True))
    _count, sorted_page, _totals = (later - earlier for earlier, later
                                    in zip(small["link sort"], large["link sort"], strict=True))
    assert page < 9_000 // 10, (small, large)
    for grown in (count, totals, sorted_page):
        assert grown < 9_000 // 4, (small, large)
