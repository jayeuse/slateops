"""The three D1 keyset lists through their routes: walks, the cursor's 422s, and totals (P3, P7)."""

import base64
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import get_current_user
from app.core.database.session import get_db
from app.main import create_app
from app.systems.access.users.models import UserRole
from app.systems.manage.audit.models import AuditAction, AuditLog
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.record_triggers.models import RecordTriggerEvent, RecordTriggerRun
from app.systems.sandbox.records.models import Record
from app.systems.sandbox.relationships.models import RelationshipEdge
from tests.organization_scope_support import scoped_override
from tests.rbac.support import add_user
from tests.sandbox_record_triggers.support import document_baseline, publish_trigger

pytestmark = pytest.mark.integration

ROWS = 7
INVALID = {"loc": ["query", "cursor"], "msg": "Invalid cursor", "type": "value_error"}
WITH_OFFSET = {
    "loc": ["query", "cursor"],
    "msg": "A cursor cannot be combined with an offset",
    "type": "value_error",
}
OTHER_SORT = {
    "loc": ["query", "cursor"],
    "msg": "A cursor pages only the created_at order",
    "type": "value_error",
}


@dataclass
class _World:
    db: Session
    client: TestClient
    request_id: UUID
    field: Field
    record: Record
    module_id: UUID
    trigger_id: UUID

    def add_audit_row(self, at: datetime) -> str:
        identity = uuid7()
        self.db.connection().execute(AuditLog.__table__.insert().values(
            id=identity, org_id=self.record.org_id, created_at=at, action=AuditAction.UPDATE,
            entity_type="reports", entity_id=uuid7(), request_id=self.request_id,
        ))
        return str(identity)

    def add_link(self) -> str:
        target = Record(org_id=self.record.org_id, module_id=self.module_id, data={})
        self.db.add(target)
        self.db.flush()
        edge = RelationshipEdge(
            org_id=self.record.org_id, field_id=self.field.id, source_record_id=self.record.id,
            target_record_id=target.id,
        )
        self.db.add(edge)
        self.db.flush()
        return str(edge.id)

    def add_run(self) -> str:
        event = RecordTriggerEvent(
            org_id=self.record.org_id, record_id=self.record.id, module_id=self.module_id,
            event_kind="field-changed", state="succeeded", next_attempt_at=datetime.now(UTC),
        )
        self.db.add(event)
        self.db.flush()
        run = RecordTriggerRun(
            org_id=self.record.org_id, event_id=event.id, trigger_id=self.trigger_id,
            state="skipped", details={},
        )
        self.db.add(run)
        self.db.flush()
        return str(run.id)


@pytest.fixture
def world(integration_db: Session) -> Iterator[_World]:
    db = integration_db
    document_baseline(db)
    _actor, module, _fields, definition = publish_trigger(db)
    admin = add_user(db, role=UserRole.ADMIN)
    field = Field(
        org_id=module.org_id, module_id=module.id, name="Link", type=FieldType.RELATIONSHIP,
        position=99, relationship_target_module_id=module.id,
        relationship_multiple_targets=True, relationship_multiple_sources=True,
    )
    record = Record(org_id=module.org_id, module_id=module.id, data={})
    db.add_all([field, record])
    db.flush()
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_current_user] = scoped_override(lambda: admin)
    with TestClient(application) as client:
        yield _World(db, client, uuid7(), field, record, module.id, definition.id)


def _lists(world: _World) -> dict[str, tuple[str, dict[str, Any], Callable[[], str]]]:
    """Each list: its path, the parameters that bound it to this test's rows, and an adder."""

    start = datetime(2026, 11, 1, tzinfo=UTC)
    minutes = iter(range(1_000))
    return {
        "audit": (
            "/api/audit-logs", {"request_id": str(world.request_id)},
            lambda: world.add_audit_row(start + timedelta(minutes=next(minutes))),
        ),
        "relationships": (
            "/api/relationships", {"source_record_id": str(world.record.id)}, world.add_link,
        ),
        "runs": ("/api/sandbox/trigger-runs", {}, world.add_run),
    }


def _page(world: _World, path: str, params: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    response = world.client.get(path, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    page = body.get("pagination", body)
    return [row["id"] for row in body["items"]], page


def _raw(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


def _next(page: dict[str, Any]) -> str | None:
    return page.get("next_cursor", page.get("nextCursor"))


@pytest.mark.parametrize(
    ("name", "order"),
    [("audit", "desc"), ("audit", "asc"), ("relationships", "asc"), ("relationships", "desc"),
     ("runs", None)],
)
def test_a_cursor_walk_neither_repeats_nor_skips_while_rows_are_added_p3(
    world: _World, name: str, order: str | None
) -> None:
    path, bounded, add = _lists(world)[name]
    existing = {add() for _row in range(ROWS)}
    params = {**bounded, "limit": 2, **({"sort_order": order} if order else {})}

    walked, page = _page(world, path, params)
    first_total = page["total"]
    while _next(page) is not None:
        add()
        ids, page = _page(world, path, {**params, "cursor": _next(page)})
        walked += ids
        assert page["offset"] == 0

    assert len(walked) == len(set(walked))
    assert existing <= set(walked)
    assert first_total == ROWS


@pytest.mark.parametrize("name", ["audit", "relationships", "runs"])
def test_a_cursor_page_keeps_the_whole_total_and_bad_cursors_get_a_fixed_422_p7(
    world: _World, name: str
) -> None:
    path, bounded, add = _lists(world)[name]
    for _row in range(ROWS):
        add()
    params = {**bounded, "limit": 2}
    _ids, first = _page(world, path, params)
    _ids, second = _page(world, path, {**params, "cursor": _next(first)})
    assert (first["total"], second["total"]) == (ROWS, ROWS)

    refusals = {
        "offset": ({"cursor": _next(first), "offset": 2}, WITH_OFFSET),
        "bad": ({"cursor": "not*base64"}, INVALID),
        "no offset in time": ({"cursor": _raw(f"2026-11-09T12:00:00|{uuid7()}")}, INVALID),
    }
    if name != "runs":
        refusals["other sort"] = ({"cursor": _next(first), "sort_by": "updated_at"
                                   if name == "relationships" else "action"}, OTHER_SORT)
    for label, (extra, detail) in refusals.items():
        refused = world.client.get(path, params={**params, **extra})
        assert refused.status_code == 422, (label, refused.text)
        assert refused.json()["detail"] == [detail], label
    oversize = world.client.get(path, params={**params, "cursor": "A" * 129})
    assert oversize.status_code == 422
    assert oversize.json()["detail"][0]["loc"] == ["query", "cursor"]


def test_the_notification_list_ignores_a_cursor_and_serves_the_offset_page(
    world: _World,
) -> None:
    # D23: notifications keep offset paging; the cursor is not a parameter of that list.
    plain = world.client.get("/api/notifications", params={"limit": 5})
    with_cursor = world.client.get("/api/notifications", params={"limit": 5, "cursor": "x"})

    assert plain.status_code == with_cursor.status_code == 200
    assert with_cursor.json() == plain.json()
    assert "next_cursor" not in with_cursor.json()["pagination"]
