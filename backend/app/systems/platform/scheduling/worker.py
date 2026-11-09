"""Process-local scheduling of durable Report, Board and Comms work, woken on demand.

The thread sleeps until the earliest of: work due in an organization it probed, a work
hint (``WorkSignals``, from this process's invalidation listener), the 30 s safety poll,
and the retention, partition and seal timers. A round reads the active organizations
once and probes each woken, due or (on the safety poll) every organization with one
statement (``due_probe.py``). It runs only the kinds that are due, and hands due trigger
work to the trigger lanes. A kind that ran is probed again after at least one second, so
a row that stays due cannot spin the thread. The safety poll also materializes reminders.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.base_model import utc_now
from app.core.config import Settings
from app.core.database.organization_scope import current_worker_organization, worker_organization
from app.core.database.session import AuditSession, get_engine
from app.core.observability import failure_cause, log_event
from app.systems.manage.audit.retention import ensure_audit_partitions
from app.systems.manage.audit.seals import seal_audit
from app.systems.manage.health import signals
from app.systems.manage.workspace.organizations import active_organization_ids
from app.systems.platform.scheduling.due_probe import (
    COMMS,
    POSTS,
    REMINDERS,
    REPORTS,
    TRIGGERS,
    probe_due,
)
from app.systems.platform.scheduling.execution import execute_due_report_runs
from app.systems.platform.scheduling.post_execution import (
    execute_due_post_publications,
)
from app.systems.platform.scheduling.reminder_execution import execute_due_reminders
from app.systems.platform.scheduling.retention import sweep_organization
from app.systems.platform.scheduling.work_signals import WorkSignals, WorkWake

_POLL_SECONDS = 1
_SAFETY_SECONDS = 30
_RETENTION_SECONDS = 300
_PARTITION_SECONDS = 3600
_SEAL_SECONDS = 3600
_SEAL_BACKLOG_SECONDS = 60
_MAX_RETRY_SECONDS = 60
_SHUTDOWN_SECONDS = 5
_KINDS = (REPORTS, POSTS, REMINDERS, COMMS)
_PROBE = "probe"
_REASONS = {
    REPORTS: ("report_scheduling_poll_failed", "report-scheduling"),
    POSTS: ("post_scheduling_poll_failed", "board-posts"),
    REMINDERS: ("event_reminder_poll_failed", "board-events"),
    COMMS: ("comms_scheduling_poll_failed", "comms-jobs"),
    _PROBE: ("work_probe_failed", "scheduling"),
}


@dataclass(frozen=True, slots=True)
class _PollFailure:
    """The first failed organization of one poll, its cause, and how many failed."""

    org_id: UUID | None
    cause: str
    count: int


def _failure(failures: list[tuple[UUID | None, str]]) -> _PollFailure | None:
    return _PollFailure(failures[0][0], failures[0][1], len(failures)) if failures else None


def _each_organization(job: Callable[[], object]) -> _PollFailure | None:
    """Run ``job`` once per active organization; one failure does not stop the others."""

    try:
        organizations = active_organization_ids(get_engine())
    except Exception as error:
        return _PollFailure(None, failure_cause(error), 1)
    failures: list[tuple[UUID | None, str]] = []
    for org_id in organizations:
        try:
            with worker_organization(org_id):
                job()
        except Exception as error:
            failures.append((org_id, failure_cause(error)))
    return _failure(failures)


def _report_failure(reason_code: str, upstream: str, failure: _PollFailure) -> None:
    log_event(
        "operational_attention",
        reason_code=reason_code,
        upstream=upstream,
        org_id=failure.org_id,
        cause=failure.cause,
        count=failure.count,
    )


class ReportSchedulingWorker:
    """Run the scheduled work kinds in one thread without sharing request sessions."""

    def __init__(
        self,
        settings: Settings,
        *,
        comms_poll: Callable[[datetime | None], object] | None = None,
        comms_retention: Callable[[datetime | None], bool] | None = None,
        work_signals: WorkSignals | None = None,
    ) -> None:
        self._enabled = settings.environment != "test" or settings.e2e_background_workers
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._comms_poll = comms_poll
        self._comms_retention = comms_retention
        self._work_signals = work_signals or WorkSignals()
        self._retry = dict.fromkeys((*_KINDS, _PROBE), _POLL_SECONDS)
        self._ready_at = dict.fromkeys((*_KINDS, _PROBE), 0.0)
        self._reported = dict.fromkeys((*_KINDS, _PROBE), False)
        # Monotonic time each organization must be probed again; absent: nothing queued.
        self._next_probe: dict[UUID, float] = {}
        self._reminder_followup: set[UUID] = set()
        self._next_full = math.inf
        self._comms_backlog: frozenset[UUID] = frozenset()
        self._retention_failure_reported = False
        self._comms_retention_failure_reported = False
        self._partition_failure_reported = False
        self._seal_backlog = False
        self._seal_failure_reported = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def retry_seconds(self) -> int:
        return self._retry[REPORTS]

    @property
    def post_retry_seconds(self) -> int:
        return self._retry[POSTS]

    @property
    def reminder_retry_seconds(self) -> int:
        return self._retry[REMINDERS]

    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._stop.clear()
        thread = threading.Thread(target=self._run, name="slateops-scheduled-work", daemon=True)
        thread.start()
        self._thread = thread

    def stop(self) -> bool:
        self._stop.set()
        self._work_signals.interrupt()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=_SHUTDOWN_SECONDS)
            if thread.is_alive():
                log_event(
                    "operational_attention",
                    reason_code="report_scheduling_shutdown_timeout",
                    upstream="report-scheduling",
                )
                return False
        self._thread = None
        self._running = False
        return True

    def run_once(self, *, now: datetime | None = None) -> list[UUID]:
        """Run every kind in every organization, unprobed; return the Report run IDs."""

        return self._poll(now=now, kinds=frozenset(_KINDS))

    def run_retention_once(self, *, now: datetime | None = None) -> None:
        """Sweep every organization once."""

        self._poll_retention(now=now)

    def ensure_audit_partitions_once(self) -> None:
        """Create the missing audit months for the whole installation."""

        self._poll_audit_partitions()

    def seal_audit_once(self, *, now: datetime | None = None) -> bool:
        """Seal every audit chain up to the horizon; True when a backlog remains."""

        self._poll_audit_seals(now=now)
        return self._seal_backlog

    def _poll(
        self,
        *,
        now: datetime | None,
        kinds: frozenset[str] | None = None,
        wake: WorkWake | None = None,
        full: bool = False,
        due: frozenset[UUID] = frozenset(),
        retention: bool = False,
        comms_backlog: bool = False,
        partitions: bool = False,
        seals: bool = False,
    ) -> list[UUID]:
        """One round: the given kinds unprobed, or the woken, due or (full) every probe."""

        wake = wake or WorkWake()
        completed: list[UUID] = []
        if kinds is not None or full or wake.probe or wake.reminders or due:
            completed = self._round(now=now, kinds=kinds, wake=wake, full=full, due=due)
        if (retention or comms_backlog) and not self._stop.is_set():
            self._poll_retention(now=now, platform=retention)
        if partitions and not self._stop.is_set():
            self._poll_audit_partitions()
        if seals and not self._stop.is_set():
            self._poll_audit_seals(now=now)
        return completed

    def _round(
        self,
        *,
        now: datetime | None,
        kinds: frozenset[str] | None,
        wake: WorkWake,
        full: bool,
        due: frozenset[UUID],
    ) -> list[UUID]:
        try:
            organizations = active_organization_ids(get_engine())
        except Exception as error:
            failure = _PollFailure(None, failure_cause(error), 1)
            for kind in kinds if kinds is not None else (_PROBE,):
                self._settle(kind, failure)
            if kinds is None:
                self._next_full = time.monotonic() + self._retry[_PROBE]
            return []
        self._next_full = math.inf
        active = set(organizations)
        self._next_probe = {org: at for org, at in self._next_probe.items() if org in active}
        handed: list[UUID] = []
        if kinds is not None:
            plan = {kind: list(organizations) for kind in kinds}
        else:
            wanted = wake.probe | wake.reminders | due
            targets = [org for org in organizations if full or org in wanted]
            plan, handed = self._plan(targets, now=now, full=full, reminders=wake.reminders)
        completed: list[UUID] = []
        for kind in _KINDS:
            orgs = plan.get(kind)
            if orgs and not self._stop.is_set():
                self._run_kind(kind, orgs, self._job(kind, now, completed))
        if handed:
            self._work_signals.hand_triggers(frozenset(handed))
        return completed

    def _plan(
        self,
        targets: list[UUID],
        *,
        now: datetime | None,
        full: bool,
        reminders: frozenset[UUID],
    ) -> tuple[dict[str, list[UUID]], list[UUID]]:
        """Probe each target once; return the kinds to run and the trigger hand-off."""

        current, wall = time.monotonic(), now or utc_now()
        plan: dict[str, list[UUID]] = {kind: [] for kind in _KINDS}
        handed: list[UUID] = []
        failures: list[tuple[UUID | None, str]] = []
        followup, self._reminder_followup = self._reminder_followup, set()
        for org in targets:
            if self._stop.is_set():
                break
            try:
                with worker_organization(org):
                    times = probe_due(get_engine())
            except Exception as error:
                # Never let a failed probe stop the work: run every kind there.
                failures.append((org, failure_cause(error)))
                times = dict.fromkeys((*_KINDS, TRIGGERS), wall)
            next_at = math.inf
            for kind in (*_KINDS, TRIGGERS):
                at = times.get(kind)
                if at is not None and at > wall:
                    next_at = min(next_at, current + (at - wall).total_seconds())
                elif at is None:
                    continue
                elif kind == TRIGGERS:
                    handed.append(org)
                elif self._ready_at[kind] > current:
                    next_at = min(next_at, self._ready_at[kind])
                else:
                    plan[kind].append(org)
                    # Probe again after the floor: more may be due, or a retry queued.
                    next_at = min(next_at, current + _POLL_SECONDS)
                    if kind == REMINDERS:
                        # A delivered reminder's next occurrence needs materializing.
                        self._reminder_followup.add(org)
            if org not in plan[REMINDERS] and (full or org in reminders or org in followup):
                plan[REMINDERS].append(org)
            if next_at == math.inf:
                self._next_probe.pop(org, None)
            else:
                self._next_probe[org] = next_at
        self._settle(_PROBE, _failure(failures))
        return plan, handed

    def _job(self, kind: str, now: datetime | None, completed: list[UUID]) -> Callable[[], object]:
        if kind == REPORTS:
            return lambda: completed.extend(execute_due_report_runs(get_engine(), now=now))
        if kind == POSTS:
            return lambda: execute_due_post_publications(get_engine(), now=now)
        if kind == REMINDERS:
            return lambda: execute_due_reminders(get_engine(), now=now)
        comms_poll = self._comms_poll
        return (lambda: comms_poll(now)) if comms_poll is not None else (lambda: None)

    def _run_kind(self, kind: str, organizations: list[UUID], job: Callable[[], object]) -> None:
        if kind == COMMS and self._comms_poll is None:
            return
        failures: list[tuple[UUID | None, str]] = []
        for org_id in organizations:
            try:
                with worker_organization(org_id):
                    job()
            except Exception as error:
                failures.append((org_id, failure_cause(error)))
        self._settle(kind, _failure(failures))

    def _settle(self, kind: str, failure: _PollFailure | None) -> None:
        """Back a failing kind off (1 s doubling to 60 s) and report each streak once."""

        if failure is None:
            self._retry[kind] = _POLL_SECONDS
            self._ready_at[kind] = 0.0
            self._reported[kind] = False
            return
        self._retry[kind] = min(self._retry[kind] * 2, _MAX_RETRY_SECONDS)
        self._ready_at[kind] = time.monotonic() + self._retry[kind]
        if not self._reported[kind]:
            _report_failure(*_REASONS[kind], failure)
            self._reported[kind] = True

    def _poll_retention(self, *, now: datetime | None, platform: bool = True) -> None:
        if platform:
            failure = _each_organization(
                lambda: sweep_organization(get_engine(), now=now, stopping=self._stop.is_set)
            )
            if failure is not None and not self._retention_failure_reported:
                _report_failure("retention_sweep_failed", "retention", failure)
            self._retention_failure_reported = failure is not None
        self._poll_comms_retention(now=now, only=None if platform else self._comms_backlog)

    def _poll_comms_retention(self, *, now: datetime | None, only: frozenset[UUID] | None) -> None:
        """One Comms retention batch per organization; a batch with more repeats soon."""

        retention = self._comms_retention
        if retention is None or self._stop.is_set():
            return
        more: set[UUID] = set()

        def job() -> None:
            org = current_worker_organization()
            if org is not None and (only is None or org in only) and retention(now):
                more.add(org)

        failure = _each_organization(job)
        self._comms_backlog = frozenset(more)
        if failure is not None and not self._comms_retention_failure_reported:
            _report_failure("comms_retention_failed", "comms-jobs", failure)
        self._comms_retention_failure_reported = failure is not None

    def _poll_audit_partitions(self) -> None:
        """Run outside any organization: a partition belongs to the installation."""

        try:
            with AuditSession(bind=get_engine()) as db:
                skipped = ensure_audit_partitions(db)
        except Exception as error:
            self._report_partition_problem(
                "audit_partition_failed", _PollFailure(None, failure_cause(error), 1)
            )
            return
        if skipped:
            self._report_partition_problem(
                "audit_partition_skipped", _PollFailure(None, "rows_in_default", skipped)
            )
            return
        self._partition_failure_reported = False

    def _poll_audit_seals(self, *, now: datetime | None) -> None:
        """Bind each organization in turn; the installation chain binds none."""

        failure: _PollFailure | None = None
        try:
            result = seal_audit(get_engine(), now=now or utc_now())
        except Exception as error:
            self._seal_backlog = False
            failure = _PollFailure(None, failure_cause(error), 1)
        else:
            self._seal_backlog = result.backlog
            if result.failures:
                failure = _PollFailure(result.failed, result.cause or "", result.failures)
        if failure is None:
            self._seal_failure_reported = False
        elif not self._seal_failure_reported:
            _report_failure("audit_seal_failed", "audit-seals", failure)
            self._seal_failure_reported = True

    def _report_partition_problem(self, reason_code: str, failure: _PollFailure) -> None:
        if not self._partition_failure_reported:
            _report_failure(reason_code, "audit-partitions", failure)
            self._partition_failure_reported = True

    def _run(self) -> None:
        self._running = True
        start = time.monotonic()
        next_safety = next_partition = next_seal = start
        next_retention = start + _RETENTION_SECONDS
        next_comms_retention = math.inf
        try:
            while not self._stop.is_set():
                current = time.monotonic()
                wake = self._work_signals.take()
                full = wake.everything or current >= min(next_safety, self._next_full)
                retention_due = current >= next_retention
                comms_backlog = current >= next_comms_retention
                partitions_due = current >= next_partition
                seals_due = current >= next_seal
                self._poll(
                    now=None,
                    wake=wake,
                    full=full,
                    due=frozenset(org for org, at in self._next_probe.items() if at <= current),
                    retention=retention_due,
                    comms_backlog=comms_backlog,
                    partitions=partitions_due,
                    seals=seals_due,
                )
                # Outside any organization binding: the heartbeats are installation-wide.
                signals.beat("report_scheduling")
                if self._comms_poll is not None:
                    signals.beat("comms_jobs")
                completed_at = time.monotonic()
                if full:
                    next_safety = completed_at + _SAFETY_SECONDS
                if retention_due:
                    next_retention = completed_at + _RETENTION_SECONDS
                if retention_due or comms_backlog:
                    next_comms_retention = (
                        completed_at + _POLL_SECONDS if self._comms_backlog else math.inf
                    )
                if partitions_due:
                    next_partition = completed_at + _PARTITION_SECONDS
                if seals_due:
                    next_seal = completed_at + (
                        _SEAL_BACKLOG_SECONDS if self._seal_backlog else _SEAL_SECONDS
                    )
                if self._stop.is_set():
                    break
                wake_at = min(
                    next_safety,
                    self._next_full,
                    next_retention,
                    next_comms_retention,
                    next_partition,
                    next_seal,
                    *self._next_probe.values(),
                )
                self._work_signals.sleep(max(0.0, wake_at - time.monotonic()))
        finally:
            self._running = False
