"""CSV and Excel files of a sheet, cell by cell as the exporter sees it (spec X4, D9.1).

The record export rules apply: CSV text goes through ``safe_text``; Excel writes text as
strings (``strings_to_formulas`` is off), so nothing in a cell is ever evaluated. Both
writers stop at the record export caps (10,000 rows, 8 MiB) with ``export_limit_exceeded``.
A link cell exports as the record's name; a cell the exporter cannot read as "No access".
"""

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from xlsxwriter import Workbook
from xlsxwriter.exceptions import FileCreateError

from app.systems.openview.worksheets.schemas import (
    Cell,
    SheetLinkCell,
    SheetStateCell,
    SheetUnlinkedCell,
    SheetValueCell,
)
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.records import export as record_export
from app.systems.sandbox.records.display import UNAVAILABLE_USER
from app.systems.sandbox.records.export_xlsx import (
    MAX_RAW_CONTENT_BYTES,
    write_cell,
    write_text,
)

# The words the sheet grid shows for a cell state (frontend `sheet-grid.ts`).
STATE_WORDS = {
    "no_access": "No access",
    "deleted": "Deleted record",
    "removed": "Removed record",
    "unavailable": "Unavailable",
    "field_removed": "Field removed",
    "column_removed": "Column removed",
    "multiple_matches": "Several matches",
}
XlsxValue = str | int | float | bool | date | datetime | None


@dataclass(frozen=True)
class ExportColumn:
    """How one column's values are written: as a field of ``kind`` would be in a record."""

    name: str
    kind: FieldType
    options: dict[str, str] = field(default_factory=dict)

    def field(self) -> Field:
        """A transient field, never added to a session, that the record writers read."""

        options = [{"id": key, "label": label} for key, label in self.options.items()]
        return Field(id=uuid4(), type=self.kind.value, config={"options": options})


@dataclass(frozen=True)
class CellFormat:
    timezone: str
    locale: str
    people: dict[str, str]  # the names of the people the exporter can see, by ID


def _words(cell: Cell) -> str | None:
    if isinstance(cell, SheetStateCell):
        return STATE_WORDS.get(cell.state, "No access")
    if isinstance(cell, SheetLinkCell):
        return cell.link.label
    if isinstance(cell, SheetUnlinkedCell):
        return cell.unlinked
    return None


def _value(cell: Cell) -> Any:
    return cell.value if isinstance(cell, SheetValueCell) else None


def csv_cell(cell: Cell, column: ExportColumn, rules: CellFormat) -> str:
    words = _words(cell)
    if words is not None:
        return record_export.safe_text(words)
    value = _value(cell)
    if value is None:
        return ""
    if column.kind is FieldType.USER:
        return record_export.safe_text(rules.people.get(str(value), UNAVAILABLE_USER))
    return record_export.format_cell(value, column.field(), rules.timezone, rules.locale)


def xlsx_cell(cell: Cell, column: ExportColumn, rules: CellFormat) -> XlsxValue:
    words = _words(cell)
    if words is not None:
        return words
    value = _value(cell)
    if value is None:
        return None
    if column.kind is FieldType.USER:
        return rules.people.get(str(value), UNAVAILABLE_USER)
    return record_export.xlsx_cell(value, column.field(), rules.timezone)


def encode_csv(
    columns: list[ExportColumn], rows: Iterable[list[Cell]], rules: CellFormat,
) -> tuple[bytes, int]:
    result = bytearray()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)

    def append(cells: list[str]) -> None:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(cells)
        encoded = buffer.getvalue().encode("utf-8")
        if len(result) + len(encoded) > record_export.MAX_BYTES:
            raise record_export.limit_exceeded()
        result.extend(encoded)

    append([record_export.safe_text(column.name) for column in columns])
    count = 0
    for cells in rows:
        count += 1
        if count > record_export.MAX_ROWS:
            raise record_export.limit_exceeded()
        append([csv_cell(cell, column, rules) for cell, column in zip(cells, columns, strict=True)])
    return bytes(result), count


def encode_xlsx(
    columns: list[ExportColumn], rows: Iterable[list[Cell]], rules: CellFormat, author: str,
) -> tuple[bytes, int]:
    count = 0
    raw_bytes = 0
    try:
        with TemporaryDirectory(prefix="slateops-sheet-export-") as temporary:
            output = Path(temporary) / "export.xlsx"
            with Workbook(str(output), {
                "constant_memory": True, "tmpdir": temporary,
                "strings_to_formulas": False, "strings_to_urls": False,
            }) as workbook:
                workbook.set_properties({"author": author})
                tab = workbook.add_worksheet("Rows")
                header = workbook.add_format({"bold": True})
                plain = workbook.add_format({"valign": "top"})
                formats = {
                    FieldType.DATE: workbook.add_format({"num_format": "yyyy-mm-dd"}),
                    FieldType.DATETIME: workbook.add_format(
                        {"num_format": "yyyy-mm-dd hh:mm:ss"}
                    ),
                    FieldType.INTEGER: workbook.add_format({"num_format": "0"}),
                }
                for index, column in enumerate(columns):
                    write_text(tab, 0, index, column.name, header)
                for cells in rows:
                    count += 1
                    if count > record_export.MAX_ROWS:
                        raise record_export.limit_exceeded()
                    for index, (cell, column) in enumerate(zip(cells, columns, strict=True)):
                        value = xlsx_cell(cell, column, rules)
                        write_cell(tab, count, index, value, formats.get(column.kind, plain))
                        if value is not None:
                            raw_bytes += len(str(value).encode("utf-8"))
                            if raw_bytes > MAX_RAW_CONTENT_BYTES:
                                raise record_export.limit_exceeded()
                tab.freeze_panes(1, 0)
            if output.stat().st_size > record_export.MAX_BYTES:
                raise record_export.limit_exceeded()
            content = output.read_bytes()
    except FileCreateError as error:
        raise HTTPException(503, detail="Unable to create export") from error
    return content, count
