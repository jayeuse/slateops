"""Route 23, Appears in: rows that link to a record, in sheets the viewer can see (N5, V7).

The record must be readable (404 otherwise, as for a missing one). Only live links in a
link column of the sheet's current structure count, on live rows of sheets that pass the
access rule for the viewer, so private, deleted and hidden sheets never show. Each row comes
with its cells as the viewer sees them; every sheet of the page reads from one budget, so a
page of rows can never cost more than one read (S-11).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.common.dependencies import get_current_user
from app.common.listing import PaginationMetadata, StandardListResponse
from app.core.database import get_db
from app.systems.access.users.models import User
from app.systems.openview.worksheets import from_sheet
from app.systems.openview.worksheets.access import visible_worksheet_clause
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.query import read_rows
from app.systems.openview.worksheets.schemas import Cell, SheetPersonRef
from app.systems.openview.worksheets.serializers import person_refs, structure_view
from app.systems.openview.worksheets.sheet_lookup_cost import Budget
from app.systems.openview.worksheets.structure import SheetLinkColumn, WorksheetStructure
from app.systems.sandbox.records.access import record_access


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
Actor = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]


class SheetAppearanceColumn(BaseModel):
    key: str
    name: str
    type: str


class SheetAppearance(BaseModel):
    """One sheet row that links to the record, with the row as the viewer sees it."""

    worksheet_id: UUID
    worksheet_title: str
    owner: SheetPersonRef
    row_id: UUID
    row_number: int
    column_key: str
    column_name: str
    columns: list[SheetAppearanceColumn]
    cells: dict[str, Cell]


class SheetAppearanceRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


def _links(user_db: Session, user: User, record_id: UUID) -> Any:
    """Live links to the record on live rows of sheets the viewer can see."""

    return (
        select(WorksheetRowLink.id, WorksheetRowLink.row_id, WorksheetRowLink.column_key,
               Worksheet.id.label("worksheet_id"))
        .join(WorksheetRow, and_(
            WorksheetRow.org_id == WorksheetRowLink.org_id,
            WorksheetRow.id == WorksheetRowLink.row_id,
            WorksheetRow.is_deleted.is_(False),
        ))
        .join(Worksheet, and_(
            Worksheet.org_id == WorksheetRowLink.org_id,
            Worksheet.id == WorksheetRowLink.worksheet_id,
        ))
        .where(
            WorksheetRowLink.target_record_id == record_id,
            WorksheetRowLink.is_deleted.is_(False),
            # A link column of the sheet's current structure, so the total counts only rows
            # that the page shows.
            Worksheet.structure.op("->")("columns").op("@>")(func.jsonb_build_array(
                func.jsonb_build_object("key", WorksheetRowLink.column_key, "type", "link"),
            )),
            visible_worksheet_clause(user_db, user),
        )
    )


def _row_numbers(db: Session, row_ids: list[UUID]) -> dict[UUID, int]:
    """Each row's place among the live rows of its sheet, from 1."""

    earlier = aliased(WorksheetRow, name="earlier")
    numbered = db.execute(
        select(WorksheetRow.id, func.count(earlier.id))
        .join(earlier, and_(
            earlier.worksheet_id == WorksheetRow.worksheet_id,
            earlier.is_deleted.is_(False),
            (earlier.position < WorksheetRow.position)
            | and_(earlier.position == WorksheetRow.position, earlier.id <= WorksheetRow.id),
        ))
        .where(WorksheetRow.id.in_(row_ids))
        .group_by(WorksheetRow.id)
    ).tuples()
    return {row_id: int(count) for row_id, count in numbered}


@router.get(
    "/records/{record_id}/worksheet-rows",
    response_model=StandardListResponse[SheetAppearance],
    responses={404: {"description": "The record is missing or unreadable"}},
)
def list_appearances(
    record_id: UUID, user: Actor, db: Database,
    params: Annotated[SheetAppearanceRequest, Query()],
) -> StandardListResponse[SheetAppearance]:
    """Route 23: every row that links here in a sheet the viewer can see (SH-28)."""

    if record_access(db, user, record_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={
            "code": "record_not_found", "message": "Record not found",
        })
    links = _links(db, user, record_id).subquery()
    total = int(db.scalar(select(func.count()).select_from(links)) or 0)
    page = db.execute(
        select(links.c.id, links.c.row_id, links.c.column_key, links.c.worksheet_id)
        .join(Worksheet, Worksheet.id == links.c.worksheet_id)
        .join(WorksheetRow, WorksheetRow.id == links.c.row_id)
        .order_by(Worksheet.title, Worksheet.id, WorksheetRow.position, WorksheetRow.id,
                  links.c.id)
        .offset(params.offset).limit(params.limit + 1)
    ).mappings().all()
    shown = page[: params.limit]
    sheets = {sheet.id: sheet for sheet in db.scalars(
        select(Worksheet).where(Worksheet.id.in_({item["worksheet_id"] for item in shown})))}
    budget = Budget(from_sheet.READ_BUDGET)  # one read for the whole page
    rows: dict[UUID, Any] = {}
    views: dict[UUID, list[SheetAppearanceColumn]] = {}
    for sheet in sorted(sheets.values(), key=lambda item: (item.title, str(item.id))):
        wanted = [item["row_id"] for item in shown if item["worksheet_id"] == sheet.id]
        rows.update(read_rows(db, user, sheet, wanted, budget))
        views[sheet.id] = [SheetAppearanceColumn(key=column.key, name=column.name,
                                                 type=column.type)
                           for column in structure_view(db, user, sheet).columns]
    owners = person_refs(db, (sheet.owner_id for sheet in sheets.values()))
    numbers = _row_numbers(db, [item["row_id"] for item in shown])
    items = []
    for item in shown:
        sheet = sheets[item["worksheet_id"]]
        structure = WorksheetStructure.model_validate(sheet.structure)
        column = next((column for column in structure.columns
                       if column.key == item["column_key"]), None)
        row = rows.get(item["row_id"])
        if not isinstance(column, SheetLinkColumn) or row is None:
            continue  # a link left behind by a removed column is no appearance
        items.append(SheetAppearance(
            worksheet_id=sheet.id, worksheet_title=sheet.title, owner=owners[sheet.owner_id],
            row_id=item["row_id"], row_number=numbers.get(item["row_id"], 0),
            column_key=column.key, column_name=column.name, columns=views[sheet.id],
            cells=row.cells,
        ))
    return StandardListResponse(items=items, pagination=PaginationMetadata(
        limit=params.limit, offset=params.offset, count=len(items), total=total,
        has_more=len(page) > params.limit,
    ))
