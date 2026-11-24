"""Small Excel files for the import parser tests, built in memory (spec D9.3, D14 E1-E7)."""

import io
import zipfile
from collections.abc import Callable
from datetime import date

from xlsxwriter import Workbook


def workbook(fill: Callable[[Workbook], None] | None = None) -> bytes:
    """Two visible tabs and one hidden tab; the first holds every value kind."""

    output = io.BytesIO()
    with Workbook(output, {"in_memory": True, "strings_to_formulas": False}) as book:
        first = book.add_worksheet("Grades")
        first.write_row(0, 0, ["Student", "Score", "Passed", "Due", "Note", "Total"])
        first.write_row(1, 0, ["Alice", 12.5, True])
        dated = book.add_format({"num_format": "yyyy-mm-dd"})
        first.write_datetime(1, 3, date(2026, 11, 24), dated)
        first.write_string(1, 4, "=1+1")
        first.write_formula(1, 5, "=B2*2", None, 25)
        first.write_formula(2, 5, "=B3*2", None, "")  # replaced below by a formula with no value
        hidden = book.add_worksheet("Secret")
        hidden.write(0, 0, "hidden")
        hidden.hide()
        book.add_worksheet("Empty")
        if fill is not None:
            fill(book)
    return output.getvalue()


def rewrite(content: bytes, change: Callable[[str, bytes], bytes | None],
            extra: dict[str, bytes] | None = None) -> bytes:
    """A copy of an xlsx with parts changed, dropped (``None``) or added."""

    source = zipfile.ZipFile(io.BytesIO(content))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = change(item.filename, source.read(item.filename))
            if data is not None:
                target.writestr(item.filename, data)
        for name, data in (extra or {}).items():
            target.writestr(name, data)
    return output.getvalue()


def without_saved_value(content: bytes) -> bytes:
    """The second formula keeps its formula and loses its saved result."""

    def change(name: str, data: bytes) -> bytes:
        if name == "xl/worksheets/sheet1.xml":
            return data.replace(b"<f>B3*2</f><v></v>", b"<f>B3*2</f>")
        return data

    return rewrite(content, change)


def sheet_xml(rows: str, dimension: str | None = "A1:A1") -> bytes:
    ref = f'<dimension ref="{dimension}"/>' if dimension else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{ref}<sheetData>{rows}</sheetData></worksheet>"
    ).encode()


def with_first_sheet(content: bytes, xml: bytes) -> bytes:
    return rewrite(content, lambda name, data: xml if name == "xl/worksheets/sheet1.xml" else data)
