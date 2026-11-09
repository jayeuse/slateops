"""A controlled clock for the scheduling worker loop: no test waits on real time.

``install`` patches the worker module's monotonic clock and ``utc_now`` to one clock, and
replaces the worker's stop event and ``WorkSignals`` sleep with versions that advance it.
``ControlledClock.at`` plans an action (for example a wake) at a controlled instant.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.systems.platform.scheduling.work_signals import WorkSignals

START = datetime(2026, 1, 1, 12, tzinfo=UTC)
_MAX_SLEEPS = 100_000


class ControlledClock:
    def __init__(self, *, until: float, start: datetime = START) -> None:
        self.value = 0.0
        self.until = until
        self.start = start
        self._planned: list[tuple[float, Callable[[], None]]] = []
        self.sleeps = 0

    def monotonic(self) -> float:
        return self.value

    def utc(self) -> datetime:
        return self.start + timedelta(seconds=self.value)

    def at(self, instant: float, action: Callable[[], None]) -> None:
        self._planned.append((instant, action))
        self._planned.sort(key=lambda item: item[0])

    def advance(self, seconds: float) -> None:
        """Move time forward; a planned action inside the step ends the step at its instant."""

        assert seconds >= 0
        self.sleeps += 1
        assert self.sleeps < _MAX_SLEEPS, "the worker loop never slept forward"
        target = self.value + seconds
        if self._planned and self._planned[0][0] <= target:
            instant, action = self._planned.pop(0)
            self.value = max(self.value, instant)
            action()
            return
        self.value = target


class ControlledStop:
    def __init__(self, clock: ControlledClock) -> None:
        self._clock = clock
        self._set = False

    def is_set(self) -> bool:
        return self._set or self._clock.value > self._clock.until

    def set(self) -> None:
        self._set = True

    def clear(self) -> None:
        self._set = False

    def wait(self, seconds: float) -> bool:
        self._clock.advance(seconds)
        return self.is_set()


class ControlledSignals(WorkSignals):
    def __init__(self, clock: ControlledClock) -> None:
        super().__init__()
        self._clock = clock

    def sleep(self, seconds: float) -> None:
        self._clock.advance(seconds)


def install(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, worker: Any, clock: ControlledClock
) -> ControlledSignals:
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=clock.monotonic), raising=False)
    monkeypatch.setattr(module, "utc_now", clock.utc, raising=False)
    worker._stop = ControlledStop(clock)
    signals = ControlledSignals(clock)
    worker._work_signals = signals
    return signals


def nothing_due(_engine: object) -> dict[str, datetime | None]:
    return {}
