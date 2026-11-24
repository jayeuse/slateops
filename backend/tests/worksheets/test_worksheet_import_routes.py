"""Routes 21 and 22: read an Excel file, preview the key matching (D9.3, D14 E5; SH-35,
SH-36, SH-59). One ``worksheets.import.file_parsed`` event per parse, with no content."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.users.models import UserRole
from app.systems.openview.worksheets import import_router
from app.systems.sandbox.records.models import Record
from tests.conftest import create_member, create_organization
from tests.rbac.support import _client, add_module
from tests.worksheets.import_files import workbook
from tests.worksheets.support import SheetWorld, Students, add_students, sheet_world

pytestmark = pytest.mark.integration
PATH = "/api/worksheet-import-files"


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    found: list[Any] = []
    monkeypatch.setattr(import_router, "append_committed_security_event",
                        lambda payload, org_id=None: found.append((payload, org_id)))
    return found


def _upload(application: FastAPI, db: Session, person: Any, content: Any,
            tab: int = 0) -> Any:
    db.commit()  # the route ends its read transaction before the parser runs
    return _client(application, person, db).post(
        PATH, params={"tab": tab}, content=content,
        headers={"content-type": "application/octet-stream"},
    )


def test_a_member_reads_a_tab_and_one_event_records_the_parse(
    application: FastAPI, integration_db: Session, events: list[Any],
) -> None:
    world = sheet_world(integration_db)
    content = workbook()
    response = _upload(application, integration_db, world.owner, content)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["tab_index"], body["row_count"], body["column_count"]) == (0, 2, 6)
    assert body["tabs"] == [{"index": 0, "name": "Grades"}, {"index": 1, "name": "Empty"}]
    [(event, org_id)] = events
    assert (event.event_type, event.actor_id, org_id) == (
        "worksheets.import.file_parsed", world.owner.id, world.sheet.org_id,
    )
    assert event.metadata == {"outcome": "accepted", "reason": None,
                              "bytes": len(content), "row_count": 2}


def test_a_refused_file_answers_422_and_records_its_reason_without_content(
    application: FastAPI, integration_db: Session, events: list[Any],
) -> None:
    world = sheet_world(integration_db)
    refused = _upload(application, integration_db, world.owner, b"Alice,secret")
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "import_file_invalid"
    [(event, _org)] = events
    assert event.metadata == {"outcome": "refused", "reason": "unreadable", "bytes": 12,
                              "row_count": 0}
    assert "secret" not in str(event.model_dump())


def test_a_guest_cannot_import_and_starts_no_parser(
    application: FastAPI, integration_db: Session, events: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[bool] = []
    monkeypatch.setattr(import_router, "parse_import",
                        lambda *args: started.append(True) or {})
    world = sheet_world(integration_db)
    response = _upload(application, integration_db, world.guest, workbook())
    assert (response.status_code, response.json()["detail"]["code"]) == (
        403, "import_forbidden",
    )
    assert (started, events) == ([], [])


def test_an_oversize_body_is_refused_before_any_parser_starts(
    application: FastAPI, integration_db: Session, events: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[bool] = []
    monkeypatch.setattr(import_router, "parse_import",
                        lambda *args: started.append(True) or {})
    world = sheet_world(integration_db)
    oversize = b"x" * (10 * 1024 * 1024 + 1)
    assert _upload(application, integration_db, world.owner, oversize).status_code == 413

    def chunked() -> Iterator[bytes]:
        for _ in range(11):
            yield b"x" * (1024 * 1024)

    assert _upload(application, integration_db, world.owner, chunked()).status_code == 413
    assert (started, events) == ([], [])


def test_a_tab_outside_its_bounds_is_refused(
    application: FastAPI, integration_db: Session, events: list[Any],
) -> None:
    world = sheet_world(integration_db)
    assert _upload(application, integration_db, world.owner, workbook(), -1).status_code == 422
    missing = _upload(application, integration_db, world.owner, workbook(), 5)
    assert (missing.status_code, missing.json()["detail"]["code"]) == (422, "import_tab_invalid")
    assert [event.metadata["reason"] for event, _org in events] == ["tab"]


def _matches(application: FastAPI, db: Session, person: Any, body: dict[str, Any]) -> Any:
    return _client(application, person, db).post("/api/worksheet-import-matches", json=body)


@pytest.fixture
def students(integration_db: Session) -> tuple[SheetWorld, Students]:
    world = sheet_world(integration_db)
    found = add_students(integration_db, world, [world.owner])
    return world, found


def test_keys_match_live_readable_records_once_or_not_at_all(
    application: FastAPI, integration_db: Session, students: tuple[SheetWorld, Students],
) -> None:
    """SH-35: matched, not matched and matched more than once, decided per key."""

    db = integration_db
    world, found = students
    twin = Record(org_id=found.module.org_id, module_id=found.module.id,
                  data={str(found.name.id): "Bob"})
    gone = Record(org_id=found.module.org_id, module_id=found.module.id,
                  data={str(found.name.id): "Zed"}, is_deleted=True, deleted_at=utc_now())
    db.add_all([twin, gone])
    db.flush()
    response = _matches(application, db, world.owner, {
        "module_id": str(found.module.id), "field_id": str(found.name.id),
        "keys": ["Alice", "Bob", "Zed", "Nobody", "Alice"],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"] == [
        {"key": "Alice", "state": "matched",
         "record": {"record_id": str(found.alice.id), "label": "Alice"}},
        {"key": "Bob", "state": "ambiguous", "record": None},
        {"key": "Zed", "state": "unmatched", "record": None},
        {"key": "Nobody", "state": "unmatched", "record": None},
        {"key": "Alice", "state": "matched",
         "record": {"record_id": str(found.alice.id), "label": "Alice"}},
    ]
    assert body["counts"] == {"matched": 2, "unmatched": 2, "ambiguous": 1}


def test_an_unreadable_module_or_a_field_of_another_answers_like_a_missing_one(
    application: FastAPI, integration_db: Session, students: tuple[SheetWorld, Students],
) -> None:
    db = integration_db
    world, found = students
    hidden = add_module(db, world.department, "Hidden")
    answers = []
    for module_id, field_id in (
        (hidden.id, found.name.id),                   # unreadable module
        (found.module.id, world.reader_access.id),    # not a field of the module
        (world.sheet.id, found.name.id),              # no such module
    ):
        response = _matches(application, db, world.owner, {
            "module_id": str(module_id), "field_id": str(field_id), "keys": ["Alice"],
        })
        answers.append((response.status_code, response.json()["detail"]))
    assert answers == [(404, {"code": "module_not_found", "message": "Module not found"})] * 3


def test_an_administrator_of_another_organization_finds_no_module(
    application: FastAPI, integration_db: Session, students: tuple[SheetWorld, Students],
) -> None:
    """X8, SEC: route 22 answers 404 for a module of another organization, even to an admin."""

    db = integration_db
    _world, found = students
    other = create_organization(db)
    stranger, _membership = create_member(db, other, UserRole.ADMIN.value)
    response = _matches(application, db, stranger, {
        "module_id": str(found.module.id), "field_id": str(found.name.id), "keys": ["Alice"],
    })
    assert (response.status_code, response.json()["detail"]) == (
        404, {"code": "module_not_found", "message": "Module not found"},
    )


def test_a_full_file_memory_budget_refuses_the_answer_as_busy(
    application: FastAPI, integration_db: Session, events: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-B13-3: with a 1 MiB budget, a 2,000-row tab cannot reserve its answer: 503, a time
    to retry, and the refusal is recorded."""

    from app.systems.platform.files import providers

    settings = providers.get_settings()
    monkeypatch.setattr(providers, "get_settings",
                        lambda: settings.model_copy(update={"file_memory_budget_mib": 1}))
    monkeypatch.setattr(providers, "_pool", None)

    def fill(book: Any) -> None:
        sheet = book.add_worksheet("Large")
        for row in range(2_000):
            sheet.write_row(row, 0, [row * 100 + column + 0.5 for column in range(10)])

    world = sheet_world(integration_db)
    content = workbook(fill)
    assert len(content) < 1024 * 1024
    response = _upload(application, integration_db, world.owner, content, 2)
    assert (response.status_code, response.json()["detail"]["code"]) == (503, "files_busy")
    assert response.headers["retry-after"] == "1"
    [(event, _org)] = events
    assert event.metadata == {"outcome": "refused", "reason": "busy", "bytes": len(content),
                              "row_count": 0}
