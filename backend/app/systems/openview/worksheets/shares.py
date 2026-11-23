"""Sharing a sheet (routes 16 to 19; V2, V5, V6, V9, L7, D14 R1).

Only the owner of a private sheet shares it. A person target must be an active member of
the bound organization whom the owner can see (`visible_person_ids`); a group target must
be a live group of the bound organization. Any other target answers the same 404 as an ID
that does not exist, and no answer names it. A guest gets View only.
"""

from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.listing import ListQuerySpec, StandardListResponse, execute_standard_list
from app.core.base_model import utc_now
from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group
from app.systems.access.policy.readers import active_account_clause
from app.systems.access.policy.transaction_access import forget_access
from app.systems.access.users.membership import bound_membership_join
from app.systems.access.users.models import Membership, User, UserRole
from app.systems.access.users.person_visibility import visible_person_ids
from app.systems.openview.worksheets.access import load_visible_worksheet, worksheet_states
from app.systems.openview.worksheets.locking import lock_for_write
from app.systems.openview.worksheets.models import Worksheet, WorksheetShare
from app.systems.openview.worksheets.schemas import (
    SheetGroupRef,
    SheetShare,
    SheetShareCreate,
    SheetShareListRequest,
    SheetShareSort,
)
from app.systems.openview.worksheets.serializers import person_refs

SHARE_LIST = ListQuerySpec(
    sort_fields={SheetShareSort.CREATED_AT: cast(ColumnElement[Any], WorksheetShare.created_at)},
    default_sort=SheetShareSort.CREATED_AT,
    tie_breaker=cast(ColumnElement[Any], WorksheetShare.id),
)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message})


def _target_not_found() -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, "share_target_not_found",
                  "Person or group not found")


def _guest_view_only() -> HTTPException:
    return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "guest_view_only",
                  "A guest can only get View")


def owned_private(db: Session, user: User, worksheet_id: UUID) -> Worksheet:
    """404 when hidden, 409 when open (L7), 403 for anyone but the owner (V5)."""

    sheet = load_visible_worksheet(db, user, worksheet_id)
    if sheet is None:
        raise _error(status.HTTP_404_NOT_FOUND, "worksheet_not_found", "Sheet not found")
    present, level = worksheet_states(db, user, [sheet])[sheet.id]
    if not present:
        raise _error(status.HTTP_409_CONFLICT, "worksheet_open", "The sheet is open and read-only")
    if level != "owner":
        raise _error(status.HTTP_403_FORBIDDEN, "worksheet_read_only", "Only the owner can do this")
    return sheet


def _locked(db: Session, user: User, sheet: Worksheet) -> Worksheet:
    lock_for_write(db, sheet, user.id, [])
    forget_access(db, user.id)  # R4: the owner check again, from fresh reads
    return owned_private(db, user, sheet.id)


def _person(db: Session, owner: User, user_id: UUID) -> Membership:
    membership = db.scalar(
        select(Membership).join(User, bound_membership_join())
        .where(Membership.user_id == user_id, active_account_clause())
    )
    if membership is None or user_id == owner.id or (
        user_id not in visible_person_ids(db, owner, [user_id])
    ):
        raise _target_not_found()
    return membership


def _group(db: Session, group_id: UUID) -> Group:
    group = db.scalar(select(Group).where(
        Group.id == group_id, Group.org_id == bound_organization_column(),
        Group.is_deleted.is_(False),
    ))
    if group is None:
        raise _target_not_found()
    return group


def _live_share(db: Session, sheet: Worksheet, share_id: UUID) -> WorksheetShare:
    share = db.get(WorksheetShare, share_id)
    if share is None or share.worksheet_id != sheet.id or share.is_deleted:
        raise _error(status.HTTP_404_NOT_FOUND, "share_not_found", "Share not found")
    return share


def share_views(db: Session, shares: Sequence[WorksheetShare]) -> list[SheetShare]:
    people = person_refs(db, (share.user_id for share in shares if share.user_id))
    group_ids = {share.group_id for share in shares if share.group_id}
    groups = {
        group.id: group.name
        for group in db.scalars(select(Group).where(Group.id.in_(group_ids)))
    } if group_ids else {}
    return [
        SheetShare(
            id=share.id, subject="user" if share.user_id else "group",
            user=people.get(share.user_id) if share.user_id else None,
            group=SheetGroupRef(id=share.group_id, name=groups.get(share.group_id, ""))
            if share.group_id else None,
            level="edit" if share.level == "edit" else "view",
            created_at=share.created_at,
        )
        for share in shares
    ]


def list_shares(
    db: Session, user: User, worksheet_id: UUID, params: SheetShareListRequest,
) -> StandardListResponse[SheetShare]:
    sheet = owned_private(db, user, worksheet_id)
    result = execute_standard_list(db, select(WorksheetShare).where(
        WorksheetShare.worksheet_id == sheet.id, WorksheetShare.is_deleted.is_(False),
    ), params, SHARE_LIST)
    return StandardListResponse(items=share_views(db, result.items),
                                pagination=result.pagination)


def create_share(
    db: Session, user: User, worksheet_id: UUID, payload: SheetShareCreate,
) -> WorksheetShare:
    sheet = _locked(db, user, owned_private(db, user, worksheet_id))
    if payload.subject == "user":
        membership = _person(db, user, cast(UUID, payload.user_id))
        if payload.level == "edit" and membership.role == UserRole.GUEST.value:
            raise _guest_view_only()
    else:
        _group(db, cast(UUID, payload.group_id))
    existing = db.scalar(select(WorksheetShare.id).where(
        WorksheetShare.worksheet_id == sheet.id, WorksheetShare.is_deleted.is_(False),
        WorksheetShare.subject == payload.subject,
        WorksheetShare.user_id.is_(None) if payload.user_id is None
        else WorksheetShare.user_id == payload.user_id,
        WorksheetShare.group_id.is_(None) if payload.group_id is None
        else WorksheetShare.group_id == payload.group_id,
    ))
    if existing is not None:
        raise _error(status.HTTP_409_CONFLICT, "share_exists", "This share exists already")
    share = WorksheetShare(
        org_id=sheet.org_id, worksheet_id=sheet.id, subject=payload.subject,
        user_id=payload.user_id, group_id=payload.group_id, level=payload.level,
        created_by=user.id,
    )
    db.add(share)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "share_exists",
                     "This share exists already") from error
    return share


def change_share(
    db: Session, user: User, worksheet_id: UUID, share_id: UUID, level: str,
) -> WorksheetShare:
    sheet = owned_private(db, user, worksheet_id)
    _live_share(db, sheet, share_id)
    sheet = _locked(db, user, sheet)
    share = _live_share(db, sheet, share_id)
    if level == "edit" and share.user_id is not None:
        membership = db.scalar(select(Membership).where(
            Membership.user_id == share.user_id,
            Membership.org_id == bound_organization_column(),
        ))
        if membership is not None and membership.role == UserRole.GUEST.value:
            raise _guest_view_only()
    share.level = level
    return share


def remove_share(db: Session, user: User, worksheet_id: UUID, share_id: UUID) -> None:
    sheet = owned_private(db, user, worksheet_id)
    _live_share(db, sheet, share_id)
    sheet = _locked(db, user, sheet)
    share = _live_share(db, sheet, share_id)
    share.is_deleted, share.deleted_at = True, utc_now()
