"""A commit that queues or reschedules work carries a work hint; a worker's claim does not."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from uuid6 import uuid7

from app.core.database.organization_scope import worker_organization
from app.core.database.session import AuditSession
from app.systems.manage.audit import listeners
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.openview.reports.models import Report
from app.systems.openview.reports.schedule_models import ReportSchedule
from app.systems.platform.events.models import WORK_ENTITIES, InvalidationEvent
from app.systems.platform.scheduling.execution import execute_due_report_runs
from tests.platform_scheduling.test_execution import NOW

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.platform_scheduling.test_execution",)


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[list[InvalidationEvent]]:
    """Each committed transaction's work hints, in commit order (empty when it had none)."""

    commits: list[list[InvalidationEvent]] = []

    def publish(events, **_kwargs) -> bool:
        commits.append([event for event in events if event.entity in WORK_ENTITIES])
        return True

    monkeypatch.setattr(listeners, "publish_invalidations", publish)
    return commits


def test_queueing_due_work_hints_once_and_the_claim_and_finish_do_not(
    scheduled_report, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = scheduled_report
    with AuditSession(subject.owner_engine) as db:
        org_id = db.get(Report, subject.report_id).org_id
    commits = _capture(monkeypatch)

    with worker_organization(org_id):
        assert len(execute_due_report_runs(subject.runtime_engine, now=NOW)) == 1

    hint = InvalidationEvent("work_scheduled", org_id=org_id)
    # Materialize (schedule moved, work queued) hints; the claim and the finished run,
    # the worker's own updates, publish only their audited events.
    assert [hints for hints in commits if hints] == [[hint]]
    assert commits[0] == [hint]


def test_a_schedule_change_in_a_rolled_back_savepoint_sends_no_hint(
    scheduled_report, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject = scheduled_report
    commits = _capture(monkeypatch)

    with AuditSession(subject.owner_engine) as db:
        db.info[AUDIT_CONTEXT_KEY] = AuditContext(request_id=uuid7())
        schedule = db.scalar(
            select(ReportSchedule).where(ReportSchedule.report_id == subject.report_id)
        )
        assert schedule is not None
        org_id = schedule.org_id
        savepoint = db.begin_nested()
        schedule.next_due_at = NOW - timedelta(hours=1)
        db.flush()
        savepoint.rollback()
        db.commit()
        rolled_back = list(commits)
        schedule.next_due_at = NOW - timedelta(hours=2)
        db.commit()

    assert all(not hints for hints in rolled_back)
    assert commits[-1] == [InvalidationEvent("work_scheduled", org_id=org_id)]
