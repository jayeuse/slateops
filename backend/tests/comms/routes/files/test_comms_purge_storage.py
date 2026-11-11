"""A confirmed conversation purge cannot erase metadata over an uncertain Storage delete."""

import re
from uuid import UUID

import pytest
from sqlalchemy import event, func, update

from app.systems.comms.messages.models import CommsMessage
from app.systems.platform.files import purge as file_purge
from app.systems.platform.files.models import File
from app.systems.platform.files.providers import ProviderUnavailable
from tests.comms.routes.files.test_attachment_routes import _reserve
from tests.comms.routes.message_support import _ok, send
from tests.comms.routes.test_comms_purge import confirmation
from tests.comms.routes.test_comms_purge import purge_case as purge_case

pytestmark = pytest.mark.integration

# Row locks and advisory locks, as a statement takes them.
LOCK = re.compile(r"FOR (NO KEY )?UPDATE|FOR (KEY )?SHARE|pg_(try_)?advisory", re.IGNORECASE)
PROJECTION_KEY = "comms:realtime-grants:"


def _archived_attachment(case, api, org) -> tuple[str, dict, str, dict]:
    """An uploaded attachment on a removed message in an archived conversation."""
    root = f"/api/comms/conversations/{org.conversation}"
    file = _reserve(case, api, org, org.conversation, org.author)
    assert api.put(root + f"/files/{file['id']}/content", content=case.content,
                   headers={"Content-Type": "application/octet-stream"}).status_code == 200
    key = case.object_key(org, UUID(file["id"]))
    message = send(api, root + "/messages", "", attachment_ids=[file["id"]])
    message_path = root + "/messages/" + message["id"]
    version = api.get(message_path).headers["etag"]
    removed = api.post(message_path + "/removal", headers={"If-Match": version})
    assert removed.status_code == 200
    current = api.get(root)
    assert api.post(
        root + "/archive", headers={"If-Match": current.headers["etag"]},
    ).status_code == 200
    return root, file, key, message


def test_uncertain_storage_delete_preserves_parent_and_resumes_through_fresh_confirmation(
    purge_case, file_routes, monkeypatch,
):
    case, org = file_routes, file_routes.world.first
    api = case.client(org.author, org.id)
    root, file, key, message = _archived_attachment(case, api, org)
    message_path = root + "/messages/" + message["id"]
    preview = _ok(api.post(root + "/purge/preview"))

    def unavailable(_key):
        raise ProviderUnavailable("controlled owned Storage refusal")

    with monkeypatch.context() as patch:
        patch.setattr(case.storage, "delete", unavailable)
        assert api.post(root + "/purge", json=confirmation(preview)).status_code == 503
    assert api.get(root).status_code == 200
    assert case.storage.download(key) == case.content
    with case.world.session(org) as db:
        assert db.get(CommsMessage, UUID(message["id"])) is not None
        retained = db.get(File, UUID(file["id"]))
        assert retained.state == "deleting" and retained.failure_code == "deletion_unresolved"
    current = api.get(message_path)
    assert api.post(message_path + "/restoration",
                    headers={"If-Match": current.headers["etag"]}).status_code == 422
    fresh = _ok(api.post(root + "/purge/preview"))
    result = _ok(api.post(root + "/purge", json=confirmation(fresh)))
    assert result["purged_file_count"] == result["purged_message_count"] == 1
    assert case.storage.download(key) is None and api.get(root).status_code == 404


def test_a_file_purged_by_another_purge_keeps_the_projection_guard_first(
    purge_case, file_routes, monkeypatch,
):
    """SD19 step 1, ID30: the guard is a transaction's first lock, before any authority row.

    Another administrator's purge finalizes the file between this purge's file lookup and its
    file lock, so the file claim returns without a commit and the conversation graph is
    deleted in the same transaction. A conversation or administrator lock taken before the
    guard there can deadlock with a publish or an administrator change that holds the guard.
    """
    case, org = file_routes, file_routes.world.first
    api = case.client(org.author, org.id)
    root, file, _key, _message = _archived_attachment(case, api, org)
    preview = _ok(api.post(root + "/purge/preview"))
    original_load = file_purge.load
    finalized: list[UUID] = []

    def load_after_other_purge(db, file_id, **options):
        if not options and not finalized:
            finalized.append(file_id)
            with case.world.owner.begin() as connection:
                connection.execute(update(File).where(File.id == file_id).values(
                    state="purged", is_deleted=True, deleted_at=func.now(), operation_id=None,
                    operation_expires_at=None, deletion_origin=None, failure_code=None,
                ))
        return original_load(db, file_id, **options)

    open_statements: dict[int, list[tuple[str, object]]] = {}
    transactions: list[list[tuple[str, object]]] = []

    def record(connection, _cursor, statement, parameters, *_args):
        open_statements.setdefault(id(connection), []).append((statement, parameters))

    def close(connection):
        transactions.append(open_statements.pop(id(connection), []))

    monkeypatch.setattr(file_purge, "load", load_after_other_purge)
    runtime = case.world.runtime
    event.listen(runtime, "before_cursor_execute", record)
    event.listen(runtime, "commit", close)
    event.listen(runtime, "rollback", close)
    try:
        result = _ok(api.post(root + "/purge", json=confirmation(preview)))
    finally:
        event.remove(runtime, "before_cursor_execute", record)
        event.remove(runtime, "commit", close)
        event.remove(runtime, "rollback", close)
    assert finalized == [UUID(file["id"])]
    assert result["purged_file_count"] == result["purged_message_count"] == 1
    assert api.get(root).status_code == 404

    def is_guard(parameters) -> bool:
        return isinstance(parameters, dict) and str(parameters.get("key", "")).startswith(
            PROJECTION_KEY
        )

    guarded = [statements for statements in transactions if any(
        is_guard(parameters) for _statement, parameters in statements
    )]
    assert guarded, "no transaction took the projection guard"
    locks_before_guard = [
        " ".join(statement.split())[:80]
        for statements in guarded
        for statement, _parameters in statements[
            :next(index for index, (_s, p) in enumerate(statements) if is_guard(p))
        ]
        if LOCK.search(statement)
    ]
    assert locks_before_guard == []
