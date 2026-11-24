"""Routes 16 to 19: sharing a sheet (V2, V5, V6, V9, L7, D14 R1; SH-8 to SH-11)."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.core.database.organization_scope import scope_session
from app.systems.access.policy.models import AccessLevel, Group, GroupMember
from app.systems.access.users.models import User, UserRole
from tests.conftest import create_member, create_organization, membership_of
from tests.rbac.support import _client, add_user, make_group_access
from tests.worksheets.support import SheetWorld, sheet_world

pytestmark = pytest.mark.integration
TARGET_NOT_FOUND = {"detail": {"code": "share_target_not_found",
                               "message": "Person or group not found"}}


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def world(integration_db: Session) -> SheetWorld:
    return sheet_world(integration_db)


def _as(application: FastAPI, db: Session, person: User) -> TestClient:
    return _client(application, person, db)


def _body(response: Any) -> Any:
    return {key: value for key, value in response.json().items() if key != "request_id"}


def _share(application: FastAPI, db: Session, world: SheetWorld, body: dict[str, Any],
           person: User | None = None) -> Any:
    return _as(application, db, person or world.owner).post(
        f"/api/worksheets/{world.sheet.id}/shares", json=body,
    )


def _level(application: FastAPI, db: Session, world: SheetWorld, person: User) -> Any:
    answer = _as(application, db, person).get(f"/api/worksheets/{world.sheet.id}")
    return answer.json()["my_level"] if answer.status_code == 200 else answer.status_code


def _reader(db: Session, world: SheetWorld, name: str) -> User:
    person = add_user(db, name=name)
    make_group_access(db, [person], world.department, world.module, level=AccessLevel.READ)
    return person


def test_the_owner_shares_changes_and_removes_a_persons_access(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    friend = _reader(db, world, "share-friend")
    assert _level(application, db, world, friend) == 404
    created = _share(application, db, world,
                     {"subject": "user", "user_id": str(friend.id), "level": "view"})
    assert created.status_code == 201, created.text
    share = created.json()
    assert {key: share[key] for key in ("subject", "user", "group", "level")} == {
        "subject": "user",
        "user": {"id": str(friend.id), "display_name": friend.username, "is_guest": False},
        "group": None, "level": "view",
    }
    assert _level(application, db, world, friend) == "view"
    path = f"/api/worksheets/{world.sheet.id}/shares/{share['id']}"

    def owner() -> TestClient:  # one app: each client sets the acting person again
        return _as(application, db, world.owner)

    assert owner().patch(path, json={"level": "edit"}).json()["level"] == "edit"
    assert _level(application, db, world, friend) == "edit"
    assert owner().delete(path).status_code == 204
    assert _level(application, db, world, friend) == 404
    listed = owner().get(f"/api/worksheets/{world.sheet.id}/shares").json()["items"]
    assert {item["level"] for item in listed} == {"view", "edit"}
    assert str(friend.id) not in str(listed)


def test_a_group_share_follows_membership_and_the_higher_level_wins(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    friend = _reader(db, world, "group-friend")
    team = Group(org_id=world.sheet.org_id, name=f"Team {uuid7().hex}")
    db.add(team)
    db.flush()
    member = GroupMember(org_id=team.org_id, group_id=team.id, user_id=friend.id)
    # The owner shares only with groups they belong to (DEC-0047 1).
    db.add_all([member, GroupMember(org_id=team.org_id, group_id=team.id,
                                    user_id=world.owner.id)])
    db.flush()
    created = _share(application, db, world,
                     {"subject": "group", "group_id": str(team.id), "level": "view"})
    assert created.status_code == 201, created.text
    assert created.json()["group"] == {"id": str(team.id), "name": team.name, "member_count": 2}
    assert _level(application, db, world, friend) == "view"
    member.is_deleted, member.deleted_at = True, utc_now()
    db.flush()
    assert _level(application, db, world, friend) == 404
    member.is_deleted, member.deleted_at = False, None
    db.flush()
    assert _level(application, db, world, friend) == "view"
    assert _share(application, db, world, {
        "subject": "user", "user_id": str(friend.id), "level": "edit",
    }).status_code == 201
    assert _level(application, db, world, friend) == "edit"


def test_a_guest_gets_view_and_never_edit(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    guest = add_user(db, name="share-guest", role=UserRole.GUEST)
    make_group_access(db, [guest], world.department, world.module, level=AccessLevel.READ)
    refused = _share(application, db, world,
                     {"subject": "user", "user_id": str(guest.id), "level": "edit"})
    assert (refused.status_code, refused.json()["detail"]["code"]) == (422, "guest_view_only")
    created = _share(application, db, world,
                     {"subject": "user", "user_id": str(guest.id), "level": "view"})
    assert created.status_code == 201
    assert _level(application, db, world, guest) == "view"
    raised = _as(application, db, world.owner).patch(
        f"/api/worksheets/{world.sheet.id}/shares/{created.json()['id']}", json={"level": "edit"},
    )
    assert (raised.status_code, raised.json()["detail"]["code"]) == (422, "guest_view_only")


def test_a_target_the_owner_cannot_see_answers_like_a_random_id(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    home = world.sheet.org_id
    deleted = Group(org_id=home, name=f"Gone {uuid7().hex}")
    db.add(deleted)
    db.flush()
    deleted.is_deleted, deleted.deleted_at = True, utc_now()
    other = create_organization(db)
    stranger, _ = create_member(db, other, UserRole.MEMBER.value)
    away = Group(org_id=other.id, name=f"Away {uuid7().hex}")
    db.add(away)
    db.flush()
    scope_session(db, home)
    targets = [
        {"subject": "user", "user_id": str(uuid7())},
        {"subject": "user", "user_id": str(stranger.id)},
        {"subject": "user", "user_id": str(world.outsider.id)},  # shares nothing with the owner
        {"subject": "group", "group_id": str(uuid7())},
        {"subject": "group", "group_id": str(deleted.id)},
        {"subject": "group", "group_id": str(away.id)},
    ]
    answers = [_share(application, db, world, {**target, "level": "view"}) for target in targets]
    assert [(answer.status_code, _body(answer)) for answer in answers] == [
        (404, TARGET_NOT_FOUND),
    ] * len(targets)


def test_a_second_live_share_to_the_same_target_is_refused(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    again = _share(application, integration_db, world,
                   {"subject": "user", "user_id": str(world.viewer.id), "level": "edit"})
    assert (again.status_code, again.json()["detail"]["code"]) == (409, "share_exists")


def test_only_the_owner_of_a_private_sheet_manages_its_shares(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    base = f"/api/worksheets/{world.sheet.id}/shares"
    share_id = _as(application, db, world.owner).get(base).json()["items"][0]["id"]
    body = {"subject": "user", "user_id": str(world.peer.id), "level": "view"}
    for person, expected in ((world.editor, (403, "worksheet_read_only")),
                             (world.peer, (404, "worksheet_not_found"))):
        client = _as(application, db, person)
        for answer in (client.get(base), client.post(base, json=body),
                       client.patch(f"{base}/{share_id}", json={"level": "view"}),
                       client.delete(f"{base}/{share_id}")):
            assert (answer.status_code, answer.json()["detail"]["code"]) == expected
    membership_of(db, world.owner.id).worksheets_released_at = (
        world.sheet.created_at + timedelta(seconds=1)
    )
    db.flush()
    owner = _as(application, db, world.owner)
    for answer in (owner.post(base, json=body),
                   owner.patch(f"{base}/{share_id}", json={"level": "view"}),
                   owner.delete(f"{base}/{share_id}")):
        assert (answer.status_code, answer.json()["detail"]["code"]) == (409, "worksheet_open")


def test_a_recipient_who_loses_record_read_gets_not_found_until_it_returns(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    row = db.scalars(select(GroupMember).where(
        GroupMember.group_id == world.reader_access.group_id,
        GroupMember.user_id == world.viewer.id,
    )).one()
    row.is_deleted, row.deleted_at = True, utc_now()
    db.flush()
    assert _level(application, db, world, world.viewer) == 404
    row.is_deleted, row.deleted_at = False, None
    db.flush()
    assert _level(application, db, world, world.viewer) == "view"


def test_a_group_the_owner_is_not_in_answers_like_a_random_id(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    others = Group(org_id=world.sheet.org_id, name=f"Others {uuid7().hex}")
    db.add(others)
    db.flush()
    db.add(GroupMember(org_id=others.org_id, group_id=others.id, user_id=world.peer.id))
    db.flush()
    answers = [
        _share(application, db, world, {"subject": "group", "group_id": str(group_id),
                                        "level": "view"})
        for group_id in (others.id, uuid7())
    ]
    assert [(answer.status_code, _body(answer)) for answer in answers] == [
        (404, TARGET_NOT_FOUND), (404, TARGET_NOT_FOUND),
    ]
    assert others.name not in str([answer.json() for answer in answers])


def test_a_share_to_a_person_who_left_cannot_change_but_can_be_removed(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    friend = _reader(db, world, "share-leaver")
    created = _share(application, db, world,
                     {"subject": "user", "user_id": str(friend.id), "level": "view"})
    path = f"/api/worksheets/{world.sheet.id}/shares/{created.json()['id']}"
    membership_of(db, friend.id).status = "disabled"
    db.flush()
    raised = _as(application, db, world.owner).patch(path, json={"level": "edit"})
    assert (raised.status_code, _body(raised)) == (404, TARGET_NOT_FOUND)
    assert _as(application, db, world.owner).delete(path).status_code == 204


def test_shares_and_candidates_tell_guests_and_group_sizes(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    """The Share dialog offers a guest View only and shows "Group · n people"."""

    db = integration_db
    owner = _as(application, db, world.owner)
    shares = {(item["user"] or item["group"])["id"]: item
              for item in owner.get(f"/api/worksheets/{world.sheet.id}/shares").json()["items"]}
    assert shares[str(world.guest.id)]["user"]["is_guest"] is True
    assert shares[str(world.viewer.id)]["user"]["is_guest"] is False
    assert shares[str(world.share_group.id)]["group"]["member_count"] == 1
    candidates = owner.get(f"/api/worksheets/{world.sheet.id}/share-candidates").json()
    people = {person["id"]: person["is_guest"] for person in candidates["people"]}
    assert (people[str(world.guest.id)], people[str(world.viewer.id)]) == (True, False)
    assert candidates["groups"] == [{"id": str(world.reader_access.group_id),
                                     "name": candidates["groups"][0]["name"],
                                     "member_count": 6}]
    created = _share(application, db, world, {
        "subject": "group", "group_id": str(world.reader_access.group_id), "level": "view",
    })
    assert created.status_code == 201, created.text
    assert created.json()["group"]["member_count"] == 6
