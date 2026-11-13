"""``has_other_grants`` on access groups (P3-B2, Security finding S3-4).

Membership in a group gives a Board level, a Comms channel grant or a Comms capability
beside its department access. A group response says so, so Add access never reuses
such a group as "exactly this access".
"""

from collections.abc import Callable
from importlib import import_module
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.core.database.base import Base
from app.core.database.organization_scope import scope_session
from app.systems.access.policy.models import Group
from app.systems.access.policy.other_grants import groups_with_other_grants
from app.systems.access.users.models import User
from app.systems.boards.models import BoardGroup
from app.systems.comms.conversations.models import CommsCategory, CommsChannelAccess
from app.systems.comms.settings.models import CommsCapabilityGrant
from tests.access.user_admin_support import UserAdminWorld
from tests.access.user_admin_support import world as world
from tests.boards.support import project_board
from tests.conftest import create_organization
from tests.rbac.support import organization

# Each table with a foreign key to ``groups``, and why it does or does not give a member more.
GROUP_REFERENCES = {
    "group_members": "membership itself",
    "group_access": "department and module levels, listed in `access`",
    "board_groups": "a project Board level: has_other_grants",
    "comms_channel_access": "a Comms channel or category grant: has_other_grants",
    "comms_capability_grants": "a Comms capability: has_other_grants",
    "sandbox_derived_objects": "the publish's link to a derived group; gives a member nothing",
}


def _deleted(row: Any) -> Any:
    row.is_deleted, row.deleted_at = True, utc_now()
    return row


def _group(db: Session, org_id: Any = None) -> Group:
    group = Group(org_id=org_id or organization(db).id, name=f"Other grants {uuid7().hex}")
    db.add(group)
    db.flush()
    return group


def _board(db: Session, group: Group) -> BoardGroup:
    row = BoardGroup(
        org_id=group.org_id, board_id=project_board(db).id, group_id=group.id, level="read"
    )
    db.add(row)
    return row


def _channel(db: Session, group: Group | None, creator: User, user: User | None = None) -> Any:
    category = CommsCategory(org_id=organization(db).id, name=f"Category {uuid7().hex}")
    db.add(category)
    db.flush()
    row = CommsChannelAccess(
        org_id=category.org_id,
        category_id=category.id,
        subject="group" if group is not None else "user",
        group_id=None if group is None else group.id,
        user_id=None if user is None else user.id,
        level="read",
        created_by=creator.id,
    )
    db.add(row)
    return row


def _capability(db: Session, group: Group | None, org_id: Any = None) -> CommsCapabilityGrant:
    row = CommsCapabilityGrant(
        org_id=org_id or (group.org_id if group is not None else organization(db).id),
        scope="workspace",
        capability="reply",
        subject="group" if group is not None else "everyone",
        group_id=None if group is None else group.id,
        granted=True,
    )
    db.add(row)
    return row


SOURCES: dict[str, Callable[[Session, Group, User], Any]] = {
    "board": lambda db, group, _admin: _board(db, group),
    "channel": lambda db, group, admin: _channel(db, group, admin),
    "capability": lambda db, group, _admin: _capability(db, group),
}


def _listed(world: UserAdminWorld, *groups: Group) -> dict[str, bool]:
    response = world.client(world.admin).get(
        "/api/access/groups", params={"search": "Other grants", "limit": 100}
    )
    assert response.status_code == 200, response.text
    flags = {item["id"]: item["has_other_grants"] for item in response.json()["items"]}
    return {str(group.id): flags[str(group.id)] for group in groups}


def _read(world: UserAdminWorld, group: Group) -> bool:
    response = world.client(world.admin).get(f"/api/access/groups/{group.id}")
    assert response.status_code == 200, response.text
    return bool(response.json()["has_other_grants"])


@pytest.mark.integration
@pytest.mark.parametrize("source", sorted(SOURCES))
def test_one_live_grant_of_each_source_sets_the_flag_in_the_list_and_the_read(
    world: UserAdminWorld, source: str
) -> None:
    """B2-AC1 (board), B2-AC2 (channel), B2-AC3 (capability `reply`)."""

    db = world.db
    granted, plain = _group(db), _group(db)
    SOURCES[source](db, granted, world.admin)
    db.commit()
    assert _listed(world, granted, plain) == {str(granted.id): True, str(plain.id): False}
    assert (_read(world, granted), _read(world, plain)) == (True, False)


@pytest.mark.integration
def test_deleted_user_and_everyone_rows_leave_the_flag_false(world: UserAdminWorld) -> None:
    """B2-AC4: none, soft-deleted rows only, a user channel grant and an everyone capability."""

    db = world.db
    nothing, deleted = _group(db), _group(db)
    _deleted(_board(db, deleted))
    _deleted(_channel(db, deleted, world.admin))
    _deleted(_capability(db, deleted))
    _channel(db, None, world.admin, user=world.colleague)
    _capability(db, None)
    db.commit()
    assert _listed(world, nothing, deleted) == {str(nothing.id): False, str(deleted.id): False}


@pytest.mark.integration
def test_the_list_reads_the_flag_for_the_whole_page_in_one_statement(
    world: UserAdminWorld,
) -> None:
    """B2-AC5: a page of three groups costs the same statements as a page of one."""

    db = world.db
    groups = [_group(db) for _ in range(3)]
    for group in groups:
        _capability(db, group)
    db.commit()

    def statements(limit: int) -> int:
        seen: list[str] = []

        def count(*_arguments: object) -> None:
            seen.append("statement")

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", count)
        try:
            response = world.client(world.admin).get(
                "/api/access/groups", params={"search": "Other grants", "limit": limit}
            )
        finally:
            event.remove(connection, "before_cursor_execute", count)
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == limit
        assert all(item["has_other_grants"] for item in response.json()["items"])
        return len(seen)

    statements(1)  # The first request of the transaction also resolves the actor's access.
    assert statements(1) == statements(3)
    seen: list[str] = []
    connection = db.connection()

    def listener(*_arguments: object) -> None:
        seen.append("statement")

    event.listen(connection, "before_cursor_execute", listener)
    try:
        flagged = groups_with_other_grants(db, [group.id for group in groups])
    finally:
        event.remove(connection, "before_cursor_execute", listener)
    assert (flagged, len(seen)) == (frozenset(group.id for group in groups), 1)


@pytest.mark.integration
def test_every_group_write_response_carries_the_flag(world: UserAdminWorld) -> None:
    """B2-AC6: create (a new group is false), patch, members and access."""

    client = world.client(world.admin)
    created = client.post("/api/access/groups", json={"name": f"Other grants {uuid7().hex}"})
    assert created.status_code == 201, created.text
    assert created.json()["has_other_grants"] is False

    group = world.group
    _board(world.db, group)
    world.db.commit()

    def etag() -> str:
        world.db.refresh(group)
        return f'"{group.id}:{group.revision}"'

    patched = client.patch(
        f"/api/access/groups/{group.id}", json={"name": f"Renamed {uuid7().hex}"},
        headers={"If-Match": etag()},
    )
    members = client.put(
        f"/api/access/groups/{group.id}/members",
        json={"member_ids": [str(world.colleague.id)]}, headers={"If-Match": etag()},
    )
    access = client.put(
        f"/api/access/groups/{group.id}/access",
        json={"access": [{"department_id": str(world.inventory.id), "level": "read"}]},
        headers={"If-Match": etag()},
    )
    for response in (patched, members, access):
        assert response.status_code == 200, response.text
        assert response.json()["has_other_grants"] is True


@pytest.mark.integration
def test_a_grant_of_another_organization_never_sets_the_flag(
    integration_owner_db: Session,
) -> None:
    """B2-AC8: the helper reads the bound organization only (the owner role skips RLS)."""

    db = integration_owner_db
    home = organization(db)
    away = create_organization(db)
    group = _group(db, away.id)
    _capability(db, group, away.id)
    db.flush()
    assert groups_with_other_grants(db, [group.id]) == frozenset({group.id})
    scope_session(db, home.id)
    assert groups_with_other_grants(db, [group.id]) == frozenset()


def test_tables_with_a_foreign_key_to_groups_are_all_decided() -> None:
    """B2-AC7: a new reference to `groups` must be judged before it ships."""

    import_module("app.core.database.model_registry")  # Every model is in the metadata.
    referencing = {
        table.name
        for table in Base.metadata.tables.values()
        for key in table.foreign_keys
        if key.column.table.name == "groups"
    }
    assert referencing == set(GROUP_REFERENCES), (
        "A table references groups: decide whether membership in a group gives something "
        f"through this table. New: {sorted(referencing - set(GROUP_REFERENCES))}; "
        f"gone: {sorted(set(GROUP_REFERENCES) - referencing)}"
    )


def test_the_flag_reader_skips_an_empty_page_and_fails_closed_on_a_database_error() -> None:
    """B2-AC5: no statement for an empty page; a failed read is 503, never a false "false"."""

    quiet = Mock(spec=Session)
    assert groups_with_other_grants(quiet, []) == frozenset()
    quiet.scalars.assert_not_called()
    broken = Mock(spec=Session)
    broken.scalars.side_effect = SQLAlchemyError("unavailable")
    with pytest.raises(HTTPException) as refused:
        groups_with_other_grants(broken, [uuid7()])
    assert refused.value.status_code == 503

