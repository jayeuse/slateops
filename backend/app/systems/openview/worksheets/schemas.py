"""Wire shapes of the sheet routes (spec D10)."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.common.listing import SortOrder, StandardListRequest
from app.systems.openview.worksheets.access import WorksheetLevel
from app.systems.openview.worksheets.structure import Column, SheetColumnGroup, TotalFunction

Title = Annotated[str, Field(min_length=1, max_length=200)]


def _trimmed(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


class WorksheetSort(StrEnum):
    TITLE = "title"
    UPDATED_AT = "updated_at"
    CREATED_AT = "created_at"


class WorksheetListRequest(StandardListRequest[WorksheetSort]):
    pass


class SheetBlankSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["blank"]


class WorksheetCreate(BaseModel):
    """A new sheet on exactly one record or one module."""

    model_config = ConfigDict(extra="forbid")

    record_id: UUID | None = None
    module_id: UUID | None = None
    title: Title
    # Later units add the structure, copy and template sources to this union.
    source: SheetBlankSource

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, value: object) -> object:
        return _trimmed(value)

    @model_validator(mode="after")
    def _one_anchor(self) -> "WorksheetCreate":
        if (self.record_id is None) == (self.module_id is None):
            raise ValueError("Give exactly one of record_id and module_id")
        return self


class WorksheetRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, value: object) -> object:
        return _trimmed(value)


class SheetPersonRef(BaseModel):
    id: UUID
    display_name: str


class SheetGroupRef(BaseModel):
    id: UUID
    name: str


class SheetHiddenSourceColumn(BaseModel):
    """A From another sheet column whose source sheet the viewer cannot see (D14 S1)."""

    key: str
    name: str
    type: Literal["sheet_lookup"]
    state: Literal["no_access"]


class SheetStructureView(BaseModel):
    """The structure as one viewer may see it."""

    structureVersion: int
    nextColumnSeq: int
    columns: list[Column | SheetHiddenSourceColumn]
    groups: list[SheetColumnGroup]
    totals: dict[str, TotalFunction]


class WorksheetSummary(BaseModel):
    id: UUID
    record_id: UUID | None
    module_id: UUID | None
    title: str
    owner: SheetPersonRef
    state: Literal["private", "open"]
    my_level: WorksheetLevel
    live_row_count: int
    revision: int
    updated_at: datetime
    is_deleted: bool
    deleted_at: datetime | None
    # The record's title for a record sheet, the module's name for a module sheet.
    anchor_title: str
    module_name: str
    # Whether the sheet has a live share; answered to its owner only (else null).
    shared: bool | None
    # The group whose share alone gives the viewer the sheet, else null.
    access_group: str | None


class WorksheetDetail(WorksheetSummary):
    structure: SheetStructureView
    etag: str
    created_at: datetime


class SheetShareCandidates(BaseModel):
    people: list[SheetPersonRef]
    groups: list[SheetGroupRef]


class SheetRowSort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(max_length=9)
    order: Literal["asc", "desc"] = "asc"


class SheetRowsQuery(BaseModel):
    """Route 9: one sort column, search text and one page of up to 200 rows (F7)."""

    model_config = ConfigDict(extra="forbid")

    sort: SheetRowSort | None = None
    search: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=200, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @field_validator("search", mode="before")
    @classmethod
    def _search(cls, value: object) -> object:
        trimmed = _trimmed(value)
        return trimmed or None


class SheetValueCell(BaseModel):
    # B10 adds the computed error cell, {"value": null, "error": "division_by_zero"}.
    model_config = ConfigDict(extra="forbid")

    value: JsonValue


class SheetLinkTarget(BaseModel):
    record_id: UUID
    label: str


class SheetLinkCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link: SheetLinkTarget


class SheetUnlinkedCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unlinked: str


class SheetStateCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal[
        "no_access", "deleted", "removed", "unavailable", "field_removed", "column_removed",
        "multiple_matches",
    ]


Cell = SheetValueCell | SheetLinkCell | SheetUnlinkedCell | SheetStateCell


class SheetRow(BaseModel):
    id: UUID
    revision: int
    etag: str
    position: int
    cells: dict[str, Cell]


class SheetTotal(BaseModel):
    fn: TotalFunction
    # An integer for count; a decimal string for sum, average, min and max.
    value: int | str | None
    hidden_count: int


class SheetRowPagination(BaseModel):
    """The list pagination shape, with the 200-row page of the grid (plan decision 7)."""

    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
    count: int = Field(ge=0)
    total: int = Field(ge=0)
    has_more: bool


class SheetRowPage(BaseModel):
    items: list[SheetRow]
    pagination: SheetRowPagination
    totals: dict[str, SheetTotal]


class SheetStructureUpdate(BaseModel):
    """Route 6: the whole column list. New columns use keys from ``nextColumnSeq`` on."""

    model_config = ConfigDict(extra="forbid")

    columns: list[Column]
    groups: list[SheetColumnGroup] = Field(default_factory=list)
    totals: dict[str, TotalFunction] = Field(default_factory=dict)


class SheetCellChange(BaseModel):
    """One changed cell and the cell as the person last saw it (F4)."""

    model_config = ConfigDict(extra="forbid")

    value: JsonValue
    expected: Cell


_AFTER_ROW = (
    "Where the row goes. Absent: the end of the sheet (a save leaves the row in place). "
    "Null: the top. A row ID: right after that row."
)


class SheetRowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cells: dict[str, JsonValue] = Field(default_factory=dict)
    after_row_id: UUID | None = Field(default=None, description=_AFTER_ROW)


class SheetRowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cells: dict[str, SheetCellChange] = Field(default_factory=dict)
    after_row_id: UUID | None = Field(default=None, description=_AFTER_ROW)


class SheetRowBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: UUID
    cells: dict[str, SheetCellChange]


class SheetRowBatch(BaseModel):
    """Route 14: up to 100 creates and updates in one transaction (paste, import)."""

    model_config = ConfigDict(extra="forbid")

    structure_revision: int = Field(ge=1)
    creates: list[SheetRowCreate] = Field(default_factory=list)
    updates: list[SheetRowBatchUpdate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounded(self) -> "SheetRowBatch":
        if len(self.creates) + len(self.updates) > 100:
            raise ValueError("A batch holds at most 100 creates and updates")
        if len({update.row_id for update in self.updates}) != len(self.updates):
            raise ValueError("row_repeated: a batch changes each row once")
        return self


class SheetRowBatchResult(BaseModel):
    rows: list[SheetRow]


class SheetShareSort(StrEnum):
    CREATED_AT = "created_at"


class SheetShareListRequest(StandardListRequest[SheetShareSort]):
    pass


class SheetShareCreate(BaseModel):
    """Route 17: a View or Edit share to one person or one group (V2)."""

    model_config = ConfigDict(extra="forbid")

    subject: Literal["user", "group"]
    user_id: UUID | None = None
    group_id: UUID | None = None
    level: Literal["view", "edit"]

    @model_validator(mode="after")
    def _one_target(self) -> "SheetShareCreate":
        if (self.subject == "user") != (self.user_id is not None and self.group_id is None) or (
            self.subject == "group" and (self.group_id is None or self.user_id is not None)
        ):
            raise ValueError("Give user_id for a person share or group_id for a group share")
        return self


class SheetShareUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["view", "edit"]


class SheetShare(BaseModel):
    id: UUID
    subject: Literal["user", "group"]
    user: SheetPersonRef | None
    group: SheetGroupRef | None
    level: Literal["view", "edit"]
    created_at: datetime


class SheetExportRequest(BaseModel):
    """Route 20: a data file (CSV or Excel) or the structure only (template, D9.2)."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["csv", "xlsx", "template"]


class SheetHistorySort(StrEnum):
    CREATED_AT = "created_at"


class SheetHistoryRequest(StandardListRequest[SheetHistorySort]):
    """Route 15: newest first by default; ``row_id`` keeps one row's changes."""

    sort_order: SortOrder = SortOrder.DESC
    row_id: UUID | None = None


class SheetRowRevision(BaseModel):
    """One row change with the row's cells after it, masked for the reader (H3, N4)."""

    id: UUID
    row_id: UUID
    revision: int
    action: Literal["create", "update", "delete", "restore"]
    changed_keys: list[str]
    cells: dict[str, Cell]
    author: SheetPersonRef | None
    created_at: datetime
