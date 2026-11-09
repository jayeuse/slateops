"""One statement that tells the scheduler when each kind of work is next due.

Run in a bound organization (row-level security reads one organization at a time). Each
kind's time is the least of its pending ``next_attempt_at`` (new work and retries) and
its running ``lease_expires_at`` (a lease that expires is claimable again), so a retry
back-off and an abandoned lease are honored on time. Reports add the enabled schedules'
``next_due_at``; Comms adds export cleanup. None means nothing of that kind is queued.
Each part is a ``min`` over a due index (``ix_scheduled_work_due``,
``ix_scheduled_work_expired``, ``ix_record_trigger_events_due``,
``ix_report_schedules_due``, ``ix_comms_exports_cleanup``).

Each part reads only times up to ``HORIZON`` from now (P1). No due index starts with
``org_id``, so an unbounded ``min`` in an organization with nothing due steps over every
other organization's later rows. A time past the horizon reads as None: the scheduler's
30-second safety poll (``worker._SAFETY_SECONDS``) probes again before it comes due.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Engine, ScalarSelect, SQLColumnExpression, func, select

from app.core.database.organization_scope import bound_organization_column
from app.core.database.session import AuditSession
from app.systems.comms.jobs.models import CommsExport
from app.systems.openview.reports.schedule_models import ReportSchedule
from app.systems.platform.scheduling.models import ScheduledWork, WorkKind, WorkState
from app.systems.sandbox.record_triggers.models import RecordTriggerEvent, TriggerEventState

REPORTS = "reports"
POSTS = "posts"
REMINDERS = "reminders"
COMMS = "comms"
TRIGGERS = "triggers"

# Two safety polls (``worker._SAFETY_SECONDS`` = 30): a later time is seen by a later probe.
HORIZON = timedelta(seconds=60)

_WORK_KINDS: dict[str, tuple[WorkKind, ...]] = {
    REPORTS: (WorkKind.REPORT_RUN,),
    POSTS: (WorkKind.POST_PUBLISH,),
    REMINDERS: (WorkKind.EVENT_REMINDER,),
    COMMS: (
        WorkKind.COMMS_SCHEDULED_MESSAGE,
        WorkKind.COMMS_EXPORT,
        WorkKind.COMMS_LINK_PREVIEW,
    ),
}


def _soon(column: SQLColumnExpression[datetime | None]) -> ColumnElement[bool]:
    return column <= func.now() + HORIZON


def _work(kind: WorkKind) -> list[ScalarSelect[Any]]:
    bound = ScheduledWork.org_id == bound_organization_column()
    return [
        select(func.min(ScheduledWork.next_attempt_at))
        .where(
            bound, ScheduledWork.kind == kind, ScheduledWork.state == WorkState.PENDING,
            _soon(ScheduledWork.next_attempt_at),
        )
        .scalar_subquery(),
        select(func.min(ScheduledWork.lease_expires_at))
        .where(
            bound, ScheduledWork.kind == kind, ScheduledWork.state == WorkState.RUNNING,
            _soon(ScheduledWork.lease_expires_at),
        )
        .scalar_subquery(),
    ]


def _schedules() -> ScalarSelect[Any]:
    return (
        select(func.min(ReportSchedule.next_due_at))
        .where(
            ReportSchedule.org_id == bound_organization_column(),
            ReportSchedule.enabled.is_(True),
            ReportSchedule.is_deleted.is_(False),
            ReportSchedule.deleted_at.is_(None),
            _soon(ReportSchedule.next_due_at),
        )
        .scalar_subquery()
    )


def _export_cleanup() -> ScalarSelect[Any]:
    # A pending cleanup with no time is due at once, as the export worker reads it.
    due = func.coalesce(CommsExport.cleanup_after, func.now())
    return (
        select(func.min(due))
        .where(
            CommsExport.org_id == bound_organization_column(),
            CommsExport.cleanup_pending.is_(True),
            _soon(due),
        )
        .scalar_subquery()
    )


def _triggers() -> list[ScalarSelect[Any]]:
    bound = RecordTriggerEvent.org_id == bound_organization_column()
    return [
        select(func.min(RecordTriggerEvent.next_attempt_at))
        .where(
            bound, RecordTriggerEvent.state == TriggerEventState.PENDING,
            _soon(RecordTriggerEvent.next_attempt_at),
        )
        .scalar_subquery(),
        select(func.min(RecordTriggerEvent.lease_expires_at))
        .where(
            bound, RecordTriggerEvent.state == TriggerEventState.RUNNING,
            _soon(RecordTriggerEvent.lease_expires_at),
        )
        .scalar_subquery(),
    ]


def _columns() -> dict[str, ColumnElement[datetime]]:
    parts: dict[str, list[ScalarSelect[Any]]] = {
        name: [part for kind in kinds for part in _work(kind)]
        for name, kinds in _WORK_KINDS.items()
    }
    parts[REPORTS].append(_schedules())
    parts[COMMS].append(_export_cleanup())
    parts[TRIGGERS] = _triggers()
    # LEAST ignores NULL parts; all NULL gives NULL.
    return {name: func.least(*values).label(name) for name, values in parts.items()}


def probe_due(engine: Engine) -> dict[str, datetime | None]:
    """When each kind is next due in the bound organization, in one statement."""

    columns = _columns()
    with AuditSession(bind=engine) as db:
        row = db.execute(select(*columns.values())).one()
    return dict(zip(columns, row, strict=True))
