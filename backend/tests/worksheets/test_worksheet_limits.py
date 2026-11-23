"""A change past a sheet limit is refused with 422 `worksheet_limit` (F6, D8; SH-44)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.systems.openview.worksheets.models import Worksheet
from tests.rbac.support import _client
from tests.worksheets.support import STRUCTURE, SheetWorld, sheet_world

pytestmark = pytest.mark.integration
TEXTS = {
    **STRUCTURE, "nextColumnSeq": 10,
    "columns": [{"key": f"c{index}", "name": f"Text {index}", "type": "text"}
                for index in range(1, 10)],
}


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def world(integration_db: Session) -> SheetWorld:
    found = sheet_world(integration_db)
    found.sheet.structure = dict(TEXTS)
    integration_db.flush()
    return found


def _limit(response: Any) -> tuple[int, str, str, int]:
    detail = response.json()["detail"]
    return response.status_code, detail["code"], detail["limit"], detail["maximum"]


def _create(application: FastAPI, db: Session, world: SheetWorld, cells: dict[str, Any]) -> Any:
    return _client(application, world.owner, db).post(
        f"/api/worksheets/{world.sheet.id}/rows", json={"cells": cells}
    )


def test_a_structure_of_more_than_one_hundred_columns_is_refused(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    columns = [{"key": f"c{index}", "name": f"Column {index}", "type": "text"}
               for index in range(1, 102)]
    refused = _client(application, world.owner, integration_db).put(
        f"/api/worksheets/{world.sheet.id}/structure",
        json={"columns": columns, "groups": [], "totals": {}},
        headers={"If-Match": f'"{world.sheet.id}:1"'},
    )
    assert _limit(refused) == (422, "worksheet_limit", "columns", 100)
    assert "100 columns" in refused.json()["detail"]["message"]


def test_a_text_cell_holds_four_thousand_characters(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    assert _create(application, integration_db, world, {"c1": "x" * 4000}).status_code == 201
    refused = _create(application, integration_db, world, {"c1": "x" * 4001})
    assert _limit(refused) == (422, "worksheet_limit", "cell", 4000)


def test_a_row_holds_thirty_two_kibibytes(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    cells = {f"c{index}": "x" * 4000 for index in range(1, 10)}  # about 36,000 bytes
    assert _limit(_create(application, integration_db, world, cells)) == (
        422, "worksheet_limit", "row_size", 32768,
    )


def test_a_sheet_holds_ten_thousand_rows_and_eight_mebibytes(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    sheet = db.get(Worksheet, world.sheet.id)
    assert sheet is not None
    sheet.live_row_count = 10000
    db.flush()
    assert _limit(_create(application, db, world, {"c1": "x"})) == (
        422, "worksheet_limit", "rows", 10000,
    )
    sheet.live_row_count, sheet.data_bytes = 1, 8388608 - 10
    db.flush()
    assert _limit(_create(application, db, world, {"c1": "x" * 100})) == (
        422, "worksheet_limit", "sheet_size", 8388608,
    )
