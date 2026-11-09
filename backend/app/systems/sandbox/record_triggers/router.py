"""Read-only recent-run API for published Sandbox triggers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.dependencies import require_admin
from app.common.listing.cursor import CURSOR_MAX_LENGTH
from app.core.database import get_db
from app.systems.access.users.models import User
from app.systems.sandbox.record_triggers.schemas import TriggerRunListResponse
from app.systems.sandbox.record_triggers.service import list_recent_runs

router = APIRouter(prefix="/sandbox", tags=["sandbox-triggers"])
ReadActor = Annotated[User, Depends(require_admin)]
Database = Annotated[Session, Depends(get_db)]


@router.get(
    "/trigger-runs",
    response_model=TriggerRunListResponse,
    operation_id="list_sandbox_trigger_runs",
)
def get_trigger_runs(
    _actor: ReadActor,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    cursor: Annotated[str | None, Query(max_length=CURSOR_MAX_LENGTH)] = None,
) -> TriggerRunListResponse:
    return list_recent_runs(db, limit=limit, offset=offset, cursor=cursor)
