"""The keyset list indexes of `2bbcb1deeee9` (K66, K67): concurrent builds that writes pass (DBI-9).

`alembic check` sees the index names; these tests own what it cannot: the concurrent form, the
order of build and drop, the downgrade, and that record and link writes commit while a build
waits.
"""

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.records.models import Record
from tests.conftest import alembic_heads, guarded_create_engine
from tests.database_pool import dispose_process_engines
from tests.operations.migration_support import guarded_migration_environment, run_alembic
from tests.race_support import join, start, wait_until_blocked_by
from tests.rbac.support import add_department, add_module

pytestmark = pytest.mark.integration

PREVIOUS = "176d4af952fa"
REVISION = "2bbcb1deeee9"
NEW = {
    "ix_record_trigger_runs_org_created": "record_trigger_runs",
    "ix_relationship_edges_org_created": "relationship_edges",
}
OLD = "ix_record_trigger_runs_created"
TABLES = ("record_trigger_runs", "relationship_edges")


@pytest.fixture
def migration() -> Iterator[tuple[dict[str, str], Engine]]:
    """The test starts at the head and hands the database back at the head."""

    environment = guarded_migration_environment()
    [head] = alembic_heads()
    dispose_process_engines()
    engine = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"], poolclass=NullPool)
    try:
        yield environment, engine
    finally:
        run_alembic(environment, "upgrade", head)
        engine.dispose()


def _indexes(engine: Engine) -> dict[str, tuple[str, bool]]:
    """Each index of the two tables: its definition and whether it is valid."""

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid "
                "FROM pg_index AS i JOIN pg_class AS c ON c.oid = i.indexrelid "
                "WHERE i.indrelid = ANY(ARRAY['public.record_trigger_runs'::regclass, "
                "'public.relationship_edges'::regclass])"
            )
        )
        return {name: (definition, valid) for name, definition, valid in rows}


def _security(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        policies = connection.execute(
            text(
                "SELECT tablename, policyname, roles::text, cmd, qual, with_check "
                "FROM pg_policies WHERE tablename = ANY(:tables) ORDER BY 1, 2"
            ),
            {"tables": list(TABLES)},
        ).all()
        security = connection.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity, relacl::text "
                "FROM pg_class WHERE oid = ANY(ARRAY['public.record_trigger_runs'::regclass, "
                "'public.relationship_edges'::regclass]) ORDER BY 1"
            )
        ).all()
    return [*map(tuple, policies), *map(tuple, security)]


@contextmanager
def _statements() -> Iterator[list[str]]:
    seen: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        seen.append(statement.strip())

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def test_the_revision_only_builds_and_drops_indexes_concurrently(
    migration: tuple[dict[str, str], Engine],
) -> None:
    environment, engine = migration
    upgraded, security = _indexes(engine), _security(engine)
    assert {name: valid for name, (_definition, valid) in upgraded.items() if name in NEW} == (
        dict.fromkeys(NEW, True)
    )
    assert OLD not in upgraded
    for name, table in NEW.items():
        assert f"ON public.{table} USING btree (org_id, created_at, id)" in upgraded[name][0]

    with _statements() as down:
        run_alembic(environment, "downgrade", PREVIOUS)
    restored = _indexes(engine)
    assert not set(NEW) & set(restored)
    assert restored[OLD] == (
        "CREATE INDEX ix_record_trigger_runs_created ON public.record_trigger_runs "
        "USING btree (created_at, id)", True,
    )
    with _statements() as up:
        # This revision's own statements; later revisions change other indexes.
        run_alembic(environment, "upgrade", REVISION)

    assert _indexes(engine) == upgraded
    assert _security(engine) == security
    for seen in (down, up):
        changes = [
            statement for statement in seen
            if re.match(r"(CREATE|DROP|ALTER|GRANT|REVOKE)\b", statement, re.IGNORECASE)
        ]
        assert changes and all(
            re.match(r"(CREATE INDEX CONCURRENTLY|DROP INDEX CONCURRENTLY) ", statement)
            for statement in changes
        ), changes
    built_and_dropped = [
        re.sub(r" ON .*| IF EXISTS", "", statement)
        for statement in up
        if re.match(r"(CREATE|DROP) INDEX CONCURRENTLY ", statement)
    ]
    assert built_and_dropped == [
        "CREATE INDEX CONCURRENTLY ix_record_trigger_runs_org_created",
        "CREATE INDEX CONCURRENTLY ix_relationship_edges_org_created",
        f"DROP INDEX CONCURRENTLY {OLD}",
    ]
    [head] = alembic_heads()
    run_alembic(environment, "upgrade", head)
    run_alembic(environment, "check")


def test_record_and_link_writes_commit_while_a_build_waits_dbi_9(
    migration: tuple[dict[str, str], Engine],
) -> None:
    environment, engine = migration
    [head] = alembic_heads()
    with Session(bind=engine, expire_on_commit=False) as db:
        module = add_module(db, add_department(db))
        field = Field(
            org_id=module.org_id, module_id=module.id, name="Link", type=FieldType.RELATIONSHIP,
            position=0, relationship_target_module_id=module.id,
            relationship_multiple_targets=True, relationship_multiple_sources=True,
        )
        source, target = (Record(org_id=module.org_id, module_id=module.id, data={}) for _ in "st")
        db.add_all([field, source, target])
        db.commit()
        values = {"org": module.org_id, "module": module.id, "field": field.id,
                  "source": source.id, "target": target.id}
    try:
        run_alembic(environment, "downgrade", PREVIOUS)
        with engine.connect() as holder:
            # A writer on the runs table: the first concurrent build waits for it.
            holder.execute(text("LOCK TABLE public.record_trigger_runs IN ROW EXCLUSIVE MODE"))
            holder_pid = holder.connection.driver_connection.info.backend_pid
            thread, results = start(lambda: run_alembic(environment, "upgrade", head))
            builder = wait_until_blocked_by(engine, holder_pid)
            with engine.begin() as writer:
                writer.execute(
                    text("INSERT INTO public.records (id, org_id, module_id, data) "
                         "VALUES (gen_random_uuid(), :org, :module, '{}')"),
                    values,
                )
                writer.execute(
                    text("INSERT INTO public.relationship_edges (id, org_id, field_id, "
                         "source_record_id, target_record_id) "
                         "VALUES (gen_random_uuid(), :org, :field, :source, :target)"),
                    values,
                )
            with engine.connect() as observer:
                still_waiting = observer.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid "
                         "AND NOT granted)"),
                    {"pid": builder},
                )
            holder.rollback()
            join(thread, results)
        assert still_waiting is True
        with engine.connect() as connection:
            committed = connection.execute(
                text("SELECT (SELECT count(*) FROM public.records WHERE module_id = :module), "
                     "(SELECT count(*) FROM public.relationship_edges WHERE field_id = :field)"),
                values,
            ).one()
        assert tuple(committed) == (3, 1)
        assert {name: valid for name, (_d, valid) in _indexes(engine).items() if name in NEW} == (
            dict.fromkeys(NEW, True)
        )
    finally:
        with engine.begin() as connection:
            for table in ("relationship_edges", "records", "fields", "modules", "departments"):
                connection.execute(text(f"DELETE FROM public.{table} WHERE org_id = :org"), values)
            connection.execute(text("DELETE FROM public.organizations WHERE id = :org"), values)
