"""Hostile expressions stop at route 6, cheaply (spec D7.1, D14 S3; SH-72).

A fan-out chain whose expanded size is above the budget is refused at save in under one
second, and 1,000 characters of nested brackets give 422, never a recursion error.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from tests.rbac.support import _client
from tests.worksheets.support import SheetWorld, sheet_world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _save(application: FastAPI, db: Session, world: SheetWorld,
          columns: list[dict[str, Any]]) -> Any:
    return _client(application, world.owner, db).put(
        f"/api/worksheets/{world.sheet.id}/structure",
        json={"columns": columns, "groups": [], "totals": {}},
        headers={"If-Match": f'"{world.sheet.id}:1"'},
    )


def _computed(key: str, name: str, expression: str) -> dict[str, Any]:
    return {"key": key, "name": name, "type": "computed", "computed": {"expression": expression}}


def test_a_fan_out_chain_over_the_budget_is_refused_at_save_within_a_second(
    application: FastAPI, integration_db: Session,
) -> None:
    world = sheet_world(integration_db)
    columns = [{"key": "c1", "name": "Points", "type": "int"},
               _computed("c2", "Step 0", " + ".join(["{Points}"] * 50))]
    columns += [_computed(f"c{3 + index}", f"Step {index + 1}",
                          " + ".join([f"{{Step {index}}}"] * 50)) for index in range(9)]
    started = time.perf_counter()
    refused = _save(application, integration_db, world, columns)
    elapsed = time.perf_counter() - started
    assert refused.status_code == 422, refused.text
    assert (refused.json()["detail"]["code"], refused.json()["detail"]["reason"]) == (
        "expression_invalid", "too_large",
    )
    assert elapsed < 1.0, elapsed


def test_a_thousand_characters_of_nested_brackets_give_422(
    application: FastAPI, integration_db: Session,
) -> None:
    world = sheet_world(integration_db)
    expression = "(" * 499 + "1" + ")" * 499 + " "
    assert len(expression) == 1_000
    refused = _save(application, integration_db, world, [_computed("c1", "Deep", expression)])
    assert refused.status_code == 422, refused.text
    assert (refused.json()["detail"]["code"], refused.json()["detail"]["reason"]) == (
        "expression_invalid", "too_deep",
    )
