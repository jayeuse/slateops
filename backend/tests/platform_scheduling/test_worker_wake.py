"""The scheduling worker sleeps until work is due, a hint arrives, or its safety poll."""

from collections.abc import Callable
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from uuid6 import uuid7

from app.systems.manage.audit.seals import SealPass
from app.systems.platform.scheduling import worker as module
from tests.platform_scheduling.worker_clock import START, ControlledClock, install

ORGANIZATION = uuid7()


class _World:
    """The worker's collaborators, each recording the controlled times it ran."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        clock: ControlledClock,
        due: Callable[[float], dict[str, datetime | None]],
    ) -> None:
        self.lists: list[float] = []
        self.probes: list[float] = []
        self.runs: dict[str, list[float]] = {"reports": [], "posts": [], "reminders": []}
        self.comms: list[float] = []
        self.retention: list[float] = []

        def organizations(_engine: object) -> list[UUID]:
            self.lists.append(clock.value)
            return [ORGANIZATION]

        def probe(_engine: object) -> dict[str, datetime | None]:
            self.probes.append(clock.value)
            return due(clock.value)

        def job(kind: str) -> Callable[..., list[object]]:
            return lambda *_a, **_k: self.runs[kind].append(clock.value) or []

        monkeypatch.setattr(module, "active_organization_ids", organizations)
        monkeypatch.setattr(module, "probe_due", probe, raising=False)
        monkeypatch.setattr(module, "get_engine", lambda: None)
        monkeypatch.setattr(module, "execute_due_report_runs", job("reports"))
        monkeypatch.setattr(module, "execute_due_post_publications", job("posts"))
        monkeypatch.setattr(module, "execute_due_reminders", job("reminders"))
        monkeypatch.setattr(module, "sweep_organization", Mock())
        monkeypatch.setattr(module, "ensure_audit_partitions", Mock(return_value=0))
        monkeypatch.setattr(module, "seal_audit", Mock(return_value=SealPass(backlog=False)))
        monkeypatch.setattr(module, "log_event", Mock())


def _worker(
    monkeypatch: pytest.MonkeyPatch,
    *,
    until: float,
    due: Callable[[float], dict[str, datetime | None]] = lambda _t: {},
    retention: Callable[[float], bool] | None = None,
) -> tuple[module.ReportSchedulingWorker, ControlledClock, _World, list[object]]:
    clock = ControlledClock(until=until)
    world = _World(monkeypatch, clock, due)
    handed: list[object] = []

    def comms_retention(_now: datetime | None) -> bool:
        world.retention.append(clock.value)
        return retention(clock.value) if retention is not None else False

    worker = module.ReportSchedulingWorker(
        SimpleNamespace(environment="development"),
        comms_poll=lambda _now: world.comms.append(clock.value),
        comms_retention=comms_retention,
    )
    signals = install(monkeypatch, module, worker, clock)
    signals.attach_triggers(lambda orgs: handed.append((clock.value, orgs)), lambda _orgs: None)
    return worker, clock, world, handed


def _in(window: tuple[float, float], times: list[float]) -> list[float]:
    return [instant for instant in times if window[0] < instant <= window[1]]


def test_an_idle_worker_probes_at_most_twice_a_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _clock, world, handed = _worker(monkeypatch, until=60)

    worker._run()

    # After the start-up round, 60 s of idle time: the 30 s safety poll twice, each one
    # organization-list read and one probe for the organization. Nothing was due.
    assert _in((0, 60), world.lists) == [30, 60]
    assert _in((0, 60), world.probes) == [30, 60]
    assert world.runs["reports"] == world.runs["posts"] == world.comms == handed == []
    # The safety poll also materializes reminders (a new occurrence may need queueing).
    assert world.runs["reminders"] == [0, 30, 60]


def test_a_wake_probes_its_organization_at_once_not_at_the_safety_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    due_from = 5.0
    worker, clock, world, _handed = _worker(
        monkeypatch,
        until=31,
        # The hint's work is due at t = 5 s; running it consumes it, as a claim does.
        due=lambda now: {"reports": START + timedelta(seconds=due_from)} if now == due_from else {},
    )
    clock.at(5, lambda: worker._work_signals.mark(ORGANIZATION))

    worker._run()

    assert world.probes[:2] == [0, 5]
    assert world.runs["reports"] == [5]


@pytest.mark.parametrize("kind", ["reports", "triggers"])
def test_work_due_later_runs_when_due_without_a_hint(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    # A failed attempt retries 4 s later (``next_attempt_at``); nothing announces it.
    retry_at = START + timedelta(seconds=4)
    worker, _clock, world, handed = _worker(
        monkeypatch,
        until=10,
        due=lambda now: {kind: retry_at} if now <= 4 else {},
    )

    worker._run()

    assert world.probes[:2] == [0, 4]
    if kind == "triggers":
        assert handed == [(4, frozenset({ORGANIZATION}))]
    else:
        assert world.runs["reports"] == [4]


def test_comms_retention_runs_on_its_timer_and_repeats_while_it_has_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker, _clock, world, _handed = _worker(
        monkeypatch, until=600, retention=lambda now: now < 302
    )

    worker._run()

    # Two batches report more work, so the third runs; then the 300 s timer again.
    assert world.retention == [300, 301, 302, 600]
    assert world.comms == []
