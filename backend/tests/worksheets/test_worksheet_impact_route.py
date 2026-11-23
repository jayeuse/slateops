"""Route 24: how many private sheets a leave would open (L5, D3.2; SH-55)."""

import pytest
from uuid6 import uuid7

from app.core.database.organization_scope import scope_session
from tests.conftest import create_member, create_organization
from tests.worksheets.leave_support import LeaveWorld
from tests.worksheets.leave_support import leave_world as leave_world

pytestmark = pytest.mark.integration


def test_an_admin_reads_the_count_and_nothing_else(leave_world: LeaveWorld) -> None:
    world = leave_world
    path = f"/api/users/{world.sheets.owner.id}/worksheet-impact"
    answer = world.client(world.sheets.admin).get(path)
    assert (answer.status_code, answer.json()) == (200, {"opening_count": 2})
    assert world.client(world.sheets.admin).get(
        f"/api/users/{world.sheets.peer.id}/worksheet-impact"
    ).json() == {"opening_count": 0}


def test_a_member_is_refused(leave_world: LeaveWorld) -> None:
    world = leave_world
    answer = world.client(world.sheets.editor).get(
        f"/api/users/{world.sheets.owner.id}/worksheet-impact"
    )
    assert answer.status_code == 403


def test_a_person_of_another_organization_is_not_found(leave_world: LeaveWorld) -> None:
    world, db = leave_world, leave_world.db
    home = world.sheets.sheet.org_id
    other = create_organization(db)
    stranger, _ = create_member(db, other, "member")
    scope_session(db, home)
    db.commit()
    admin = world.client(world.sheets.admin)
    for user_id in (stranger.id, uuid7()):
        answer = admin.get(f"/api/users/{user_id}/worksheet-impact")
        assert answer.status_code == 404, answer.text
