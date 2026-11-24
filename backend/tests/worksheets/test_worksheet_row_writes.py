"""Routes 10, 12, 13 and 14: row writes with per-cell conflict checks (F4, D14 R2; SH-42).

Every saved cell names the value the person saw (`expected`); the server compares it with
what that person sees now, masked. A cell the person sees as No access cannot be changed.
"""

import json
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import event, select
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
    STRUCTURE,
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


NUMBERS = {
    **STRUCTURE, "nextColumnSeq": 4,
    "columns": [
        {"key": "c1", "name": "Amount", "type": "number"},
        {"key": "c2", "name": "Count", "type": "int"},
        {"key": "c3", "name": "Mark", "type": "decimal",
         "decimal": {"places": 2, "currency": False}},
    ],
}
REFUSED = None


@pytest.mark.parametrize(
    ("locale", "text", "stored"),
    [
        ("en-US", "1.5", 1.5), ("en-US", "1234.5", 1234.5),
        ("en-US", "1,5", REFUSED), ("en-US", "1.234,5", REFUSED),
        ("de-DE", "1,5", 1.5), ("de-DE", "1.234,5", 1234.5),
        ("de-DE", "1.5", REFUSED), ("de-DE", "1234.5", REFUSED),
        *((locale, text, REFUSED) for locale in ("en-US", "de-DE")
          for text in ("NaN", "Infinity", "1e5000")),
    ],
)
def test_a_number_typed_as_text_follows_the_locale_strictly_and_stays_finite(
    application: FastAPI, integration_db: Session, locale: str, text: str,
    stored: float | None,
) -> None:
    db = integration_db
    world = sheet_world(db)
    world.sheet.structure = dict(NUMBERS)
    organization = db.get(WorkspaceProfile, world.sheet.org_id)
    assert organization is not None
    organization.locale = locale
    db.flush()
    rows = Rows(application, db, world)
    answer = rows.create(world.owner, {"c1": text})
    if stored is REFUSED:
        assert _code(answer) == (422, "cell_invalid")
    else:
        assert answer.status_code == 201, answer.text
        assert answer.json()["cells"]["c1"] == {"value": stored}


@pytest.mark.parametrize(
    ("cells", "accepted"),
    [
        ({"c2": 9007199254740991}, True),
        ({"c2": 9007199254740992}, False),
        ({"c1": 9007199254740992}, False),
        ({"c1": 10**40}, False),
        ({"c3": "1e5000"}, False),
    ],
    ids=["largest-safe-integer", "integer-past-browser-precision",
         "whole-number-past-browser-precision", "huge-number", "huge-decimal"],
)
def test_numbers_stay_within_what_a_browser_reads_exactly(
    application: FastAPI, integration_db: Session, cells: dict[str, Any], accepted: bool,
) -> None:
    db = integration_db
    world = sheet_world(db)
    world.sheet.structure = dict(NUMBERS)
    db.flush()
    answer = Rows(application, db, world).create(world.owner, cells)
    if accepted:
        assert answer.status_code == 201, answer.text
    else:
        assert _code(answer) == (422, "cell_invalid")


def test_a_batch_reads_its_rows_in_a_fixed_number_of_statements(
    integration_db: Session, world: SheetWorld, rows: Rows,
) -> None:
    db = integration_db
    client = _client(rows.application, world.owner, db)

    def selects_for(count: int) -> int:
        added = [
            WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id,
                         position=(position + 1) * 1024, data={"c3": "x"},
                         data_bytes=10)  # the stored size of {"c3":"x"}
            for position in range(count)
        ]
        db.add_all(added)
        db.flush()
        ids = [row.id for row in added]
        seen: list[str] = []

        def count_select(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                seen.append(statement)

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", count_select)
        try:
            answer = client.post(f"{rows.base}/batch", json={
                "structure_revision": 1,
                "updates": [{"row_id": str(row_id),
                             "cells": {"c3": {"value": "y", "expected": {"value": "x"}}}}
                            for row_id in ids],
            })
        finally:
            event.remove(connection, "before_cursor_execute", count_select)
        assert answer.status_code == 200, answer.text
        return len(seen)

    assert selects_for(100) - selects_for(10) < 10


def test_a_number_too_small_to_keep_is_refused(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    world.sheet.structure = dict(NUMBERS)
    db.flush()
    answer = Rows(application, db, world).create(world.owner, {"c1": "1e-400"})
    assert _code(answer) == (422, "cell_invalid")


def test_a_batch_that_names_one_row_twice_is_refused(
    integration_db: Session, world: SheetWorld, rows: Rows,
) -> None:
    row_id = rows.create(world.owner, {"c3": "x"}).json()["id"]
    change = {"c3": {"value": "y", "expected": {"value": "x"}}}
    answer = _client(rows.application, world.owner, integration_db).post(
        f"{rows.base}/batch",
        json={"structure_revision": 1, "updates": [{"row_id": row_id, "cells": change}] * 2},
    )
    assert answer.status_code == 422
    assert "row_repeated" in answer.text


def test_a_link_target_that_was_not_locked_is_refused(
    world: SheetWorld, students: Students, rows: Rows, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B8 review N-1: a target that turns readable after the pre-lock read is never written."""

    from app.systems.openview.worksheets import row_writes

    monkeypatch.setattr(row_writes, "readable_records", lambda *_args: set())
    created = rows.create(world.owner, {"c1": {"record_id": str(students.alice.id)}})
    assert _code(created) == (422, "link_target_invalid")
    assert rows.order(world.owner) == []


@pytest.mark.parametrize("author_left", [False, True])
def test_a_conflict_names_who_changed_the_cell_when_the_saver_can_see_them(
    integration_db: Session, world: SheetWorld, rows: Rows, author_left: bool,
) -> None:
    """The 412 `changed_by` is the author of the latest change to a conflicting key, or
    null when the person saving cannot see that author (here: a disabled account)."""

    from app.systems.manage.audit.context import set_audit_actor

    db = integration_db
    world.group_member.display_name = "Gina Group"
    set_audit_actor(db, world.owner.id)
    row_id = rows.create(world.owner, {"c3": "x", "c4": 1}).json()["id"]
    set_audit_actor(db, world.group_member.id)
    assert rows.patch(world.group_member, row_id, {
        "c3": {"value": "y", "expected": {"value": "x"}},
    }).status_code == 200
    set_audit_actor(db, world.owner.id)
    assert rows.patch(world.owner, row_id, {
        "c4": {"value": 2, "expected": {"value": 1}},
    }).status_code == 200
    if author_left:
        world.group_member.status = "disabled"
        db.flush()
    set_audit_actor(db, world.editor.id)
    stale = rows.patch(world.editor, row_id, {"c3": {"value": "z", "expected": {"value": "x"}}})
    assert _code(stale) == (412, "cell_changed")
    assert stale.json()["detail"]["changed_by"] == (
        None if author_left else {"id": str(world.group_member.id), "display_name": "Gina Group"}
    )


def _import_structure(students: Students) -> dict[str, Any]:
    structure = editable_structure(students)
    existing: list[Any] = [*structure["columns"]]
    columns = [*existing,
               {"key": "c10", "name": "Amount", "type": "number"},
               {"key": "c11", "name": "Email", "type": "email"},
               {"key": "c12", "name": "Remark", "type": "text"},
               {"key": "c13", "name": "Detail", "type": "text"}]
    return {**structure, "columns": columns, "nextColumnSeq": 14}


@pytest.mark.parametrize(("locale", "key", "text"), [
    ("en-US", "c10", "0,123"),
    ("de-DE", "c10", "0.123"),
    ("en-IN", "c10", "123,456"),
    ("de-CH", "c10", "1'234"),
    ("en-US", "c11", "not an email"),
    ("en-US", "c9", "2026-02-30"),
])
def test_an_import_batch_stores_a_cell_that_fails_its_rule_empty_and_counts_it(
    integration_db: Session, world: SheetWorld, students: Students, rows: Rows,
    locale: str, key: str, text: str,
) -> None:
    """D9.3 step 3, D10 route 14: with `invalid_cells: "empty"` the cell is stored empty and
    counted; the default refuses the batch; history records only the stored cells."""

    db = integration_db
    db.get(WorkspaceProfile, world.sheet.org_id).locale = locale
    world.sheet.structure = _import_structure(students)
    db.flush()
    client = _client(rows.application, world.owner, db)
    path = f"{rows.base}/batch"
    creates = [{"cells": {"c3": "kept", key: text}}, {"cells": {"c3": "second"}}]
    refused = client.post(path, json={"structure_revision": 1, "creates": creates})
    assert (_code(refused), refused.json()["detail"]["key"]) == ((422, "cell_invalid"), key)
    assert text not in refused.text  # the message is fixed text; it never repeats the value
    assert rows.order(world.owner) == []
    done = client.post(path, json={"structure_revision": 1, "creates": creates,
                                   "invalid_cells": "empty"})
    assert done.status_code == 200, done.text
    assert done.json()["emptied"] == 1
    first = done.json()["rows"][0]
    assert (first["cells"]["c3"], first["cells"][key]) == ({"value": "kept"}, {"value": None})
    stored = db.scalars(select(WorksheetRow).where(
        WorksheetRow.id == UUID(first["id"])).execution_options(populate_existing=True)).one()
    assert stored.data == {"c3": "kept"}  # the emptied cell is not stored, as null or text
    history = db.scalars(select(WorksheetRowRevision).where(
        WorksheetRowRevision.row_id == stored.id)).one()
    assert (history.data, history.changed_keys) == ({"c3": "kept"}, ["c3"])
    assert text not in json.dumps(done.json())


def test_empty_mode_still_refuses_links_updates_and_a_changed_structure(
    integration_db: Session, world: SheetWorld, students: Students, rows: Rows,
) -> None:
    """Only a create cell that fails its column's rule is emptied (D10 route 14)."""

    db = integration_db
    client = _client(rows.application, world.owner, db)
    path = f"{rows.base}/batch"
    row_id = rows.create(world.owner, {"c3": "x"}).json()["id"]
    hidden = add_students(db, world, [world.editor], "Hidden list")
    plain = {"structure_revision": 1, "invalid_cells": "empty"}
    link = client.post(path, json={**plain, "creates": [
        {"cells": {"c1": {"record_id": str(hidden.alice.id)}}}]})
    assert _code(link) == (422, "link_target_invalid")
    update = client.post(path, json={**plain, "updates": [
        {"row_id": row_id, "cells": {"c4": {"value": "many", "expected": {"value": None}}}}]})
    assert _code(update) == (422, "cell_invalid")
    stale = client.post(path, json={**plain, "structure_revision": 99,
                                    "creates": [{"cells": {"c4": "many"}}]})
    assert _code(stale) == (409, "structure_changed")
    unknown = client.post(path, json={**plain, "creates": [{"cells": {"c99": "x"}}]})
    assert _code(unknown) == (422, "cell_invalid")
    too_long = "x" * 4_001
    unlinked = client.post(path, json={**plain, "creates": [
        {"cells": {"c1": {"unlinked": too_long}}}]})
    assert (_code(unlinked), unlinked.json()["detail"]["limit"]) == (
        (422, "worksheet_limit"), "cell")
    long_update = client.post(path, json={**plain, "updates": [
        {"row_id": row_id, "cells": {"c3": {"value": too_long, "expected": {"value": "x"}}}}]})
    assert (_code(long_update), long_update.json()["detail"]["limit"]) == (
        (422, "worksheet_limit"), "cell")
    structure = _import_structure(students)
    world.sheet.structure = {**structure, "nextColumnSeq": 15, "columns": [
        *structure["columns"],
        {"key": "c14", "name": "Mentor", "type": "link",
         "link": {"moduleId": str(hidden.module.id)}}]}
    db.flush()
    hidden_link = client.post(path, json={**plain, "creates": [{"cells": {"c14": "x"}}]})
    assert _code(hidden_link) == (403, "cell_no_access")
    wide = "\U0001f600" * 4_000  # 16 KB in each of three text cells: over the 32 KiB row
    request = db.begin_nested()  # the refusal comes after the row is flushed; a request
    size = client.post(path, json={**plain, "creates": [  # session closes unfinished, so
        {"cells": {"c3": wide, "c12": wide, "c13": wide, "c10": "x"}}]})
    request.rollback()  # roll back here as `get_db` discards it
    assert (_code(size), size.json()["detail"]["limit"]) == ((422, "worksheet_limit"),
                                                             "row_size")
    assert len(rows.order(world.owner)) == 1
    # A text over the 4,000-character cell limit is the cell's own problem (D9.3): the
    # default refuses the batch, and import mode stores that cell empty.
    long = {"creates": [{"cells": {"c3": too_long, "c12": "kept"}}]}
    refused = client.post(path, json={"structure_revision": 1, **long})
    assert (_code(refused), refused.json()["detail"]["limit"]) == (
        (422, "worksheet_limit"), "cell")
    assert len(rows.order(world.owner)) == 1
    emptied = client.post(path, json={**plain, **long})
    assert (emptied.status_code, emptied.json()["emptied"]) == (200, 1)
    cells = emptied.json()["rows"][0]["cells"]
    assert (cells["c3"], cells["c12"]) == ({"value": None}, {"value": "kept"})
    assert too_long not in emptied.text
    stored = db.scalars(select(WorksheetRow).where(
        WorksheetRow.id == UUID(emptied.json()["rows"][0]["id"]),
    ).execution_options(populate_existing=True)).one()
    history = db.scalars(select(WorksheetRowRevision).where(
        WorksheetRowRevision.row_id == stored.id)).one()
    assert (stored.data, history.data) == ({"c12": "kept"}, {"c12": "kept"})
    # The length check runs before the email rule, so a long value costs only its length.
    hostile = "a@" + "." * (512 * 1024) + "@"  # under the JSON body cap
    started = time.perf_counter()
    email = client.post(path, json={**plain, "creates": [{"cells": {"c11": hostile}}]})
    assert time.perf_counter() - started < 5
    assert (email.status_code, email.json()["emptied"]) == (200, 1)
    clean = client.post(path, json={"structure_revision": 1,
                                    "creates": [{"cells": {"c4": 3}}]})
    assert (clean.status_code, clean.json()["emptied"]) == (200, 0)


@pytest.mark.parametrize("limit", ["row_size", "sheet_size", "rows", "cell"])
def test_import_mode_empties_only_the_cell_length_limit(
    monkeypatch: pytest.MonkeyPatch, limit: str,
) -> None:
    """Of the sheet limits, only a cell's own length is a cell problem (D9.3)."""

    from app.systems.openview.worksheets import row_writes
    from app.systems.openview.worksheets.cells import worksheet_limit

    def refuse(*_args: Any) -> Any:
        raise worksheet_limit(limit, 1, "A limit")

    monkeypatch.setattr(row_writes, "_convert", refuse)
    context = SimpleNamespace(empty_invalid=True, emptied=0,
                              columns={"c3": SimpleNamespace(type="text")})
    if limit == "cell":
        assert row_writes._create_cell(None, None, context, "c3", "x") is row_writes._EMPTIED
        assert context.emptied == 1
    else:
        with pytest.raises(HTTPException):
            row_writes._create_cell(None, None, context, "c3", "x")
        assert context.emptied == 0
