"""Bounded background worker for published Sandbox triggers."""

from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta
from uuid import UUID

from app.core.base_model import utc_now
from app.core.config import Settings
from app.core.database.organization_scope import worker_organization
from app.core.database.session import AuditSession, get_engine
from app.core.observability import failure_cause, log_event
from app.systems.manage.health import signals
from app.systems.manage.workspace.organizations import active_organization_ids
from app.systems.platform.scheduling.work_signals import WorkSignals
from app.systems.sandbox.record_triggers.execution import (
    MAX_CLAIM_BATCH,
    ClaimedTriggerEvent,
    claim_due_events,
    mark_claim_failed,
    release_claim,
)
from app.systems.sandbox.record_triggers.outbox import (
    ScheduleDefinition,
    enqueue_due_schedules,
    next_schedule_minute,
    schedule_definitions,
)
from app.systems.sandbox.record_triggers.runner import execute_claim

# Every interval with work, log how many events ran, their mean run time and the longest
# wait from the record change to the run (the automation delay users see).
_METRICS_SECONDS = 10.0
# Shutdown waits this long in total for every lane to finish its current event.
_STOP_SECONDS = 5.0
# Lane 0 re-reads every organization's schedule definitions at least this often.
_DEFINITIONS_SECONDS = 30.0
_MINUTE = timedelta(minutes=1)


class TriggerWorker:
    """Claim and execute durable events on several lanes, woken by work, not by a timer.

    Each lane is one thread. It sleeps until it is handed organizations: by a work hint
    (``WorkSignals``), by the scheduler's due probe (a retry or an expired lease), or by
    another lane. At start every lane visits every organization. A lane claims a small
    batch from the shared queue (FOR UPDATE SKIP LOCKED) in each organization it holds,
    starting at a different one per lane, so a burst spreads over every lane; the claim
    keeps one record's events in order. A lane that ran events hands the same
    organizations to every lane: its runs may have queued follow-up events or freed a
    record's next event. Only lane 0 queues due schedules: it keeps each organization's
    published schedule definitions and wakes at the next local minute in which one fires.
    """

    def __init__(self, settings: Settings, *, work_signals: WorkSignals | None = None) -> None:
        self._enabled = settings.environment != "test" or settings.e2e_background_workers
        self._lanes = settings.trigger_workers
        self._claim_limit = max(1, MAX_CLAIM_BATCH // self._lanes)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._wake = threading.Condition()
        # Per lane, under ``_wake``: every organization, or these organizations, to visit.
        self._everything = [True] * self._lanes
        self._targets: list[set[UUID]] = [set() for _ in range(self._lanes)]
        # The organizations of each lane's current pass; absent: every organization.
        self._passes: dict[int, frozenset[UUID]] = {}
        self._schedule_at: datetime | None = None
        self._definitions: dict[UUID, list[ScheduleDefinition]] = {}
        self._stale: set[UUID] | None = None  # None: every organization
        self._refresh_at = 0.0
        self._next_minute: datetime | None = None
        self._handled_until: datetime | None = None
        self._failures = 0
        self._active_lanes = 0
        self._claim_retry_seconds = 1
        self._metrics_started = time.monotonic()
        self._metrics_count = 0
        self._metrics_run_ms = 0
        self._metrics_max_wait_ms = 0
        if work_signals is not None:
            work_signals.attach_triggers(self.hand, self.refresh_schedules)

    @property
    def running(self) -> bool:
        return self._active_lanes > 0

    def start(self) -> None:
        if not self._enabled or self._threads:
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=self._run,
                args=(lane,),
                name=f"slateops-triggers-{lane}",
                daemon=True,
            )
            for lane in range(self._lanes)
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> bool:
        self._stop.set()
        with self._wake:
            self._wake.notify_all()
        deadline = time.monotonic() + _STOP_SECONDS
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in self._threads):
            log_event(
                "operational_attention",
                reason_code="sandbox_trigger_shutdown_timeout",
                upstream="sandbox-triggers",
            )
            return False
        self._threads = []
        return True

    def hand(self, organizations: frozenset[UUID] | None) -> None:
        """Wake every lane to claim in these organizations (None: every organization)."""

        with self._wake:
            for lane in range(self._lanes):
                if organizations is None:
                    self._everything[lane] = True
                else:
                    self._targets[lane].update(organizations)
            self._wake.notify_all()

    def refresh_schedules(self, organizations: frozenset[UUID] | None) -> None:
        """A definition changed: lane 0 re-reads these organizations' schedules."""

        with self._wake:
            if organizations is None or self._stale is None:
                self._stale = None
            else:
                self._stale.update(organizations)
            self._refresh_at = 0.0
            self._wake.notify_all()

    def run_once(self, lane: int = 0) -> int:
        try:
            organizations = active_organization_ids(get_engine())
        except Exception as error:
            self._claim_failed(error)
            return 0
        held = self._passes.get(lane)
        if held is not None:
            organizations = [org_id for org_id in organizations if org_id in held]
        if organizations:
            first = lane % len(organizations)
            organizations = organizations[first:] + organizations[:first]
        processed = 0
        for org_id in organizations:
            with worker_organization(org_id):
                processed += self._run_organization(lane)
            if self._stop.is_set():
                break
        return processed

    def _run_organization(self, lane: int) -> int:
        claims = self._enqueue_and_claim(lane)
        for index, claim in enumerate(claims):
            if self._stop.is_set():
                self._release(claims[index:])
                break
            self._execute(claim)
        return len(claims)

    def _take(self, lane: int) -> tuple[bool, frozenset[UUID] | None]:
        """This lane's next pass: (False, _) for none; None for every organization."""

        if self._everything[lane]:
            self._everything[lane] = False
            self._targets[lane].clear()
            return True, None
        if self._targets[lane]:
            held = frozenset(self._targets[lane])
            self._targets[lane].clear()
            return True, held
        return False, None

    def _run(self, lane: int) -> None:
        with self._lock:
            self._active_lanes += 1
        try:
            while not self._stop.is_set():
                with self._wake:
                    has_pass, target = self._take(lane)
                    failures = self._failures
                schedule_at = self._due_minute() if lane == 0 else None
                if schedule_at is not None and not has_pass:
                    has_pass = True
                    target = frozenset(org for org, rows in self._definitions.items() if rows)
                processed = 0
                if has_pass:
                    if target is None:
                        self._passes.pop(lane, None)
                    else:
                        self._passes[lane] = target
                    if lane == 0:
                        self._schedule_at = schedule_at
                    try:
                        processed = self.run_once(lane)
                    finally:
                        self._passes.pop(lane, None)
                        self._schedule_at = None
                if lane == 0:
                    # One lane speaks for the worker; outside any organization binding.
                    signals.beat("record_triggers")
                self._report_metrics()
                if self._stop.is_set():
                    break
                if lane == 0:
                    self._refresh_definitions()
                with self._wake:
                    if processed and has_pass:
                        self._hand_locked(target)
                    elif self._failures != failures and has_pass:
                        # A claim failed: try the same organizations after the back-off.
                        self._wake.wait(self._claim_retry_seconds)
                        self._hand_locked(target, lane)
                    while not self._stop.is_set() and not self._ready(lane):
                        self._wake.wait(self._idle_seconds(lane))
        finally:
            with self._lock:
                self._active_lanes -= 1

    def _hand_locked(self, target: frozenset[UUID] | None, only: int | None = None) -> None:
        for lane in range(self._lanes) if only is None else (only,):
            if target is None:
                self._everything[lane] = True
            else:
                self._targets[lane].update(target)
        self._wake.notify_all()

    def _ready(self, lane: int) -> bool:
        return self._everything[lane] or bool(self._targets[lane]) or (
            lane == 0 and self._schedule_ready()
        )

    def _schedule_ready(self) -> bool:
        if self._stale is None or self._stale or time.monotonic() >= self._refresh_at:
            return True
        return self._next_minute is not None and self._next_minute <= utc_now()

    def _idle_seconds(self, lane: int) -> float | None:
        if lane != 0:
            return None
        seconds = max(0.0, self._refresh_at - time.monotonic())
        if self._next_minute is not None:
            seconds = min(seconds, (self._next_minute - utc_now()).total_seconds())
        return max(0.0, seconds) if math.isfinite(seconds) else None

    def _due_minute(self) -> datetime | None:
        """The current time when a schedule minute has come (lane 0), else None."""

        now = utc_now()
        minute = self._next_minute
        if minute is None or minute > now:
            return None
        self._handled_until = minute + _MINUTE
        self._next_minute = self._compute_next_minute(now)
        return now

    def _compute_next_minute(self, now: datetime) -> datetime | None:
        after = now if self._handled_until is None else max(now, self._handled_until)
        everything = [definition for rows in self._definitions.values() for definition in rows]
        return next_schedule_minute(everything, after=after)

    def _refresh_definitions(self) -> None:
        """Lane 0: re-read stale (or, every 30 s, all) organizations' schedules."""

        with self._wake:
            stale, due = self._stale, time.monotonic() >= self._refresh_at
            if not due and stale is not None and not stale:
                return
            if due:
                stale = None
            self._stale = set()
        try:
            organizations = active_organization_ids(get_engine())
            if stale is not None:
                organizations = [org_id for org_id in organizations if org_id in stale]
            else:
                self._definitions = {}
            for org_id in organizations:
                with worker_organization(org_id), AuditSession(bind=get_engine()) as db:
                    self._definitions[org_id] = schedule_definitions(db)
        except Exception as error:
            log_event(
                "operational_attention",
                reason_code="sandbox_trigger_schedule_read_failed",
                upstream="sandbox-triggers",
                cause=failure_cause(error),
            )
        if due:
            self._refresh_at = time.monotonic() + _DEFINITIONS_SECONDS
        self._next_minute = self._compute_next_minute(utc_now())

    def _enqueue_and_claim(self, lane: int = 0) -> list[ClaimedTriggerEvent]:
        try:
            with AuditSession(bind=get_engine()) as db:
                if lane == 0 and self._schedule_at is not None:
                    enqueue_due_schedules(db, now=self._schedule_at)
                claims = claim_due_events(db, limit=self._claim_limit)
                db.commit()
                with self._lock:
                    self._claim_retry_seconds = 1
                return claims
        except Exception as error:
            self._claim_failed(error)
            return []

    def _claim_failed(self, error: Exception) -> None:
        with self._lock:
            self._failures += 1
            self._claim_retry_seconds = min(self._claim_retry_seconds * 2, 60)
        log_event(
            "operational_attention",
            reason_code=f"sandbox_trigger_claim_failed_{type(error).__name__.lower()}",
            upstream="sandbox-triggers",
        )

    def _release(self, claims: list[ClaimedTriggerEvent]) -> None:
        try:
            with AuditSession(bind=get_engine()) as db:
                for claim in claims:
                    release_claim(db, claim)
                db.commit()
        except Exception as error:
            log_event(
                "operational_attention",
                reason_code=f"sandbox_trigger_release_failed_{type(error).__name__.lower()}",
                upstream="sandbox-triggers",
            )

    def _report_metrics(self) -> None:
        """Log one line for every lane together, once per interval."""

        with self._lock:
            if time.monotonic() - self._metrics_started < _METRICS_SECONDS:
                return
            count, run_ms, max_wait_ms = (
                self._metrics_count,
                self._metrics_run_ms,
                self._metrics_max_wait_ms,
            )
            self._metrics_started = time.monotonic()
            self._metrics_count = self._metrics_run_ms = self._metrics_max_wait_ms = 0
        if count:
            log_event(
                "worker_metrics",
                upstream="sandbox-triggers",
                count=count,
                duration_ms=run_ms // count,
                age_ms=max_wait_ms,
            )

    def _execute(self, claim: ClaimedTriggerEvent) -> None:
        waited = 0
        if claim.queued_at is not None:
            waited = int((utc_now() - claim.queued_at).total_seconds() * 1000)
        started = time.perf_counter()
        try:
            self._run_claim(claim)
        finally:
            run_ms = int((time.perf_counter() - started) * 1000)
            with self._lock:
                self._metrics_max_wait_ms = max(self._metrics_max_wait_ms, waited)
                self._metrics_count += 1
                self._metrics_run_ms += run_ms

    def _run_claim(self, claim: ClaimedTriggerEvent) -> None:
        try:
            with AuditSession(bind=get_engine()) as db:
                if execute_claim(db, claim):
                    db.commit()
                else:
                    db.rollback()
        except Exception:
            log_event(
                "operational_attention",
                reason_code="sandbox_trigger_execution_failed",
                operation_id=claim.id,
                upstream="sandbox-triggers",
            )
            try:
                with AuditSession(bind=get_engine()) as db:
                    if mark_claim_failed(db, claim):
                        log_event(
                            "operational_attention",
                            reason_code="sandbox_trigger_event_failed",
                            operation_id=claim.id,
                            upstream="sandbox-triggers",
                        )
                    db.commit()
            except Exception:
                log_event(
                    "operational_attention",
                    reason_code="sandbox_trigger_retry_failed",
                    operation_id=claim.id,
                    upstream="sandbox-triggers",
                )
