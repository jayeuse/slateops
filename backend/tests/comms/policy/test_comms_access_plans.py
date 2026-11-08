"""Pages of the Comms member counts as the runtime reads them (plan step 3.3, DBI-2, B2).

The counts evaluate C conversations against N people. Read for each pair, the pages grow
with C x N (16 times from 2 x 10 to 8 x 40); read once for each input, with C + N
(4 times). Pages, not time: buffers count each page visit, warm or cold.
"""

from typing import Any

import pytest
from sqlalchemy import event

import app.systems.comms.access as comms_access
from app.systems.access.policy.models import GroupAccess
from app.systems.comms.access import conversation_reader_counts
from app.systems.comms.conversations.models import CommsConversation, CommsMember
from app.systems.sandbox.departments.models import Department
from tests.comms.policy.conftest import PolicyCase

pytestmark = pytest.mark.integration

SMALL, LARGE = (2, 10), (8, 40)


def _pages(plan: dict[str, Any]) -> int:
    return int(plan["Shared Hit Blocks"]) + int(plan["Shared Read Blocks"])


def _count_pages(
    case: PolicyCase, monkeypatch: pytest.MonkeyPatch, channels: list[Any], people: list[Any]
) -> int:
    """Run the real counts for these people, then explain their statement as the runtime."""

    db = case.db
    captured: list[tuple[str, Any]] = []

    def capture(_connection, _cursor, statement, parameters, _context, _many) -> None:
        if "count(DISTINCT" in statement and not statement.startswith("EXPLAIN"):
            captured.append((statement, parameters))

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    monkeypatch.setattr(
        comms_access, "organization_member_ids", lambda _db: [person.id for person in people]
    )
    try:
        counts = conversation_reader_counts(db, [channel.id for channel in channels])
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert set(counts) == {channel.id for channel in channels}
    (statement, parameters), = captured
    cursor = db.connection().connection.cursor()
    cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
    cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)
    return _pages(cursor.fetchone()[0][0]["Plan"])


def test_member_count_pages_grow_with_conversations_plus_people(
    policy_case: PolicyCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, db = policy_case, policy_case.db
    channels_count, people_count = LARGE
    people = [case.person(f"Counted {n}") for n in range(people_count)]
    channels = []
    for n in range(channels_count):
        department = Department(org_id=case.org.id, department_name=f"Counted {n}")
        db.add(department)
        db.flush()
        group = case.group(*people[: 5 * (n + 1)], name=f"Counted {n}")
        db.add(GroupAccess(org_id=case.org.id, group_id=group.id,
                           department_id=department.id, level="read"))
        channel = CommsConversation(org_id=case.org.id, kind="channel", scope="department",
                                    name=f"Counted {n}", department_id=department.id,
                                    created_by=case.admin.id)
        db.add(channel)
        db.flush()
        db.add(CommsMember(org_id=case.org.id, conversation_id=channel.id,
                           user_id=people[n].id, role="manager"))
        channels.append(channel)
    db.flush()

    small = _count_pages(case, monkeypatch, channels[: SMALL[0]], people[: SMALL[1]])
    large = _count_pages(case, monkeypatch, channels, people)

    ratio = (LARGE[0] + LARGE[1]) / (SMALL[0] + SMALL[1])
    assert large <= small * ratio * 5 / 4, {"small": small, "large": large}
