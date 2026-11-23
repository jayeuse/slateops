"""The stored structure of a sheet (spec D1.7) and the sheet limits (spec D8).

The structure holds columns, column groups and totals. Rules that need the database (the
link target module, the lookup field type, the source sheet of a From another sheet column)
and the expression grammar belong to the routes that save a structure.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

MAX_COLUMNS = 100
MAX_ROWS = 10_000
MAX_TEXT_CELL_CHARACTERS = 4_000
MAX_ROW_BYTES = 32 * 1024
MAX_SHEET_BYTES = 8 * 1024 * 1024
MAX_EXPRESSION_CHARACTERS = 1_000

ColumnKey = Annotated[str, StringConstraints(pattern=r"^c[0-9a-z]{1,8}$")]
OptionId = Annotated[str, StringConstraints(pattern=r"^o[0-9a-z]{1,8}$")]
Places = Annotated[int, Field(ge=0, le=18)]
TotalFunction = Literal["sum", "average", "min", "max", "count"]
PlainType = Literal[
    "text", "long_text", "email", "url", "number", "int", "boolean", "date", "datetime", "user",
]

# Columns whose value is never a number: only count totals them.
_NOT_NUMERIC = frozenset(
    {"text", "long_text", "email", "url", "boolean", "date", "datetime", "user", "select", "link"}
)


def _not_blank(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} cannot be blank")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Column(_Strict):
    key: ColumnKey
    name: Annotated[str, Field(max_length=150)]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _not_blank(value, "Column names")


class SheetPlainColumn(_Column):
    type: PlainType


class SheetDecimalOptions(_Strict):
    places: Places
    currency: bool = False


class SheetDecimalColumn(_Column):
    type: Literal["decimal"]
    decimal: SheetDecimalOptions


class SheetSelectOption(_Strict):
    id: OptionId
    label: Annotated[str, Field(max_length=100)]

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return _not_blank(value, "Option labels")


class SheetSelectOptions(_Strict):
    options: list[SheetSelectOption] = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def _unique(cls, options: list[SheetSelectOption]) -> list[SheetSelectOption]:
        ids = {option.id for option in options}
        labels = {option.label for option in options}
        if len(ids) != len(options) or len(labels) != len(options):
            raise ValueError("Option IDs and labels must be unique")
        return options


class SheetSelectColumn(_Column):
    type: Literal["select"]
    select: SheetSelectOptions


class SheetLinkOptions(_Strict):
    moduleId: UUID


class SheetLinkColumn(_Column):
    type: Literal["link"]
    link: SheetLinkOptions


class SheetLookupOptions(_Strict):
    linkKey: ColumnKey
    fieldId: UUID


class SheetLookupColumn(_Column):
    type: Literal["lookup"]
    lookup: SheetLookupOptions


class SheetComputedOptions(_Strict):
    # A bound on the body only: route 6 refuses an expression above 1,000 characters with
    # `expression_invalid` (D7.1), and the stored form with keys can be a little longer.
    expression: str = Field(min_length=1, max_length=2 * MAX_EXPRESSION_CHARACTERS)
    places: Places | None = None


class SheetComputedColumn(_Column):
    type: Literal["computed"]
    computed: SheetComputedOptions


class SheetFromSheetOptions(_Strict):
    sourceWorksheetId: UUID
    sourceColumnKey: ColumnKey
    linkKey: ColumnKey
    sourceLinkKey: ColumnKey


class SheetFromSheetColumn(_Column):
    type: Literal["sheet_lookup"]
    sheet_lookup: SheetFromSheetOptions


Column = Annotated[
    SheetPlainColumn | SheetDecimalColumn | SheetSelectColumn | SheetLinkColumn
    | SheetLookupColumn | SheetComputedColumn | SheetFromSheetColumn,
    Field(discriminator="type"),
]


class SheetColumnGroup(_Strict):
    name: Annotated[str, Field(max_length=150)]
    keys: list[ColumnKey] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _not_blank(value, "Group names")


class WorksheetStructure(_Strict):
    structureVersion: Literal[1]
    nextColumnSeq: int = Field(ge=1)
    columns: list[Column] = Field(default_factory=list, max_length=MAX_COLUMNS)
    groups: list[SheetColumnGroup] = Field(default_factory=list)
    totals: dict[ColumnKey, TotalFunction] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _refuse_relationship(cls, data: Any) -> Any:
        columns = data.get("columns") if isinstance(data, dict) else None
        if isinstance(columns, list) and any(
            isinstance(column, dict) and column.get("type") == "relationship"
            for column in columns
        ):
            raise ValueError("relationship is not a column type; use a link column")
        return data

    @model_validator(mode="after")
    def _consistent(self) -> "WorksheetStructure":
        types = {column.key: column.type for column in self.columns}
        if len(types) != len(self.columns):
            raise ValueError("Column keys must be unique")
        if len({column.name.casefold() for column in self.columns}) != len(self.columns):
            raise ValueError("Column names must be unique, ignoring case")
        for column in self.columns:
            options = column.lookup if isinstance(column, SheetLookupColumn) else (
                column.sheet_lookup if isinstance(column, SheetFromSheetColumn) else None
            )
            if options is not None and types.get(options.linkKey) != "link":
                raise ValueError(f"Column {column.key}: linkKey must name a link column")
        self._check_groups(list(types))
        for key, function in self.totals.items():
            if key not in types:
                raise ValueError("Totals must name columns")
            if function != "count" and types[key] in _NOT_NUMERIC:
                raise ValueError(f"Total of {key}: only count works on a {types[key]} column")
        return self

    def _check_groups(self, order: list[str]) -> None:
        position = {key: index for index, key in enumerate(order)}
        grouped: set[str] = set()
        for group in self.groups:
            if any(key not in position for key in group.keys):
                raise ValueError("Group keys must name columns")
            start = position[group.keys[0]]
            if [position[key] for key in group.keys] != list(
                range(start, start + len(group.keys))
            ):
                raise ValueError("Group keys must be adjacent columns in order")
            if grouped.intersection(group.keys):
                raise ValueError("Groups cannot overlap")
            grouped.update(group.keys)
