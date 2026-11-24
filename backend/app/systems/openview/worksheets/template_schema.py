"""The template file's wire shape, version 1 (spec D9.2, X5, X6; D14 S1).

Export writes it and route 3 reads it. A file of another version is refused with
``template_unsupported_version``, and a From another sheet column with
``template_sheet_lookup``: both before any other check, so nothing is created.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.systems.openview.worksheets.structure import (
    MAX_COLUMNS,
    ColumnKey,
    SheetColumnGroup,
    SheetComputedColumn,
    SheetDecimalColumn,
    SheetPlainColumn,
    SheetSelectColumn,
    TotalFunction,
)

TEMPLATE_KIND = "slateops-worksheet-template"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SheetTemplateLink(_Strict):
    moduleName: str
    departmentName: str


class SheetTemplateLinkColumn(_Strict):
    key: ColumnKey
    name: str
    type: Literal["link"]
    link: SheetTemplateLink


class SheetTemplateLookup(_Strict):
    linkKey: ColumnKey
    fieldName: str


class SheetTemplateLookupColumn(_Strict):
    key: ColumnKey
    name: str
    type: Literal["lookup"]
    lookup: SheetTemplateLookup


TemplateColumn = Annotated[
    SheetPlainColumn | SheetDecimalColumn | SheetSelectColumn | SheetComputedColumn
    | SheetTemplateLinkColumn | SheetTemplateLookupColumn,
    Field(discriminator="type"),
]


class SheetTemplate(_Strict):
    """Version 1 of the template file (D9.2); import validates against the same model."""

    kind: Literal["slateops-worksheet-template"]
    schemaVersion: Literal[1]
    title: Annotated[str, Field(max_length=200)]
    columns: list[TemplateColumn] = Field(max_length=MAX_COLUMNS)
    groups: list[SheetColumnGroup]
    totals: dict[ColumnKey, TotalFunction]

    @model_validator(mode="before")
    @classmethod
    def _refuse_other_files(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        version = data.get("schemaVersion")
        if version != 1:
            raise PydanticCustomError(
                "template_unsupported_version",
                "This template version is not supported; export the template again",
            )
        columns = data.get("columns")
        if isinstance(columns, list) and any(
            isinstance(column, dict) and column.get("type") == "sheet_lookup"
            for column in columns
        ):
            raise PydanticCustomError(
                "template_sheet_lookup",
                "A template cannot hold From another sheet columns",
            )
        return data
