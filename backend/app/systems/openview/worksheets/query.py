"""Route 9 and route 11 over the per-viewer projection (F7, K6, K7).

Sort, search and totals read only the masked expressions of :mod:`projection`, so a hidden
value never decides an order, a match or a total. Blank and hidden cells sort last in both
directions. Totals cover every live row, whatever the search, and count the hidden cells.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow
from app.systems.openview.worksheets.projection import (
    ERROR_STATES,
    RowProjection,
    project_rows,
)
from app.systems.openview.worksheets.schemas import (
    Cell,
    SheetErrorCell,
    SheetLinkCell,
    SheetLinkTarget,
    SheetMatchesCell,
    SheetRow,
    SheetRowPage,
    SheetRowPagination,
    SheetRowsQuery,
    SheetStateCell,
    SheetTotal,
    SheetUnlinkedCell,
    SheetValueCell,
)
from app.systems.openview.worksheets.structure import WorksheetStructure


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def projected_rows(projection: RowProjection, sheet: Worksheet) -> Select[Any]:
    columns: list[Any] = [WorksheetRow.id, WorksheetRow.revision, WorksheetRow.position]
    for column in projection.columns:
        columns += [
            column.state.label(f"{column.key}__state"),
            column.value.label(f"{column.key}__value"),
            column.label.label(f"{column.key}__label"),
        ]
    return (
        select(*columns)
        .select_from(projection.source)
        .where(
            WorksheetRow.org_id == sheet.org_id,
            WorksheetRow.worksheet_id == sheet.id,
            WorksheetRow.is_deleted.is_(False),
        )
    )


def projected_cell(row: Any, key: str) -> Cell:
    state = row[f"{key}__state"]
    if state == "link":
        return SheetLinkCell(link=SheetLinkTarget(
            record_id=UUID(str(row[f"{key}__value"])), label=row[f"{key}__label"],
        ))
    if state == "unlinked":
        return SheetUnlinkedCell(unlinked=row[f"{key}__label"])
    if state in ERROR_STATES:
        return SheetErrorCell(value=None, error=state)
    if state == "multiple_matches":
        return SheetMatchesCell(state="multiple_matches", count=int(row[f"{key}__value"]))
    if state is not None:
        return SheetStateCell(state=state)
    return SheetValueCell(value=row[f"{key}__value"])


def _view(row: Any, keys: list[str]) -> SheetRow:
    return SheetRow(
        id=row["id"], revision=row["revision"], etag=f'"{row["id"]}:{row["revision"]}"',
        position=row["position"], cells={key: projected_cell(row, key) for key in keys},
    )


_AGGREGATES: dict[str, Callable[[Any], Any]] = {
    "sum": func.sum, "average": func.avg, "min": func.min, "max": func.max,
}


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


def _totals(
    db: Session, projection: RowProjection, structure: WorksheetStructure, sheet: Worksheet,
) -> dict[str, SheetTotal]:
    if not structure.totals:
        return {}
    aggregates: list[Any] = []
    for key, function in structure.totals.items():
        column = projection.column(key)
        if function == "count":
            value = func.count().filter(column.shown)
        else:
            value = _AGGREGATES[function](column.number)
        aggregates += [value, func.count().filter(column.hidden)]
    found = db.execute(
        projected_rows(projection, sheet).with_only_columns(*aggregates, maintain_column_froms=True)
    ).one()
    totals: dict[str, SheetTotal] = {}
    for index, (key, function) in enumerate(structure.totals.items()):
        value, hidden = found[2 * index], found[2 * index + 1]
        totals[key] = SheetTotal(
            fn=function,
            value=int(value) if function == "count" else _decimal_text(value),
            hidden_count=int(hidden),
        )
    return totals


def _invalid_sort() -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "sort_column_invalid", "message": "Sort by a column of this sheet"},
    )


def query_rows(db: Session, user: User, sheet: Worksheet, request: SheetRowsQuery) -> SheetRowPage:
    structure = WorksheetStructure.model_validate(sheet.structure)
    keys = [column.key for column in structure.columns]
    if request.sort is not None and request.sort.key not in keys:
        raise _invalid_sort()
    projection = project_rows(db, user, structure)
    statement = projected_rows(projection, sheet)
    if request.search is not None:
        pattern = _like(request.search)
        texts = [column.text.ilike(pattern, escape="\\") for column in projection.columns]
        statement = statement.where(or_(*texts)) if texts else statement.where(false())
    counted = int(db.scalar(
        statement.with_only_columns(func.count(), maintain_column_froms=True)
    ) or 0)
    order: list[Any] = []
    if request.sort is not None:
        sort = projection.column(request.sort.key).sort
        order.append(
            sort.desc().nulls_last() if request.sort.order == "desc" else sort.asc().nulls_last()
        )
    order += [WorksheetRow.position, WorksheetRow.id]
    found = db.execute(
        statement.order_by(*order).offset(request.offset).limit(request.limit + 1)
    ).mappings().all()
    page = found[: request.limit]
    return SheetRowPage(
        items=[_view(row, keys) for row in page],
        pagination=SheetRowPagination(
            limit=request.limit, offset=request.offset, count=len(page), total=counted,
            has_more=len(found) > request.limit,
        ),
        totals=_totals(db, projection, structure, sheet),
    )


def read_row(db: Session, user: User, sheet: Worksheet, row_id: UUID) -> SheetRow | None:
    structure = WorksheetStructure.model_validate(sheet.structure)
    projection = project_rows(db, user, structure)
    found = db.execute(
        projected_rows(projection, sheet).where(WorksheetRow.id == row_id)
    ).mappings().one_or_none()
    return None if found is None else _view(found, [column.key for column in structure.columns])


def read_rows(
    db: Session, user: User, sheet: Worksheet, row_ids: list[UUID],
) -> dict[UUID, SheetRow]:
    """Several rows as the person sees them, in one statement (batch saves, responses)."""

    if not row_ids:
        return {}
    structure = WorksheetStructure.model_validate(sheet.structure)
    projection = project_rows(db, user, structure)
    keys = [column.key for column in structure.columns]
    found = db.execute(
        projected_rows(projection, sheet).where(WorksheetRow.id.in_(row_ids))
    ).mappings().all()
    return {row["id"]: _view(row, keys) for row in found}
