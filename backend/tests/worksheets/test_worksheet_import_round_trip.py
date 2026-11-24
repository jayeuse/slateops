"""An organization re-imports its own CSV export (B9 note for B13; X4, X8, X9).

The browser reads the CSV and sends each cell as text through route 10, as an import does.
Every column comes back as it left, in a comma-decimal locale too (X4, X12). The browser
removes the one apostrophe the export puts before formula-like text, so that text comes
back as it was and stays text (X11). A person column cannot be filled from a file: the
browser leaves it out, so it stays blank (X12).
"""

import csv
import io
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.export import build_export
from app.systems.openview.worksheets.export_files import NEEDS_MARK, csv_text
from app.systems.sandbox.records.export import safe_text
from tests.rbac.support import _client
from tests.worksheets.support import add_sheet, sheet_world

STRUCTURE = {
    "structureVersion": 1, "nextColumnSeq": 8, "groups": [], "totals": {},
    "columns": [
        {"key": "c1", "name": "Note", "type": "text"},
        {"key": "c2", "name": "Points", "type": "int"},
        {"key": "c3", "name": "Mark", "type": "decimal", "decimal": {"places": 2}},
        {"key": "c4", "name": "Score", "type": "number"},
        {"key": "c5", "name": "Status", "type": "select",
         "select": {"options": [{"id": "o1", "label": "Pass"}, {"id": "o2", "label": "Fail"}]}},
        {"key": "c6", "name": "Done", "type": "boolean"},
        {"key": "c7", "name": "Due", "type": "date"},
        {"key": "c8", "name": "Teacher", "type": "user"},
    ],
}
ROWS = [
    {"c1": "=1+1", "c2": 1234567, "c3": 12.5, "c4": 0.25, "c5": "Pass", "c6": True,
     "c7": "2026-11-24"},
    {"c1": "second", "c2": -7, "c3": -3.25, "c4": 1000.5, "c5": "Fail", "c6": False,
     "c7": "2027-01-02"},
    *({"c1": text, "c2": 0, "c3": 0, "c4": 0, "c5": "Pass", "c6": False, "c7": "2027-01-03"}
      for text in ("'=x", "'=A1", " =x", "' =x", "\nline", "'hello")),
]
# The browser's rule (frontend ``fromExport``), written out literally: one apostrophe goes
# when the rest of the text still needs the mark.
BROWSER_MARKED = re.compile(
    r"'(?='*(?:[\t\r\n]|[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029"
    r"\u202f\u205f\u3000]*[=+\-@]))"
)


def unescape(text: str) -> str:
    """What the browser does to each CSV cell: drop the export's one mark."""

    return text[1:] if BROWSER_MARKED.match(text) else text


@pytest.mark.parametrize(("text", "written"), [
    ("=1+1", "'=1+1"),
    ("'=A1", "''=A1"),
    (" =x", "' =x"),
    ("' =x", "'' =x"),
    ("\nline", "'\nline"),
    ("'hello", "'hello"),
    ("hello", "hello"),
    ("", ""),
])
def test_csv_text_marks_exactly_the_text_that_needs_it(text: str, written: str) -> None:
    """X12: the mark is one apostrophe, and the browser's removal gives the text back."""

    assert csv_text(text) == written
    assert unescape(written) == text


def test_formula_like_text_is_exactly_what_the_record_export_escapes() -> None:
    """Without a leading apostrophe, the mark goes where ``safe_text`` puts it, for every
    first character in the Basic Multilingual Plane."""

    for code in range(0x10000):
        for text in (chr(code), chr(code) + "=", chr(code) + " @", chr(code) + "x"):
            if text.startswith("'"):
                continue
            assert (NEEDS_MARK.match(text) is not None) == (safe_text(text) != text), text


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.mark.integration
@pytest.mark.parametrize("locale", ["de-DE", "en-US", "fr-FR"])
def test_a_sheet_reimports_its_own_csv_export(
    application: FastAPI, integration_db: Session, locale: str,
) -> None:
    db = integration_db
    world = sheet_world(db)
    db.get(WorkspaceProfile, world.sheet.org_id).locale = locale
    world.sheet.structure = dict(STRUCTURE)
    target = add_sheet(db, world.owner, record=world.record)
    target.structure = dict(STRUCTURE)
    db.flush()
    owner = _client(application, world.owner, db)
    for cells in ROWS:
        cells = {**cells, "c8": str(world.viewer.id)}
        created = owner.post(f"/api/worksheets/{world.sheet.id}/rows", json={"cells": cells})
        assert created.status_code == 201, created.text
    exported = build_export(db, reader_id=world.owner.id, worksheet_id=world.sheet.id,
                            format="csv")
    header, *lines = list(csv.reader(io.StringIO(exported.content.decode())))
    keys = [column["key"] for column in STRUCTURE["columns"]]
    for line in lines:
        cells: dict[str, Any] = {key: unescape(text) for key, text in zip(keys, line, strict=True)
                                 if key != "c8"}  # a person column is not filled from a file
        imported = owner.post(f"/api/worksheets/{target.id}/rows", json={"cells": cells})
        assert imported.status_code == 201, (locale, line, imported.text)
    read = owner.post(f"/api/worksheets/{target.id}/rows/query", json={}).json()["items"]
    original = owner.post(f"/api/worksheets/{world.sheet.id}/rows/query",
                          json={}).json()["items"]
    assert [{**row["cells"], "c8": None} for row in read] == [
        {**row["cells"], "c8": None} for row in original
    ]
    assert [row["cells"]["c8"] for row in read] == [{"value": None}] * 8
    assert [row["cells"]["c8"] for row in original] == [{"value": str(world.viewer.id)}] * 8
    assert [row["cells"]["c1"] for row in read] == [
        {"value": text} for text in (
            "=1+1", "second", "'=x", "'=A1", " =x", "' =x", "\nline", "'hello",
        )
    ]
    assert header == [column["name"] for column in STRUCTURE["columns"]]
