"""Sheet presence topics in the Realtime join function and the write policy (D13, SH-71).

A ``worksheet:`` topic admits only a 60-second ``realtime_presence`` token whose ``topic``
claim names exactly that topic, with a live grant for the same person on a sheet that is
not deleted. Every other topic keeps requiring the OpenComms ``realtime`` token. Browsers
may write only presence, and only on sheet topics (besides the retained ``probe``).
"""

import json
import os
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session
from websockets.sync.client import ClientConnection

from app.core.base_model import utc_now
from app.core.config import get_settings
from app.systems.openview.worksheets.models import Worksheet, WorksheetRealtimeGrant
from app.systems.platform.realtime.tokens import mint_presence_token, mint_realtime_token
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from operations import provision_database_role as provisioner
from tests.conftest import (
    create_member,
    create_organization,
    guarded_create_engine,
    membership_of,
)
from tests.realtime.test_realtime_channel_acceptance import _assert_refused, _read_until, _socket
from tests.worksheets.support import STRUCTURE, SheetWorld, add_sheet, sheet_world

pytestmark = pytest.mark.integration


def _can_join(connection: Connection, topic: str, claims: dict[str, object]) -> bool:
    with connection.begin_nested():
        connection.execute(
            text("SELECT set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps(claims)},
        )
        return bool(
            connection.scalar(
                text("SELECT public.can_join_realtime_topic(:topic)"), {"topic": topic}
            )
        )


def _topic(org_id: UUID, sheet_id: UUID) -> str:
    return f"org:{org_id}:worksheet:{sheet_id}"


def _presence(user_id: UUID, org_id: UUID, topic: str) -> dict[str, object]:
    return {
        "role": "authenticated",
        "purpose": "realtime_presence",
        "sub": str(user_id),
        "org_id": str(org_id),
        "topic": topic,
    }


def _comms(user_id: UUID, org_id: UUID) -> dict[str, object]:
    return {
        "role": "authenticated",
        "purpose": "realtime",
        "sub": str(user_id),
        "org_id": str(org_id),
    }


def _grant(db: Session, world: SheetWorld, user_id: UUID, sheet_id: UUID,
           seconds: int = 60) -> WorksheetRealtimeGrant:
    grant = WorksheetRealtimeGrant(
        org_id=world.sheet.org_id, user_id=user_id, worksheet_id=sheet_id,
        expires_at=utc_now() + timedelta(seconds=seconds),
    )
    db.add(grant)
    db.flush()
    return grant


def test_a_presence_token_joins_only_its_own_live_sheet_topic(integration_owner_db):
    """SH-71: the topic claim, the grant, the purpose and the organization all bind."""

    db = integration_owner_db
    world = sheet_world(db)
    org = world.sheet.org_id
    second = add_sheet(db, world.owner, record=world.record)
    topic, other_topic = _topic(org, world.sheet.id), _topic(org, second.id)
    _grant(db, world, world.viewer.id, world.sheet.id)
    _grant(db, world, world.viewer.id, second.id)
    connection = db.connection()
    claims = _presence(world.viewer.id, org, topic)

    assert _can_join(connection, topic, claims)
    # The OpenComms token is refused on a sheet topic even with a live grant.
    assert not _can_join(connection, topic, _comms(world.viewer.id, org))
    # A presence token opens no other topic, even one the person has a grant for.
    assert not _can_join(connection, other_topic, claims)
    for suffix in ("probe", "presence", f"user:{world.viewer.id}", f"conversation:{uuid4()}"):
        assert not _can_join(connection, f"org:{org}:{suffix}", claims)
    other = create_organization(db)
    assert not _can_join(connection, _topic(other.id, world.sheet.id), claims)
    assert not _can_join(
        connection, _topic(other.id, world.sheet.id),
        _presence(world.viewer.id, other.id, _topic(other.id, world.sheet.id)),
    )
    # The claim must name the topic exactly.
    for claimed in (other_topic, topic.upper(), topic + " ", None):
        assert not _can_join(connection, topic, {**claims, "topic": claimed})
    no_topic = {key: value for key, value in claims.items() if key != "topic"}
    assert not _can_join(connection, topic, no_topic)
    assert not _can_join(connection, topic, {**claims, "role": "anon"})
    assert not _can_join(connection, f"org:{org}:worksheet:not-a-uuid",
                         {**claims, "topic": f"org:{org}:worksheet:not-a-uuid"})
    # Someone else's token, and a person without a grant, are refused.
    assert not _can_join(connection, topic, _presence(world.peer.id, org, topic))
    assert not _can_join(connection, topic, _presence(world.editor.id, org, topic))


def test_the_join_ends_with_the_grant_the_sheet_or_the_membership(integration_owner_db):
    """PR5, SH-65: an expired grant, a deleted sheet or an ended membership refuses the join."""

    db = integration_owner_db
    world = sheet_world(db)
    org = world.sheet.org_id
    topic = _topic(org, world.sheet.id)
    connection = db.connection()
    claims = _presence(world.viewer.id, org, topic)
    grant = _grant(db, world, world.viewer.id, world.sheet.id)
    assert _can_join(connection, topic, claims)

    grant.expires_at = utc_now() - timedelta(seconds=1)
    db.flush()
    assert not _can_join(connection, topic, claims)

    grant.expires_at = utc_now() + timedelta(seconds=60)
    world.sheet.is_deleted, world.sheet.deleted_at = True, utc_now()
    db.flush()
    assert not _can_join(connection, topic, claims)

    world.sheet.is_deleted, world.sheet.deleted_at = False, None
    db.flush()
    assert _can_join(connection, topic, claims)
    membership_of(db, world.viewer.id).status = "disabled"
    db.flush()
    assert not _can_join(connection, topic, claims)


def test_the_existing_topics_still_need_the_opencomms_token(integration_owner_db):
    """The ``realtime`` branches are unchanged: the presence purpose opens none of them."""

    db = integration_owner_db
    world = sheet_world(db)
    org = world.sheet.org_id
    connection = db.connection()
    comms = _comms(world.viewer.id, org)
    for suffix in ("probe", "presence", f"user:{world.viewer.id}"):
        assert _can_join(connection, f"org:{org}:{suffix}", comms)
        assert not _can_join(
            connection, f"org:{org}:{suffix}", {**comms, "purpose": "realtime_presence"}
        )


def test_grant_rows_are_unique_per_person_and_sheet_and_go_with_the_sheet(
    integration_owner_db,
):
    """One grant per organization, person and sheet; purging the sheet removes its grants."""

    from sqlalchemy.exc import IntegrityError

    db = integration_owner_db
    world = sheet_world(db)
    _grant(db, world, world.viewer.id, world.sheet.id)
    with db.begin_nested(), pytest.raises(IntegrityError):
        _grant(db, world, world.viewer.id, world.sheet.id)
    sheet = add_sheet(db, world.owner, record=world.record)
    _grant(db, world, world.viewer.id, sheet.id)
    db.connection().execute(
        text("DELETE FROM public.worksheets WHERE id = :id"), {"id": sheet.id}
    )
    assert db.connection().scalar(
        text("SELECT count(*) FROM public.worksheet_realtime_grants WHERE worksheet_id = :id"),
        {"id": sheet.id},
    ) == 0


def test_the_write_policy_admits_presence_only_on_sheet_topics(integration_owner_db):
    """The provisioned write policy is exactly the managed expression: probe writes stay,
    and a sheet topic accepts the ``presence`` extension only (no broadcast)."""

    connection = integration_owner_db.connection()
    with connection.begin_nested():
        connection.execute(text("SET LOCAL search_path TO pg_catalog"))
        expression = connection.scalar(
            text(
                "SELECT pg_get_expr(polwithcheck, polrelid) FROM pg_policy "
                "JOIN pg_class ON pg_class.oid = pg_policy.polrelid "
                "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
                "WHERE nspname = 'realtime' AND relname = 'messages' "
                "AND polname = 'slateops_realtime_member_write'"
            )
        )
    assert expression == provisioner.REALTIME_WRITE_EXPRESSION
    assert "extension = 'presence'::text" in expression
    assert "'org:%:worksheet:%'::text" in expression


@pytest.fixture
def live_sheet() -> Iterator[tuple[UUID, UUID, UUID]]:
    """A committed organization, member, sheet and live grant that Realtime can read."""

    engine = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"])
    with Session(engine) as db:
        organization = create_organization(db)
        member, _membership = create_member(db, organization)
        department = Department(org_id=organization.id, department_name=f"Live {uuid4().hex}")
        db.add(department)
        db.flush()
        module = Module(org_id=organization.id, department_id=department.id,
                        module_name=f"Live {uuid4().hex}")
        db.add(module)
        db.flush()
        sheet = Worksheet(org_id=organization.id, module_id=module.id, owner_id=member.id,
                          title="Live", structure=dict(STRUCTURE))
        db.add(sheet)
        db.flush()
        db.add(WorksheetRealtimeGrant(org_id=organization.id, user_id=member.id,
                                      worksheet_id=sheet.id,
                                      expires_at=utc_now() + timedelta(seconds=60)))
        ids = (organization.id, member.id, sheet.id)
        db.commit()
    try:
        yield ids
    finally:
        with engine.begin() as connection:
            parameters = {"org": ids[0], "user": ids[1]}
            for statement in (
                "DELETE FROM public.worksheets WHERE org_id = :org",
                "DELETE FROM public.modules WHERE org_id = :org",
                "DELETE FROM public.departments WHERE org_id = :org",
                "DELETE FROM public.memberships WHERE user_id = :user",
                "DELETE FROM public.audit_logs WHERE org_id = :org",
                "DELETE FROM public.users WHERE id = :user",
                "DELETE FROM public.organizations WHERE id = :org",
            ):
                connection.execute(text(statement), parameters)
        engine.dispose()


def _push(ws: ClientConnection, topic: str, ref: str, event: str,
          payload: dict[str, Any]) -> None:
    ws.send(json.dumps({"topic": f"realtime:{topic}", "event": event, "ref": ref,
                        "join_ref": "1", "payload": payload}))


def test_a_sheet_topic_takes_presence_and_drops_broadcasts(
    live_sheet: tuple[UUID, UUID, UUID],
) -> None:
    """SH-71 on the live Realtime service: the presence token joins its topic and tracks a
    cell; a broadcast on the topic reaches no one; the OpenComms token cannot join it and
    the presence token cannot join the probe."""

    settings = get_settings()
    org, user, sheet = live_sheet
    topic = f"org:{org}:worksheet:{sheet}"
    token, _expires_at = mint_presence_token(settings, user_id=user, org_id=org, topic=topic)
    refused = "You do not have permissions to read from this Channel topic"
    _assert_refused(settings, topic, mint_realtime_token(settings, user_id=user,
                                                         org_id=org).token, refused)
    _assert_refused(settings, f"org:{org}:probe", token, refused)

    with _socket(settings) as ws:
        _push(ws, topic, "1", "phx_join", {
            "config": {"broadcast": {"self": True, "ack": True},
                       "presence": {"key": str(user), "enabled": True}, "private": True},
            "access_token": token,
        })
        joined = _read_until(ws, lambda m: m.get("event") == "phx_reply" and m.get("ref") == "1")
        assert joined is not None and joined["payload"]["status"] == "ok", joined
        marker = uuid4().hex
        seen: list[dict[str, Any]] = []
        _push(ws, topic, "forged", "broadcast",
              {"type": "broadcast", "event": "cursor", "payload": {"marker": marker}})
        _read_until(ws, lambda m: seen.append(m) or (
            m.get("event") == "phx_reply" and m.get("ref") == "forged"))
        cell = {"row_id": str(uuid4()), "column_key": "c1"}
        _push(ws, topic, "track", "presence",
              {"type": "presence", "event": "track", "payload": cell})
        tracked = _read_until(ws, lambda m: seen.append(m) or (
            m.get("event") == "presence_diff"
            and str(user) in m.get("payload", {}).get("joins", {})))
        assert tracked is not None, seen
        [meta] = tracked["payload"]["joins"][str(user)]["metas"]
        assert {key: meta[key] for key in cell} == cell
        assert all(marker not in json.dumps(message) for message in seen)
