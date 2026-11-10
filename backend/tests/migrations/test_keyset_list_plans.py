"""Plans of the trigger run and relationship lists, as the runtime reads them (K66, K67, C5, P1).

One large organization holds 20,000 runs and 20,000 links; a small one, written after it,
holds one link and no runs, which is the K66 case. Pages and plan shape only (plan rules 9 and
10). Parallel workers stay on, so the capped count shows the plan that `LIMIT 10001` invites
at production volume (K64).
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.database.organization_scope import scope_session
from app.core.database.session import AuditSession
from app.systems.access.users.models import User, UserRole
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.record_triggers.service import list_recent_runs
from app.systems.sandbox.records.models import Record
from app.systems.sandbox.relationships.models import RelationshipEdge
from app.systems.sandbox.relationships.projection import list_relationships
from app.systems.sandbox.relationships.schemas import RelationshipListRequest
from tests.conftest import create_member, create_organization
from tests.migrations.audit_partition_support import (
    AuditEngines,
    committed_history,
    plan_nodes,
    plan_pages,
    prepared_plan_pages,
)
from tests.migrations.plan_profiles import PROFILES, apply_profile
from tests.sandbox_record_triggers.support import document_baseline, publish_trigger

pytestmark = pytest.mark.integration

ROWS = 20_000
# A small organization's statements read a few index pages: about 35 for its one link, each
# looked up by key. Without an index that leads with org_id, its trigger run list read every
# run of the installation (345 and 700 pages here; 114,389 on development data, K66). The
# same ceiling as the audit K10 test.
SMALL_ORGANIZATION_PAGE_CEILING = 60
TABLES = {"runs": "record_trigger_runs", "relationships": "relationship_edges"}
# The largest page that the reads below ask for, with its extra row.
PAGE_ROWS = 26
# A deep cursor page reads one more index descent at most; offset 2,500 read 75,899 pages.
DEPTH_PAGE_MARGIN = 10


@dataclass(frozen=True)
class _Lists:
    engines: AuditEngines
    large: UUID
    small: UUID
    large_admin: UUID
    small_admin: UUID


def _load(db: Session, module_id: UUID, definition_id: UUID, field_id: UUID) -> None:
    """Records, then one event and one run for each record, and a link to each record."""

    values = {
        "org": db.get_one(Field, field_id).org_id, "module": module_id,
        "definition": definition_id, "field": field_id, "rows": ROWS,
    }
    db.connection().execute(
        text(
            "INSERT INTO public.records (id, org_id, module_id, data, created_at) "
            "SELECT gen_random_uuid(), :org, :module, '{}'::jsonb, "
            "  now() - make_interval(secs => step) FROM generate_series(0, :rows) AS step"
        ),
        values,
    )
    db.connection().execute(
        text(
            "INSERT INTO public.record_trigger_events (id, org_id, record_id, module_id, "
            "  event_kind, changed_field_ids, \"values\", previous_values, depth, action_budget, "
            "  state, attempt_count, next_attempt_at) "
            "SELECT gen_random_uuid(), :org, records.id, :module, 'field-changed', '[]', '{}', "
            "  '{}', 0, 100, 'succeeded', 1, now() "
            "FROM public.records WHERE records.module_id = :module"
        ),
        values,
    )
    db.connection().execute(
        text(
            "INSERT INTO public.record_trigger_runs (id, org_id, event_id, trigger_id, state, "
            "  details, created_at) "
            "SELECT gen_random_uuid(), :org, events.id, :definition, 'skipped', '{}'::jsonb, "
            "  events.created_at - make_interval(secs => row_number() OVER ()::int) "
            "FROM public.record_trigger_events AS events WHERE events.module_id = :module"
        ),
        values,
    )
    db.connection().execute(
        text(
            "INSERT INTO public.relationship_edges (id, org_id, field_id, source_record_id, "
            "  target_record_id, created_at) "
            "SELECT gen_random_uuid(), :org, :field, source.id, target.id, target.created_at "
            "FROM (SELECT id FROM public.records WHERE module_id = :module "
            "      ORDER BY created_at DESC LIMIT 1) AS source "
            "JOIN public.records AS target ON target.module_id = :module "
            "  AND target.id <> source.id"
        ),
        values,
    )


@pytest.fixture(scope="module")
def lists() -> Iterator[_Lists]:
    with committed_history() as engines, AuditSession(
        bind=engines.owner, expire_on_commit=False
    ) as db:
        document_baseline(db)
        actor, module, _fields, definition = publish_trigger(db)
        field = Field(
            org_id=module.org_id, module_id=module.id, name="Link", type=FieldType.RELATIONSHIP,
            position=99, relationship_target_module_id=module.id,
            relationship_multiple_targets=True, relationship_multiple_sources=True,
        )
        db.add(field)
        db.flush()
        _load(db, module.id, definition.id, field.id)
        small = create_organization(db)
        small_admin, _member = create_member(db, small, UserRole.ADMIN.value)
        small_department = Department(org_id=small.id, department_name="Small")
        db.add(small_department)
        db.flush()
        small_module = Module(
            org_id=small.id, department_id=small_department.id, module_name="Small"
        )
        db.add(small_module)
        db.flush()
        small_field = Field(
            org_id=small.id, module_id=small_module.id, name="Link",
            type=FieldType.RELATIONSHIP, position=0,
            relationship_target_module_id=small_module.id,
            relationship_multiple_targets=True, relationship_multiple_sources=True,
        )
        ends = [Record(org_id=small.id, module_id=small_module.id, data={}) for _end in "st"]
        db.add_all([small_field, *ends])
        db.flush()
        db.add(RelationshipEdge(
            org_id=small.id, field_id=small_field.id, source_record_id=ends[0].id,
            target_record_id=ends[1].id,
        ))
        db.commit()
        world = _Lists(engines, module.org_id, small.id, actor.id, small_admin.id)
        with engines.owner.begin() as connection:
            for table in ("records", *TABLES.values()):
                connection.execute(text(f"ANALYZE public.{table}"))
        yield world


def _plans(
    world: _Lists,
    org_id: UUID,
    table: str,
    read: Callable[[Session], Any],
    profile: str = "development",
) -> list[Any]:
    """Run the real read as the runtime, then read the plan of each statement on `table`."""

    captured: list[tuple[str, Any]] = []

    def capture(_connection, _cursor, statement, parameters, _context, _many) -> None:
        if f"FROM {table}" in statement and not statement.startswith("EXPLAIN"):
            captured.append((statement, parameters))

    runtime = world.engines.runtime
    with AuditSession(bind=runtime) as db:
        scope_session(db, org_id)
        event.listen(runtime, "before_cursor_execute", capture)
        try:
            read(db)
        finally:
            event.remove(runtime, "before_cursor_execute", capture)
        assert captured
        cursor = db.connection().connection.cursor()
        # The fixture's tables are below the parallel size limits; production ones are not.
        cursor.execute("SET LOCAL min_parallel_table_scan_size = 0")
        cursor.execute("SET LOCAL min_parallel_index_scan_size = 0")
        apply_profile(cursor, profile)
        plans = []
        for statement, parameters in captured:
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)
            plans.append(cursor.fetchone()[0][0]["Plan"])
        db.rollback()
    return plans


def _read(
    name: str, reader: UUID, *, cursor: str | None = None, limit: int = 25, offset: int = 0
) -> Callable[[Session], Any]:
    if name == "runs":
        return lambda db: list_recent_runs(
            db, limit=min(limit, 20), offset=offset, cursor=cursor
        )
    return lambda db: list_relationships(
        db,
        RelationshipListRequest(limit=limit, offset=offset, cursor=cursor),
        reader=db.get_one(User, reader),
    )


def _cursor_after(world: _Lists, name: str, rows: int) -> str:
    """The cursor that the list gives after its first `rows` rows."""

    with AuditSession(bind=world.engines.runtime) as db:
        scope_session(db, world.large)
        answer = _read(name, world.large_admin, limit=1, offset=rows - 1)(db)
        db.rollback()
    if name == "runs":
        cursor = answer.next_cursor
    else:
        cursor = answer[1].next_cursor
    assert isinstance(cursor, str)
    return cursor


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("name", sorted(TABLES))
def test_a_small_organization_reads_a_few_pages_of_each_list_c5(
    lists: _Lists, name: str, profile: str
) -> None:
    world = lists

    count, page = _plans(
        world, world.small, TABLES[name], _read(name, world.small_admin), profile
    )

    pages = (plan_pages(count), plan_pages(page))
    assert max(pages) <= SMALL_ORGANIZATION_PAGE_CEILING, pages
    scans = [
        node["Node Type"]
        for plan in (count, page)
        for node in plan_nodes(plan)
        if node.get("Relation Name") == TABLES[name]
        and "Seq Scan" in node["Node Type"]
        and node["Actual Loops"] > 0
    ]
    assert scans == []


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("name", sorted(TABLES))
def test_the_first_page_of_each_list_reads_in_index_order_with_no_sort_p1(
    lists: _Lists, name: str, profile: str
) -> None:
    world = lists
    for org, reader in ((world.large, world.large_admin), (world.small, world.small_admin)):
        _count, page = _plans(world, org, TABLES[name], _read(name, reader), profile)

        # The run list sorts its joined page rows (page ids first); never the list itself.
        sorted_rows = [
            sum(child["Actual Rows"] for child in node["Plans"])
            for node in plan_nodes(page)
            if "Sort" in node["Node Type"]
        ]
        assert [rows for rows in sorted_rows if rows > PAGE_ROWS] == []


@pytest.mark.parametrize("name", sorted(TABLES))
def test_a_page_after_2500_rows_reads_as_few_pages_as_page_1_p2(
    lists: _Lists, name: str
) -> None:
    # The cursor condition sits in the index condition, so depth costs no pages (DBI-1).
    world = lists
    cursor = _cursor_after(world, name, 2_500)

    _count, first = _plans(world, world.large, TABLES[name], _read(name, world.large_admin))
    _count, deep = _plans(
        world, world.large, TABLES[name], _read(name, world.large_admin, cursor=cursor)
    )

    assert plan_pages(deep) <= plan_pages(first) + DEPTH_PAGE_MARGIN, (
        plan_pages(first), plan_pages(deep),
    )


@pytest.mark.parametrize("name", sorted(TABLES))
def test_a_page_statement_run_again_keeps_its_custom_plan_p8(lists: _Lists, name: str) -> None:
    # psycopg prepares a statement after five runs; PostgreSQL may then plan it generically,
    # without the organization or the cursor (K71). After 12 runs it must still plan per value.
    world = lists
    cursor = _cursor_after(world, name, 2_500)
    captured: list[tuple[str, Any]] = []

    def capture(_connection, _cursor, statement, parameters, _context, _many) -> None:
        if f"FROM {TABLES[name]}" in statement and "LIMIT" in statement:
            captured.append((statement, parameters))

    runtime = world.engines.runtime
    with AuditSession(bind=runtime) as db:
        scope_session(db, world.large)
        event.listen(runtime, "before_cursor_execute", capture)
        try:
            _read(name, world.large_admin, cursor=cursor)(db)
        finally:
            event.remove(runtime, "before_cursor_execute", capture)
        # The count statement runs first; the page statement is the last one.
        statement, parameters = captured[-1]
        generic, generic_pages = prepared_plan_pages(
            db.connection().connection.cursor(), statement, parameters
        )
        db.rollback()
    _count, first = _plans(world, world.large, TABLES[name], _read(name, world.large_admin))

    # P8: no generic plan, or a generic plan within the P2 ceiling.
    assert generic == 0 or generic_pages <= plan_pages(first) + DEPTH_PAGE_MARGIN, (
        generic, generic_pages, plan_pages(first),
    )
