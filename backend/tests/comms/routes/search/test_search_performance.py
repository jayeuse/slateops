"""Thirty searches over 100,000 owned messages; provider-auth latency is not measured."""

import json
import os
import re
from time import perf_counter

import pytest
from sqlalchemy import event, func, literal, select, text
from uuid6 import uuid7

from app.systems.comms.messages.models import CommsMessage
from tests.comms.conftest import NOW
from tests.comms.routes.structure_support import ROOT, _ok
from tests.repository import REPOSITORY_ROOT

pytestmark = pytest.mark.integration

SEARCH_INDEX = "ix_comms_messages_body_search"
SEARCH_FUNCTION = "public.comms_search_message_ids"
# A word only the rows below hold. "history" must stay out of them: the seeded total is exact.
SELECTIVE_TERM = "quillwort"
SELECTIVE_ROWS = 50
# About 3 x 13, the most pages a statement read locally on 3 runs (10 to 13; no CI figure yet).
# The D22 definer function finds the matches through the search index, so the pages follow the
# 50 matches, not the 100,000 rows of the organization (REQ-0005; it was 8,006 while row
# security kept `@@` from the index). Another organization's matches for the same word still
# add pages (D22-1); the two-organization test below records them.
SELECTIVE_PAGE_CEILING = 40
BROAD_PAGE_FACTOR = 3


def _add_selective_rows(
    connection, org, term: str = SELECTIVE_TERM, rows: int = SELECTIVE_ROWS, conversation=None
) -> None:
    connection.execute(CommsMessage.__table__.insert(), [
        {
            "id": uuid7(), "org_id": org.id,
            "conversation_id": conversation or org.conversation,
            "author_id": org.author, "client_key": uuid7(), "seq": 100_000 + position,
            "body": f"Rare {term} note", "send_fingerprint": "c" * 64,
            "created_at": NOW,
        }
        for position in range(1, rows + 1)
    ])


def _search_sql(
    case, api, term: str, marker: str = SEARCH_FUNCTION + "(", **filters
) -> tuple[dict, list]:
    """One real search, and its count and page statements with their bound parameters."""
    captured = []

    def capture(_connection, _cursor, statement, parameters, _context, _many):
        # The count statement names only the function (K52); the page also ranks. A search
        # inside one conversation names `plainto_tsquery(` in both instead.
        if marker in statement:
            captured.append((statement, parameters))

    event.listen(case.world.runtime, "before_cursor_execute", capture)
    try:
        page = _ok(api.get(ROOT + "/search", params={"q": term, "limit": 50, **filters}))
    finally:
        event.remove(case.world.runtime, "before_cursor_execute", capture)
    assert len(captured) == 2, captured
    return page, captured


def _root_plans(case, org, statements) -> list[dict]:
    """Replay captured SQL under the same organization scope; the plan's root nodes."""
    plans = []
    with case.world.session(org) as db:
        cursor = db.connection().connection.cursor()
        cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        for sql, parameters in statements:
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, parameters)
            plans.append(cursor.fetchone()[0][0]["Plan"])
        db.rollback()
    return plans


def _nodes(plan: dict):
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def _body_plans(case, org, term: str) -> dict[str, dict]:
    """The function body's plans as its owner, bound to `org`: with the values, and generic.

    The outer plan shows only a function scan. PostgreSQL 17 plans a SQL function body
    once with parameters, not values, so the generic plan is the one that runs.
    """
    plans = {}
    with case.world.owner.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) == "slateops_owner"
        connection.execute(
            text("SELECT set_config('slateops.org_id', :org, true)"), {"org": str(org.id)}
        )
        body = connection.scalar(text(
            f"SELECT prosrc FROM pg_proc WHERE oid = '{SEARCH_FUNCTION}(text, uuid[])'"
            "::regprocedure"
        ))
        connection.exec_driver_sql("SET LOCAL max_parallel_workers_per_gather = 0")
        connection.exec_driver_sql("PREPARE comms_search_body(text, uuid[]) AS " + body)
        for mode in ("force_custom_plan", "force_generic_plan"):
            connection.exec_driver_sql(f"SET LOCAL plan_cache_mode = {mode}")
            plans[mode] = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) EXECUTE comms_search_body("
                f"'{term}', ARRAY['{org.conversation}']::uuid[])"
            ).scalar_one()[0]["Plan"]
        connection.exec_driver_sql("DEALLOCATE comms_search_body")
        connection.rollback()
    return plans


def _pages_read(plan: dict) -> int:
    # Buffers count each page visit, warm or cold, so the number does not depend on the cache.
    return plan["Shared Hit Blocks"] + plan["Shared Read Blocks"]


def _table_and_index_pages(case) -> int:
    with case.world.owner.connect() as connection:
        return connection.scalar(text(
            f"SELECT (pg_relation_size('comms_messages') + pg_relation_size('{SEARCH_INDEX}'))"
            " / current_setting('block_size')::bigint"
        ))


def test_search_over_one_hundred_thousand_messages_is_bounded_and_measured(
    message_routes, monkeypatch, record_property
):
    from app.systems.comms import search as search_module

    case, org = message_routes, message_routes.world.first
    case.seed_large_history()
    with case.world.owner.begin() as connection:
        _add_selective_rows(connection, org)
        connection.execute(text("ANALYZE comms_messages"))
        # A pending list makes the page count depend on how much the last insert left behind.
        connection.execute(text(f"SELECT gin_clean_pending_list('{SEARCH_INDEX}')"))
    handler_samples, baseline_selects, handler_selects, body_rows = [], [], [], []
    active = [False]
    original = search_module.query_messages

    def timed(*args, **kwargs):
        active[0] = True
        started = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            handler_samples.append((perf_counter() - started) * 1000)
            active[0] = False

    def observe(_connection, cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            (handler_selects if active[0] else baseline_selects).append(statement)
            if re.search(r"\bbody\b", statement):
                body_rows.append(cursor.rowcount)

    monkeypatch.setattr(search_module, "query_messages", timed)
    api = case.client(org.peer, org.id)
    event.listen(case.world.runtime, "after_cursor_execute", observe)
    samples, counts, setup = [], [], []
    try:
        for limit in (2, 100):
            baseline_selects.clear()
            handler_selects.clear()
            page = _ok(api.get(ROOT + "/search", params={"q": "history", "limit": limit}))
            assert page["pagination"]["total"] == 100_000 and page["pagination"]["count"] == limit
            counts.append((len(baseline_selects), len(handler_selects)))
        for _ in range(5):
            started = perf_counter()
            assert (
                api.get(ROOT + "/search", params={"q": "history", "limit": 50}).status_code == 200
            )
            setup.append((perf_counter() - started) * 1000)
        handler_samples.clear()
        for _ in range(30):
            started = perf_counter()
            page = _ok(api.get(ROOT + "/search", params={"q": "history", "limit": 50}))
            samples.append((perf_counter() - started) * 1000)
            assert page["pagination"]["total"] == 100_000 and page["pagination"]["count"] == 50
    finally:
        event.remove(case.world.runtime, "after_cursor_execute", observe)
    assert counts[0] == counts[1] and all(value > 0 for value in counts[0])
    assert body_rows and all(0 <= rows <= 100 for rows in body_rows)
    evidence = {
        "request_ms": samples,
        "handler_ms": handler_samples,
        "warmup_ms": setup,
        "request_p95_ms": sorted(samples)[28],
        "handler_p95_ms": sorted(handler_samples)[28],
        "select_counts_baseline_handler": counts,
        "principal": "Supplied principal; real membership, current policy and PostgreSQL",
        "production_org_baseline_reference": (
            "6 warm or 9 cold SELECTs plus scope; provider-auth latency not measured"
        ),
    }
    # After `evidence`: these requests also pass through `timed`, and must not join its samples.
    selective_page, selective_sql = _search_sql(case, api, SELECTIVE_TERM)
    assert selective_page["pagination"]["total"] == SELECTIVE_ROWS
    selective = _root_plans(case, org, selective_sql)
    body = _body_plans(case, org, SELECTIVE_TERM)
    _, broad_sql = _search_sql(case, api, "history")
    broad = _root_plans(case, org, broad_sql)
    broad_ceiling = BROAD_PAGE_FACTOR * _table_and_index_pages(case)
    evidence["pages_read"] = {
        "selective_count_and_page": [_pages_read(plan) for plan in selective],
        "broad_count_and_page": [_pages_read(plan) for plan in broad],
        "broad_ceiling": broad_ceiling,
        "selective_body_custom_and_generic": [_pages_read(plan) for plan in body.values()],
    }
    path = (
        REPOSITORY_ROOT
        / "backend/test-results/s19"
        / os.environ["SLATEOPS_FULLSTACK_RUN_ID"]
        / "search-100000.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    record_property("search_request_p95_ms", evidence["request_p95_ms"])
    record_property("search_handler_p95_ms", evidence["handler_p95_ms"])
    record_property("search_pages_read", json.dumps(evidence["pages_read"]))
    # Page counts do not depend on runner speed, so they block in every run, CI included.
    for mode, plan in body.items():
        used = {node.get("Index Name") for node in _nodes(plan)}
        assert SEARCH_INDEX in used, (mode, plan)
    for plan in selective:
        # The function runs in a ProjectSet node, whose buffers hold the pages its body read,
        # so the ceiling covers them.
        calls = [node for node in _nodes(plan) if node["Node Type"] == "ProjectSet"]
        assert calls and all(_pages_read(call) > 0 for call in calls), plan
    for plan in selective:
        assert _pages_read(plan) <= SELECTIVE_PAGE_CEILING, evidence["pages_read"]
    for plan in broad:
        assert _pages_read(plan) <= broad_ceiling, evidence["pages_read"]
        assert plan["Temp Read Blocks"] + plan["Temp Written Blocks"] == 0, plan
    # The page counts, the index assertions and the temp-block check above block in every run.
    # The wall-clock p95 is a report in every run (job summary in CI, the record_property
    # values above elsewhere): the broad case reads its matches twice by design, in the
    # function and then by primary key (D22, accepted by the Human Owner on 2026-11-09).
    if job_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(job_summary, "a", encoding="utf-8") as summary:
            summary.write(f"Search p95: {evidence['request_p95_ms']:.1f} ms (report only)\n")


FOREIGN_MATCHES = 20_000
# S4's own word, so its 20,000 rows (and their index entries until a vacuum) never reach the
# selective search above when both tests run on one database (NB1).
FOREIGN_TERM = "bladderwort"


def _add_foreign_matches(connection, org) -> None:
    """One set-based statement: `FOREIGN_MATCHES` rows of `org` that match `FOREIGN_TERM`."""
    series = func.generate_series(1, FOREIGN_MATCHES).table_valued("value").render_derived()
    connection.execute(CommsMessage.__table__.insert().from_select(
        [
            "id", "org_id", "conversation_id", "author_id", "client_key", "seq", "body",
            "send_fingerprint", "created_at",
        ],
        select(
            func.gen_random_uuid(), literal(org.id), literal(org.conversation),
            literal(org.author), func.gen_random_uuid(), series.c.value + 1_000,
            literal(f"Foreign {FOREIGN_TERM} note"), literal("c" * 64), literal(NOW),
        ),
    ))


def _settle(case) -> None:
    with case.world.owner.begin() as connection:
        connection.execute(text("ANALYZE comms_messages"))
        connection.execute(text(f"SELECT gin_clean_pending_list('{SEARCH_INDEX}')"))


def test_another_organizations_matches_do_not_change_a_search_and_its_pages_are_recorded(
    message_routes, record_property
):
    """D22-1: the search index has no `org_id`, so another organization's matches for the
    same word add pages to this search. The results must not change; the pages are recorded
    for the trigger (a second client organization in one production installation)."""
    case, org, other = message_routes, message_routes.world.first, message_routes.world.second
    with case.world.owner.begin() as connection:
        _add_selective_rows(connection, org, FOREIGN_TERM)
    _settle(case)
    api = case.client(org.peer, org.id)
    alone, alone_sql = _search_sql(case, api, FOREIGN_TERM)
    alone_pages = [_pages_read(plan) for plan in _root_plans(case, org, alone_sql)]
    with case.world.owner.begin() as connection:
        _add_foreign_matches(connection, other)
    _settle(case)
    beside, beside_sql = _search_sql(case, api, FOREIGN_TERM)
    beside_pages = [_pages_read(plan) for plan in _root_plans(case, org, beside_sql)]
    pages = {"foreign_0": alone_pages, f"foreign_{FOREIGN_MATCHES}": beside_pages}
    print("D22-1 count and page statement pages:", json.dumps(pages))
    record_property("search_pages_beside_foreign_matches", json.dumps(pages))
    assert alone["pagination"]["total"] == SELECTIVE_ROWS
    assert beside == alone


SMALL_CONVERSATION_ROWS = 20


def test_a_search_inside_one_conversation_reads_that_conversations_matches(
    message_routes, record_property
):
    """NB3: a common word searched inside a small conversation reads that conversation's
    rows under row-level security, as before step 3.8, not every match of the word first
    (100,000 in the large conversation): the function's generic plan cannot use the
    conversation index, so this search does not call it."""
    case, org = message_routes, message_routes.world.first
    case.seed_large_history()
    with case.world.owner.begin() as connection:
        _add_selective_rows(
            connection, org, "history", SMALL_CONVERSATION_ROWS, org.other_conversation
        )
    _settle(case)
    api = case.client(org.peer, org.id)
    inside, statements = _search_sql(
        case, api, "history", "plainto_tsquery(", **{"in": str(org.other_conversation)}
    )
    assert not any(SEARCH_FUNCTION in sql for sql, _ in statements), statements
    pages = [_pages_read(plan) for plan in _root_plans(case, org, statements)]
    print("NB3 filtered broad search, count and page statement pages:", pages)
    record_property("search_pages_inside_one_conversation", json.dumps(pages))
    assert inside["pagination"]["total"] == SMALL_CONVERSATION_ROWS
    for count in pages:
        assert count <= SELECTIVE_PAGE_CEILING, pages
