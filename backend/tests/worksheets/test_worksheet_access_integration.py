"""Who sees a sheet and at what level (spec D0, D2: V1-V7, L0, L2, L9; SH-11, SH-14, SH-19).

One rule answers every surface: `visible_worksheet_ids` (lists, counts, SSE),
`worksheet_level` (routes) and `load_visible_worksheet` (the identical 404).
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.core.database.organization_scope import scope_session
from app.systems.access.policy.models import GroupMember
from app.systems.access.users.models import UserRole, UserStatus
from app.systems.openview.worksheets.access import (
    load_visible_worksheet,
    visible_worksheet_ids,
    worksheet_level,
)
from app.systems.openview.worksheets.models import WorksheetShare
from tests.conftest import create_member, create_organization, membership_of
from tests.worksheets.support import SheetWorld, sheet_world

pytestmark = pytest.mark.integration


def _levels(db: Session, world: SheetWorld) -> dict[str, str | None]:
    return {
        name: worksheet_level(db, person, world.sheet) for name, person in world.people().items()
    }


def _seen(db: Session, world: SheetWorld) -> dict[str, bool]:
    """Whether the list clause and the loader each show the sheet; they must agree."""

    seen = {}
    for name, person in world.people().items():
        listed = world.sheet.id in visible_worksheet_ids(db, person, world.sheet.org_id)
        loaded = load_visible_worksheet(db, person, world.sheet.id) is world.sheet
        assert listed == loaded, name
        seen[name] = listed
    return seen


def _soft_delete(row: Any) -> None:
    row.is_deleted = True
    row.deleted_at = utc_now()


PRIVATE = {
    "owner": "owner", "view share": "view", "edit share": "edit",
    "edit share by group": "edit", "guest with edit share": "view",
    "peer": None, "module manager": None, "admin": None,
    "member without module access": None,
}


@pytest.mark.parametrize("anchor", ["record", "module"])
def test_a_private_sheet_reaches_its_owner_and_recipients_only(
    integration_db: Session, anchor,
) -> None:
    world = sheet_world(integration_db, anchor)
    assert _levels(integration_db, world) == PRIVATE
    assert _seen(integration_db, world) == {name: level is not None for name, level in
                                            PRIVATE.items()}


def _disable_membership(db: Session, world: SheetWorld) -> None:
    membership_of(db, world.owner.id).status = UserStatus.DISABLED.value


def _disable_account(db: Session, world: SheetWorld) -> None:
    world.owner.status = UserStatus.DISABLED.value


def _remove_membership(db: Session, world: SheetWorld) -> None:
    _soft_delete(membership_of(db, world.owner.id))


def _delete_account(db: Session, world: SheetWorld) -> None:
    _soft_delete(world.owner)


# Every reader of the record reads an open sheet; a member who cannot read it never does.
OPEN = {
    **{name: "view" for name in PRIVATE if name != "owner"},
    "member without module access": None,
}


@pytest.mark.parametrize("anchor", ["record", "module"])
@pytest.mark.parametrize(
    "leave", [_disable_membership, _disable_account, _remove_membership, _delete_account],
    ids=["membership-disabled", "account-disabled", "membership-removed", "account-deleted"],
)
def test_a_sheet_opens_read_only_to_every_reader_when_its_owner_leaves(
    integration_db: Session, anchor, leave,
) -> None:
    db = integration_db
    world = sheet_world(db, anchor)
    leave(db, world)
    db.flush()
    levels = _levels(db, world)
    assert levels.pop("owner") is None
    assert levels == OPEN
    seen = _seen(db, world)
    assert seen.pop("owner") is False
    assert seen == {name: level is not None for name, level in OPEN.items()}


def test_a_release_cutoff_after_the_sheet_keeps_it_open_when_the_owner_returns(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    membership = membership_of(db, world.owner.id)
    created = world.sheet.created_at
    for released_at, owner, peer in (
        (created + timedelta(seconds=1), "view", "view"),  # invited again after the sheet
        (created, "owner", None),  # the sheet was made at the cutoff: still private
        (created - timedelta(seconds=1), "owner", None),  # made after the new invitation
    ):
        membership.worksheets_released_at = released_at
        db.flush()
        assert worksheet_level(db, world.owner, world.sheet) == owner
        assert worksheet_level(db, world.peer, world.sheet) == peer


def test_an_owner_without_module_read_loses_the_sheet_and_it_stays_private(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    row = db.scalars(select(GroupMember).where(
        GroupMember.group_id == world.reader_access.group_id,
        GroupMember.user_id == world.owner.id,
    )).one()
    _soft_delete(row)
    db.flush()
    assert _levels(db, world) == {**PRIVATE, "owner": None}
    row.is_deleted, row.deleted_at = False, None
    db.flush()
    assert _levels(db, world) == PRIVATE  # read returns: the sheet returns to its owner


def test_a_recipient_without_record_read_loses_the_share_until_read_returns(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    row = db.scalars(select(GroupMember).where(
        GroupMember.group_id == world.reader_access.group_id,
        GroupMember.user_id == world.viewer.id,
    )).one()
    _soft_delete(row)
    db.flush()
    assert _levels(db, world) == {**PRIVATE, "view share": None}
    assert _seen(db, world)["view share"] is False
    row.is_deleted, row.deleted_at = False, None
    db.flush()
    assert _levels(db, world) == PRIVATE


@pytest.mark.parametrize("anchor", ["record", "module"])
def test_a_deleted_record_or_module_hides_its_sheets_from_everyone(
    integration_db: Session, anchor,
) -> None:
    db = integration_db
    world = sheet_world(db, anchor)
    _soft_delete(world.record if anchor == "record" else world.module)
    db.flush()
    assert _levels(db, world) == dict.fromkeys(PRIVATE)
    assert _seen(db, world) == dict.fromkeys(PRIVATE, False)


def test_a_removed_share_and_a_deleted_group_give_nothing(integration_db: Session) -> None:
    db = integration_db
    world = sheet_world(db)
    viewer_share = db.scalars(select(WorksheetShare).where(
        WorksheetShare.worksheet_id == world.sheet.id,
        WorksheetShare.user_id == world.viewer.id,
    )).one()
    _soft_delete(viewer_share)
    _soft_delete(world.share_group)
    db.flush()
    assert _levels(db, world) == {
        **PRIVATE, "view share": None, "edit share by group": None,
    }


def test_the_loader_answers_alike_for_a_missing_a_deleted_and_a_hidden_sheet(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    assert load_visible_worksheet(db, world.peer, world.sheet.id) is None
    assert load_visible_worksheet(db, world.owner, uuid7()) is None
    assert load_visible_worksheet(db, world.owner, world.sheet.id) is world.sheet
    _soft_delete(world.sheet)
    db.flush()
    assert load_visible_worksheet(db, world.owner, world.sheet.id) is None
    assert worksheet_level(db, world.owner, world.sheet) is None


def test_an_administrator_of_another_organization_sees_no_sheet(
    integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    home = world.sheet.org_id
    other = create_organization(db)  # binds the session to the other organization
    stranger, _membership = create_member(db, other, UserRole.ADMIN.value)
    assert visible_worksheet_ids(db, stranger, other.id) == frozenset()
    assert visible_worksheet_ids(db, stranger, home) == frozenset()
    assert load_visible_worksheet(db, stranger, world.sheet.id) is None
    scope_session(db, home)
    assert worksheet_level(db, stranger, world.sheet) is None
    assert load_visible_worksheet(db, stranger, world.sheet.id) is None
