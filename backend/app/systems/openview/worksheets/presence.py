"""Sheet presence: the 60-second presence token and its join grant (spec PR3-PR6, D13).

``POST /worksheets/{id}/presence-token`` charges the person's own budget first, so a
refusal also costs. It then reads the access rule again, under the grant's own lock, and
answers a hidden sheet with the same 404 as a missing one (dropping any grant the person
still holds there) at once, without waiting on any writer. For a visible sheet it reads
access again once it holds the sheet row for share, so a share removal or a delete in
progress finishes first; both drop the grants they end. A visible sheet gets a token
that joins only its topic and a grant that expires with the token.
Presence itself never touches the database: grants are unaudited, publish no event, and
are swept once expired or once the person no longer sees the sheet.
"""

from datetime import datetime, timedelta
from math import ceil
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.dependencies import get_current_user
from app.core import base_model
from app.core.config import get_settings
from app.core.database import get_db
from app.core.database.organization_scope import bound_organization_column
from app.systems.access.identity.models import IdentityRateLimitBucket
from app.systems.access.identity.rate_limits import lock_bucket, rate_limit_fingerprint
from app.systems.access.policy.transaction_access import forget_access
from app.systems.access.users.membership import bound_organization
from app.systems.access.users.models import User
from app.systems.openview.worksheets.access import (
    load_visible_worksheet,
    visible_worksheet_clause,
)
from app.systems.openview.worksheets.locking import lock_sheet_for_read, locked_read
from app.systems.openview.worksheets.models import Worksheet, WorksheetRealtimeGrant
from app.systems.openview.worksheets.row_writes import error
from app.systems.platform.realtime.tokens import mint_presence_token


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
Actor = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]

# A viewer refreshes every 45 s per open sheet; twelve a minute leaves room for several
# open sheets and reloads. Separate from the OpenComms token budget (D13).
BUDGET = 12
BUDGET_WINDOW = timedelta(seconds=60)


class SheetPresenceToken(BaseModel):
    token: str
    topic: str
    expires_at: datetime
    viewers: list[UUID]


def presence_topic(org_id: UUID, worksheet_id: UUID) -> str:
    return f"org:{org_id}:worksheet:{worksheet_id}"


def _charge(db: Session, org_id: UUID, user_id: UUID, now: datetime) -> None:
    """One issuance from the person's budget, committed before any access read."""

    fingerprint = rate_limit_fingerprint("worksheet-presence", f"{org_id}:{user_id}", None)
    bucket = lock_bucket(db, fingerprint)
    if bucket is None:
        bucket = IdentityRateLimitBucket(
            fingerprint=fingerprint, attempt_count=0, window_started_at=now
        )
        db.add(bucket)
    elif now - bucket.window_started_at >= BUDGET_WINDOW:
        bucket.window_started_at, bucket.attempt_count = now, 0
    if bucket.attempt_count >= BUDGET:
        retry = (bucket.window_started_at + BUDGET_WINDOW - now).total_seconds()
        db.commit()
        refused = error(status.HTTP_429_TOO_MANY_REQUESTS, "presence_rate_limited",
                        "Wait before joining again")
        refused.headers = {"Retry-After": str(max(1, ceil(retry))), "Cache-Control": "no-store"}
        raise refused
    bucket.attempt_count += 1
    db.commit()


def _lock_grant(db: Session, org_id: UUID, user_id: UUID, worksheet_id: UUID) -> None:
    db.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"worksheets:presence-grant:{org_id}:{user_id}:{worksheet_id}"},
    )


def _grant(db: Session, org_id: UUID, user_id: UUID, worksheet_id: UUID) -> (
    WorksheetRealtimeGrant | None
):
    return locked_read(db, lambda: db.scalars(
        select(WorksheetRealtimeGrant)
        .where(
            WorksheetRealtimeGrant.org_id == org_id,
            WorksheetRealtimeGrant.user_id == user_id,
            WorksheetRealtimeGrant.worksheet_id == worksheet_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none())


def _visible(db: Session, user_id: UUID, worksheet_id: UUID) -> bool:
    """The access rule from fresh reads."""

    forget_access(db, user_id)
    actor = db.get(User, user_id, populate_existing=True)
    return actor is not None and load_visible_worksheet(db, actor, worksheet_id) is not None


def _refuse(db: Session, org_id: UUID, user_id: UUID, worksheet_id: UUID) -> NoReturn:
    """The 404 of a missing sheet; the person's grant there, if any, goes."""

    grant = _grant(db, org_id, user_id, worksheet_id)
    if grant is not None:
        db.delete(grant)
    db.commit()
    raise error(status.HTTP_404_NOT_FOUND, "worksheet_not_found", "Sheet not found")


@router.post(
    "/worksheets/{worksheet_id}/presence-token", response_model=SheetPresenceToken,
    responses={
        404: {"description": "The sheet is missing, deleted or not visible"},
        429: {
            "description": "Twelve presence tokens a minute per person",
            "headers": {"Retry-After": {"schema": {"type": "integer", "minimum": 1}}},
        },
    },
)
def issue_presence_token(worksheet_id: UUID, user: Actor, db: Database) -> SheetPresenceToken:
    """A 60-second token for the sheet's presence topic, for a person who can see it."""

    org_id, user_id = bound_organization(db), user.id
    _charge(db, org_id, user_id, base_model.utc_now())
    _lock_grant(db, org_id, user_id, worksheet_id)
    # A hidden sheet answers like a missing one at once, without waiting on any writer.
    if not _visible(db, user_id, worksheet_id):
        _refuse(db, org_id, user_id, worksheet_id)
    # A share removal or a delete holds the sheet row for update: read access again after it.
    lock_sheet_for_read(db, worksheet_id)
    if not _visible(db, user_id, worksheet_id):
        _refuse(db, org_id, user_id, worksheet_id)
    grant = _grant(db, org_id, user_id, worksheet_id)
    topic = presence_topic(org_id, worksheet_id)
    token, expires_at = mint_presence_token(
        get_settings(), user_id=user_id, org_id=org_id, topic=topic, now=base_model.utc_now()
    )
    if grant is None:
        db.add(WorksheetRealtimeGrant(
            org_id=org_id, user_id=user_id, worksheet_id=worksheet_id, expires_at=expires_at
        ))
    else:
        grant.expires_at = expires_at
    db.flush()
    viewers = db.scalars(
        select(WorksheetRealtimeGrant.user_id).where(
            WorksheetRealtimeGrant.org_id == org_id,
            WorksheetRealtimeGrant.worksheet_id == worksheet_id,
            WorksheetRealtimeGrant.expires_at > base_model.utc_now(),
        )
    ).all()
    db.commit()
    return SheetPresenceToken(
        token=token, topic=topic, expires_at=expires_at,
        viewers=sorted(viewers, key=str),
    )


def sweep_expired_grants(db: Session, now: datetime) -> int:
    """One worker pass for the bound organization; the caller commits."""

    rows = db.scalars(
        select(WorksheetRealtimeGrant).where(
            WorksheetRealtimeGrant.org_id == bound_organization_column(),
            WorksheetRealtimeGrant.expires_at <= now,
        )
    ).all()
    for row in rows:
        db.delete(row)
    return len(rows)


def revoke_stale_grants(db: Session, worksheet_id: UUID | None = None) -> None:
    """After an authority write, a removed share or a deleted sheet: drop the grants of
    people who no longer see their sheet (one sheet's, or the organization's).

    It never renews or adds a grant; only the token route does that.
    """

    db.flush()
    rows = db.scalars(
        select(WorksheetRealtimeGrant).where(
            WorksheetRealtimeGrant.org_id == bound_organization_column(),
            *([WorksheetRealtimeGrant.worksheet_id == worksheet_id]
              if worksheet_id is not None else []),
        )
    ).all()
    sheets: dict[UUID, set[UUID]] = {}
    for row in rows:
        sheets.setdefault(row.user_id, set()).add(row.worksheet_id)
    for user_id, granted in sheets.items():
        forget_access(db, user_id)
        actor = db.get(User, user_id, populate_existing=True)
        visible = set(db.scalars(
            select(Worksheet.id).where(
                Worksheet.id.in_(granted), visible_worksheet_clause(db, actor)
            )
        )) if actor is not None else set()
        for row in rows:
            if row.user_id == user_id and row.worksheet_id not in visible:
                db.delete(row)
