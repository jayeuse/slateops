"""The revision after `2bbcb1deeee9` drops `ix_comms_messages_live_roots` (plan step 4.2, K80).

No reader's filter implies the index predicate: history asks for `parent_id IS NULL OR
also_send_to_channel` with no `is_deleted` term, so it reads `uq_comms_messages_sequence`. These
tests own what `alembic check` cannot: the concurrent drop, the exact D13 definition that the
downgrade gives back (`test_partial_index_predicates.py` downgrades through it), the history
plans before and after, and that message writes commit while the drop waits (DBI-9).
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.database import Base
from app.core.database.organization_scope import scope_session
from app.core.database.session import AuditSession
from app.systems.comms.messages.reads import history
from app.systems.comms.messages.schemas import HistoryRequest
from tests.conftest import alembic_heads, create_member, create_organization
from tests.migrations.audit_partition_support import (
    AuditEngines,
    committed_history,
    plan_nodes,
)
from tests.operations.migration_support import guarded_migration_environment, run_alembic
from tests.race_support import join, start, wait_until_blocked_by

pytestmark = pytest.mark.integration

PREVIOUS = "2bbcb1deeee9"
REVISION = "bd01bc005861"
DROPPED = "ix_comms_messages_live_roots"
SEQUENCE_INDEX = "uq_comms_messages_sequence"
# The D13 definition (`65bf3d1eb512`), as `pg_get_indexdef` prints it.
D13_DEFINITION = (
    "CREATE INDEX ix_comms_messages_live_roots ON public.comms_messages USING btree "
    "(org_id, conversation_id, seq) WHERE ((parent_id IS NULL) AND (is_deleted IS FALSE))"
)
ROWS = 20_000
NOW = datetime(2026, 11, 1, 9, tzinfo=UTC)
READS = {
    "roots": HistoryRequest(limit=50),
    "before_seq": HistoryRequest(limit=50, before_seq=10_000),
    "around_seq": HistoryRequest(limit=50, around_seq=10_000),
}


@dataclass(frozen=True)
class _Conversation:
    engines: AuditEngines
    org: UUID
    author: UUID
    conversation: UUID


def _messages(org: UUID, author: UUID, conversation: UUID) -> list[dict[str, Any]]:
    """One root at seq 1; every fifth later message replies to it, one in ten is deleted."""

    root = uuid7()
    rows = []
    for seq in range(1, ROWS + 1):
        reply = seq > 1 and seq % 5 == 0
        deleted = seq % 10 == 3
        created = NOW + timedelta(seconds=seq)
        rows.append({
            "id": root if seq == 1 else uuid7(), "org_id": org, "conversation_id": conversation,
            "author_id": author, "client_key": uuid7(), "seq": seq, "body": f"Message {seq}",
            "send_fingerprint": "c" * 64, "created_at": created,
            "parent_id": root if reply else None, "is_deleted": deleted,
            "deleted_at": created if deleted else None,
        })
    return rows


@pytest.fixture(scope="module")
def conversation() -> Iterator[_Conversation]:
    with committed_history() as engines:
        yield _seed(engines)


def _seed(engines: AuditEngines) -> _Conversation:
    # The session ends before the tests: an open snapshot makes a concurrent build wait.
    with Session(engines.owner) as db:
        organization = create_organization(db)
        author, _membership = create_member(db, organization)
        conversation_id = uuid7()
        tables = Base.metadata.tables
        connection = db.connection()
        connection.execute(tables["comms_conversations"].insert().values(
            id=conversation_id, org_id=organization.id, kind="channel", scope="organization",
            name="Conversation", topic="", position=0, created_by=author.id,
        ))
        connection.execute(tables["comms_conversation_counters"].insert().values(
            org_id=organization.id, conversation_id=conversation_id, last_seq=ROWS,
        ))
        connection.execute(tables["comms_members"].insert().values(
            org_id=organization.id, conversation_id=conversation_id, user_id=author.id,
            role="member", joined_at=NOW,
        ))
        connection.execute(
            tables["comms_messages"].insert(),
            _messages(organization.id, author.id, conversation_id),
        )
        world = _Conversation(engines, organization.id, author.id, conversation_id)
        db.commit()
    return world


@pytest.fixture
def environment(conversation: _Conversation) -> Iterator[dict[str, str]]:
    """The test starts at the head and hands the database back at the head."""

    environment = guarded_migration_environment()
    [head] = alembic_heads()
    try:
        yield environment
    finally:
        run_alembic(environment, "upgrade", head)


def _indexes(engine: Engine) -> dict[str, tuple[str, bool]]:
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid "
            "FROM pg_index AS i JOIN pg_class AS c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'public.comms_messages'::regclass"
        ))
        return {name: (definition, valid) for name, definition, valid in rows}


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


def _vacuum(engine: Engine) -> None:
    # Plan rule (lesson b): the plan read sees no dead index entries that other tests left.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM (INDEX_CLEANUP ON, ANALYZE) public.comms_messages"))


def _history(world: _Conversation) -> dict[str, tuple[list[str], set[str], list[set[str]]]]:
    """Each read as the runtime: its item ids, the scans of its statements ordered by `seq`,
    and the `comms_messages` scans of every statement (the has-older and has-newer probes
    find one row, so a sequential scan can be their cheapest plan at either revision).
    """

    _vacuum(world.engines.owner)
    runtime = world.engines.runtime
    answers: dict[str, tuple[list[str], set[str], list[set[str]]]] = {}
    for name, request in READS.items():
        captured: list[tuple[str, Any]] = []

        def capture(
            _connection, _cursor, statement, parameters, _context, _many, seen=captured
        ) -> None:
            if "comms_messages.seq" in statement and not statement.startswith("EXPLAIN"):
                seen.append((statement, parameters))

        with AuditSession(bind=runtime) as db:
            scope_session(db, world.org)
            event.listen(runtime, "before_cursor_execute", capture)
            try:
                response = history(db, world.author, world.conversation, request)
            finally:
                event.remove(runtime, "before_cursor_execute", capture)
            assert captured, name
            cursor = db.connection().connection.cursor()
            ordered: set[str] = set()
            scans: list[set[str]] = []
            for statement, parameters in captured:
                cursor.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + statement, parameters)
                scans.append({
                    node.get("Index Name", node["Node Type"])
                    for node in plan_nodes(cursor.fetchone()[0][0]["Plan"])
                    if node.get("Relation Name") == "comms_messages"
                })
                if "ORDER BY comms_messages.seq" in statement:
                    ordered |= scans[-1]
            db.rollback()
        answers[name] = ([str(item.id) for item in response.items], ordered, scans)
    return answers


def test_the_head_has_no_live_roots_index_and_the_downgrade_restores_d13_a42a(
    conversation: _Conversation, environment: dict[str, str]
) -> None:
    engine = conversation.engines.owner
    [head] = alembic_heads()
    upgraded = _indexes(engine)
    assert DROPPED not in upgraded

    # Record only this revision's statements; later revisions change other tables.
    run_alembic(environment, "downgrade", REVISION)
    with _statements() as down:
        run_alembic(environment, "downgrade", PREVIOUS)
    assert _indexes(engine)[DROPPED] == (D13_DEFINITION, True)
    with _statements() as up:
        run_alembic(environment, "upgrade", REVISION)
    run_alembic(environment, "upgrade", head)

    assert _indexes(engine) == upgraded
    changes = {
        name: [
            statement for statement in seen
            if re.match(r"(CREATE|DROP|ALTER|GRANT|REVOKE)\b", statement, re.IGNORECASE)
        ]
        for name, seen in (("down", down), ("up", up))
    }
    assert changes == {
        "down": [f"CREATE INDEX CONCURRENTLY {DROPPED} ON comms_messages "
                 "(org_id, conversation_id, seq) WHERE parent_id IS NULL AND is_deleted IS FALSE"],
        "up": [f"DROP INDEX CONCURRENTLY IF EXISTS {DROPPED}"],
    }
    run_alembic(environment, "check")


def test_history_reads_the_sequence_index_before_and_after_the_drop_a42b(
    conversation: _Conversation, environment: dict[str, str]
) -> None:
    after = _history(conversation)
    run_alembic(environment, "downgrade", PREVIOUS)
    before = _history(conversation)

    for answers in (after, before):
        assert {name: ordered for name, (_ids, ordered, _scans) in answers.items()} == (
            dict.fromkeys(READS, {SEQUENCE_INDEX})
        )
    assert {name: scans for name, (_ids, _ordered, scans) in after.items()} == {
        name: scans for name, (_ids, _ordered, scans) in before.items()
    }
    assert {name: ids for name, (ids, _ordered, _scans) in after.items()} == {
        name: ids for name, (ids, _ordered, _scans) in before.items()
    }
    assert [len(ids) for ids, _ordered, _scans in after.values()] == [50, 50, 50]


def test_a_message_insert_commits_while_the_drop_waits_dbi_9_a42c(
    conversation: _Conversation, environment: dict[str, str]
) -> None:
    world = conversation
    engine = world.engines.owner
    [head] = alembic_heads()
    run_alembic(environment, "downgrade", PREVIOUS)
    with engine.connect() as holder:
        # A writer's open transaction: the concurrent drop waits for it to end.
        holder.execute(text("LOCK TABLE public.comms_messages IN ROW EXCLUSIVE MODE"))
        holder_pid = holder.connection.driver_connection.info.backend_pid
        thread, results = start(lambda: run_alembic(environment, "upgrade", head))
        dropper = wait_until_blocked_by(engine, holder_pid)
        with engine.begin() as writer:
            writer.execute(
                Base.metadata.tables["comms_messages"].insert().values(
                    id=uuid7(), org_id=world.org, conversation_id=world.conversation,
                    author_id=world.author, client_key=uuid7(), seq=ROWS + 1,
                    body="Written while the drop waits", send_fingerprint="d" * 64,
                    created_at=NOW,
                )
            )
        with engine.connect() as observer:
            still_waiting = observer.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)"),
                {"pid": dropper},
            )
        holder.rollback()
        join(thread, results)

    assert still_waiting is True
    with engine.connect() as connection:
        written = connection.scalar(
            text("SELECT count(*) FROM public.comms_messages WHERE seq = :seq "
                 "AND conversation_id = :conversation"),
            {"seq": ROWS + 1, "conversation": world.conversation},
        )
    assert written == 1
    assert DROPPED not in _indexes(engine)
