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
from sqlalchemy import Select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.openview.worksheets.access import (
    visible_worksheet_ids,
    visible_worksheet_statement,
)
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow
from app.systems.openview.worksheets.projection import project_rows
from app.systems.openview.worksheets.query import _rows
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
