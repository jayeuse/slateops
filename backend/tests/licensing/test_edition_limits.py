"""Edition limits, Office gates, the read-only state and the license route (spec editions.md)."""

from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.systems.manage.licensing import limits
from app.systems.manage.licensing.editions import DESK, Edition, Limit
from app.systems.manage.licensing.models import InstallationLicense
from app.systems.manage.licensing.state import forget_cached_state
from app.systems.openview.worksheets.models import Worksheet
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.record_triggers.models import RecordTriggerEvent
from app.systems.sandbox.record_triggers.outbox import enqueue_record_event
from tests.conftest import make_operator, membership_of
from tests.licensing.support import install, license_text
from tests.rbac.support import _client
from tests.worksheets.support import SheetWorld, sheet_world

pytestmark = pytest.mark.integration
DESK_FILE = license_text(Edition.DESK, seats=2)


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def world(integration_db: Session) -> Iterator[SheetWorld]:
    yield sheet_world(integration_db)
    forget_cached_state()


def _detail(error: pytest.ExceptionInfo[HTTPException]) -> dict[str, Any]:
    return cast(dict[str, Any], error.value.detail)


def _refusal(error: pytest.ExceptionInfo[HTTPException]) -> tuple[int, str, str | None]:
    detail = _detail(error)
    return error.value.status_code, detail["code"], detail.get("limit")


def test_desk_refuses_a_seat_or_a_guest_above_its_limits_and_office_allows_them(
    integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    install(db, DESK_FILE)  # the world already has more than two members and one guest
    with pytest.raises(HTTPException) as seat:
        limits.require_person(db, "member")
    assert _refusal(seat) == (403, "edition_limit", "seats")
    assert "Desk allows 2 people" in _detail(seat)["message"]
    with pytest.raises(HTTPException) as guest:
        limits.require_person(db, "guest")
    assert _refusal(guest) == (403, "edition_limit", "guests")
    row = db.scalar(select(InstallationLicense))
    assert row is not None
    row.license_text = license_text(Edition.OFFICE, seats=25)
    db.flush()
    forget_cached_state()
    limits.require_person(db, "member")
    limits.require_person(db, "guest")


def test_desk_refuses_a_record_above_the_module_limit(
    integration_db: Session, world: SheetWorld, monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(integration_db, DESK_FILE)
    monkeypatch.setitem(DESK.limits, Limit.RECORDS, 1)  # the module holds one record
    with pytest.raises(HTTPException) as refused:
        limits.require_records(integration_db, world.module.id)
    assert _refusal(refused) == (403, "edition_limit", "records")
    monkeypatch.setitem(DESK.limits, Limit.RECORDS, 2)
    limits.require_records(integration_db, world.module.id)


def test_desk_refuses_a_published_department_above_its_limit_but_not_a_change(
    integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    install(db, DESK_FILE)
    db.add_all([Department(org_id=world.department.org_id, department_name=f"Extra {n}")
                for n in (1, 2)])
    db.flush()  # now above the limit of two
    before = limits.structure_counts(db)
    world.department.department_name = "Renamed"
    limits.require_publish_growth(db, before)  # nothing new: allowed above the limit
    db.add(Department(org_id=world.department.org_id, department_name="One more"))
    with pytest.raises(HTTPException) as refused:
        limits.require_publish_growth(db, before)
    assert _refusal(refused) == (403, "edition_limit", "departments")


def test_desk_refuses_an_eleventh_sheet_through_the_route(
    application: FastAPI, integration_db: Session, world: SheetWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(integration_db, DESK_FILE)
    used = integration_db.scalar(
        select(func.count(Worksheet.id)).where(Worksheet.is_deleted.is_(False))
    )
    monkeypatch.setitem(DESK.limits, Limit.SHEETS, used)
    created = _client(application, world.owner, integration_db).post("/api/worksheets", json={
        "record_id": str(world.record.id), "title": "One too many", "source": {"kind": "blank"},
    })
    assert created.status_code == 403, created.text
    assert created.json()["detail"]["limit"] == "sheets"


def test_desk_refuses_a_row_above_the_sheet_row_limit(
    application: FastAPI, integration_db: Session, world: SheetWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(integration_db, DESK_FILE)
    monkeypatch.setitem(DESK.limits, Limit.SHEET_ROWS, 0)
    added = _client(application, world.owner, integration_db).post(
        f"/api/worksheets/{world.sheet.id}/rows", json={"cells": {}}
    )
    assert added.status_code == 403, added.text
    assert added.json()["detail"]["limit"] == "sheet_rows"


def test_desk_hides_office_features_and_runs_no_automation(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    install(db, DESK_FILE)
    listed = _client(application, world.admin, db).get("/api/dashboards")
    assert listed.status_code == 403
    assert listed.json()["detail"]["code"] == "edition_required"
    queued = db.scalar(select(func.count(RecordTriggerEvent.id)))
    enqueue_record_event(db, world.record, previous=None)
    db.flush()
    assert db.scalar(select(func.count(RecordTriggerEvent.id))) == queued


def test_every_edition_holds_one_organization(
    integration_db: Session, world: SheetWorld,
) -> None:
    install(integration_db, DESK_FILE)
    with pytest.raises(ValueError, match="one organization"):
        limits.require_first_organization(integration_db)


def _write(path: str = "/api/records") -> Any:
    return SimpleNamespace(method="POST", url=SimpleNamespace(path=path))


def test_an_ended_license_above_desk_limits_lets_only_administrators_write(
    integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    install(db, license_text(Edition.OFFICE, ends=date(2026, 1, 31)))  # ended by mid-March
    member = membership_of(db, world.owner.id)
    with pytest.raises(HTTPException) as refused:
        limits.refuse_read_only_write(_write(), db, member)
    assert _detail(refused)["code"] == "license_read_only"
    limits.refuse_read_only_write(_write(), db, membership_of(db, world.admin.id))
    reading = SimpleNamespace(method="GET", url=SimpleNamespace(path="/api/records"))
    limits.refuse_read_only_write(cast(Any, reading), db, member)


def test_the_installation_owner_imports_a_license_and_members_see_no_counts(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    make_operator(db, world.admin)
    owner = _client(application, world.admin, db)
    refused = owner.put("/api/license", json={"text": "not a license"})
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "license_invalid"
    imported = owner.put("/api/license", json={"text": license_text(Edition.HEADQUARTERS)})
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert (body["edition"], body["phase"], body["can_import"]) == ("headquarters", "active", True)
    seats = next(item for item in body["limits"] if item["limit"] == "seats")
    assert seats["allowed"] == 25 and seats["used"] >= 3
    assert [price["monthly_usd"] for price in body["editions"]] == [0, 39, 89]
    member = _client(application, world.owner, db).get("/api/license").json()
    assert member["edition"] == "headquarters" and member["can_import"] is False
    assert {item["used"] for item in member["limits"]} == {None}
    not_owner = _client(application, world.manager, db).put(
        "/api/license", json={"text": license_text()}
    )
    assert not_owner.status_code == 403
