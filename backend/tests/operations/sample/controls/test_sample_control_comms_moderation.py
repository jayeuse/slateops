"""The reporter's moderation queue never shows the report on a room they do not moderate."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from operations.sample.controls.comms_moderation import reporter_queue_hides

ROOM = str(uuid4())
DEPARTMENT_CHANNEL = str(uuid4())


def _queue(*conversation_ids: str, has_more: bool = False) -> httpx.Response:
    items = [{"id": str(uuid4()), "conversation_id": identity} for identity in conversation_ids]
    count = len(items)
    pagination = {"limit": 100, "offset": 0, "count": count, "total": count + has_more}
    return httpx.Response(200, json={"items": items, "pagination": {**pagination,
                                     "total_is_capped": False, "has_more": has_more}})


@pytest.mark.parametrize(
    ("response", "hidden"),
    (
        # A reporter who moderates nothing cannot open the queue.
        (httpx.Response(403, json={"detail": {"code": "comms_capability_denied"}}), True),
        # D44 with setup spec R2: a department manager moderates the department's derived
        # channel, so the queue opens, scoped to that channel, without the room's report.
        (_queue(), True),
        (_queue(DEPARTMENT_CHANNEL), True),
        # The reporter must never see the report on the room they only post in.
        (_queue(ROOM), False),
        (_queue(DEPARTMENT_CHANNEL, has_more=True), False),
        (httpx.Response(403, json={"detail": {"code": "comms_unavailable"}}), False),
        (httpx.Response(500, json={}), False),
    ),
    ids=("refused", "empty", "department", "room", "unread_page", "other_403", "error"),
)
def test_reporter_queue_hides_the_report_on_an_unmoderated_room(
    response: httpx.Response, hidden: bool
) -> None:
    assert reporter_queue_hides(response, ROOM) is hidden
