"""Shared catalog reads and engines for the audit partition tests."""

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from psycopg.sql import Literal
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from uuid6 import uuid7

from tests.conftest import alembic_heads, guarded_create_engine
from tests.database_pool import dispose_process_engines
from tests.operations.migration_support import guarded_migration_environment, run_alembic

DEFAULT_PARTITION = "audit_logs_default"
INSUFFICIENT_PRIVILEGE = "42501"
LOCK_NOT_AVAILABLE = "55P03"
_LEAVES = text(
    "SELECT child.relname FROM pg_catalog.pg_inherits AS link "
    "JOIN pg_catalog.pg_class AS child ON child.oid = link.inhrelid "
    "WHERE link.inhparent = 'public.audit_logs'::regclass ORDER BY 1"
)
_INSERT_ROW = text(
    "INSERT INTO public.audit_logs (id, org_id, created_at, action, entity_type) "
    "VALUES (:id, :org_id, :created_at, 'create', :entity_type)"
)


@dataclass(frozen=True)
class AuditEngines:
    owner: Engine
    runtime: Engine


@pytest.fixture
def audit_engines() -> Iterator[AuditEngines]:
    # NullPool: a lock that a test holds ends with its connection, not with a pooled session.
    owner = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"], poolclass=NullPool)
    runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
    try:
        yield AuditEngines(owner, runtime)
    finally:
        owner.dispose()
        runtime.dispose()


@contextmanager
def committed_history() -> Iterator[AuditEngines]:
    """Engines for rows that a test commits; they leave with `downgrade base`."""

    environment = guarded_migration_environment()
    [head] = alembic_heads()
    dispose_process_engines()
    owner = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"], poolclass=NullPool)
    runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"], poolclass=NullPool)
    try:
        yield AuditEngines(owner, runtime)
    finally:
        run_alembic(environment, "downgrade", "base")
        run_alembic(environment, "upgrade", head)
        owner.dispose()
        runtime.dispose()


def plan_nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", ()):
        yield from plan_nodes(child)


def plan_pages(plan: dict[str, Any]) -> int:
    # Buffers count each page visit, warm or cold, so the number does not depend on the cache.
    return int(plan["Shared Hit Blocks"]) + int(plan["Shared Read Blocks"])


# `bool` before `int`: a bool is an int.
_SQL_TYPES = {
    UUID: "uuid", datetime: "timestamptz", bool: "boolean", int: "bigint", str: "text",
}


def prepared_plan_pages(raw: Any, statement: str, parameters: dict[str, Any]) -> tuple[int, int]:
    """Prepare `statement`, run it 12 times, and return (generic plans, generic plan pages).

    The pages are those of the generic plan, read with `EXPLAIN EXECUTE` under
    `force_generic_plan`, as `prepare_threshold` makes psycopg prepare after five runs (K71).
    """

    names: list[str] = []

    def number(match: re.Match[str]) -> str:
        if match.group(1) not in names:
            names.append(match.group(1))
        return f"${names.index(match.group(1)) + 1}"

    text_with_numbers = re.sub(r"%\((\w+)\)s", number, statement).replace("%%", "%")
    values = [parameters[name] for name in names]
    # SQL PREPARE needs the parameter types, and EXECUTE takes literals, not bound values.
    types = ", ".join(
        next(name for kind, name in _SQL_TYPES.items() if isinstance(value, kind))
        for value in values
    )
    arguments = ", ".join(Literal(value).as_string(raw) for value in values)
    raw.execute(f"PREPARE p8_page ({types}) AS {text_with_numbers}")
    for _run in range(12):
        raw.execute(f"EXECUTE p8_page({arguments})")
        raw.fetchall()
    raw.execute("SELECT generic_plans FROM pg_prepared_statements WHERE name = 'p8_page'")
    generic = int(raw.fetchone()[0])
    raw.execute("SET LOCAL plan_cache_mode = force_generic_plan")
    raw.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE p8_page({arguments})")
    pages = plan_pages(raw.fetchone()[0][0]["Plan"])
    raw.execute("DEALLOCATE p8_page")
    return generic, pages


def leaf_names(connection: Connection) -> list[str]:
    return list(connection.scalars(_LEAVES))


def month_starts(connection: Connection, count: int = 3) -> list[str]:
    """The first day of this month and the next ones, as the database clock says, in UTC."""

    return list(
        connection.scalars(
            text(
                "SELECT to_char(date_trunc('month', now() AT TIME ZONE 'UTC') "
                "+ make_interval(months => step), 'YYYY-MM-DD') "
                "FROM generate_series(0, :last) AS step ORDER BY step"
            ),
            {"last": count - 1},
        )
    )


def partition_name(first_day: str) -> str:
    year, month, _day = first_day.split("-")
    return f"audit_logs_y{year}m{month}"


def insert_audit_row(
    connection: Connection,
    created_at: str,
    *,
    org_id: UUID | None = None,
    row_id: UUID | None = None,
) -> UUID:
    """Add the smallest valid row; with no organization it is an installation row."""

    identity = row_id or uuid7()
    connection.execute(
        _INSERT_ROW,
        {
            "id": identity,
            "org_id": org_id,
            "created_at": created_at,
            "entity_type": "records" if org_id else "users",
        },
    )
    return identity


def sqlstate(error: DBAPIError) -> Any:
    return getattr(error.orig, "sqlstate", None)
