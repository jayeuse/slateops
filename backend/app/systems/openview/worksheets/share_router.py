"""Share routes 16 to 19 (spec D10). The 404 loader runs first (R5)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.common.dependencies import get_current_user
from app.common.listing import StandardListResponse
from app.core.database import get_db
from app.systems.access.users.models import User
from app.systems.openview.worksheets.schemas import (
    SheetShare,
    SheetShareCreate,
    SheetShareListRequest,
    SheetShareUpdate,
)
from app.systems.openview.worksheets.shares import (
    change_share,
    create_share,
    list_shares,
    remove_share,
    share_views,
)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
Actor = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get(
    "/worksheets/{worksheet_id}/shares", response_model=StandardListResponse[SheetShare]
)
def list_worksheet_shares(
    worksheet_id: UUID, user: Actor, db: Database,
    params: Annotated[SheetShareListRequest, Query()],
) -> StandardListResponse[SheetShare]:
    return list_shares(db, user, worksheet_id, params)


@router.post(
    "/worksheets/{worksheet_id}/shares", response_model=SheetShare,
    status_code=status.HTTP_201_CREATED,
)
def create_worksheet_share(
    worksheet_id: UUID, payload: SheetShareCreate, user: Actor, db: Database,
) -> SheetShare:
    share = create_share(db, user, worksheet_id, payload)
    db.commit()
    db.refresh(share)
    return share_views(db, [share])[0]


@router.patch("/worksheets/{worksheet_id}/shares/{share_id}", response_model=SheetShare)
def update_worksheet_share(
    worksheet_id: UUID, share_id: UUID, payload: SheetShareUpdate, user: Actor, db: Database,
) -> SheetShare:
    share = change_share(db, user, worksheet_id, share_id, payload.level)
    db.commit()
    db.refresh(share)
    return share_views(db, [share])[0]


@router.delete(
    "/worksheets/{worksheet_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_worksheet_share(
    worksheet_id: UUID, share_id: UUID, user: Actor, db: Database,
) -> None:
    remove_share(db, user, worksheet_id, share_id)
    db.commit()
