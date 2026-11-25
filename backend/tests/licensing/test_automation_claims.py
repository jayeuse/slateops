"""Desk claims no queued automation event (spec editions.md ED-7)."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.systems.sandbox.record_triggers import worker as trigger_worker


def test_desk_leaves_queued_automation_events_unclaimed(monkeypatch: pytest.MonkeyPatch) -> None:
    claimed: list[str] = []
    monkeypatch.setattr(trigger_worker, "AuditSession", lambda bind: nullcontext(object()))
    monkeypatch.setattr(trigger_worker, "get_engine", lambda: None)
    monkeypatch.setattr(trigger_worker, "has_feature", lambda db, feature: False)
    monkeypatch.setattr(
        trigger_worker, "claim_due_events", lambda db, limit: claimed.append("claim") or []
    )
    worker = SimpleNamespace(_schedule_at=None, _claim_limit=10, _lock=nullcontext())
    assert trigger_worker.TriggerWorker._enqueue_and_claim(cast(Any, worker)) == []
    assert claimed == []
