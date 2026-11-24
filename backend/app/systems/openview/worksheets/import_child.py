"""Isolated Excel import parser (spec D9.3, D9.4, D14 E1-E4).

It runs as its own process with CPU, memory and core limits, reads the exact bytes the
route checked from stdin, and imports no settings, database or web framework. Before
python-calamine sees the file: the archive bounds of the file validator, the marker names
of other formats, a zip that starts at byte 0, unique part names and tab names in any letter case, a
match between calamine's sheet list and ``workbook.xml``, and a streaming ``defusedxml``
pre-scan of the chosen sheet (rows, columns, the used range, strict cell references, cell
text and the shared-string text the cells reference). Calamine then reads the same sheet by
its position, and its own used range is checked again before any row becomes Python. It
writes JSON to stdout, counting each byte, and exits with one code per refusal reason.
"""

import io
import json
import re
import resource
import sys
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import PurePosixPath
from typing import Any

from defusedxml.ElementTree import fromstring, iterparse
from python_calamine import CalamineError, CalamineWorkbook, SheetTypeEnum, SheetVisibleEnum

from app.systems.platform.files.validation import MAX_BYTES, InvalidContent, inspect_content

MAX_FILE_ROWS = 10_001  # 10,000 rows and a header row
MAX_COLUMNS = 100
MAX_CELL_CHARACTERS = 4_000
OUTPUT_LIMIT = 16 * 1024 * 1024
EXIT = {"archive_bounds": 10, "macro": 11, "unreadable": 12, "rows": 13, "columns": 14,
        "cell": 15, "limit": 16, "tab": 17}
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RELATIONSHIP = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_CELL = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_ROW = re.compile(r"[1-9][0-9]{0,6}")
_ZIP_START = b"PK\x03\x04"
_FOREIGN = ("xl/workbook.bin", "content.xml", "mimetype")  # xlsb and ods inside a zip


class Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _column(letters: str) -> int:
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - 64
    return value


def _position(ref: str | None) -> tuple[int, int] | None:
    found = _CELL.fullmatch(ref or "")
    return None if found is None else (int(found.group(2)), _column(found.group(1)))


def _classify(content: bytes) -> str:
    """After the validator refused the file: macro content, else the archive bounds."""

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [item.filename.lower() for item in archive.infolist()]
    except (zipfile.BadZipFile, OSError, ValueError):
        return "unreadable"
    if any("vba" in name for name in names):
        return "macro"
    types = next((item for item in names if item == "[content_types].xml"), None)
    if types is not None:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive, archive.open(
                "[Content_Types].xml",
            ) as part:
                text = part.read(MAX_BYTES).lower()  # bounded: the file may be a bomb
        except (KeyError, zipfile.BadZipFile, OSError, ValueError):
            return "archive_bounds"
        if b"macroenabled" in text or b"vba" in text:
            return "macro"
    return "archive_bounds"


def _sheets(archive: zipfile.ZipFile) -> list[tuple[str, str, bool]]:
    """Each sheet of ``workbook.xml``: its name, its part and whether it is a visible
    worksheet (the only kind offered)."""

    book = fromstring(archive.read("xl/workbook.xml"), forbid_dtd=True)
    relations = fromstring(archive.read("xl/_rels/workbook.xml.rels"), forbid_dtd=True)
    targets = {item.attrib.get("Id"): (item.attrib.get("Target", ""), item.attrib.get("Type", ""))
               for item in relations}
    found = []
    for sheet in book.iter(f"{_MAIN}sheet"):
        target, kind = targets.get(sheet.attrib.get(_RELATIONSHIP), ("", ""))
        part = target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
        visible = sheet.attrib.get("state", "visible") == "visible" and kind.endswith(
            "/worksheet")
        found.append((sheet.attrib.get("name", ""), part, visible))
    return found


def _local(tag: str) -> str:
    """An element name without its namespace: the reader does not check namespaces."""

    return tag.rpartition("}")[2]


def _children(node: Any, name: str) -> list[Any]:
    return [child for child in node if _local(child.tag) == name]


def _text_length(node: Any) -> int:
    return sum(len(item.text or "") for item in node.iter() if _local(item.tag) == "t")


def _shared_lengths(archive: zipfile.ZipFile) -> list[int]:
    """Shared strings under any letter case of their name, as the reader finds them."""

    found = [name for name in archive.namelist() if name.lower() == "xl/sharedstrings.xml"]
    if not found:
        return []
    lengths = []
    stream = io.BytesIO(archive.read(found[0]))
    for _event, node in iterparse(stream, forbid_dtd=True):
        if _local(node.tag) == "si":
            lengths.append(_text_length(node))
            node.clear()
    return lengths


def _prescan(archive: zipfile.ZipFile, part: str, shared: list[int]) -> int:
    """Refuse a sheet that is too large or reaches outside its used range; return the
    number of formulas with no saved result."""

    bounds: tuple[int, int] | None = None
    row_number = column_number = 0
    referenced = formulas = 0
    stream = io.BytesIO(archive.read(part))
    for event, node in iterparse(stream, events=("start", "end"), forbid_dtd=True):
        tag = _local(node.tag)
        if event == "start":
            if tag == "dimension":
                bounds = _position(node.attrib.get("ref", "").split(":")[-1])
            elif tag == "row":
                given = node.attrib.get("r")
                if given is not None and _ROW.fullmatch(given) is None:
                    raise Refused("unreadable")
                row_number = int(given) if given is not None else row_number + 1
                column_number = 0
                if row_number > MAX_FILE_ROWS:
                    raise Refused("rows")
            elif tag == "c":
                reference = node.attrib.get("r")
                position = _position(reference)
                if reference is not None and (position is None or position[0] != row_number):
                    raise Refused("unreadable")  # a cell reference outside its row
                column_number = position[1] if position else column_number + 1
                if column_number > MAX_COLUMNS:
                    raise Refused("columns")
                if bounds and (row_number > bounds[0] or column_number > bounds[1]):
                    raise Refused("unreadable")
            continue
        if tag == "c":
            kind = node.attrib.get("t")
            values = _children(node, "v")
            value = values[0] if values else None
            if _children(node, "f") and value is None:
                formulas += 1
            if kind == "s" and value is not None and (value.text or "").isdigit():
                index = int(value.text or "0")
                length = shared[index] if index < len(shared) else 0
            else:
                length = _text_length(node) or len(
                    value.text or "" if value is not None else "")
            if length > MAX_CELL_CHARACTERS:
                raise Refused("cell")
            referenced += length
            if referenced > OUTPUT_LIMIT // 2:
                raise Refused("limit")
            node.clear()
        elif tag == "row":
            node.clear()
    return formulas


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time() else value.isoformat()
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    if value == "":
        return None
    return value


class _Output:
    def __init__(self) -> None:
        self.written = 0

    def write(self, text: str) -> None:
        data = text.encode()
        self.written += len(data)
        if self.written > OUTPUT_LIMIT:
            raise Refused("limit")
        sys.stdout.buffer.write(data)


def _check_archive(content: bytes) -> None:
    """A zip whose first entry starts at byte 0, with no foreign marker and no two names
    that differ only in letter case."""

    if not content.startswith(_ZIP_START):
        raise Refused("unreadable")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError) as error:
        raise Refused("unreadable") from error
    lowered = [item.filename.lower() for item in entries]
    if (not entries or min(item.header_offset for item in entries) != 0
            or len(set(lowered)) != len(lowered)
            or any(name in _FOREIGN for name in lowered)):
        raise Refused("unreadable")


def _check_reach(sheet: Any) -> None:
    """The reader's own used range, before any row becomes a Python object."""

    end = sheet.end
    if end is not None and end[0] + 1 > MAX_FILE_ROWS:
        raise Refused("rows")
    if end is not None and end[1] + 1 > MAX_COLUMNS:
        raise Refused("columns")


def parse(content: bytes, tab: int) -> None:
    _check_archive(content)
    try:
        inspect_content("import.xlsx", content)
    except InvalidContent as error:
        raise Refused(_classify(content)) from error
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        sheets = _sheets(archive)
        if len({name.casefold() for name, _part, _visible in sheets}) != len(sheets):
            raise Refused("unreadable")  # two tabs of one name
        offered = [(position, name, part)
                   for position, (name, part, visible) in enumerate(sheets) if visible]
        if tab >= len(offered):
            raise Refused("tab")
        position, _name, part = offered[tab]
        formulas = _prescan(archive, part, _shared_lengths(archive))
    with CalamineWorkbook.from_filelike(io.BytesIO(content)) as book:
        listed = [(item.name, item.typ == SheetTypeEnum.WorkSheet
                   and item.visible == SheetVisibleEnum.Visible) for item in book.sheets_metadata]
        if listed != [(sheet_name, visible) for sheet_name, _part, visible in sheets]:
            raise Refused("unreadable")  # the two readers disagree on the workbook
        sheet = book.get_sheet_by_index(position)
        _check_reach(sheet)
        rows = sheet.to_python(skip_empty_area=False)
    width = max((len(row) for row in rows), default=0)
    while rows and all(_cell(value) is None for value in rows[-1]):
        rows.pop()
    output = _Output()
    output.write('{"tabs":' + json.dumps(
        [{"index": index, "name": item[1]} for index, item in enumerate(offered)],
    ) + f',"tab_index":{tab},"formula_without_value_count":{formulas},"rows":[')
    for index, row in enumerate(rows):
        cells = [_cell(value) for value in row] + [None] * (width - len(row))
        if any(isinstance(cell, str) and len(cell) > MAX_CELL_CHARACTERS for cell in cells):
            raise Refused("cell")
        output.write(("," if index else "") + json.dumps(cells, ensure_ascii=False))
    output.write(f'],"row_count":{len(rows)},"column_count":{width if rows else 0}}}')


def main() -> int:
    # Bound CPU, address space and core files even if the native reader loops or expands.
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    content = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        return EXIT["archive_bounds"]
    try:
        parse(content, int(sys.argv[1]))
    except Refused as refused:
        return EXIT[refused.reason]
    except (CalamineError, KeyError, ValueError, OSError, SyntaxError, zipfile.BadZipFile):
        return EXIT["unreadable"]
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
