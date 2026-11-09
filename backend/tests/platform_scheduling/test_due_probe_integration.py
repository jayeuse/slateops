"""The due probe sees schedules, queued work, retries and expired leases (K48)."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from uuid6 import uuid7

from app.core.database.organization_scope import worker_organization
from app.core.database.session import AuditSession
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.openview.reports.models import Report
from app.systems.platform.scheduling.due_probe import probe_due
from app.systems.platform.scheduling.materializer import materialize_due_schedules
from app.systems.platform.scheduling.models import ScheduledWork, WorkState
from app.systems.platform.scheduling.service import LEASE_DURATION, claim_due_work
from tests.platform_scheduling.test_execution import NOW

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.platform_scheduling.test_execution",)


def test_the_probe_follows_a_report_from_schedule_to_lease_to_retry(scheduled_report) -> None:
    subject = scheduled_report
    runtime = subject.runtime_engine
    with AuditSession(subject.owner_engine) as db:
        org_id = db.get(Report, subject.report_id).org_id

    with worker_organization(org_id):
        # The enabled schedule is due.
        assert probe_due(runtime)["reports"] == NOW
        with AuditSession(runtime) as db:
            assert len(materialize_due_schedules(db, now=NOW)) == 1
            db.commit()
        # The schedule moved to tomorrow; the queued work (next_attempt_at) is due now.
        assert probe_due(runtime)["reports"] == NOW
        with AuditSession(runtime) as db:
            assert len(claim_due_work(db, now=NOW, limit=1)) == 1
            db.commit()
        # Running: due again when its lease expires.
        assert probe_due(runtime)["reports"] == NOW + LEASE_DURATION
        with AuditSession(runtime) as db:
            db.info[AUDIT_CONTEXT_KEY] = AuditContext(request_id=uuid7())
            work = db.scalar(
                select(ScheduledWork).where(ScheduledWork.report_id == subject.report_id)
            )
            assert work is not None
            work.state = WorkState.PENDING
            work.lease_token = None
            work.lease_expires_at = None
            work.next_attempt_at = NOW + timedelta(seconds=4)
            db.commit()
        # A retry: due when its back-off ends.
        times = probe_due(runtime)
    assert times["reports"] == NOW + timedelta(seconds=4)
    assert times["triggers"] is None and times["posts"] is None
