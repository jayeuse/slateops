"""The Excel import parser in its child process (spec D9.3, D9.4, D14 E1-E4; SH-36).

Each hostile file is refused with one reason before python-calamine reads it, the child's
output and each cell are capped, and any other exit of the child is a refusal, never a 500.
"""

import io
import json
import resource
import subprocess
import sys
import zipfile
from typing import Any

import pytest

from app.systems.openview.worksheets import import_worker
from app.systems.openview.worksheets.import_worker import ImportRefused, parse_import
from tests.worksheets.import_files import (
    rewrite,
    sheet_xml,
    with_first_sheet,
    without_saved_value,
    workbook,
)


def _refused(content: bytes, tab: int = 0) -> ImportRefused:
    with pytest.raises(ImportRefused) as refused:
        parse_import(content, tab)
    return refused.value


def test_a_workbook_reads_its_chosen_visible_tab_with_typed_values() -> None:
    parsed = parse_import(without_saved_value(workbook()), 0)
    assert parsed["tabs"] == [{"index": 0, "name": "Grades"}, {"index": 1, "name": "Empty"}]
    assert parsed["tab_index"] == 0
    assert parsed["rows"] == [
        ["Student", "Score", "Passed", "Due", "Note", "Total"],
        ["Alice", 12.5, True, "2026-11-24", "=1+1", 25],
    ]  # the row whose only cell is a formula without a saved value reads empty, and goes
    assert parsed["formula_without_value_count"] == 1
    assert (parsed["row_count"], parsed["column_count"]) == (2, 6)
    assert parse_import(workbook(), 1)["rows"] == []


def _bomb(content: bytes) -> bytes:
    return rewrite(content, lambda name, data: data,
                   {"xl/media/padding.xml": b"<a>" + b" " * 3_000_000 + b"</a>"})


def _entries(content: bytes) -> bytes:
    return rewrite(content, lambda name, data: data,
                   {f"docProps/extra{index}.xml": b"<a/>" for index in range(2_050)})


def _macro_part(content: bytes) -> bytes:
    return rewrite(content, lambda name, data: data, {"xl/vbaProject.bin": b"\x00" * 64})


def _macro_type(content: bytes) -> bytes:
    def change(name: str, data: bytes) -> bytes:
        if name == "[Content_Types].xml":
            return data.replace(b"sheet.main+xml", b"sheet.macroEnabled.main+xml")
        return data

    return rewrite(content, change)


def _xlsb(content: bytes) -> bytes:
    return rewrite(content, lambda name, data: data, {"xl/workbook.bin": b"\x00" * 64})


def _ods(content: bytes) -> bytes:
    return rewrite(content, lambda name, data: data,
                   {"mimetype": b"application/vnd.oasis.opendocument.spreadsheet",
                    "content.xml": b"<office:document-content/>"})


def _far_corner(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml(
        '<row r="1"><c r="A1"><v>1</v></c></row>'
        '<row r="1048576"><c r="XFD1048576"><v>1</v></c></row>',
    ))


def _outside_dimension(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml('<row r="3"><c r="C3"><v>1</v></c></row>'))


def _rows(content: bytes) -> bytes:
    rows = "".join(f'<row r="{index}"><c r="A{index}"><v>1</v></c></row>'
                   for index in range(1, 10_003))
    return with_first_sheet(content, sheet_xml(rows, "A1:A10002"))


def _columns(content: bytes) -> bytes:
    cells = "".join(f"<c><v>{index}</v></c>" for index in range(101))
    return with_first_sheet(content, sheet_xml(f"<row>{cells}</row>", None))


def _long_cell(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml(
        f'<row r="1"><c r="A1" t="inlineStr"><is><t>{"x" * 4_001}</t></is></c></row>',
    ))


def _shared_strings(content: bytes) -> bytes:
    """One 3,000-character shared string in 10,000 cells: 30 MB of text from 3 kB."""

    def change(name: str, data: bytes) -> bytes:
        if name == "xl/sharedStrings.xml":
            return (
                b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                b'count="1" uniqueCount="1"><si><t>' + b"y" * 3_000 + b"</t></si></sst>"
            )
        if name == "xl/worksheets/sheet1.xml":
            rows = "".join(
                f'<row r="{row}">' + "".join(
                    f'<c r="{chr(65 + col)}{row}" t="s"><v>0</v></c>' for col in range(10)
                ) + "</row>" for row in range(1, 1_001)
            )
            return sheet_xml(rows, "A1:J1000")
        return data

    return rewrite(content, change)


def _cell_outside_its_row(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml(
        '<row r="1"><c r="A1"><v>1</v></c></row>'
        '<row r="2"><c r="A20000"><v>2</v></c></row>', None))


def _lowercase_reference(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml(
        '<row r="1"><c r="A1"><v>1</v></c><c r="da1"><v>2</v></c></row>', None))


def _four_letter_column(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml(
        '<row r="1"><c r="A1"><v>1</v></c><c r="AAAA1"><v>2</v></c></row>', None))


def _padded_row_reference(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml(
        '<row r="1"><c r="A1"><v>1</v></c></row>'
        '<row r="2"><c r="A00020000"><v>2</v></c></row>', None))


def _row_number_not_digits(content: bytes) -> bytes:
    return with_first_sheet(content, sheet_xml('<row r="x2"><c><v>1</v></c></row>', None))


def _shared_strings_other_case(content: bytes) -> bytes:
    """The shared strings part under another letter case: 12 MB of text from 3 kB."""

    def change(name: str, data: bytes) -> bytes | None:
        if name == "xl/sharedStrings.xml":
            return None
        if name in ("xl/_rels/workbook.xml.rels", "[Content_Types].xml"):
            return data.replace(b"sharedStrings.xml", b"SharedStrings.xml")
        if name == "xl/worksheets/sheet1.xml":
            rows = "".join(f'<row r="{row}"><c r="A{row}" t="s"><v>0</v></c></row>'
                           for row in range(1, 4_001))
            return sheet_xml(rows, "A1:A4000")
        return data

    return rewrite(content, change, {"xl/SharedStrings.xml": (
        b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        b'count="1" uniqueCount="1"><si><t>' + b"y" * 3_000 + b"</t></si></sst>")})


def _names_differ_only_in_case(content: bytes) -> bytes:
    small = sheet_xml('<row r="1"><c r="A1"><v>1</v></c></row>')
    return rewrite(content, lambda name, data: data, {"xl/worksheets/Sheet1.xml": small})


def _signature_prefix(content: bytes) -> bytes:
    return bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 504 + content


@pytest.mark.parametrize(("make", "reason"), [
    (_bomb, "archive_bounds"),
    (_entries, "archive_bounds"),
    (_macro_part, "macro"),
    (_macro_type, "macro"),
    (_xlsb, "unreadable"),
    (_ods, "unreadable"),
    (_far_corner, "limit"),
    (_outside_dimension, "unreadable"),
    (_rows, "limit"),
    (_columns, "limit"),
    (_long_cell, "limit"),
    (_shared_strings, "limit"),
    (_cell_outside_its_row, "unreadable"),
    (_lowercase_reference, "unreadable"),
    (_four_letter_column, "unreadable"),
    (_padded_row_reference, "unreadable"),
    (_row_number_not_digits, "unreadable"),
    (_shared_strings_other_case, "limit"),
    (_names_differ_only_in_case, "unreadable"),
    (_signature_prefix, "unreadable"),
], ids=lambda value: getattr(value, "__name__", value))
def test_a_hostile_file_is_refused_with_its_reason(make: Any, reason: str) -> None:
    refused = _refused(make(workbook()))
    assert refused.reason == reason
    assert refused.status_code == 422


def test_row_and_column_limits_answer_worksheet_limit() -> None:
    assert _refused(_rows(workbook())).detail == {
        "code": "worksheet_limit", "message": "A sheet holds at most 10,000 rows",
        "limit": "rows", "maximum": 10_000,
    }
    assert _refused(_columns(workbook())).detail["limit"] == "columns"


def test_a_tab_that_is_not_there_is_refused() -> None:
    refused = _refused(workbook(), 2)  # two visible tabs
    assert (refused.status_code, refused.reason, refused.detail["code"]) == (
        422, "tab", "import_tab_invalid",
    )


def test_tab_names_that_repeat_in_any_letter_case_are_refused() -> None:
    """The parser reads the tab by its position; two tabs of one name are ambiguous."""

    for repeated in (b'name="Grades"', b'name="GRADES"'):
        twin = rewrite(workbook(), lambda name, data, repeated=repeated: data.replace(
            b'name="Empty"', repeated) if name == "xl/workbook.xml" else data)
        for tab in (0, 1):
            assert _refused(twin, tab).reason == "unreadable"


def test_the_reader_refuses_a_tab_whose_cells_reach_past_the_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second check on the reader's own used range, before any row becomes Python."""

    from app.systems.openview.worksheets import import_child

    monkeypatch.setattr(import_child, "_prescan", lambda archive, part, shared: 0)
    for make, reason in ((_rows, "rows"), (_columns, "columns")):
        with pytest.raises(import_child.Refused) as refused:
            import_child.parse(make(workbook()), 0)
        assert refused.value.reason == reason


def test_a_child_that_dies_or_overflows_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_worker, "CHILD", ["-c", "import os; os.abort()"])
    assert _refused(workbook()).reason == "unreadable"
    monkeypatch.setattr(import_worker, "CHILD", [
        "-c", "import sys; sys.stdout.write('x' * 100_000); sys.stdout.flush()",
    ])
    monkeypatch.setattr(import_worker, "OUTPUT_LIMIT", 1_000)
    assert _refused(workbook()).reason == "limit"


def test_the_answer_is_reserved_in_the_file_memory_budget_as_it_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parsed answer counts against the request's file memory; a full budget refuses
    the file as busy, with a time to retry."""

    from fastapi import HTTPException

    reserved: list[int] = []
    monkeypatch.setattr(import_worker, "reserve_download", reserved.append)
    parsed = parse_import(workbook(), 0)
    compact = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False).encode()
    assert sum(reserved) >= import_worker.ANSWER_MEMORY_FACTOR * len(compact)
    assert all(size % import_worker.ANSWER_MEMORY_FACTOR == 0 for size in reserved)

    def busy(size: int) -> None:
        raise HTTPException(503, detail={"code": "files_busy"}, headers={"Retry-After": "1"})

    monkeypatch.setattr(import_worker, "reserve_download", busy)
    refused = _refused(workbook())
    assert (refused.reason, refused.status_code, refused.detail["code"]) == (
        "busy", 503, "files_busy",
    )
    assert refused.headers == {"Retry-After": "1"}


def test_the_reservation_covers_the_largest_answer_the_limits_allow() -> None:
    """10,001 rows of 100 two-character texts: the parent's peak while it decodes,
    validates and renders the answer stays inside the reserved bytes."""

    import tracemalloc

    from app.systems.openview.worksheets.import_router import SheetImportFile

    row = json.dumps(["ab"] * 100, ensure_ascii=False)
    output = ('{"tabs":[{"index":0,"name":"A"}],"tab_index":0,'
              '"formula_without_value_count":0,"rows":[' + ",".join([row] * 10_001)
              + '],"row_count":10001,"column_count":100}').encode()
    tracemalloc.start()
    try:
        model = SheetImportFile.model_validate(json.loads(output))
        rendered = model.model_dump_json().encode()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert len(rendered) > 0
    assert peak + len(output) <= import_worker.ANSWER_MEMORY_FACTOR * len(output)


def test_the_pre_scan_reads_rows_and_strings_in_any_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the reader's own range check switched off, the pre-scan alone still refuses
    rows and shared text written under another XML namespace."""

    from app.systems.openview.worksheets import import_child

    monkeypatch.setattr(import_child, "_check_reach", lambda sheet: None)
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    def sheet(rows: str) -> bytes:
        return (f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{main}">'
                f"<sheetData>{rows}</sheetData></worksheet>").encode()

    many = "".join(f'<row xmlns="urn:x" r="{r}"><c r="A{r}"><v>{r}</v></c></row>'
                   for r in range(1, 20_001))
    strings = "".join(f'<row xmlns="urn:x" r="{r}"><c r="A{r}" t="s"><v>0</v></c></row>'
                      for r in range(1, 3_001))
    shared = (f'<sst xmlns="urn:y" count="1" uniqueCount="1"><si><t>{"y" * 3_000}</t></si>'
              "</sst>").encode()
    for rows, extra, reason in ((many, None, "rows"), (strings, shared, "limit")):
        def change(name: str, data: bytes, rows: str = rows, extra: Any = extra) -> bytes:
            if name == "xl/worksheets/sheet1.xml":
                return sheet(rows)
            return extra if extra is not None and name == "xl/sharedStrings.xml" else data

        with pytest.raises(import_child.Refused) as refused:
            import_child.parse(rewrite(workbook(), change), 0)
        assert refused.value.reason == reason


def test_the_child_loads_no_settings_database_or_web_framework() -> None:
    probe = (
        "import sys; import app.systems.openview.worksheets.import_child; "
        "print(sorted(m for m in ('sqlalchemy', 'fastapi', 'app.core.config') if m in "
        "sys.modules))"
    )
    loaded = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            check=True, env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"})
    assert loaded.stdout.strip() == "[]"


def test_an_archive_that_is_not_a_zip_is_unreadable() -> None:
    assert _refused(b"not a zip").reason in {"archive_bounds", "unreadable"}
    assert zipfile.is_zipfile(io.BytesIO(workbook()))


def test_the_child_runs_with_a_512_mib_address_space_limit() -> None:
    """D14 E4: the limits the child sets before it reads any byte, read from inside it.

    The address-space limit is Linux only (as in ``validation_child.py``): the server image
    is Linux, so CI proves 512 MiB; on a macOS workstation it stays unlimited.
    """

    probe = (
        "import resource, sys; "
        "from app.systems.openview.worksheets import import_child; "
        "import_child.parse = lambda content, tab: sys.stdout.write("
        "str(resource.getrlimit(resource.RLIMIT_AS)) + str(resource.getrlimit("
        "resource.RLIMIT_CORE)) + str(resource.getrlimit(resource.RLIMIT_CPU))); "
        "raise SystemExit(import_child.main())"
    )
    limits = subprocess.run(
        [sys.executable, "-c", probe, "0"], input=workbook(), capture_output=True,
        check=True, env={"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"},
    ).stdout.decode()
    space = 512 * 1024 * 1024 if sys.platform == "linux" else resource.RLIM_INFINITY
    assert limits == str((space, space)) + str((0, 0)) + str((30, 30))
