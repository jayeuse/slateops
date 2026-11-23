"""Sheet events reach exactly the people who can see the sheet (spec D6, D14 C1-C5).

T1 holds the delivery of every other entity to the value captured at 242dc04e, before the
`worksheets` class existed. The capture is `worksheet_delivery_baseline.json`.
"""

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

import app.systems.platform.events.router as events_router
from app.core.base_model import utc_now
from app.core.database.base import Base
from app.systems.access.policy.models import AccessLevel
from app.systems.access.policy.scope import allowed_module_ids
from app.systems.access.users.membership import current_membership
from app.systems.access.users.models import Membership, User, UserStatus
from app.systems.boards.access import readable_board_ids
from app.systems.manage.audit.listeners import REALTIME_INVALIDATION_KEY
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.access import visible_worksheet_ids
from app.systems.openview.worksheets.models import (
    WorksheetRow,
    WorksheetRowLink,
    WorksheetRowRevision,
    WorksheetShare,
)
from app.systems.platform.events.hub import (
    EventHub,
    EventSubscription,
    EventViewer,
    _access_signature,
    _can_receive,
)
from app.systems.platform.events.models import (
    InvalidationEvent,
    event_for_entity,
    parse_invalidation_payload,
)
from app.systems.platform.events.router import EventPrincipal, event_stream
from tests.conftest import membership_of
from tests.rbac.support import add_user, make_group_access
from tests.worksheets.support import add_sheet, sheet_world

BASELINE = Path(__file__).with_name("worksheet_delivery_baseline.json")
ORG = UUID("01900000-0000-7000-8000-0000000000a1")
OTHER_ORG = UUID("01900000-0000-7000-8000-0000000000a2")
MODULE = UUID("01900000-0000-7000-8000-0000000000b1")
BOARD = UUID("01900000-0000-7000-8000-0000000000b2")
ROW = UUID("01900000-0000-7000-8000-0000000000b3")
MEMBER = UUID("01900000-0000-7000-8000-0000000000c1")


def _viewers() -> dict[str, EventViewer]:
    return {
        "admin": EventViewer(
            UUID("01900000-0000-7000-8000-0000000000c0"), "admin", None, board_ids=None,
            org_id=ORG,
        ),
        "member": EventViewer(
            MEMBER, "member", frozenset({MODULE}), board_ids=frozenset({BOARD}), org_id=ORG,
        ),
        "guest": EventViewer(
            UUID("01900000-0000-7000-8000-0000000000c2"), "guest", frozenset({MODULE}),
            board_ids=frozenset({BOARD}), org_id=ORG,
        ),
        "operator": EventViewer(
            UUID("01900000-0000-7000-8000-0000000000c3"), "member", frozenset(),
            board_ids=frozenset(), org_id=ORG, operator=True,
        ),
        "other_org_admin": EventViewer(
            UUID("01900000-0000-7000-8000-0000000000c4"), "admin", None, board_ids=None,
            org_id=OTHER_ORG,
        ),
    }


def _subscription(viewer: EventViewer) -> EventSubscription:
    return EventSubscription(asyncio.Queue(), viewer, _access_signature(viewer), viewer.user_id)


def _existing_entities() -> list[str]:
    tables = {name for name in Base.metadata.tables if not name.startswith("worksheet")}
    return sorted(tables | {"workspace_profiles", "work_scheduled", "work_triggers", "resync"})


def _observe(entities: list[str]) -> dict[str, Any]:
    """Classification, transport and delivery of each entity, as plain data."""

    viewers = _viewers()
    observed: dict[str, Any] = {
        "signatures": {name: list(_access_signature(viewer)) for name, viewer in viewers.items()},
    }
    for entity in entities:
        for scope, org_id in (("org", ORG), ("account", None)):
            key = f"{entity}|{scope}"
            try:
                event = event_for_entity(
                    entity, ROW, recipient_id=MEMBER, module_id=MODULE, board_id=BOARD,
                    org_id=org_id,
                )
            except ValueError:
                observed[key] = "classification refused"
                continue
            if event is None:
                observed[key] = "no event"
                continue
            try:
                parsed = parse_invalidation_payload(event.to_transport_json())
            except ValueError:
                observed[key] = {"payload": event.to_payload(), "transport": "refused"}
                continue
            observed[key] = {
                "payload": event.to_payload(),
                "receivers": sorted(
                    name for name, viewer in viewers.items()
                    if _can_receive(_subscription(viewer), parsed)
                ),
            }
    return observed


def test_t1_every_existing_entity_is_classified_and_delivered_as_before_sheets() -> None:
    baseline = json.loads(BASELINE.read_text())
    assert _observe(_existing_entities()) == baseline


# --- T2 to T5: the `worksheets` class ------------------------------------------------------


def _sheet_viewer(db: Session, person: User, org_id: UUID) -> EventViewer:
    """The viewer that `_reauthorize_in_database` builds, from the same functions."""

    membership = current_membership(db, person)
    assert membership is not None
    return EventViewer(
        user_id=person.id,
        role=membership.role,
        module_ids=allowed_module_ids(db, person, AccessLevel.READ),
        board_ids=readable_board_ids(db, person),
        org_id=org_id,
        worksheet_ids=visible_worksheet_ids(db, person, org_id),
    )


def _sheet_event(sheet_id: UUID, org_id: UUID) -> InvalidationEvent:
    event = event_for_entity("worksheets", sheet_id, org_id=org_id)
    assert event is not None
    return parse_invalidation_payload(event.to_transport_json())


@pytest.mark.integration
def test_t2_a_sheet_event_reaches_its_owner_recipients_and_open_sheet_readers_only(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    org_id = world.sheet.org_id
    # A second sheet whose owner left: it is open to every reader of the record.
    departed = add_user(db)
    make_group_access(db, [departed], world.department, world.module, level=AccessLevel.READ)
    open_sheet = add_sheet(db, departed, record=world.record)
    membership_of(db, departed.id).status = UserStatus.DISABLED.value
    db.flush()
    people = world.people()
    viewers = {name: _sheet_viewer(db, person, org_id) for name, person in people.items()}
    viewers["admin of another organization"] = EventViewer(
        uuid7(), "admin", None, board_ids=None, org_id=uuid7(),
    )

    def receivers(sheet_id: UUID) -> set[str]:
        event = _sheet_event(sheet_id, org_id)
        return {
            name for name, viewer in viewers.items()
            if _can_receive(_subscription(viewer), event)
        }

    assert receivers(world.sheet.id) == {
        "owner", "view share", "edit share", "edit share by group", "guest with edit share",
    }
    assert receivers(open_sheet.id) == {
        "owner", "view share", "edit share", "edit share by group", "guest with edit share",
        "peer", "module manager", "admin",
    }


@pytest.mark.integration
def test_t3_each_sheet_table_publishes_only_the_sheet_id(integration_db: Session) -> None:
    db = integration_db
    world = sheet_world(db)
    expected = [{"entity": "worksheets", "entity_id": str(world.sheet.id)}]

    def published(*rows: object) -> list[dict[str, str]]:
        db.info.pop(REALTIME_INVALIDATION_KEY, None)
        db.add_all(rows)
        db.flush()
        return [
            event.to_payload() for event in db.info.get(REALTIME_INVALIDATION_KEY, [])
            if event.entity.startswith("worksheet")
        ]

    org_id = world.sheet.org_id
    row = WorksheetRow(
        org_id=org_id, worksheet_id=world.sheet.id, position=1024, data={}, data_bytes=2,
    )
    assert published(row) == expected
    assert published(WorksheetRowLink(
        org_id=org_id, worksheet_id=world.sheet.id, row_id=row.id, column_key="c1",
        target_record_id=world.record.id,
    )) == expected
    assert published(WorksheetRowRevision(
        org_id=org_id, worksheet_id=world.sheet.id, row_id=row.id, revision=1,
        action="create", data={}, changed_keys=[],
    )) == expected
    assert published(WorksheetShare(
        org_id=org_id, worksheet_id=world.sheet.id, subject="user", user_id=world.peer.id,
        level="view", created_by=world.owner.id,
    )) == expected
    world.sheet.title = "Renamed"
    assert published() == expected


def test_t3_another_worksheet_table_publishes_nothing() -> None:
    assert event_for_entity("worksheet_presence", ROW, org_id=ORG) is None
    with pytest.raises(ValueError, match="invalid invalidation payload"):
        parse_invalidation_payload(
            {"entity": "worksheet_presence", "entity_id": str(ROW), "org_id": str(ORG)}
        )


async def _not_disconnected() -> bool:
    return False


def _authorizer(*viewers: EventViewer):
    answers = iter(viewers)

    async def reauthorize(_principal: EventPrincipal) -> EventViewer | None:
        return next(answers)

    return reauthorize


def _stream(viewers: tuple[EventViewer, ...], hub: EventHub) -> Any:
    return event_stream(
        SimpleNamespace(is_disconnected=_not_disconnected), hub, EventPrincipal("token"),
        # Every step queues its event first, so no heartbeat is due; this bounds a hang.
        heartbeat_seconds=30, reauthorize=_authorizer(*viewers),
    )


RESYNC = b"event: resync\ndata: {}\n\n"


@pytest.mark.integration
def test_t4_a_removed_share_resyncs_and_an_opened_sheet_reaches_a_record_reader(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    org_id = world.sheet.org_id
    shared = _sheet_viewer(db, world.viewer, org_id)
    admin_before = _sheet_viewer(db, world.admin, org_id)
    viewer_share = db.scalars(select(WorksheetShare).where(
        WorksheetShare.worksheet_id == world.sheet.id,
        WorksheetShare.user_id == world.viewer.id,
    )).one()
    viewer_share.is_deleted, viewer_share.deleted_at = True, utc_now()
    db.flush()
    unshared = _sheet_viewer(db, world.viewer, org_id)
    membership_of(db, world.owner.id).status = UserStatus.DISABLED.value
    db.flush()
    admin_after = _sheet_viewer(db, world.admin, org_id)
    event = _sheet_event(world.sheet.id, org_id)
    payload = (
        b"event: invalidate\ndata: "
        + json.dumps({"entity": "worksheets", "entity_id": str(world.sheet.id)},
                     separators=(",", ":"), sort_keys=True).encode()
        + b"\n\n"
    )

    async def exercise() -> None:
        hub = EventHub()
        removed = _stream((shared, unshared), hub)
        assert await anext(removed) == RESYNC
        await hub.publish(event)
        assert await anext(removed) == RESYNC  # the share is gone: resync, not the event
        await removed.aclose()

        hub = EventHub()
        opened = _stream((admin_before, admin_after, admin_after), hub)
        assert await anext(opened) == RESYNC
        # Any next event checks access again; the admin now reads the opened sheet.
        await hub.publish(InvalidationEvent("records", module_id=world.module.id, org_id=org_id))
        assert await anext(opened) == RESYNC
        await hub.publish(event)
        assert await anext(opened) == payload
        await opened.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "payload",
    [
        {"entity": "worksheets"},
        {"entity": "worksheets", "entity_id": "not-a-uuid"},
        {"entity": "worksheets", "entity_id": str(ROW), "module_id": str(MODULE)},
        {"entity": "worksheets", "entity_id": str(ROW), "board_id": str(BOARD)},
        {"entity": "worksheets", "entity_id": str(ROW), "recipient_id": str(MEMBER)},
    ],
    ids=["no-sheet", "sheet-not-a-uuid", "module-key", "board-key", "recipient-key"],
)
def test_t5_a_sheet_payload_carries_the_sheet_id_and_nothing_else(payload) -> None:
    with pytest.raises(ValueError, match="invalid invalidation payload"):
        parse_invalidation_payload({**payload, "org_id": str(ORG)})


def test_t5_a_sheet_event_cannot_be_built_with_another_scope() -> None:
    for values in ({}, {"entity_id": ROW, "module_id": MODULE},
                   {"entity_id": ROW, "administrators_only": True},
                   {"entity_id": ROW, "all_authenticated": True}):
        with pytest.raises(ValueError, match="invalid invalidation payload"):
            InvalidationEvent("worksheets", org_id=ORG, **values)
    assert parse_invalidation_payload(
        {"entity": "worksheets", "entity_id": str(ROW), "org_id": str(ORG)}
    ).to_payload() == {"entity": "worksheets", "entity_id": str(ROW)}


def test_the_stream_snapshot_takes_the_visible_sheets_of_its_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, sheet_id = uuid7(), uuid7()
    user = SimpleNamespace(id=uuid7(), supabase_user_id=uuid7(), password_change_required_at=None)
    membership = Membership(user_id=user.id, role="admin")
    calls: list[tuple[object, object, object]] = []

    def visible(db: object, person: object, organization: object) -> frozenset[UUID]:
        calls.append((db, person, organization))
        return frozenset({sheet_id})

    database = SimpleNamespace(dirty=set(), get=lambda *_args: WorkspaceProfile(is_deleted=False))

    @contextmanager
    def session(_engine: object) -> Iterator[object]:
        yield database

    client = SimpleNamespace(verify_access_token=lambda _token: object())
    for name, value in {
        "get_supabase_auth_client": lambda: client,
        "resolve_provider_session": lambda *_args: (user, SimpleNamespace(active_org_id=org_id)),
        "load_workspace_policy": lambda _db, **_kwargs: WorkspaceProfile(ip_allow_list=[]),
        "scope_session": lambda *_args: None,
        "current_membership": lambda *_args: membership,
        "recent_provider_user": lambda _id: object(),
        "requires_mfa": lambda *_args: False,
        "allowed_module_ids": lambda *_args: None,
        "readable_board_ids": lambda *_args: None,
        "is_platform_operator": lambda *_args: False,
        "visible_worksheet_ids": visible,
        "get_engine": lambda: object(),
        "AuditSession": session,
    }.items():
        monkeypatch.setattr(events_router, name, value)
    viewer = events_router._reauthorize_in_database(EventPrincipal("token"))
    assert viewer is not None
    # An administrator gets the listed sheets, never a wildcard.
    assert viewer.worksheet_ids == frozenset({sheet_id})
    assert calls == [(database, user, org_id)]
    assert f"worksheet:{sheet_id}" in _access_signature(viewer)
