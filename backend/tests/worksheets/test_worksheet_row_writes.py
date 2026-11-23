"""Routes 10, 12, 13 and 14: row writes with per-cell conflict checks (F4, D14 R2; SH-42).

Every saved cell names the value the person saw (`expected`); the server compares it with
what that person sees now, masked. A cell the person sees as No access cannot be changed.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.users.models import User
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.models import (
    Worksheet,
    WorksheetRow,
    WorksheetRowRevision,
)
from tests.rbac.support import _client
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
    """Student List readable by the owner and the editor only; the structure links to it."""

    found = add_students(integration_db, world, [world.owner, world.editor])
    world.sheet.structure = editable_structure(found)
    integration_db.flush()
    return found


class Rows:
    def __init__(self, application: FastAPI, db: Session, world: SheetWorld) -> None:
        self.application, self.db, self.world = application, db, world
        self.base = f"/api/worksheets/{world.sheet.id}/rows"

    def create(self, person: User, cells: dict[str, Any], **extra: Any) -> Any:
        return _client(self.application, person, self.db).post(
            self.base, json={"cells": cells, **extra}
        )

    def patch(self, person: User, row_id: object, cells: dict[str, Any]) -> Any:
        return _client(self.application, person, self.db).patch(
            f"{self.base}/{row_id}", json={"cells": cells}
        )

    def read(self, person: User, row_id: object) -> Any:
        return _client(self.application, person, self.db).get(f"{self.base}/{row_id}")

    def order(self, person: User) -> list[str]:
        page = _client(self.application, person, self.db).post(f"{self.base}/query", json={})
        return [item["id"] for item in page.json()["items"]]


@pytest.fixture
def rows(application: FastAPI, integration_db: Session, world: SheetWorld,
         students: Students) -> Rows:
    return Rows(application, integration_db, world)


def _code(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]["code"]


def test_a_new_row_stores_every_column_kind_with_its_link_revision_and_counters(
    integration_db: Session, world: SheetWorld, students: Students, rows: Rows,
) -> None:
    db = integration_db
    organization = db.get(WorkspaceProfile, world.sheet.org_id)
    assert organization is not None
    organization.locale = "de-DE"  # O4: "12,5" is twelve and a half
    db.flush()
    created = rows.create(world.owner, {
        "c1": {"record_id": str(students.alice.id)}, "c3": "=1+1", "c4": 7, "c5": "12,5",
        "c6": "Pass", "c7": str(world.viewer.id), "c8": True, "c9": "2026-11-24",
    })
    assert created.status_code == 201, created.text
    row_id = created.json()["id"]
    assert created.headers["Location"] == f"{rows.base}/{row_id}"
    assert created.headers["ETag"] == f'"{row_id}:1"'
    assert created.json()["cells"] == {
        "c1": {"link": {"record_id": str(students.alice.id), "label": "Alice"}},
        "c2": {"value": "Alice"}, "c3": {"value": "=1+1"}, "c4": {"value": 7},
        "c5": {"value": "12.5"}, "c6": {"value": "o1"}, "c7": {"value": str(world.viewer.id)},
        "c8": {"value": True}, "c9": {"value": "2026-11-24"},
    }
    stored = db.get(WorksheetRow, UUID(row_id))
    sheet = db.get(Worksheet, world.sheet.id)
    assert stored is not None and sheet is not None
    db.refresh(sheet)
    assert (sheet.live_row_count, sheet.data_bytes) == (1, stored.data_bytes)
    assert "c1" not in stored.data  # a link lives in worksheet_row_links
    [revision] = db.scalars(select(WorksheetRowRevision).where(
        WorksheetRowRevision.row_id == stored.id
    )).all()
    assert (revision.revision, revision.action, sorted(revision.changed_keys)) == (
        1, "create", ["c1", "c3", "c4", "c5", "c6", "c7", "c8", "c9"],
    )
    assert revision.data["c1"] == {"record_id": str(students.alice.id)}


def test_rows_insert_after_a_row_and_renumber_when_the_gap_is_full(
    integration_db: Session, world: SheetWorld, rows: Rows,
) -> None:
    first = rows.create(world.owner, {"c3": "A"}).json()["id"]
    second = rows.create(world.owner, {"c3": "B"}).json()["id"]
    third = rows.create(world.owner, {"c3": "C"}, after_row_id=first).json()["id"]
    assert rows.order(world.owner) == [first, third, second]
    third_row = integration_db.get(WorksheetRow, UUID(third))
    first_row = integration_db.get(WorksheetRow, UUID(first))
    assert third_row is not None and first_row is not None
    third_row.position = first_row.position + 1  # no room left between first and third
    integration_db.flush()
    fourth = rows.create(world.owner, {"c3": "D"}, after_row_id=first).json()["id"]
    assert rows.order(world.owner) == [first, fourth, third, second]


def test_two_editors_save_different_cells_and_the_second_save_of_one_cell_is_refused(
    world: SheetWorld, rows: Rows,
) -> None:
    row_id = rows.create(world.owner, {"c3": "x", "c4": 1}).json()["id"]
    assert rows.patch(world.owner, row_id, {
        "c3": {"value": "y", "expected": {"value": "x"}},
    }).status_code == 200
    assert rows.patch(world.editor, row_id, {
        "c4": {"value": 2, "expected": {"value": 1}},
    }).status_code == 200
    stale = rows.patch(world.editor, row_id, {
        "c3": {"value": "z", "expected": {"value": "x"}},
        "c8": {"value": True, "expected": {"value": None}},
    })
    assert _code(stale) == (412, "cell_changed")
    detail = stale.json()["detail"]
    assert detail["keys"] == ["c3"]
    assert detail["current"]["cells"]["c3"] == {"value": "y"}
    current = rows.read(world.owner, row_id).json()["cells"]
    assert (current["c3"], current["c4"], current["c8"]) == (
        {"value": "y"}, {"value": 2}, {"value": None},
    )


def test_a_cell_the_editor_cannot_read_cannot_be_changed_whatever_they_guess(
    world: SheetWorld, students: Students, rows: Rows,
) -> None:
    row_id = rows.create(world.owner, {
        "c1": {"record_id": str(students.alice.id)}, "c3": "x",
    }).json()["id"]
    alice = {"link": {"record_id": str(students.alice.id), "label": "Alice"}}
    answers = [
        rows.patch(world.group_member, row_id, {
            "c1": {"value": None, "expected": expected},
        })
        for expected in (alice, {"state": "no_access"}, {"value": None})
    ]
    assert {(answer.status_code, str(answer.json()["detail"])) for answer in answers} == {
        (403, str({"code": "cell_no_access", "message": "This cell cannot be changed"})),
    }
    assert rows.patch(world.group_member, row_id, {
        "c3": {"value": "mine", "expected": {"value": "x"}},
    }).status_code == 200
    assert _code(rows.create(world.group_member, {
        "c1": {"record_id": str(students.alice.id)},
    })) == (403, "cell_no_access")


@pytest.mark.parametrize(
    ("cells", "code"),
    [
        ({"c1": {"record_id": "bob-deleted"}}, "link_target_invalid"),
        ({"c1": {"record_id": "other-module"}}, "link_target_invalid"),
        ({"c2": "Alice"}, "column_read_only"),
        ({"c4": "abc"}, "cell_invalid"),
        ({"c6": "Maybe"}, "cell_invalid"),
        ({"c7": "stranger"}, "cell_invalid"),
        ({"c99": "x"}, "cell_invalid"),
    ],
    ids=["deleted-target", "target-of-another-module", "lookup", "not-a-number",
         "not-an-option", "invisible-person", "unknown-column"],
)
def test_an_invalid_cell_is_refused_and_nothing_is_written(
    integration_db: Session, world: SheetWorld, students: Students, rows: Rows,
    cells: dict[str, Any], code: str,
) -> None:
    db = integration_db
    students.bob.is_deleted, students.bob.deleted_at = True, utc_now()
    other = world.record  # a record of the sheet's own module, not of Student List
    replacements = {
        "bob-deleted": str(students.bob.id), "other-module": str(other.id),
        "stranger": str(uuid7()),
    }
    resolved = {
        key: {"record_id": replacements[value["record_id"]]} if isinstance(value, dict)
        else replacements.get(value, value)
        for key, value in cells.items()
    }
    db.flush()
    assert _code(rows.create(world.owner, resolved)) == (422, code)
    assert rows.order(world.owner) == []


def test_a_row_delete_needs_its_etag_and_updates_the_counters(
    integration_db: Session, world: SheetWorld, rows: Rows,
) -> None:
    row_id = rows.create(world.owner, {"c3": "gone"}).json()["id"]
    client = _client(rows.application, world.owner, integration_db)
    path = f"{rows.base}/{row_id}"
    assert client.delete(path).status_code == 428
    assert client.delete(path, headers={"If-Match": f'"{row_id}:9"'}).status_code == 412
    assert client.delete(path, headers={"If-Match": f'"{row_id}:1"'}).status_code == 204
    assert _code(rows.read(world.owner, row_id)) == (404, "worksheet_row_not_found")
    sheet = integration_db.get(Worksheet, world.sheet.id)
    assert sheet is not None
    integration_db.refresh(sheet)
    assert (sheet.live_row_count, sheet.data_bytes) == (0, 0)
    actions = integration_db.scalars(select(WorksheetRowRevision.action).where(
        WorksheetRowRevision.row_id == UUID(row_id)
    ).order_by(WorksheetRowRevision.revision)).all()
    assert actions == ["create", "delete"]


def test_a_batch_is_one_transaction_against_one_structure_revision(
    integration_db: Session, world: SheetWorld, rows: Rows,
) -> None:
    row_id = rows.create(world.owner, {"c3": "x"}).json()["id"]
    client = _client(rows.application, world.owner, integration_db)
    path = f"{rows.base}/batch"
    creates = [{"cells": {"c3": "one"}}, {"cells": {"c3": "two"}}]
    stale = client.post(path, json={"structure_revision": 99, "creates": creates})
    assert _code(stale) == (409, "structure_changed")
    conflict = client.post(path, json={
        "structure_revision": 1, "creates": creates,
        "updates": [{"row_id": row_id, "cells": {"c3": {"value": "y",
                                                        "expected": {"value": "old"}}}}],
    })
    assert _code(conflict) == (409, "row_changed")
    assert len(rows.order(world.owner)) == 1  # nothing of the refused batch was written
    done = client.post(path, json={
        "structure_revision": 1, "creates": creates,
        "updates": [{"row_id": row_id, "cells": {"c3": {"value": "y",
                                                        "expected": {"value": "x"}}}}],
    })
    assert done.status_code == 200, done.text
    assert [row["cells"]["c3"] for row in done.json()["rows"]] == [
        {"value": "one"}, {"value": "two"}, {"value": "y"},
    ]
    too_many = client.post(path, json={
        "structure_revision": 1, "creates": [{"cells": {}}] * 101,
    })
    assert too_many.status_code == 422


def test_only_owners_and_edit_recipients_write_rows(
    world: SheetWorld, rows: Rows,
) -> None:
    assert _code(rows.create(world.viewer, {"c3": "x"})) == (403, "worksheet_read_only")
    assert _code(rows.create(world.peer, {"c3": "x"})) == (404, "worksheet_not_found")
    assert rows.create(world.editor, {"c3": "x"}).status_code == 201


def test_a_save_drops_the_values_of_removed_columns(
    integration_db: Session, world: SheetWorld, rows: Rows,
) -> None:
    row = WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id, position=1024,
                       data={"c3": "x", "c50": "left over"}, data_bytes=40)
    integration_db.add(row)
    sheet = integration_db.get(Worksheet, world.sheet.id)
    assert sheet is not None
    sheet.live_row_count, sheet.data_bytes = 1, 40
    integration_db.flush()
    assert rows.patch(world.owner, row.id, {
        "c3": {"value": "y", "expected": {"value": "x"}},
    }).status_code == 200
    integration_db.refresh(row)
    assert row.data == {"c3": "y"}
