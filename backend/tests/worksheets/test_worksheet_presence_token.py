"""The D13 presence token, `POST /api/worksheets/{id}/presence-token` (PR3, PR5, PR6; SH-64 to 66).

Only a person who can see the sheet gets a 60-second ``realtime_presence`` token bound to
the sheet topic, with a join grant that expires with it. A hidden sheet answers the same
404 as a missing one. Each request reads access again, and the issuance has its own
per-person budget. Presence writes no audit row and publishes no sheet event.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.core.config import get_settings
from app.systems.comms.realtime.models import CommsRealtimeAdmission
from app.systems.manage.audit.listeners import REALTIME_INVALIDATION_KEY
from app.systems.manage.audit.models import AuditLog
from app.systems.openview.worksheets.models import WorksheetRealtimeGrant, WorksheetShare
from tests.rbac.support import _client
from tests.realtime.test_realtime_tokens import _public_key
from tests.worksheets.support import SheetWorld, sheet_world

pytestmark = pytest.mark.integration
PATH = "/api/worksheets/{}/presence-token"


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def world(integration_db: Session) -> SheetWorld:
    return sheet_world(integration_db)


def _issue(application: FastAPI, db: Session, person: Any, sheet_id: UUID) -> Any:
    return _client(application, person, db).post(PATH.format(sheet_id))


def _grants(db: Session, sheet_id: UUID) -> dict[UUID, datetime]:
    return {
        row.user_id: row.expires_at
        for row in db.scalars(
            select(WorksheetRealtimeGrant)
            .where(WorksheetRealtimeGrant.worksheet_id == sheet_id)
            .execution_options(populate_existing=True)
        )
    }


def test_a_person_who_sees_the_sheet_gets_a_60_second_token_for_its_topic(
    application: FastAPI, world: SheetWorld, integration_db: Session,
) -> None:
    """SH-64, PR3: the token names only this sheet's topic; the grant expires with it."""

    db, sheet = integration_db, world.sheet
    topic = f"org:{sheet.org_id}:worksheet:{sheet.id}"
    response = _issue(application, db, world.viewer, sheet.id)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"token", "topic", "expires_at", "viewers"}
    assert body["topic"] == topic
    assert body["viewers"] == [str(world.viewer.id)]
    claims = jwt.decode(
        body["token"], _public_key(get_settings()).key, algorithms=["ES256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims == {
        "iss": claims["iss"], "sub": str(world.viewer.id), "role": "authenticated",
        "org_id": str(sheet.org_id), "purpose": "realtime_presence", "topic": topic,
        "iat": claims["iat"], "exp": claims["iat"] + 60,
    }
    assert claims["iss"].endswith("/api/realtime")
    expires_at = datetime.fromtimestamp(claims["exp"], UTC)
    assert datetime.fromisoformat(body["expires_at"]) == expires_at
    assert _grants(db, sheet.id) == {world.viewer.id: expires_at}

    # Every person who can see the sheet joins; viewers lists the live grants, sorted.
    for person in (world.owner, world.editor, world.group_member, world.guest):
        assert _issue(application, db, person, sheet.id).status_code == 200
    owner = _issue(application, db, world.owner, sheet.id).json()
    expected = sorted(str(person.id) for person in (
        world.owner, world.viewer, world.editor, world.group_member, world.guest,
    ))
    assert owner["viewers"] == expected
    assert len(_grants(db, sheet.id)) == 5  # a refresh renews the same grant


def test_people_who_cannot_see_the_sheet_get_the_missing_sheet_404(
    application: FastAPI, world: SheetWorld, integration_db: Session,
) -> None:
    """SH-64: a peer, a module manager and an admin get the 404 of a random ID; no grant."""

    db = integration_db
    missing = _issue(application, db, world.peer, uuid4())
    assert missing.status_code == 404
    for person in (world.peer, world.manager, world.admin, world.outsider):
        refused = _issue(application, db, person, world.sheet.id)
        assert (refused.status_code, refused.json()["detail"]) == (404, missing.json()["detail"])
        assert "token" not in refused.text
    assert _grants(db, world.sheet.id) == {}
    world.sheet.is_deleted, world.sheet.deleted_at = True, utc_now()
    db.flush()
    gone = _issue(application, db, world.owner, world.sheet.id)
    assert (gone.status_code, gone.json()["detail"]) == (404, missing.json()["detail"])


def test_a_refresh_after_losing_the_share_is_refused_and_drops_the_grant(
    application: FastAPI, world: SheetWorld, integration_db: Session,
) -> None:
    """SH-65, PR5: each refresh checks access again; the refused person's grant goes."""

    db = integration_db
    assert _issue(application, db, world.viewer, world.sheet.id).status_code == 200
    assert _issue(application, db, world.owner, world.sheet.id).status_code == 200
    share = db.scalars(select(WorksheetShare).where(
        WorksheetShare.worksheet_id == world.sheet.id, WorksheetShare.user_id == world.viewer.id,
    )).one()
    share.is_deleted, share.deleted_at = True, utc_now()
    db.flush()
    assert _issue(application, db, world.viewer, world.sheet.id).status_code == 404
    assert set(_grants(db, world.sheet.id)) == {world.owner.id}
    # An expired grant is not a viewer.
    owner_grant = db.scalars(select(WorksheetRealtimeGrant).where(
        WorksheetRealtimeGrant.user_id == world.owner.id,
    )).one()
    owner_grant.expires_at = utc_now() - timedelta(seconds=1)
    db.flush()
    editor = _issue(application, db, world.editor, world.sheet.id).json()
    assert editor["viewers"] == [str(world.editor.id)]


def test_token_issuance_has_its_own_per_person_budget(
    application: FastAPI, world: SheetWorld, integration_db: Session,
) -> None:
    """D13: twelve issuances a minute per person; refusals count; Comms is untouched."""

    db = integration_db
    for _ in range(6):
        assert _issue(application, db, world.peer, world.sheet.id).status_code == 404
    for _ in range(6):
        assert _issue(application, db, world.peer, uuid4()).status_code == 404
    limited = _issue(application, db, world.peer, world.sheet.id)
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["retry-after"]) <= 60
    assert limited.headers["cache-control"] == "no-store"
    for _ in range(12):
        assert _issue(application, db, world.viewer, world.sheet.id).status_code == 200
    refused = _issue(application, db, world.viewer, world.sheet.id)
    assert refused.status_code == 429
    assert "token" not in refused.text
    assert _issue(application, db, world.owner, world.sheet.id).status_code == 200
    assert db.scalars(select(CommsRealtimeAdmission.id).where(
        CommsRealtimeAdmission.user_id.in_((world.peer.id, world.viewer.id)),
    )).all() == []


def test_presence_writes_no_audit_row_and_publishes_no_sheet_event(
    application: FastAPI, world: SheetWorld, integration_db: Session,
) -> None:
    """SH-66, PR6, D14 C4: the grant table is unaudited and publishes nothing."""

    db = integration_db
    db.info.pop(REALTIME_INVALIDATION_KEY, None)
    db.add(WorksheetRealtimeGrant(
        org_id=world.sheet.org_id, user_id=world.peer.id, worksheet_id=world.sheet.id,
        expires_at=utc_now() + timedelta(seconds=60),
    ))
    db.flush()
    assert db.info.get(REALTIME_INVALIDATION_KEY, []) == []
    assert _issue(application, db, world.viewer, world.sheet.id).status_code == 200
    assert db.scalars(select(AuditLog.id).where(
        AuditLog.entity_type == "worksheet_realtime_grants",
    )).all() == []


def test_expired_grants_are_swept_and_an_authority_write_drops_stale_ones(
    world: SheetWorld, integration_db: Session,
) -> None:
    """PR5: the worker sweep removes expired grants only; the Comms cleanup after an
    authority write also removes the grants of people who no longer see their sheet."""

    from app.systems.comms.realtime.grants import revoke_stale
    from app.systems.openview.worksheets.presence import sweep_expired_grants

    db, sheet = integration_db, world.sheet
    now = utc_now()
    for person, seconds in ((world.owner, 60), (world.viewer, 60), (world.editor, -1),
                            (world.peer, 60)):
        db.add(WorksheetRealtimeGrant(
            org_id=sheet.org_id, user_id=person.id, worksheet_id=sheet.id,
            expires_at=now + timedelta(seconds=seconds),
        ))
    db.flush()
    assert sweep_expired_grants(db, now) == 1
    assert set(_grants(db, sheet.id)) == {world.owner.id, world.viewer.id, world.peer.id}
    share = db.scalars(select(WorksheetShare).where(
        WorksheetShare.worksheet_id == sheet.id, WorksheetShare.user_id == world.viewer.id,
    )).one()
    share.is_deleted, share.deleted_at = True, utc_now()
    db.flush()
    revoke_stale(db)
    db.flush()
    assert set(_grants(db, sheet.id)) == {world.owner.id}
