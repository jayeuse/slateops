"""Read-side projections for record trigger activity."""

from sqlalchemy import literal, select, tuple_
from sqlalchemy.orm import Session

from app.common.listing import capped_count, capped_pagination
from app.common.listing.cursor import cursor_with_offset, decode_cursor, encode_cursor
from app.systems.sandbox.record_triggers.models import (
    RecordTrigger,
    RecordTriggerEvent,
    RecordTriggerRun,
)
from app.systems.sandbox.record_triggers.schemas import (
    TriggerRunListResponse,
    TriggerRunResponse,
)


def list_recent_runs(
    db: Session, *, limit: int, offset: int, cursor: str | None = None
) -> TriggerRunListResponse:
    live = select(RecordTriggerRun.id).where(RecordTriggerRun.is_deleted.is_(False))
    newest_first = (RecordTriggerRun.created_at.desc(), RecordTriggerRun.id.desc())
    # The count never gets the cursor: the total is the whole list's, as on page 1. Unlike the
    # audit count, it reads in index order: unordered, `LIMIT 10001` chose a sequential scan
    # that read every run for an organization with none (K64; 345 pages became 3).
    counted = int(db.scalar(capped_count(live.order_by(*newest_first))) or 0)
    after = live
    if cursor is not None:
        if offset:
            raise cursor_with_offset()
        at, identity = decode_cursor(cursor)
        after = live.where(
            tuple_(RecordTriggerRun.created_at, RecordTriggerRun.id)
            < tuple_(
                literal(at, RecordTriggerRun.created_at.type),
                literal(identity, RecordTriggerRun.id.type),
            )
        )
    # Page the run IDs first: joining before OFFSET joined every skipped run, so a deep
    # page cost 64 ms at 8,659 runs instead of about 2 ms. One more ID says whether more follow.
    page = after.order_by(*newest_first).offset(offset).limit(limit + 1).subquery()
    rows, pagination = capped_pagination(
        limit=limit,
        offset=offset,
        rows=db.execute(
            select(RecordTriggerRun, RecordTrigger, RecordTriggerEvent)
            .join(page, page.c.id == RecordTriggerRun.id)
            .join(RecordTrigger, RecordTrigger.id == RecordTriggerRun.trigger_id)
            .join(RecordTriggerEvent, RecordTriggerEvent.id == RecordTriggerRun.event_id)
            .order_by(*newest_first)
        ).all(),
        counted=counted,
    )
    items = [
        TriggerRunResponse(
            id=run.id,
            created_at=run.created_at,
            trigger_id=definition.id,
            trigger_name=definition.name,
            event_kind=event.event_kind,
            state=run.state,
            details=run.details,
            attempts=event.attempt_count,
        )
        for run, definition, event in rows
    ]
    return TriggerRunListResponse(
        items=items,
        limit=limit,
        offset=offset,
        count=len(items),
        total=pagination.total,
        total_is_capped=pagination.total_is_capped,
        has_more=pagination.has_more,
        # The last returned run, never the extra run that only said more follow.
        next_cursor=encode_cursor(rows[-1][0].created_at, rows[-1][0].id)
        if pagination.has_more
        else None,
    )
