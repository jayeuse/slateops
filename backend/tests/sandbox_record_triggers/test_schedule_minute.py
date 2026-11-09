"""Lane 0 wakes at the next local minute in which a published schedule fires."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from uuid6 import uuid7

from app.systems.sandbox.record_triggers import worker as worker_module
from app.systems.sandbox.record_triggers.outbox import ScheduleDefinition, next_schedule_minute
from tests.platform_scheduling.worker_clock import ControlledClock, ControlledStop

MANILA = "Asia/Manila"


def _utc(text: str, zone: str = "UTC") -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(zone)).astimezone(UTC)


@pytest.mark.parametrize(
    ("definition", "after", "expected"),
    [
        pytest.param(
            ScheduleDefinition(MANILA, "10:05", None),
            _utc("2026-01-05T10:03:20", MANILA),
            _utc("2026-01-05T10:05:00", MANILA),
            id="later-today",
        ),
        pytest.param(
            ScheduleDefinition(MANILA, "10:05", None),
            _utc("2026-01-05T10:05:40", MANILA),
            _utc("2026-01-05T10:05:00", MANILA),
            id="the-current-minute-still-fires",
        ),
        pytest.param(
            ScheduleDefinition(MANILA, "10:05", None),
            _utc("2026-01-05T10:06:00", MANILA),
            _utc("2026-01-06T10:05:00", MANILA),
            id="tomorrow",
        ),
        pytest.param(
            # 2026-01-05 is a Monday; ISO weekday 3 is Wednesday.
            ScheduleDefinition(MANILA, "10:05", 3),
            _utc("2026-01-05T10:03:20", MANILA),
            _utc("2026-01-07T10:05:00", MANILA),
            id="weekly",
        ),
        pytest.param(
            # 02:30 does not exist on 2026-03-08 in New York; enqueue never matches it.
            ScheduleDefinition("America/New_York", "02:30", None),
            _utc("2026-03-08T01:00:00", "America/New_York"),
            _utc("2026-03-09T02:30:00", "America/New_York"),
            id="a-skipped-local-time",
        ),
        pytest.param(
            ScheduleDefinition("Nowhere/Unknown", "10:05", None),
            _utc("2026-01-05T10:03:20", MANILA),
            None,
            id="an-unknown-zone",
        ),
    ],
)
def test_next_schedule_minute(
    definition: ScheduleDefinition, after: datetime, expected: datetime | None
) -> None:
    assert next_schedule_minute([definition], after=after) == expected


class _Condition:
    """The lanes' condition on the controlled clock: a wait moves time forward."""

    def __init__(self, clock: ControlledClock) -> None:
        self._clock = clock

    def __enter__(self) -> "_Condition":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def wait(self, timeout: float | None = None) -> bool:
        assert timeout is not None, "lane 0 must never sleep without a deadline"
        self._clock.advance(timeout)
        return False

    def notify_all(self) -> None:
        return None


def test_lane_zero_sleeps_until_the_schedule_minute_and_queues_it_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = uuid7()
    clock = ControlledClock(until=240, start=_utc("2026-01-05T10:03:20", MANILA))
    queued: list[datetime] = []
    session = Mock()
    session.__enter__ = Mock(return_value=Mock())
    session.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        worker_module,
        "time",
        SimpleNamespace(monotonic=clock.monotonic, perf_counter=clock.monotonic),
    )
    monkeypatch.setattr(worker_module, "utc_now", clock.utc)
    monkeypatch.setattr(worker_module, "get_engine", Mock())
    monkeypatch.setattr(worker_module, "AuditSession", Mock(return_value=session))
    monkeypatch.setattr(worker_module, "active_organization_ids", lambda _e: [organization])
    monkeypatch.setattr(
        worker_module,
        "schedule_definitions",
        lambda _db: [ScheduleDefinition(MANILA, "10:05", None)],
    )
    monkeypatch.setattr(
        worker_module, "enqueue_due_schedules", lambda _db, *, now: queued.append(now) or 1
    )
    monkeypatch.setattr(worker_module, "claim_due_events", Mock(return_value=[]))
    monkeypatch.setattr(worker_module.signals, "beat", Mock())
    worker = worker_module.TriggerWorker(
        SimpleNamespace(environment="development", trigger_workers=1)
    )
    worker._stop = ControlledStop(clock)
    worker._wake = _Condition(clock)

    worker._run(0)

    # 10:05:00 local, once, although the definitions were re-read several times.
    assert queued == [_utc("2026-01-05T10:05:00", MANILA)]
