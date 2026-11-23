"""The four leave paths open the owner's private sheets (L0-L5, L8, H5; SH-13, 16, 47, 60, 61).

The open state is derived (D0), so each test checks what each person can do after the real
admin route commits, and the one security event that counts the sheets that opened.
"""

from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.policy.models import GroupMember
from app.systems.access.users import service
from app.systems.access.users.models import Membership, UserStatus
from app.systems.access.users.schemas import InvitationCreate
from app.systems.openview.worksheets.access import worksheet_level
from tests.conftest import make_operator
from tests.worksheets.leave_support import LeaveWorld
from tests.worksheets.leave_support import leave_world as leave_world
from tests.worksheets.support import add_sheet

pytestmark = pytest.mark.integration


def _home_membership(world: LeaveWorld) -> Membership:
    membership = world.db.scalar(select(Membership).where(
        Membership.user_id == world.sheets.owner.id,
        Membership.org_id == world.sheets.sheet.org_id,
    ))
    assert membership is not None
    return membership


def _levels(world: LeaveWorld) -> dict[str, Any]:
    sheets, sheet = world.sheets, world.sheets.sheet
    return {
        name: worksheet_level(world.db, person, sheet)
        for name, person in (("edit share", sheets.editor), ("peer", sheets.peer),
                             ("outside", sheets.outsider))
    }


PRIVATE = {"edit share": "edit", "peer": None, "outside": None}
OPEN = {"edit share": "view", "peer": "view", "outside": None}


def _leave(world: LeaveWorld, path: str) -> Any:
    admin, owner = world.sheets.admin, world.sheets.owner
    client = world.client(admin)
    if path in {"membership_disabled", "membership_removed"}:
        world.share_another_organization()
    if path in {"account_disabled", "membership_disabled"}:
        return client.patch(f"/api/users/{owner.id}", json={"status": "disabled"})
    return client.delete(f"/api/users/{owner.id}")


@pytest.mark.parametrize(
    "path", ["membership_disabled", "account_disabled", "membership_removed", "account_deleted"],
)
def test_each_leave_path_opens_the_private_sheets_and_reports_their_count(
    leave_world: LeaveWorld, path: str,
) -> None:
    world = leave_world
    assert _levels(world) == PRIVATE
    answer = _leave(world, path)
    assert answer.status_code in (200, 204), answer.text
    world.db.expire_all()
    assert _levels(world) == OPEN
    opened = [event for event in world.events
              if event["event_type"] == "worksheets.opened_on_leave"]
    assert opened == [{
        "event_type": "worksheets.opened_on_leave", "subject_id": world.sheets.owner.id,
        "metadata": {"opened_count": 2, "path": path},
    }]


def test_a_re_enabled_owner_gets_the_sheets_back_with_their_shares(
    leave_world: LeaveWorld,
) -> None:
    world = leave_world
    owner = world.sheets.owner
    assert _leave(world, "account_disabled").status_code == 200
    enabled = world.client(world.sheets.admin).patch(
        f"/api/users/{owner.id}", json={"status": "active"},
    )
    assert enabled.status_code == 200, enabled.text
    world.db.expire_all()
    assert _levels(world) == PRIVATE


def test_a_restored_member_gets_the_sheets_back_private(leave_world: LeaveWorld) -> None:
    world = leave_world
    owner = world.sheets.owner
    assert _leave(world, "membership_removed").status_code == 204
    assert _levels(world) == OPEN
    restored = world.client(world.sheets.admin).post(f"/api/users/{owner.id}/restore")
    assert restored.status_code == 200, restored.text
    world.db.expire_all()
    assert _levels(world) == PRIVATE
    assert _home_membership(world).worksheets_released_at is None


def test_a_restored_account_gets_the_sheets_back_private(leave_world: LeaveWorld) -> None:
    world = leave_world
    make_operator(world.db, world.sheets.admin)
    world.db.commit()
    assert _leave(world, "account_deleted").status_code == 204
    restored = world.client(world.sheets.admin).post(
        f"/api/users/{world.sheets.owner.id}/restore"
    )
    assert restored.status_code == 200, restored.text
    world.db.expire_all()
    assert _levels(world) == PRIVATE


def test_a_new_invitation_after_removal_keeps_the_old_sheets_open(
    leave_world: LeaveWorld,
) -> None:
    world, db = leave_world, leave_world.db
    owner = world.sheets.owner
    owner.supabase_user_id = owner.id
    db.commit()
    assert _leave(world, "membership_removed").status_code == 204
    service.invite_user(
        db, InvitationCreate(email=owner.email, username=owner.username, role="member"),
        actor_id=world.sheets.admin.id, client=Mock(),
    )
    membership = _home_membership(world)
    assert membership.worksheets_released_at is not None
    membership.status, membership.invitation_accepted_at = UserStatus.ACTIVE.value, utc_now()
    # The invitation dropped the old group rows; read on the module comes back with a group.
    db.add(GroupMember(org_id=membership.org_id, user_id=owner.id,
                       group_id=world.sheets.reader_access.group_id))
    db.flush()
    assert _levels(world) == OPEN  # Decision 6: the earlier sheets stay open
    later = add_sheet(db, owner, record=world.sheets.record)
    assert worksheet_level(db, world.sheets.peer, later) is None
    assert worksheet_level(db, owner, later) == "owner"


def test_a_leave_with_no_private_sheets_writes_no_sheet_event(
    leave_world: LeaveWorld, integration_db: Session,
) -> None:
    world = leave_world
    for sheet in world.opening:
        sheet.is_deleted, sheet.deleted_at = True, utc_now()
    integration_db.commit()
    assert _leave(world, "account_disabled").status_code == 200
    assert [event for event in world.events
            if event["event_type"] == "worksheets.opened_on_leave"] == []
