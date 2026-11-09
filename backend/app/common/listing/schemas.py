from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.common.listing.cursor import CURSOR_MAX_LENGTH


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class DeletedFilter(StrEnum):
    EXCLUDE = "exclude"
    INCLUDE = "include"
    ONLY = "only"


class StandardListRequest[SortFieldT: StrEnum](BaseModel):
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_by: SortFieldT | None = None
    sort_order: SortOrder = SortOrder.ASC
    search: str | None = Field(default=None, max_length=100)
    deleted: DeletedFilter = DeletedFilter.EXCLUDE

    @field_validator("search", mode="before")
    @classmethod
    def normalize_search(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class KeysetListRequest[SortFieldT: StrEnum](StandardListRequest[SortFieldT]):
    """A D1 keyset list: ``cursor`` replaces ``offset`` on the default created_at order."""

    cursor: str | None = Field(default=None, max_length=CURSOR_MAX_LENGTH)


class PaginationMetadata(BaseModel):
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    count: int = Field(ge=0)
    total: int = Field(ge=0)
    # True when more rows match than the count reads; ``total`` is then a lower bound (D1).
    total_is_capped: bool = False
    has_more: bool


class StandardListResponse[ResponseItemT](BaseModel):
    items: list[ResponseItemT]
    pagination: PaginationMetadata


class KeysetPaginationMetadata(PaginationMetadata):
    # The cursor after the last row of this page; None when no row follows.
    next_cursor: str | None


class KeysetListResponse[ResponseItemT](BaseModel):
    items: list[ResponseItemT]
    pagination: KeysetPaginationMetadata
