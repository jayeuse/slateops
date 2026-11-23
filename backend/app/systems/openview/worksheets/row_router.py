"""Row write routes 10, 12, 13 and 14 (spec D10). The 404 loader runs first (R5)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from app.common.dependencies import get_current_user
from app.core.database import get_db
from app.systems.access.users.models import User
from app.systems.openview.worksheets.access import load_visible_worksheet
from app.systems.openview.worksheets.query import read_rows
from app.systems.openview.worksheets.row_writes import delete_row, row_not_found, write_rows
from app.systems.openview.worksheets.schemas import (
    SheetRow,
    SheetRowBatch,
    SheetRowBatchResult,
    SheetRowBatchUpdate,
    SheetRowCreate,
    SheetRowUpdate,
)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
Actor = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
_ETAG: dict[str, dict[str, Any]] = {"ETag": {"schema": {"type": "string"}}}


def _rows(db: Session, user: User, worksheet_id: UUID, row_ids: list[UUID]) -> list[SheetRow]:
    sheet = load_visible_worksheet(db, user, worksheet_id)
    found = read_rows(db, user, sheet, row_ids) if sheet else {}
    if len(found) != len(set(row_ids)):
        raise row_not_found()
    return [found[row_id] for row_id in row_ids]


@router.post(
    "/worksheets/{worksheet_id}/rows", response_model=SheetRow,
    status_code=status.HTTP_201_CREATED,
    responses={201: {"headers": {**_ETAG, "Location": {"schema": {"type": "string"}}}}},
)
def create_worksheet_row(
    worksheet_id: UUID, payload: SheetRowCreate, user: Actor, db: Database, response: Response,
) -> SheetRow:
    [row_id] = write_rows(db, user, worksheet_id, [payload], [])
    db.commit()
    [row] = _rows(db, user, worksheet_id, [row_id])
    response.headers["Location"] = f"/api/worksheets/{worksheet_id}/rows/{row_id}"
    response.headers["ETag"] = row.etag
    return row


@router.patch(
    "/worksheets/{worksheet_id}/rows/{row_id}", response_model=SheetRow,
    responses={200: {"headers": _ETAG}, 412: {"description": "A changed cell was changed"}},
)
def update_worksheet_row(
    worksheet_id: UUID, row_id: UUID, payload: SheetRowUpdate, user: Actor, db: Database,
    response: Response,
) -> SheetRow:
    update = SheetRowBatchUpdate(row_id=row_id, cells=payload.cells)
    write_rows(db, user, worksheet_id, [], [update], conflict="cell_changed", move=payload)
    db.commit()
    [row] = _rows(db, user, worksheet_id, [row_id])
    response.headers["ETag"] = row.etag
    return row


@router.delete(
    "/worksheets/{worksheet_id}/rows/{row_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={412: {"description": "The row changed"}, 428: {"description": "If-Match"}},
)
def delete_worksheet_row(
    worksheet_id: UUID, row_id: UUID, user: Actor, db: Database, if_match: IfMatch = None,
) -> None:
    delete_row(db, user, worksheet_id, row_id, if_match)
    db.commit()


@router.post("/worksheets/{worksheet_id}/rows/batch", response_model=SheetRowBatchResult)
def write_worksheet_rows(
    worksheet_id: UUID, payload: SheetRowBatch, user: Actor, db: Database,
) -> SheetRowBatchResult:
    """Route 14: paste and import; one transaction; 409 when the columns changed."""

    written = write_rows(
        db, user, worksheet_id, payload.creates, payload.updates,
        structure_revision=payload.structure_revision,
    )
    db.commit()
    return SheetRowBatchResult(rows=_rows(db, user, worksheet_id, written))
