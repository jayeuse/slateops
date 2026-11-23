"""Sheet routes 3, 4, 5, 7, 8 and 25 (spec D10; C1-C5, V3, L7, F3, P6; D14 R5, S1).

SH-1, SH-2, SH-3, SH-4, SH-6, SH-7, SH-18, SH-41, SH-67.
"""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.core.database.organization_scope import scope_session
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User, UserRole
from app.systems.openview.worksheets.models import Worksheet
from tests.conftest import create_member, create_organization, membership_of
from tests.rbac.support import _client, add_user, make_group_access
from tests.worksheets.support import STRUCTURE, SheetWorld, add_sheet, sheet_world

pytestmark = pytest.mark.integration
NOT_FOUND = {"detail": {"code": "worksheet_not_found", "message": "Sheet not found"}}


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _body(response: Any) -> Any:
    """The answer without its per-request ID, which differs on every request."""

    body = response.json()
    return {key: value for key, value in body.items() if key != "request_id"}


def _as(application: FastAPI, db: Session, person: User) -> TestClient:
    return _client(application, person, db)


def _anchor(world: SheetWorld, anchor: str) -> dict[str, str]:
    return (
        {"record_id": str(world.record.id)} if anchor == "record"
        else {"module_id": str(world.module.id)}
    )


def _create(client: TestClient, anchor: dict[str, str], title: str = " Grades ") -> Any:
    return client.post(
        "/api/worksheets", json={**anchor, "title": title, "source": {"kind": "blank"}}
    )


def _member_with(db: Session, world: SheetWorld, level: AccessLevel) -> User:
    person = add_user(db)
    make_group_access(db, [person], world.department, world.module, level=level)
    return person


@pytest.mark.parametrize("anchor", ["record", "module"])
def test_an_owner_creates_reads_renames_deletes_and_restores_a_sheet(
    application: FastAPI, integration_db: Session, anchor: str,
) -> None:
    db = integration_db
    world = sheet_world(db, anchor)
    owner = _as(application, db, world.peer)
    created = _create(owner, _anchor(world, anchor))
    assert created.status_code == 201, created.text
    body = created.json()
    sheet_id = body["id"]
    assert created.headers["Location"] == f"/api/worksheets/{sheet_id}"
    assert created.headers["ETag"] == f'"{sheet_id}:1"'
    assert created.headers["Cache-Control"] == "no-store"
    assert {key: body[key] for key in (
        "title", "state", "my_level", "revision", "live_row_count", "is_deleted", "etag",
    )} == {
        "title": "Grades", "state": "private", "my_level": "owner", "revision": 1,
        "live_row_count": 0, "is_deleted": False, "etag": f'"{sheet_id}:1"',
    }
    assert (body["record_id"], body["module_id"]) == (
        (str(world.record.id), None) if anchor == "record" else (None, str(world.module.id))
    )
    assert body["owner"] == {"id": str(world.peer.id), "display_name": world.peer.username}
    assert body["structure"] == STRUCTURE

    # SH-1, SH-67: it shows in the anchor's list and in My sheets of its creator.
    anchor_list = (
        f"/api/records/{world.record.id}/worksheets" if anchor == "record"
        else f"/api/modules/{world.module.id}/worksheets"
    )
    for listed in (owner.get(anchor_list), owner.get("/api/worksheets")):
        assert sheet_id in {item["id"] for item in listed.json()["items"]}
    path = f"/api/worksheets/{sheet_id}"
    read = owner.get(path)
    assert (read.status_code, read.headers["ETag"]) == (200, f'"{sheet_id}:1"')
    assert owner.patch(path, json={"title": "Marks"}).status_code == 428
    assert owner.patch(
        path, json={"title": "Marks"}, headers={"If-Match": f'"{sheet_id}:0"'}
    ).json()["detail"]["code"] == "worksheet_changed"
    renamed = owner.patch(path, json={"title": "Marks"}, headers={"If-Match": f'"{sheet_id}:1"'})
    assert (renamed.status_code, renamed.json()["title"], renamed.headers["ETag"]) == (
        200, "Marks", f'"{sheet_id}:2"'
    )
    assert owner.delete(path).status_code == 428
    assert owner.delete(path, headers={"If-Match": f'"{sheet_id}:1"'}).status_code == 412
    assert owner.delete(path, headers={"If-Match": f'"{sheet_id}:2"'}).status_code == 204
    assert _body(owner.get(path)) == NOT_FOUND
    restored = owner.post(f"{path}/restore")
    assert (restored.status_code, restored.json()["is_deleted"]) == (200, False)
    assert owner.post(f"{path}/restore").json()["detail"]["code"] == "worksheet_not_deleted"


@pytest.mark.parametrize("level", [AccessLevel.READ, AccessLevel.WRITE, AccessLevel.MANAGE])
def test_a_member_with_any_level_on_the_module_creates_a_sheet(
    application: FastAPI, integration_db: Session, level: AccessLevel,
) -> None:
    world = sheet_world(integration_db)
    person = _member_with(integration_db, world, level)
    response = _create(_as(application, integration_db, person), _anchor(world, "record"))
    assert response.status_code == 201, response.text


def test_a_guest_reader_cannot_create(application: FastAPI, integration_db: Session) -> None:
    world = sheet_world(integration_db)
    response = _create(_as(application, integration_db, world.guest), _anchor(world, "record"))
    assert (response.status_code, response.json()["detail"]["code"]) == (
        403, "worksheet_create_forbidden"
    )


def test_a_create_on_an_unreadable_deleted_or_ambiguous_anchor_is_refused(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    stranger = _as(application, db, add_user(db))
    assert _create(stranger, _anchor(world, "record")).json()["detail"]["code"] == (
        "record_not_found"
    )
    assert _create(stranger, _anchor(world, "module")).json()["detail"]["code"] == (
        "module_not_found"
    )
    reader = _as(application, db, world.peer)
    assert _create(reader, {"record_id": str(uuid7())}).status_code == 404
    both = {**_anchor(world, "record"), **_anchor(world, "module")}
    assert _create(reader, both).status_code == 422
    assert _create(reader, {}).status_code == 422
    world.record.is_deleted, world.record.deleted_at = True, utc_now()
    db.flush()
    refused = _create(reader, _anchor(world, "record"))
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "record_not_active")
    # A lifecycle close deletes the module and every record of it: both anchors refuse.
    world.module.is_deleted, world.module.deleted_at = True, utc_now()
    db.flush()
    for anchor, code in (("record", "record_not_active"), ("module", "module_not_active")):
        refused = _create(reader, _anchor(world, anchor))
        assert (refused.status_code, refused.json()["detail"]["code"]) == (409, code)


def _requests(sheet_id: object) -> list[tuple[str, str, dict[str, Any]]]:
    path = f"/api/worksheets/{sheet_id}"
    match = {"If-Match": f'"{sheet_id}:1"'}
    return [
        ("GET", path, {}),
        ("PATCH", path, {"json": {"title": "X"}}),
        ("PATCH", path, {"json": {"title": "X"}, "headers": match}),
        ("DELETE", path, {}),
        ("DELETE", path, {"headers": match}),
        ("POST", f"{path}/restore", {}),
        ("GET", f"{path}/share-candidates", {}),
    ]


def test_a_hidden_sheet_answers_exactly_like_a_missing_one_on_every_route(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    for person in (world.peer, world.manager, world.admin):
        client = _as(application, db, person)
        for (method, hidden, options), (_m, missing, _o) in zip(
            _requests(world.sheet.id), _requests(uuid7()), strict=True,
        ):
            answers = [client.request(method, path, **options) for path in (hidden, missing)]
            assert [(answer.status_code, _body(answer)) for answer in answers] == [
                (404, NOT_FOUND), (404, NOT_FOUND),
            ], (person.username, method, options)


def test_a_recipient_reads_but_only_the_owner_renames_deletes_or_lists_candidates(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    path = f"/api/worksheets/{world.sheet.id}"
    match = {"If-Match": f'"{world.sheet.id}:1"'}
    for person, level in ((world.viewer, "view"), (world.editor, "edit"),
                          (world.group_member, "edit"), (world.guest, "view")):
        client = _as(application, db, person)
        assert client.get(path).json()["my_level"] == level
        for answer in (
            client.patch(path, json={"title": "X"}, headers=match),
            client.delete(path, headers=match),
            client.get(f"{path}/share-candidates"),
        ):
            assert (answer.status_code, answer.json()["detail"]["code"]) == (
                403, "worksheet_read_only"
            )


def test_an_open_sheet_reads_for_every_record_reader_and_cannot_be_renamed_or_deleted(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    # Invited again after the sheet was made: the owner is active, the sheet stays open.
    membership_of(db, world.owner.id).worksheets_released_at = (
        world.sheet.created_at + timedelta(seconds=1)
    )
    db.flush()
    path = f"/api/worksheets/{world.sheet.id}"
    for person in (world.peer, world.admin, world.owner):
        read = _as(application, db, person).get(path).json()
        assert (read["state"], read["my_level"]) == ("open", "view")
    owner = _as(application, db, world.owner)
    match = {"If-Match": f'"{world.sheet.id}:1"'}
    for answer in (
        owner.patch(path, json={"title": "X"}, headers=match),
        owner.delete(path, headers=match),
        owner.get(f"{path}/share-candidates"),
    ):
        assert (answer.status_code, answer.json()["detail"]["code"]) == (409, "worksheet_open")


def test_a_column_from_a_sheet_the_viewer_cannot_see_shows_no_source(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    seen = add_sheet(db, world.owner, record=world.record)
    hidden = add_sheet(db, world.peer, record=world.record)

    def from_sheet(key: str, source: Worksheet) -> dict[str, Any]:
        return {
            "key": key, "name": f"From {key}", "type": "sheet_lookup",
            "sheet_lookup": {
                "sourceWorksheetId": str(source.id), "sourceColumnKey": "c9",
                "linkKey": "c1", "sourceLinkKey": "c1",
            },
        }

    world.sheet.structure = {
        **STRUCTURE, "nextColumnSeq": 4,
        "columns": [
            {"key": "c1", "name": "Student", "type": "link",
             "link": {"moduleId": str(world.module.id)}},
            from_sheet("c2", seen), from_sheet("c3", hidden),
        ],
    }
    db.flush()
    columns = _as(application, db, world.owner).get(
        f"/api/worksheets/{world.sheet.id}"
    ).json()["structure"]["columns"]
    assert columns[1] == from_sheet("c2", seen)
    assert columns[2] == {
        "key": "c3", "name": "From c3", "type": "sheet_lookup", "state": "no_access",
    }


def test_share_candidates_are_visible_people_of_the_organization_and_the_owners_groups(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    home = world.sheet.org_id
    unseen = add_user(db, name="cand-unseen")  # no module, Board, group or chat in common
    seen = add_user(db, name="cand-seen")
    make_group_access(db, [seen], world.department, world.module, level=AccessLevel.READ)
    other = create_organization(db)
    create_member(db, other, UserRole.ADMIN.value, username=f"cand-away-{uuid7().hex[:8]}")
    scope_session(db, home)
    owner = _as(application, db, world.owner)
    path = f"/api/worksheets/{world.sheet.id}/share-candidates"
    found = owner.get(path, params={"q": "cand-"}).json()
    assert [person["id"] for person in found["people"]] == [str(seen.id)]
    assert str(unseen.id) not in {person["id"] for person in owner.get(path).json()["people"]}
    groups = owner.get(path).json()["groups"]
    assert [group["id"] for group in groups] == [str(world.reader_access.group_id)]


def test_share_candidates_keep_reading_past_a_page_of_people_the_owner_cannot_see(
    application: FastAPI, integration_db: Session, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.systems.openview.worksheets import candidates

    db = integration_db
    world = sheet_world(db)
    add_user(db, name="kpage-a")  # sorts first; shares nothing with the owner
    second = add_user(db, name="kpage-b")
    make_group_access(db, [second], world.department, world.module, level=AccessLevel.READ)
    monkeypatch.setattr(candidates, "_PAGE", 1)
    found = _as(application, db, world.owner).get(
        f"/api/worksheets/{world.sheet.id}/share-candidates", params={"q": "kpage-"},
    ).json()
    assert [person["id"] for person in found["people"]] == [str(second.id)]


def test_a_deleted_sheet_disappears_for_its_recipients(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    path = f"/api/worksheets/{world.sheet.id}"
    deleted = _as(application, db, world.owner).delete(
        path, headers={"If-Match": f'"{world.sheet.id}:1"'}
    )
    assert deleted.status_code == 204
    for person in (world.viewer, world.editor, world.group_member):
        client = _as(application, db, person)
        assert (client.get(path).status_code, _body(client.get(path))) == (404, NOT_FOUND)
        tab = client.get(f"/api/records/{world.record.id}/worksheets").json()["items"]
        assert tab == []


def test_an_open_sheet_cannot_be_restored(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    world.sheet.is_deleted, world.sheet.deleted_at = True, utc_now()
    membership_of(db, world.owner.id).worksheets_released_at = (
        world.sheet.created_at + timedelta(seconds=1)
    )
    db.flush()
    refused = _as(application, db, world.owner).post(f"/api/worksheets/{world.sheet.id}/restore")
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "worksheet_open")


def test_a_share_candidate_with_a_blank_display_name_shows_their_username(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    blank = add_user(db, name="blank-name")
    blank.display_name = ""
    make_group_access(db, [blank], world.department, world.module, level=AccessLevel.READ)
    db.flush()
    found = _as(application, db, world.owner).get(
        f"/api/worksheets/{world.sheet.id}/share-candidates", params={"q": "blank-name"},
    ).json()
    assert found["people"] == [{"id": str(blank.id), "display_name": blank.username}]
