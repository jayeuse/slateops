"""What a leave does to a person's sheets (spec L0-L5, H5, D3.1-D3.4).

The open state is derived (D0), so a leave changes no sheet row. Each leave path counts the
sheets that will open before it changes the user or membership row (afterwards the same
rule reads them as open already, so the count would be 0), and after its commit writes one
security event with that count and the path. The event and route 24 carry a count only:
no title, record or column.
"""

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import require_admin
from app.core.database import get_db
from app.core.database.organization_scope import bound_organization_column
from app.systems.access.users.directory import directory_membership
from app.systems.access.users.models import User
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.openview.worksheets.access import worksheet_present_clause
from app.systems.openview.worksheets.models import Worksheet
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record

LeavePath = Literal[
    "membership_disabled", "account_disabled", "membership_removed", "account_deleted",
]
OPENED_ON_LEAVE = "worksheets.opened_on_leave"


def opening_count(db: Session, user_id: UUID) -> int:
    """Sheets of the person in the bound organization that are private now (D3.1, D3.2)."""

    live_record = exists(select(Record.id).where(
        Record.id == Worksheet.record_id, Record.is_deleted.is_(False),
    ))
    live_module = exists(select(Module.id).where(
        Module.id == Worksheet.module_id, Module.is_deleted.is_(False),
    ))
    return int(db.scalar(
        select(func.count()).select_from(Worksheet).where(
            Worksheet.owner_id == user_id,
            Worksheet.org_id == bound_organization_column(),
            Worksheet.is_deleted.is_(False),
            or_(live_record, live_module),
            worksheet_present_clause(),
        )
    ) or 0)


def record_opened(
    db: Session, count: int, path: LeavePath, actor_id: UUID, subject_id: UUID,
    record: Callable[..., None],
) -> None:
    """After the leave commits: the event, in the request's organization only (D3.4)."""

    if count:
        record(
            db, OPENED_ON_LEAVE, SecurityEventOutcome.SUCCESS, uuid7(), actor_id, subject_id,
            metadata={"opened_count": count, "path": path},
        )


class WorksheetImpact(BaseModel):
    opening_count: int


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}/worksheet-impact", response_model=WorksheetImpact)
def worksheet_impact(
    user_id: UUID,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> WorksheetImpact:
    """Route 24: how many private sheets a disable or removal would open (L5, SH-55)."""

    if directory_membership(db, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return WorksheetImpact(opening_count=opening_count(db, user_id))
