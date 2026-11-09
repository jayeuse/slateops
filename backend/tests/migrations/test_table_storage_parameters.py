"""Per-table storage parameters, which `alembic check` does not compare (F12, F18)."""

import os
import subprocess
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.conftest import alembic_heads, guarded_create_engine
from tests.database_pool import dispose_process_engines
from tests.operations.migration_support import guarded_migration_environment, run_alembic

pytestmark = pytest.mark.integration

PREVIOUS = "cf8cb7605f48"
# The revision before `078b17c76d8a` (plan step 3.6), whose downgrade builds two indexes.
BEFORE_HOT_UPDATES = "b1b3908e844b"
HOT_UPDATE_INDEXES = ("ix_comms_realtime_grants_expiry", "ix_comms_presence_seen")
QUEUE_TABLE = {
    "autovacuum_vacuum_scale_factor": "0.02",
    "autovacuum_analyze_scale_factor": "0.01",
    "autovacuum_vacuum_insert_scale_factor": "0.02",
}
UPDATED_TABLE = {
    "autovacuum_vacuum_scale_factor": "0.02",
    "autovacuum_analyze_scale_factor": "0.01",
}
EXPECTED = {
    "record_trigger_events": QUEUE_TABLE,
    "in_app_notifications": QUEUE_TABLE,
    "relationship_edges": UPDATED_TABLE,
    "records": {**UPDATED_TABLE, "fillfactor": "90"},
    # Plan step 3.6: room for HOT renewals and heartbeats.
    "comms_realtime_grants": {"fillfactor": "80"},
    "comms_presence": {"fillfactor": "80"},
}


def _storage_parameters(connection: Connection) -> dict[str, dict[str, str]]:
    rows = connection.execute(
        text(
            "SELECT c.relname, c.reloptions FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
        ),
        {"tables": sorted(EXPECTED)},
    )
    return {
        name: dict(option.split("=", 1) for option in options or [])
        for name, options in rows
    }


def test_each_table_has_its_storage_parameters(integration_owner_db: Session) -> None:
    assert _storage_parameters(integration_owner_db.connection()) == EXPECTED


def test_no_index_holds_the_column_that_a_renewal_or_heartbeat_changes(
    integration_owner_db: Session,
) -> None:
    # An index on the updated column makes every renewal or heartbeat a non-HOT update.
    rows = integration_owner_db.connection().execute(
        text(
            "SELECT i.indrelid::regclass::text, a.attname FROM pg_index AS i "
            "JOIN pg_attribute AS a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid IN ('public.comms_realtime_grants'::regclass, "
            "'public.comms_presence'::regclass)"
        )
    ).all()
    indexed = {(table, column) for table, column in rows}

    assert ("comms_realtime_grants", "user_id") in indexed
    assert ("comms_realtime_grants", "expires_at") not in indexed
    assert ("comms_presence", "last_seen_at") not in indexed
    assert ("comms_presence", "state") not in indexed


def test_each_audit_partition_has_its_own_storage_parameters(
    integration_owner_db: Session,
) -> None:
    # A partitioned parent holds no storage parameters, and a partition inherits none.
    rows = integration_owner_db.connection().execute(
        text(
            "SELECT child.relname, child.reloptions FROM pg_inherits AS link "
            "JOIN pg_class AS child ON child.oid = link.inhrelid "
            "WHERE link.inhparent = 'public.audit_logs'::regclass"
        )
    )
    leaves = {
        name: dict(option.split("=", 1) for option in options or []) for name, options in rows
    }
    assert "audit_logs_default" in leaves
    assert leaves == dict.fromkeys(leaves, QUEUE_TABLE)


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


def test_downgrade_resets_the_parameters_and_upgrade_restores_them(
    migration: tuple[dict[str, str], Engine],
) -> None:
    environment, engine = migration
    [head] = alembic_heads()

    run_alembic(environment, "downgrade", PREVIOUS)
    with engine.connect() as connection:
        assert _storage_parameters(connection) == dict.fromkeys(EXPECTED, {})

    run_alembic(environment, "upgrade", head)
    with engine.connect() as connection:
        assert _storage_parameters(connection) == EXPECTED
    run_alembic(environment, "check")


def _index_validity(engine: Engine) -> dict[str, bool]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT c.relname, i.indisvalid FROM pg_index AS i "
                "JOIN pg_class AS c ON c.oid = i.indexrelid "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = ANY(:names)"
            ),
            {"names": list(HOT_UPDATE_INDEXES)},
        )
        return {name: valid for name, valid in rows}


def test_a_stopped_downgrade_rebuilds_its_invalid_index_on_the_rerun(
    migration: tuple[dict[str, str], Engine],
) -> None:
    # A real stop: a writer on `comms_presence` outlasts the 5 s lock limit, so the
    # concurrent build fails after its catalog row exists and leaves an INVALID index.
    environment, engine = migration
    with engine.connect() as holder:
        holder.execute(text("SET idle_in_transaction_session_timeout = '30s'"))
        holder.commit()
        holder.execute(text("LOCK TABLE public.comms_presence IN ROW EXCLUSIVE MODE"))
        with pytest.raises(subprocess.CalledProcessError) as failure:
            run_alembic(environment, "downgrade", BEFORE_HOT_UPDATES)
        holder.rollback()
    assert "lock timeout" in failure.value.stderr
    assert _index_validity(engine) == {
        "ix_comms_realtime_grants_expiry": True, "ix_comms_presence_seen": False,
    }

    run_alembic(environment, "downgrade", BEFORE_HOT_UPDATES)

    assert _index_validity(engine) == dict.fromkeys(HOT_UPDATE_INDEXES, True)
