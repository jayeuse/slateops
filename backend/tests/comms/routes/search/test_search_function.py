"""The Comms search function reads one organization's matches past row-level security (D22)."""

import pytest
from sqlalchemy import bindparam, event, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.exc import DBAPIError
from uuid6 import uuid7

from app.systems.access.users.models import User
from app.systems.comms.messages.models import CommsMessage
from app.systems.comms.search import CommsSearchRequest, _candidates
from tests.comms.conftest import NOW
from tests.comms.routes.structure_support import ROOT, _ok

pytestmark = pytest.mark.integration
TERM = "quillwort"
INVALID_TEXT_REPRESENTATION = "22P02"
MATCHES = text("SELECT id FROM public.comms_search_message_ids(:q, :conversations)").bindparams(
    bindparam("conversations", type_=ARRAY(PostgreSQLUUID(as_uuid=True)))
)


def _message(org, conversation, seq, body, **values):
    return {
        "id": uuid7(), "org_id": org.id, "conversation_id": conversation,
        "author_id": org.author, "client_key": uuid7(), "seq": seq, "body": body,
        "send_fingerprint": "c" * 64, "created_at": NOW,
        "is_deleted": False, "deleted_at": None, "deleted_by": None, **values,
    }


@pytest.fixture
def stored(comms_world):
    first, second = comms_world.first, comms_world.second
    rows = {
        "listed": _message(first, first.conversation, 1, f"Rare {TERM} note"),
        "unlisted": _message(first, first.other_conversation, 1, f"Rare {TERM} note"),
        "deleted": _message(
            first, first.conversation, 2, f"Rare {TERM} note",
            is_deleted=True, deleted_at=NOW, deleted_by=first.author,
        ),
        "other_word": _message(first, first.conversation, 3, "Plain note"),
        "foreign": _message(second, second.conversation, 1, f"Rare {TERM} note"),
    }
    # Owner setup SQL; the function under test then runs as the runtime.
    with comms_world.owner.begin() as connection:
        connection.execute(CommsMessage.__table__.insert(), list(rows.values()))
    return {name: row["id"] for name, row in rows.items()}


def _matches(world, org, conversations):
    with world.runtime.connect() as connection:
        connection.execute(
            text("SELECT set_config('slateops.org_id', :org, true)"), {"org": str(org.id)}
        )
        return set(connection.scalars(MATCHES, {"q": TERM, "conversations": conversations}))


def test_bound_to_one_organization_it_returns_only_its_live_matches_in_the_given_conversations(
    comms_world, stored
):
    first, second = comms_world.first, comms_world.second
    # The definer reads past row-level security, so the body's own conditions must drop
    # the other organization's match and the match in a conversation that is not passed.
    assert _matches(comms_world, first, [first.conversation, second.conversation]) == {
        stored["listed"]
    }
    assert _matches(
        comms_world, second, [first.conversation, first.other_conversation, second.conversation]
    ) == {stored["foreign"]}
    assert _matches(comms_world, first, []) == set()


def test_unbound_it_returns_nothing_and_a_malformed_binding_is_an_error(comms_world, stored):
    first, second = comms_world.first, comms_world.second
    everything = [first.conversation, first.other_conversation, second.conversation]
    with comms_world.runtime.connect() as connection:
        assert connection.scalar(
            text("SELECT nullif(current_setting('slateops.org_id', true), '') IS NULL")
        )
        assert connection.scalars(MATCHES, {"q": TERM, "conversations": everything}).all() == []
    with comms_world.runtime.connect() as connection:
        connection.execute(
            text("SELECT set_config('slateops.org_id', 'not-an-organization', true)")
        )
        with pytest.raises(DBAPIError) as refused:
            connection.execute(MATCHES, {"q": TERM, "conversations": everything})
    assert getattr(refused.value.orig, "sqlstate", None) == INVALID_TEXT_REPRESENTATION


def test_an_empty_readable_set_finds_nothing_without_an_error(comms_world, stored):
    first = comms_world.first
    request = CommsSearchRequest.model_validate({"q": TERM})
    with comms_world.session(first) as db:
        actor = db.get(User, first.author)
        assert db.scalars(_candidates(db, actor, request, set())).all() == []
        assert db.scalars(_candidates(db, actor, request, {first.conversation})).all() == [
            stored["listed"]
        ]


def test_the_function_gets_the_server_side_readable_set_never_request_input(search_case):
    case, first = search_case, search_case.world.first
    ids = case.seed_search_visibility()
    reader = case.client(first.peer, first.id)
    arguments = []

    def capture(_connection, _cursor, statement, parameters, _context, _many):
        if "public.comms_search_message_ids(" in statement:
            arguments.append(set(parameters["search_readable"]))

    event.listen(case.world.runtime, "before_cursor_execute", capture)
    try:
        # The private room is in the reader's organization, but the reader cannot read it.
        hidden = _ok(
            reader.get(ROOT + "/search", params={"q": "kumquat", "in": str(ids["private_room"])})
        )
        shown = _ok(
            reader.get(ROOT + "/search", params={"q": "kumquat", "sort_by": "created_at"})
        )
    finally:
        event.remove(case.world.runtime, "before_cursor_execute", capture)
    assert hidden["items"] == [] and hidden["pagination"]["total"] == 0
    assert [hit["message_id"] for hit in shown["items"]] == [
        str(ids["revocable"]), str(ids["reply"])
    ]
    assert arguments and all(
        argument == {first.conversation, first.other_conversation} for argument in arguments
    )
    with case.world.session(first) as db:
        assert db.scalar(
            select(CommsMessage.conversation_id).where(CommsMessage.id == ids["private"])
        ) == ids["private_room"]
