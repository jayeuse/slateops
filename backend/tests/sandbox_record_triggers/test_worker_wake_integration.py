"""A committed record change wakes the trigger lanes through the process's listener (W3)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, select

from app.core.config import Settings
from app.core.database.organization_scope import worker_organization
from app.systems.platform.events.hub import EventHub, PostgresInvalidationListener, _psycopg_url
from app.systems.platform.scheduling.due_probe import probe_due
from app.systems.platform.scheduling.work_signals import WorkSignals
from app.systems.sandbox.record_triggers import worker as worker_module
from app.systems.sandbox.record_triggers.models import RecordTriggerEvent, TriggerEventState
from tests.config_support import settings_values
from tests.race_support import WAIT
from tests.sandbox_record_triggers.test_worker_lanes_integration import (
    _Organization,
    _publish,
    _queue,
)

pytestmark = pytest.mark.integration
# The disposable engines and organizations of the lane tests.
pytest_plugins = ("tests.sandbox_record_triggers.test_worker_lanes_integration",)


def test_a_record_change_hint_reaches_the_lanes_and_the_next_pass_runs_its_event(
    engines: tuple[Engine, Engine],
    organizations: list[_Organization],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, runtime = engines
    organization = _publish(owner, organizations)
    monkeypatch.setattr(worker_module, "get_engine", lambda: runtime)
    monkeypatch.setattr(
        worker_module, "active_organization_ids", lambda _engine: [organization.org_id]
    )
    signals = WorkSignals()
    worker = worker_module.TriggerWorker(
        Settings(**settings_values(e2e_background_workers=True, trigger_workers=1), _env_file=None),
        work_signals=signals,
    )
    worker._everything[0] = False
    listener = PostgresInvalidationListener(
        EventHub(),
        _psycopg_url(os.environ["TEST_DATABASE_URL"]),
        connect_timeout_seconds=5,
        statement_timeout_ms=15_000,
        work_signals=signals,
    )
    listener.start()
    try:
        with worker._wake:
            # The listener's connect wakes every lane: it is listening from here on.
            assert worker._wake.wait_for(lambda: worker._everything[0], WAIT), "never listened"
            worker._everything[0] = False
        (record_id,) = _queue(owner, organization, 1)
        with worker._wake:
            # A hang guard only: the hint arrives as soon as the commit's NOTIFY does.
            assert worker._wake.wait_for(
                lambda: organization.org_id in worker._targets[0], WAIT
            ), "the work hint never reached the lanes"
            has_pass, target = worker._take(0)
    finally:
        assert listener.stop()

    assert has_pass and target == frozenset({organization.org_id})
    with owner.connect() as connection:
        queued_at = connection.scalar(
            select(RecordTriggerEvent.next_attempt_at).where(
                RecordTriggerEvent.record_id == record_id
            )
        )
    with worker_organization(organization.org_id):
        # The scheduler's probe sees the same event as due (K48: next_attempt_at).
        assert probe_due(runtime)["triggers"] == queued_at
    worker._passes[0] = target
    assert worker.run_once(0) >= 1
    with owner.connect() as connection:
        states = connection.scalars(
            select(RecordTriggerEvent.state).where(
                RecordTriggerEvent.record_id == record_id, RecordTriggerEvent.depth == 0
            )
        ).all()
    assert states == [TriggerEventState.SUCCEEDED]
