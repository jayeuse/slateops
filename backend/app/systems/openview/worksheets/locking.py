"""Lock order for sheet writes (spec D3.3).

1. the owner's user row, FOR SHARE: a leave takes it FOR UPDATE, so a write either commits
   before the leave or sees the open state afterwards;
2. the anchor record (or module), FOR SHARE;
3. the sheet row, FOR UPDATE.

Every wait is bounded (2 s) and answers 503, as relationship writes do.
"""

from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import Worksheet
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

