"""Lock order for sheet writes (spec D3.3).

1. the owner's user row, FOR SHARE: a leave takes it FOR UPDATE, so a write either commits
   before the leave or sees the open state afterwards;
2. the records the write reads or links (the anchor and link targets), FOR SHARE, in ID
   order, then a module anchor;
3. a share the write changes, FOR UPDATE, then the actor's live shares, FOR SHARE;
4. the sheet row, FOR UPDATE;
5. the rows the write changes, FOR UPDATE.

Every wait is bounded (2 s) and answers 503, as relationship writes do.
"""

from collections.abc import Callable, Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.systems.access.policy.models import GroupMember
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetShare
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from app.systems.sandbox.relationships.locking import wait_briefly_for_locks


def worksheet_busy() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "worksheet_busy", "message": "The sheet is busy; try again"},
    )


def lock_owner(db: Session, owner_id: UUID) -> None:
    """Step 1 alone, for a create: the creator is the owner."""

    _locked(db, lambda: db.scalar(
        select(User.id).where(User.id == owner_id).with_for_update(read=True, of=User)
    ))


def lock_anchor(db: Session, *, record_id: UUID | None, module_id: UUID | None) -> None:
    """Step 2: the record or module the sheet sits on, FOR SHARE."""

    if record_id is not None:
        _locked(db, lambda: db.scalar(
            select(Record.id).where(Record.id == record_id).with_for_update(read=True, of=Record)
        ))
    else:
        _locked(db, lambda: db.scalar(
            select(Module.id).where(Module.id == module_id).with_for_update(read=True, of=Module)
        ))


def lock_worksheet(db: Session, sheet: Worksheet) -> Worksheet:
    """Steps 1 to 3 for a change of an existing sheet; the sheet is read again under lock."""

    lock_owner(db, sheet.owner_id)
    lock_anchor(db, record_id=sheet.record_id, module_id=sheet.module_id)
    locked = _locked(db, lambda: db.scalar(
        select(Worksheet)
        .where(Worksheet.id == sheet.id)
        .execution_options(populate_existing=True)
        .with_for_update(of=Worksheet)
    ))
    if not isinstance(locked, Worksheet):
        raise worksheet_busy()
    return locked


def _locked[T](db: Session, read: Callable[[], T]) -> T:
    wait_briefly_for_locks(db)
    try:
        return read()
    except OperationalError as error:
        db.rollback()
        raise worksheet_busy() from error



def lock_for_write(
    db: Session, sheet: Worksheet, actor_id: UUID, record_ids: Iterable[UUID],
    changed_share_ids: Iterable[UUID] = (),
) -> Worksheet:
    """Steps 1 to 4 for a row or structure write; the sheet is read again under lock.

    Records come in ID order: the anchor and every link target the write reads or sets.
    The actor's live share rows are held so a share removal waits for the write.
    """

    lock_owner(db, sheet.owner_id)
    records = sorted({*record_ids, *([sheet.record_id] if sheet.record_id else [])})
    if records:
        _locked(db, lambda: db.scalars(
            select(Record.id).where(Record.id.in_(records)).order_by(Record.id)
            .with_for_update(read=True, of=Record)
        ).all())
    if sheet.module_id is not None:
        lock_anchor(db, record_id=None, module_id=sheet.module_id)
    changed = sorted(set(changed_share_ids))
    if changed:  # a share the write changes, FOR UPDATE, before the sheet (step 3)
        _locked(db, lambda: db.scalars(
            select(WorksheetShare.id).where(WorksheetShare.id.in_(changed))
            .order_by(WorksheetShare.id).with_for_update(of=WorksheetShare)
        ).all())
    lock_actor_shares(db, sheet.org_id, sheet.id, actor_id)
    locked = _locked(db, lambda: db.scalar(
        select(Worksheet)
        .where(Worksheet.id == sheet.id)
        .execution_options(populate_existing=True)
        .with_for_update(of=Worksheet)
    ))
    if not isinstance(locked, Worksheet):
        raise worksheet_busy()
    return locked


def lock_rows(db: Session, row_ids: Iterable[UUID]) -> list[WorksheetRow]:
    """Step 5: the rows a write changes, FOR UPDATE, in ID order."""

    ids = sorted(set(row_ids))
    if not ids:
        return []
    return list(_locked(db, lambda: db.scalars(
        select(WorksheetRow)
        .where(WorksheetRow.id.in_(ids))
        .order_by(WorksheetRow.id)
        .execution_options(populate_existing=True)
        .with_for_update(of=WorksheetRow)
    ).all()))


def lock_actor_shares(db: Session, org_id: UUID, worksheet_id: UUID, actor_id: UUID) -> None:
    """The actor's live shares of the sheet, FOR SHARE (step 3 of a write; an export).

    A share removal waits for the write or the export, or commits first and their access
    check then fails (D3.3, D9.1).
    """

    _locked(db, lambda: db.scalars(
        select(WorksheetShare.id)
        .where(
            WorksheetShare.org_id == org_id,
            WorksheetShare.worksheet_id == worksheet_id,
            WorksheetShare.is_deleted.is_(False),
            or_(
                WorksheetShare.user_id == actor_id,
                WorksheetShare.group_id.in_(
                    select(GroupMember.group_id).where(
                        GroupMember.org_id == org_id,
                        GroupMember.user_id == actor_id, GroupMember.is_deleted.is_(False),
                    )
                ),
            ),
        )
        .order_by(WorksheetShare.id)
        .with_for_update(read=True, of=WorksheetShare)
    ).all())
