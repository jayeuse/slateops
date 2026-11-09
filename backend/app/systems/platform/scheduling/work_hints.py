"""Add a work hint to a transaction that queues or reschedules background work.

``scheduled_work`` and ``record_trigger_events`` are not audited, and the audited
``report_schedules`` publishes no invalidation, so no event announces their changes. This
listener adds one invalidation, ``work_scheduled`` or ``work_triggers`` with the
organization only, to the transaction's post-commit buffer (``audit/listeners.py``). The
publisher thread sends it after commit on its own connection, so the request runs no extra
statement (DBI-8); a rolled back transaction or savepoint drops it with the other events.
It reads only loaded attribute state: it never emits SQL.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.database.organization_scope import session_organization
from app.core.database.session import AuditSession
from app.systems.manage.audit.listeners import REALTIME_INVALIDATION_KEY
from app.systems.openview.reports.schedule_models import ReportSchedule
from app.systems.platform.events.models import InvalidationEvent
from app.systems.platform.scheduling.models import ScheduledWork
from app.systems.platform.scheduling.work_signals import WORK_SCHEDULED, WORK_TRIGGERS
from app.systems.sandbox.record_triggers.models import RecordTriggerEvent

_PENDING = "pending"
# A change to one of these columns can make a queued row due sooner.
_WAKE_COLUMNS = ("state", "next_attempt_at")


def _loaded(instance: Any, key: str) -> Any:
    return inspect(instance).dict.get(key)


def _changed(instance: Any) -> bool:
    attrs = inspect(instance).attrs
    return any(attrs[key].history.has_changes() for key in _WAKE_COLUMNS)


def _waiting(instance: Any) -> bool:
    """A queued row a worker may claim: pending, or of a state not loaded (assume so)."""

    state = _loaded(instance, "state")
    return state is None or str(state) == _PENDING


def _hint(session: Session, instance: Any) -> str | None:
    if isinstance(instance, RecordTriggerEvent):
        entity = WORK_TRIGGERS
    elif isinstance(instance, ScheduledWork):
        entity = WORK_SCHEDULED
    elif isinstance(instance, ReportSchedule):
        return WORK_SCHEDULED
    else:
        return None
    if instance in session.new:
        return entity if _waiting(instance) else None
    return entity if _changed(instance) and _waiting(instance) else None


@event.listens_for(AuditSession, "before_flush")
def add_work_hints(session: AuditSession, _flush_context: Any, _instances: Any) -> None:
    hints: set[tuple[str, UUID]] = set()
    for instance in (*session.new, *session.dirty):
        entity = _hint(session, instance)
        if entity is None:
            continue
        org_id = _loaded(instance, "org_id") or session_organization(session)
        if isinstance(org_id, UUID):
            hints.add((entity, org_id))
    if hints:
        session.info.setdefault(REALTIME_INVALIDATION_KEY, []).extend(
            InvalidationEvent(entity, org_id=org_id) for entity, org_id in sorted(hints)
        )
