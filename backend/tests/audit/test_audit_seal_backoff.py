"""A chain that keeps failing is tried less often, up to hourly, and normally after a success."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError
from uuid6 import uuid7

from app.systems.manage.audit import seals
from tests.platform_scheduling.worker_clock import ControlledClock, install, nothing_due


def test_a_failing_chain_backs_off_from_a_minute_to_an_hour_and_resets_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.systems.platform.scheduling import worker as module

    organization = uuid7()
    clock = ControlledClock(until=14700)
    attempts: list[float] = []
    # Eight failures, one success, one failure, then success again.
    outcomes = iter([*([False] * 8), True, False])

    def seal_chain(_engine, org_id, _now) -> bool:
        if org_id is None:
            return False
        attempts.append(clock.value)
        if next(outcomes, True):
            return False
        raise OperationalError("SELECT", {}, RuntimeError("statement timeout"))

    monkeypatch.setattr(seals, "_BACKOFF", seals.ChainBackoff(), raising=False)
    monkeypatch.setattr(seals, "chains", lambda _engine: [organization, None])
    monkeypatch.setattr(seals, "seal_chain", seal_chain)
    monkeypatch.setattr(module, "probe_due", nothing_due)
    monkeypatch.setattr(module, "get_engine", lambda: None)
    monkeypatch.setattr(module, "active_organization_ids", lambda _engine: [organization])
    for job in ("execute_due_reminders", "sweep_organization"):
        monkeypatch.setattr(module, job, Mock(return_value=[]))
    monkeypatch.setattr(module, "ensure_audit_partitions", Mock(return_value=0))
    logger = Mock()
    monkeypatch.setattr(module, "log_event", logger)
    worker = module.ReportSchedulingWorker(SimpleNamespace(environment="development"))
    install(monkeypatch, module, worker, clock)

    worker._run()

    gaps = [later - earlier for earlier, later in zip(attempts, attempts[1:], strict=False)]
    # The worker still wakes every minute while a chain is behind; the chain is tried
    # 60, 120, 240, 480, 960, 1,920 s apart, then hourly. After its success it is sealed
    # on the hourly wake, and a new failure is retried after a minute again.
    assert gaps == [60, 120, 240, 480, 960, 1920, 3600, 3600, 3600, 60]
    # One report for the whole failing streak, one for the new one.
    assert [call.kwargs["reason_code"] for call in logger.call_args_list] == [
        "audit_seal_failed",
        "audit_seal_failed",
    ]
