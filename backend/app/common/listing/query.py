from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Column, Select, Table, asc, desc, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement, UnaryExpression

from app.common.listing.schemas import (
    DeletedFilter,
    PaginationMetadata,
    SortOrder,
    StandardListRequest,
)

# D1: a list counts at most this many rows; above it the total is a lower bound.
TOTAL_CAP = 10_000


@dataclass(frozen=True, slots=True)
class ListQuerySpec[SortFieldT: StrEnum]:
    sort_fields: Mapping[SortFieldT, ColumnElement[Any]]
    default_sort: SortFieldT
    tie_breaker: ColumnElement[Any]
    search_fields: tuple[ColumnElement[str], ...] = ()
    deleted_field: ColumnElement[bool] | None = None
    # Records lists keep their exact count (D1, K61). Never a request field.
    exact_total: bool = False

    def __post_init__(self) -> None:
        if not self.sort_fields:
            raise ValueError("A list query must define at least one sort field")
        if self.default_sort not in self.sort_fields:
            raise ValueError("The default sort field must be included in sort_fields")


@dataclass(frozen=True, slots=True)
class ListQueryResult[ModelT]:
    items: list[ModelT]
    pagination: PaginationMetadata


def _unsupported_parameter(parameter: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[
            {
                "loc": ["query", parameter],
                "msg": message,
                "type": "value_error",
            }
        ],
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _deleted_condition[SortFieldT: StrEnum](
    request: StandardListRequest[SortFieldT],
    spec: ListQuerySpec[SortFieldT],
) -> ColumnElement[bool] | None:
    if spec.deleted_field is None:
        if request.deleted is not DeletedFilter.EXCLUDE:
            raise _unsupported_parameter(
                "deleted",
                "This endpoint does not support deleted record filtering",
            )
        return None

    if request.deleted is DeletedFilter.EXCLUDE:
        return spec.deleted_field.is_(False)
    if request.deleted is DeletedFilter.ONLY:
        return spec.deleted_field.is_(True)
    return None


def _search_condition[SortFieldT: StrEnum](
    request: StandardListRequest[SortFieldT],
    spec: ListQuerySpec[SortFieldT],
) -> ColumnElement[bool] | None:
    if request.search is None:
        return None
    if not spec.search_fields:
        raise _unsupported_parameter(
            "search",
            "This endpoint does not support search",
        )

    pattern = f"%{_escape_like(request.search)}%"
    return or_(*(field.ilike(pattern, escape="\\") for field in spec.search_fields))


def build_standard_list_statements[ModelT, SortFieldT: StrEnum](
    statement: Select[tuple[ModelT]],
    request: StandardListRequest[SortFieldT],
    spec: ListQuerySpec[SortFieldT],
) -> tuple[Select[tuple[ModelT]], Select[tuple[int]]]:
    filtered = statement.order_by(None).limit(None).offset(None)
    conditions = [
        condition
        for condition in (
            _deleted_condition(request, spec),
            _search_condition(request, spec),
        )
        if condition is not None
    ]
    if conditions:
        filtered = filtered.where(*conditions)

    count_statement = (
        select(func.count()).select_from(filtered.subquery())
        if spec.exact_total
        else capped_count(filtered)
    )
    sort_column = spec.sort_fields[request.sort_by or spec.default_sort]
    sort_function = asc if request.sort_order is SortOrder.ASC else desc
    item_statement = filtered.order_by(
        _ordered(sort_function, sort_column), _ordered(sort_function, spec.tie_breaker)
    )
    # One row more than the page says whether more follow, with no extra statement.
    item_statement = item_statement.offset(request.offset).limit(request.limit + 1)
    return item_statement, count_statement


def _ordered(
    direction: Callable[[ColumnElement[Any]], UnaryExpression[Any]], column: ColumnElement[Any]
) -> UnaryExpression[Any]:
    """Order by ``column``; nulls last only where the column can hold a null.

    A `NOT NULL` table column keeps PostgreSQL's default null order, which matches a forward
    or backward index scan, so the index gives the order with no Sort. The rows are the same.
    """

    expression = getattr(column, "expression", column)
    never_null = (
        isinstance(expression, Column)
        and isinstance(expression.table, Table)
        and not expression.nullable
    )
    return direction(column) if never_null else direction(column).nulls_last()


def capped_count(statement: Select[Any]) -> Select[tuple[int]]:
    """Count the rows of ``statement``, but stop after one row more than ``TOTAL_CAP``."""

    return select(func.count()).select_from(statement.limit(TOTAL_CAP + 1).subquery())


def capped_pagination[RowT](
    *, limit: int, offset: int, rows: Sequence[RowT], counted: int, exact: bool = False
) -> tuple[list[RowT], PaginationMetadata]:
    """The page without its extra row, and its metadata.

    ``rows`` holds up to ``limit + 1`` rows; the extra row only says that more follow.
    ``counted`` is the capped count, or the exact count when ``exact`` is set.
    """

    page = list(rows[:limit])
    capped = not exact and counted > TOTAL_CAP
    return page, PaginationMetadata(
        limit=limit,
        offset=offset,
        count=len(page),
        total=counted if exact else min(counted, TOTAL_CAP),
        total_is_capped=capped,
        has_more=len(rows) > limit,
    )


def execute_standard_list[ModelT, SortFieldT: StrEnum](
    db: Session,
    statement: Select[tuple[ModelT]],
    request: StandardListRequest[SortFieldT],
    spec: ListQuerySpec[SortFieldT],
) -> ListQueryResult[ModelT]:
    item_statement, count_statement = build_standard_list_statements(statement, request, spec)
    counted = int(db.scalar(count_statement) or 0)
    items, pagination = capped_pagination(
        limit=request.limit,
        offset=request.offset,
        rows=db.scalars(item_statement).all(),
        counted=counted,
        exact=spec.exact_total,
    )
    return ListQueryResult(items=items, pagination=pagination)
