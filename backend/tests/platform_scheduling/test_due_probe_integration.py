"""The due probe sees schedules, queued work, retries and expired leases (K48).

It reads only what is due soon (P1): rows of other organizations that are due later do not
add to the pages that an organization with nothing due reads.
"""

import os
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, select, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.database.organization_scope import worker_organization
from app.core.database.session import AuditSession
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.openview.reports.models import Report
from app.systems.platform.scheduling.due_probe import probe_due
from app.systems.platform.scheduling.materializer import materialize_due_schedules
from app.systems.platform.scheduling.models import ScheduledWork, WorkState
from app.systems.platform.scheduling.service import LEASE_DURATION, claim_due_work
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from tests.conftest import create_organization, guarded_create_engine
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


SMALL, LARGE = 20, 2000
# One insert for each `min` that can read another organization's rows: queued and leased
# work, queued and leased trigger events, schedules. The busy organization's rows are all
# due a day from now; the idle one holds as many finished rows and nothing due, so reading
# its own rows by `org_id` costs as much as its history.
_ROWS = (
    """INSERT INTO public.reports (org_id, id, module_id, name, recipe)
    SELECT :org, gen_random_uuid(), :module, 'Probe ' || n, '{}'::jsonb
    FROM generate_series(CAST(:first AS integer), CAST(:last AS integer)) AS n""",
    """INSERT INTO public.report_schedules
        (org_id, id, report_id, enabled, cadence, timezone_name, local_time, next_due_at)
    SELECT :org, gen_random_uuid(), r.id, :enabled, 'daily', 'UTC', '09:00',
        now() + interval '1 day'
    FROM public.reports AS r
    WHERE r.org_id = :org AND NOT EXISTS (
        SELECT FROM public.report_schedules AS s WHERE s.report_id = r.id
    )""",
    """INSERT INTO public.scheduled_work (org_id, id, kind, report_id, scheduled_for,
        next_attempt_at, state, attempt_count, lease_token, lease_expires_at, created_at,
        updated_at)
    SELECT :org, gen_random_uuid(), 'report-run', :report,
        now() + (2 * n + part.step) * interval '1 minute', now() + interval '1 day', part.state,
        0, CASE WHEN part.state = 'running' THEN gen_random_uuid() END,
        CASE WHEN part.state = 'running' THEN now() + interval '1 day' END, now(), now()
    FROM generate_series(CAST(:first AS integer), CAST(:last AS integer)) AS n,
    LATERAL (VALUES (0, CAST(:work_queued AS text)), (1, CAST(:work_leased AS text)))
        AS part(step, state)""",
    """INSERT INTO public.record_trigger_events (org_id, id, record_id, module_id, event_kind,
        changed_field_ids, "values", previous_values, depth, action_budget, state,
        attempt_count, next_attempt_at, lease_token, lease_expires_at)
    SELECT :org, gen_random_uuid(), :record, :module, 'record-created', '[]', '{}', '{}', 0,
        100, part.state, 0, now() + interval '1 day',
        CASE WHEN part.state = 'running' THEN gen_random_uuid() END,
        CASE WHEN part.state = 'running' THEN now() + interval '1 day' END
    FROM generate_series(CAST(:first AS integer), CAST(:last AS integer)) AS n,
    LATERAL (VALUES (CAST(:event_queued AS text)), (CAST(:event_leased AS text))) AS part(state)""",
)
_TABLES = ("report_schedules", "scheduled_work", "record_trigger_events", "reports")
_DUE_LATER = {
    "enabled": True, "work_queued": "pending", "work_leased": "running",
    "event_queued": "pending", "event_leased": "running",
}
_FINISHED = {
    "enabled": False, "work_queued": "failed", "work_leased": "canceled",
    "event_queued": "succeeded", "event_leased": "failed",
}


def _organization(setup: Session) -> dict[str, Any]:
    org = create_organization(setup)
    department = Department(org_id=org.id, department_name=f"Probe {uuid7().hex}")
    setup.add(department)
    setup.flush()
    module = Module(org_id=org.id, department_id=department.id, module_name="Probe")
    setup.add(module)
    setup.flush()
    record = Record(org_id=org.id, module_id=module.id, data={})
    report = Report(org_id=org.id, module_id=module.id, name="Probe", recipe={})
    setup.add_all([record, report])
    setup.flush()
    return {"org": org.id, "module": module.id, "record": record.id, "report": report.id}


@pytest.fixture
def two_organizations() -> Iterator[tuple[Engine, Engine, dict[str, Any], dict[str, Any]]]:
    """An organization with history and nothing due, and one whose rows are due later."""

    owner = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"])
    runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"], pool_size=2)
    with Session(owner) as setup:
        idle, busy = _organization(setup), _organization(setup)
        setup.commit()
    try:
        yield owner, runtime, idle, busy
    finally:
        with owner.begin() as connection:
            for ids in (idle, busy):
                for table in (*_TABLES, "records", "modules", "departments"):
                    connection.execute(
                        text(f"DELETE FROM public.{table} WHERE org_id = :org"),
                        {"org": ids["org"]},
                    )
                connection.execute(
                    text("DELETE FROM public.organizations WHERE id = :org"), {"org": ids["org"]}
                )
        runtime.dispose()
        owner.dispose()


def _add_rows(
    owner: Engine, ids: dict[str, Any], states: dict[str, Any], first: int, last: int
) -> None:
    with owner.begin() as connection:
        for statement in _ROWS:
            connection.execute(text(statement), {**ids, **states, "first": first, "last": last})
        for table in _TABLES:
            connection.execute(text(f"ANALYZE public.{table}"))


def _probe_pages(runtime: Engine, org_id: UUID) -> int:
    """Pages that the probe reads as the runtime, with the organization bound."""

    captured: list[tuple[str, Any]] = []

    def capture(_connection, _cursor, statement, parameters, _context, _many) -> None:
        captured.append((statement, parameters))

    with worker_organization(org_id):
        event.listen(runtime, "before_cursor_execute", capture)
        try:
            assert set(probe_due(runtime).values()) == {None}
        finally:
            event.remove(runtime, "before_cursor_execute", capture)
        [(statement, parameters)] = [entry for entry in captured if "min(" in entry[0]]
        with AuditSession(bind=runtime) as db:
            cursor = db.connection().connection.cursor()
            cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)
            plan = cursor.fetchone()[0][0]["Plan"]
            db.rollback()
    # Buffers count each page visit, warm or cold, so the number does not depend on the cache.
    return int(plan["Shared Hit Blocks"]) + int(plan["Shared Read Blocks"])


def test_rows_due_later_elsewhere_do_not_add_to_an_idle_organizations_probe(
    two_organizations: tuple[Engine, Engine, dict[str, Any], dict[str, Any]],
) -> None:
    owner, runtime, idle, busy = two_organizations
    _add_rows(owner, idle, _FINISHED, 1, LARGE)
    _add_rows(owner, busy, _DUE_LATER, 1, SMALL)
    at_small = _probe_pages(runtime, idle["org"])

    _add_rows(owner, busy, _DUE_LATER, SMALL + 1, LARGE)
    at_large = _probe_pages(runtime, idle["org"])

    # Without the bound, a `min` over a due index steps over the busy organization's rows:
    # at least one page for each of the 1,980 rows added to it. The margin absorbs rows
    # that tests running alongside queue in their own organizations.
    assert at_large - at_small < (LARGE - SMALL) // 10, (at_small, at_large)
    # Work a day ahead is not due soon in the busy organization either; the safety poll
    # probes again long before it is.
    with worker_organization(busy["org"]):
        assert set(probe_due(runtime).values()) == {None}
