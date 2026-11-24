"""Reading rows per viewer: routes 9 and 11 (D7.3; N2, N4, N6-N8, K6, K7, F7).

SH-24, SH-26, SH-27, SH-29, SH-30 (a real publish, close and reopen).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.query import read_row
from app.systems.sandbox.fields.models import Field
from app.systems.sandbox.lifecycle.schemas import LifecycleTargetType
from app.systems.sandbox.lifecycle.service import close_lifecycle, reopen_lifecycle
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from tests.rbac.support import _client, add_module, make_group_access
from tests.sandbox_publications.support import (
    bound_field,
    bound_module,
    publish_revision,
    publish_structure,
)
from tests.worksheets.support import STRUCTURE, SheetWorld, add_sheet, sheet_world

pytestmark = pytest.mark.integration
NOT_FOUND = {"detail": {"code": "worksheet_not_found", "message": "Sheet not found"}}
EXCELLENT = "0190a000-0000-7000-8000-00000000e001"
BLANK = {"value": None}


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@dataclass(frozen=True)
class Graded:
    world: SheetWorld
    students: Module
    rows: list[UUID]
    alice: Record


def _field(db: Session, module: Module, name: str, kind: str, position: int,
           config: dict[str, Any] | None = None) -> Field:
    field = Field(org_id=module.org_id, module_id=module.id, name=name, type=kind,
                  position=position, config=config or {})
    db.add(field)
    db.flush()
    return field


def _record(db: Session, module: Module, data: dict[str, Any]) -> Record:
    record = Record(org_id=module.org_id, module_id=module.id, data=data)
    db.add(record)
    db.flush()
    return record


@pytest.fixture
def graded(integration_db: Session) -> Graded:
    """A grade sheet linking to Student List; only the owner reads Student List."""

    db = integration_db
    world = sheet_world(db)
    students = add_module(db, world.department, "Student List")
    make_group_access(db, [world.owner], world.department, students, level=AccessLevel.READ)
    name = _field(db, students, "Name", "text", 0)
    score = _field(db, students, "Score", "int", 1)
    grade = _field(db, students, "Grade", "select", 2,
                   {"options": [{"id": EXCELLENT, "label": "Excellent"}]})
    gone = _field(db, students, "Old", "text", 3)
    gone.is_deleted, gone.deleted_at = True, utc_now()
    students.title_field_id = name.id
    alice = _record(db, students, {str(name.id): "Alice", str(score.id): 90,
                                   str(grade.id): EXCELLENT})
    bob = _record(db, students, {str(name.id): "Bob", str(score.id): 70})
    bob.is_deleted, bob.deleted_at = True, utc_now()
    carol = _record(db, students, {str(name.id): "Carol", str(score.id): 80})
    carol.is_deleted, carol.deleted_at = True, utc_now()
    carol.lifecycle_close_operation_id = uuid7()
    world.sheet.structure = {
        **STRUCTURE, "nextColumnSeq": 9,
        "columns": [
            {"key": "c1", "name": "Student", "type": "link",
             "link": {"moduleId": str(students.id)}},
            {"key": "c2", "name": "Name", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(name.id)}},
            {"key": "c3", "name": "Score", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(score.id)}},
            {"key": "c4", "name": "Note", "type": "text"},
            {"key": "c5", "name": "Points", "type": "int"},
            {"key": "c6", "name": "Bonus", "type": "computed",
             "computed": {"expression": "{c5} + 1", "places": 0}},
            {"key": "c7", "name": "Old", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(gone.id)}},
            {"key": "c8", "name": "Grade", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(grade.id)}},
        ],
        "totals": {"c1": "count", "c3": "average", "c4": "count", "c5": "sum"},
    }
    cells: list[tuple[dict[str, Any], Record | None, bool]] = [
        ({"c4": "alpha", "c5": 10}, alice, False),
        ({"c4": "beta", "c5": 5}, bob, False),
        ({}, carol, False),
        ({"c4": "Gamma"}, None, True),  # the target was purged
        ({"c1": {"unlinked": "Zed Unknown"}, "c5": 7}, None, False),
        ({}, None, False),
    ]
    rows = []
    for position, (data, target, removed) in enumerate(cells, start=1):
        row = WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id,
                           position=position * 1024, data=data, data_bytes=64)
        db.add(row)
        db.flush()
        if target is not None or removed:
            db.add(WorksheetRowLink(
                org_id=row.org_id, worksheet_id=row.worksheet_id, row_id=row.id,
                column_key="c1", target_record_id=target.id if target else None,
                target_removed=removed,
            ))
        rows.append(row.id)
    db.flush()
    return Graded(world, students, rows, alice)


def _query(application: FastAPI, db: Session, person: User, graded: Graded,
           **body: Any) -> dict[str, Any]:
    response = _client(application, person, db).post(
        f"/api/worksheets/{graded.world.sheet.id}/rows/query", json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _order(graded: Graded, body: dict[str, Any]) -> list[int]:
    return [graded.rows.index(UUID(item["id"])) + 1 for item in body["items"]]


def test_the_owner_sees_each_link_state_and_its_lookups(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    body = _query(application, integration_db, graded.world.owner, graded)
    cells = [item["cells"] for item in body["items"]]
    alice = {"link": {"record_id": str(graded.alice.id), "label": "Alice"}}
    assert [row["c1"] for row in cells] == [
        alice, {"state": "deleted"}, {"state": "unavailable"}, {"state": "removed"},
        {"unlinked": "Zed Unknown"}, BLANK,
    ]
    # Lookups: the current value, blank beside a deleted or purged record (Decision 17).
    assert [(row["c2"], row["c3"], row["c7"], row["c8"]) for row in cells] == [
        ({"value": "Alice"}, {"value": 90}, {"state": "field_removed"},
         {"value": "Excellent"}),
        (BLANK, BLANK, BLANK, BLANK),
        ({"state": "unavailable"},) * 4,
        (BLANK, BLANK, BLANK, BLANK),
        (BLANK, BLANK, BLANK, BLANK),
        (BLANK, BLANK, BLANK, BLANK),
    ]
    assert cells[0]["c4"] == {"value": "alpha"} and cells[0]["c5"] == {"value": 10}
    # Bonus is {Points} + 1, blank where Points is blank (K5).
    assert [row["c6"] for row in cells] == [
        {"value": "11"}, {"value": "6"}, BLANK, BLANK, {"value": "8"}, BLANK,
    ]
    assert body["pagination"]["total"] == 6


def test_a_viewer_who_cannot_read_the_linked_module_sees_no_access_and_no_trace(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    body = _query(application, integration_db, graded.world.viewer, graded)
    for item in body["items"]:
        for key in ("c1", "c2", "c3", "c7", "c8"):
            assert item["cells"][key] == {"state": "no_access"}
    assert str(graded.alice.id) not in str(body)
    assert "Alice" not in str(body)
    assert "Zed Unknown" not in str(body)


def test_a_closed_target_module_makes_its_links_unavailable(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    graded.students.is_deleted, graded.students.deleted_at = True, utc_now()
    integration_db.flush()
    body = _query(application, integration_db, graded.world.owner, graded)
    # Links come back on reopen; a purged target never does, so it stays "removed".
    assert [item["cells"]["c1"] for item in body["items"]][:4] == [
        {"state": "unavailable"}, {"state": "unavailable"}, {"state": "unavailable"},
        {"state": "removed"},
    ]


@pytest.mark.parametrize(
    ("person", "sort", "expected"),
    [
        ("owner", {"key": "c4", "order": "asc"}, [1, 2, 4, 3, 5, 6]),
        ("owner", {"key": "c4", "order": "desc"}, [4, 2, 1, 3, 5, 6]),
        ("owner", {"key": "c5", "order": "asc"}, [2, 5, 1, 3, 4, 6]),
        ("owner", {"key": "c1", "order": "asc"}, [1, 5, 2, 3, 4, 6]),
        ("owner", {"key": "c1", "order": "desc"}, [5, 1, 2, 3, 4, 6]),
        ("owner", {"key": "c3", "order": "desc"}, [1, 2, 3, 4, 5, 6]),
        ("viewer", {"key": "c1", "order": "desc"}, [1, 2, 3, 4, 5, 6]),
    ],
    ids=["text-asc", "text-desc", "number-asc", "link-asc", "link-desc", "lookup-desc",
         "hidden-column"],
)
def test_sorting_puts_blank_and_hidden_cells_last_in_both_directions(
    application: FastAPI, integration_db: Session, graded: Graded,
    person: str, sort: dict[str, str], expected: list[int],
) -> None:
    viewer = graded.world.owner if person == "owner" else graded.world.viewer
    body = _query(application, integration_db, viewer, graded, sort=sort)
    assert _order(graded, body) == expected


@pytest.mark.parametrize(
    ("search", "owner", "viewer"),
    [("alice", [1], []), ("zed", [5], []), ("GAMMA", [4], [4]), ("Excellent", [1], [])],
)
def test_search_matches_only_text_the_viewer_can_read(
    application: FastAPI, integration_db: Session, graded: Graded,
    search: str, owner: list[int], viewer: list[int],
) -> None:
    for person, expected in ((graded.world.owner, owner), (graded.world.viewer, viewer)):
        body = _query(application, integration_db, person, graded, search=search)
        assert (_order(graded, body), body["pagination"]["total"]) == (expected, len(expected))


def test_totals_cover_every_row_and_count_the_cells_hidden_from_the_viewer(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    owner = _query(application, integration_db, graded.world.owner, graded, search="alpha")
    assert owner["totals"] == {
        "c1": {"fn": "count", "value": 2, "hidden_count": 0},
        "c3": {"fn": "average", "value": "90", "hidden_count": 0},
        "c4": {"fn": "count", "value": 3, "hidden_count": 0},
        "c5": {"fn": "sum", "value": "22", "hidden_count": 0},
    }
    viewer = _query(application, integration_db, graded.world.viewer, graded)
    assert viewer["totals"] == {
        "c1": {"fn": "count", "value": 0, "hidden_count": 6},
        "c3": {"fn": "average", "value": None, "hidden_count": 6},
        "c4": {"fn": "count", "value": 3, "hidden_count": 0},
        "c5": {"fn": "sum", "value": "22", "hidden_count": 0},
    }


def test_min_and_max_totals_cover_every_row(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    """SH-24: Points are 10, 5, 7; Bonus ({Points} + 1) is 11, 6, 8; blanks are skipped."""

    graded.world.sheet.structure = {**graded.world.sheet.structure,
                                    "totals": {"c5": "min", "c6": "max"}}
    integration_db.flush()
    body = _query(application, integration_db, graded.world.owner, graded, search="alpha")
    assert body["totals"] == {
        "c5": {"fn": "min", "value": "5", "hidden_count": 0},
        "c6": {"fn": "max", "value": "11", "hidden_count": 0},
    }


def test_a_lookup_follows_its_record_and_links_return_on_restore_and_reopen(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    """SH-26: the lookup reads the record's current value. SH-29: a restored record's link
    shows again. SH-30: links of a closed target module come back when it reopens."""

    db = integration_db
    owner = graded.world.owner
    score = str(graded.world.sheet.structure["columns"][2]["lookup"]["fieldId"])
    graded.alice.data = {**graded.alice.data, score: 95}
    bob = db.scalars(select(WorksheetRowLink.target_record_id).where(
        WorksheetRowLink.row_id == graded.rows[1])).one()
    restored = db.get(Record, bob)
    assert restored is not None
    restored.is_deleted, restored.deleted_at = False, None
    db.flush()
    cells = [item["cells"] for item in _query(application, db, owner, graded)["items"]]
    assert cells[0]["c3"] == {"value": 95}
    assert (cells[1]["c1"], cells[1]["c3"]) == (
        {"link": {"record_id": str(bob), "label": "Bob"}}, {"value": 70},
    )
    graded.students.is_deleted, graded.students.deleted_at = True, utc_now()
    db.flush()
    closed = _query(application, db, owner, graded)["items"][0]["cells"]["c1"]
    assert closed == {"state": "unavailable"}
    graded.students.is_deleted, graded.students.deleted_at = False, None
    db.flush()
    reopened = _query(application, db, owner, graded)["items"][0]["cells"]
    assert (reopened["c1"], reopened["c3"]) == (
        {"link": {"record_id": str(graded.alice.id), "label": "Alice"}}, {"value": 95},
    )


def test_a_published_field_removal_and_a_module_close_show_in_the_cells(
    integration_owner_db: Session,
) -> None:
    """SH-30 through a real Sandbox publish (the lookup's field goes: "Field removed") and a
    real lifecycle close and reopen of the link column's target module."""

    db = integration_owner_db
    publisher, document = publish_structure(db)
    requests = bound_module(db, "sample-requests")
    priority = bound_field(db, "field", "sample-requests:sample-field-requests-priority")
    target = Record(org_id=requests.org_id, module_id=requests.id,
                    data={str(priority.id): "Urgent"})
    db.add(target)
    db.flush()
    sheet = add_sheet(db, publisher, module=bound_module(db, "sample-customers"))
    sheet.structure = {
        **STRUCTURE, "nextColumnSeq": 3,
        "columns": [
            {"key": "c1", "name": "Request", "type": "link",
             "link": {"moduleId": str(requests.id)}},
            {"key": "c2", "name": "Priority", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(priority.id)}},
        ],
    }
    row = WorksheetRow(org_id=sheet.org_id, worksheet_id=sheet.id, position=1024,
                       data={}, data_bytes=2)
    db.add(row)
    db.flush()
    db.add(WorksheetRowLink(org_id=row.org_id, worksheet_id=sheet.id, row_id=row.id,
                            column_key="c1", target_record_id=target.id))
    db.flush()

    def cells() -> dict[str, Any]:
        found = read_row(db, publisher, sheet, row.id)
        assert found is not None
        return {key: cell.model_dump() for key, cell in found.cells.items()}

    assert cells()["c2"] == {"value": "Urgent"}
    updated = document.model_copy(deep=True)
    module = next(item for item in updated.design.modules if item.id == "sample-requests")
    module.fields = [field for field in module.fields
                     if field.id != "sample-field-requests-priority"]
    publish_revision(db, publisher, updated, "remove-priority")
    assert cells()["c2"] == {"state": "field_removed"}
    db.commit()
    close_lifecycle(db, LifecycleTargetType.MODULE, requests.id, None)
    assert cells()["c1"] == {"state": "unavailable"}
    reopen_lifecycle(db, LifecycleTargetType.MODULE, requests.id, None)
    assert cells()["c1"]["link"]["record_id"] == str(target.id)


def test_rows_page_in_their_saved_order_with_an_exact_total(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    body = _query(application, integration_db, graded.world.owner, graded, limit=2, offset=2)
    assert _order(graded, body) == [3, 4]
    assert {key: body["pagination"][key] for key in ("total", "count", "has_more")} == {
        "total": 6, "count": 2, "has_more": True,
    }
    deleted = integration_db.get(WorksheetRow, graded.rows[0])
    assert deleted is not None
    deleted.is_deleted, deleted.deleted_at = True, utc_now()
    integration_db.flush()
    assert _query(application, integration_db, graded.world.owner, graded)[
        "pagination"]["total"] == 5


def test_an_unknown_sort_column_is_refused(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    response = _client(application, graded.world.owner, integration_db).post(
        f"/api/worksheets/{graded.world.sheet.id}/rows/query",
        json={"sort": {"key": "c99", "order": "asc"}},
    )
    assert (response.status_code, response.json()["detail"]["code"]) == (
        422, "sort_column_invalid"
    )


def test_one_row_reads_with_the_same_cells_and_its_etag(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    db = integration_db
    owner = _client(application, graded.world.owner, db)
    path = f"/api/worksheets/{graded.world.sheet.id}/rows/{graded.rows[0]}"
    read = owner.get(path)
    assert read.status_code == 200, read.text
    assert read.headers["ETag"] == f'"{graded.rows[0]}:1"'
    listed = _query(application, db, graded.world.owner, graded)["items"][0]
    assert read.json() == listed
    missing = owner.get(f"/api/worksheets/{graded.world.sheet.id}/rows/{uuid7()}")
    assert (missing.status_code, missing.json()["detail"]["code"]) == (
        404, "worksheet_row_not_found"
    )


def _body(response: Any) -> Any:
    return {key: value for key, value in response.json().items() if key != "request_id"}


def test_a_hidden_sheet_answers_like_a_missing_one_on_both_row_routes(
    application: FastAPI, integration_db: Session, graded: Graded,
) -> None:
    peer = _client(application, graded.world.peer, integration_db)
    for sheet_id in (graded.world.sheet.id, uuid7()):
        for answer in (
            peer.post(f"/api/worksheets/{sheet_id}/rows/query", json={}),
            peer.post(f"/api/worksheets/{sheet_id}/rows/query",
                      json={"sort": {"key": "c99", "order": "asc"}}),
            peer.get(f"/api/worksheets/{sheet_id}/rows/{graded.rows[0]}"),
        ):
            assert (answer.status_code, _body(answer)) == (404, NOT_FOUND)


def _simple_sheet(db: Session, columns: list[dict[str, Any]], rows: list[dict[str, Any]],
                  totals: dict[str, str] | None = None) -> tuple[SheetWorld, list[UUID]]:
    world = sheet_world(db)
    world.sheet.structure = {
        **STRUCTURE, "nextColumnSeq": len(columns) + 1, "columns": columns,
        "totals": totals or {},
    }
    ids = []
    for position, data in enumerate(rows, start=1):
        row = WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id,
                           position=position * 1024, data=data, data_bytes=64)
        db.add(row)
        db.flush()
        ids.append(row.id)
    return world, ids


def _post(application: FastAPI, db: Session, world: SheetWorld, **body: Any) -> dict[str, Any]:
    response = _client(application, world.owner, db).post(
        f"/api/worksheets/{world.sheet.id}/rows/query", json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_decimal_cells_stored_as_decimal_text_sort_and_total_as_numbers(
    application: FastAPI, integration_db: Session,
) -> None:
    world, ids = _simple_sheet(
        integration_db,
        [{"key": "c1", "name": "Mark", "type": "decimal",
          "decimal": {"places": 2, "currency": False}}],
        [{"c1": "12.50"}, {"c1": "7.5"}],
        {"c1": "sum"},
    )
    body = _post(application, integration_db, world, sort={"key": "c1", "order": "asc"})
    assert [item["id"] for item in body["items"]] == [str(ids[1]), str(ids[0])]
    assert body["totals"]["c1"] == {"fn": "sum", "value": "20", "hidden_count": 0}


def test_search_skips_person_and_checkbox_columns(
    application: FastAPI, integration_db: Session,
) -> None:
    person = uuid7()
    world, _ids = _simple_sheet(
        integration_db,
        [{"key": "c1", "name": "Teacher", "type": "user"},
         {"key": "c2", "name": "Done", "type": "boolean"}],
        [{"c1": str(person), "c2": True}],
    )
    for search in (str(person)[:8], "true"):
        assert _post(application, integration_db, world, search=search)["items"] == []


def test_a_link_to_a_record_titled_by_a_choice_shows_the_option_label(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    houses = add_module(db, world.department, "Houses")
    make_group_access(db, [world.owner], world.department, houses, level=AccessLevel.READ)
    house = _field(db, houses, "House", "select", 0,
                   {"options": [{"id": EXCELLENT, "label": "Excellent"}]})
    houses.title_field_id = house.id
    record = _record(db, houses, {str(house.id): EXCELLENT})
    world.sheet.structure = {
        **STRUCTURE, "nextColumnSeq": 2,
        "columns": [{"key": "c1", "name": "House", "type": "link",
                     "link": {"moduleId": str(houses.id)}}],
    }
    row = WorksheetRow(org_id=world.sheet.org_id, worksheet_id=world.sheet.id, position=1024,
                       data={}, data_bytes=2)
    db.add(row)
    db.flush()
    db.add(WorksheetRowLink(org_id=row.org_id, worksheet_id=row.worksheet_id, row_id=row.id,
                            column_key="c1", target_record_id=record.id))
    db.flush()
    cell = _post(application, db, world)["items"][0]["cells"]["c1"]
    assert cell == {"link": {"record_id": str(record.id), "label": "Excellent"}}
