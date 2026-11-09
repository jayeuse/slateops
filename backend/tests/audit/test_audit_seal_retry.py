"""REQ-0009: the worker seals a failed chain again on its next short wake, not an hour later."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError
from uuid6 import uuid7

from app.systems.manage.audit import seals
from tests.platform_scheduling.worker_clock import ControlledClock, install, nothing_due


def test_a_failed_chain_is_sealed_again_on_the_next_short_wake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.systems.platform.scheduling import worker as module

    organization = uuid7()
    clock = ControlledClock(until=3700)
    attempts: list[float] = []
    outcomes = iter([OperationalError("SELECT", {}, RuntimeError("statement timeout"))])

    def seal_chain(_engine, org_id, _now) -> bool:
        if org_id is None:
            return False
        attempts.append(clock.value)
        outcome = next(outcomes, False)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(seals, "chains", lambda _engine: [organization, None])
    monkeypatch.setattr(seals, "seal_chain", seal_chain)
    monkeypatch.setattr(module, "probe_due", nothing_due)
    monkeypatch.setattr(module, "get_engine", lambda: None)
    monkeypatch.setattr(module, "active_organization_ids", lambda _engine: [organization])
    for job in (
        "execute_due_report_runs",
        "execute_due_post_publications",
        "execute_due_reminders",
        "sweep_organization",
    ):
        monkeypatch.setattr(module, job, Mock(return_value=[]))
    monkeypatch.setattr(module, "ensure_audit_partitions", Mock(return_value=0))
    logger = Mock()
    monkeypatch.setattr(module, "log_event", logger)
    worker = module.ReportSchedulingWorker(SimpleNamespace(environment="development"))
    install(monkeypatch, module, worker, clock)

    worker._run()

    assert attempts == [0, 60, 3660]
    assert [call.kwargs["reason_code"] for call in logger.call_args_list] == ["audit_seal_failed"]
