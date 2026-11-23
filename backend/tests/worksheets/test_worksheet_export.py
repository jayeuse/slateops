"""Route 20 data export: CSV and Excel as the exporter sees the sheet (X2-X4, D9.1; SH-31).

The file content is built by the snapshot builder, here run on the test's own session; the
route journeys run on committed rows, because the snapshot is a separate connection.
"""

import csv
import io
from datetime import timedelta
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.openview.worksheets import export as sheet_export
from app.systems.openview.worksheets.export import ExportFile, build_export
from app.systems.openview.worksheets.models import WorksheetRow
from tests.conftest import membership_of
from tests.rbac.support import _client
from tests.worksheets.committed_support import CommittedSheet
from tests.worksheets.export_support import ExportJourney
from tests.worksheets.export_support import committed_sheet as committed_sheet
from tests.worksheets.export_support import journey as journey
from tests.worksheets.support import (
    SheetWorld,
    Students,
    add_students,
    editable_structure,
    sheet_world,
)

pytestmark = pytest.mark.integration
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADER = ["Student", "Name", "Note", "Points", "Mark", "Status", "Teacher", "Done", "Due"]


@pytest.fixture(scope="module")
def application() -> Any:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


@pytest.fixture
def world(integration_db: Session, application: FastAPI) -> tuple[SheetWorld, Students]:
    """Two rows written through route 10: a linked student and an unlinked one."""

    db = integration_db
    found = sheet_world(db)
    students = add_students(db, found, [found.owner, found.editor])
    found.viewer.display_name = "Vera Viewer"
    found.sheet.structure = editable_structure(students)
    db.flush()
    rows = f"/api/worksheets/{found.sheet.id}/rows"
    for cells in (
        {"c1": {"record_id": str(students.alice.id)}, "c3": "=1+1", "c4": 7, "c5": "12.5",
         "c6": "Pass", "c7": str(found.viewer.id), "c8": True, "c9": "2026-11-24"},
        {"c1": {"unlinked": "@SUM(A1)"}, "c3": "-2", "c6": "Fail"},
    ):
        created = _client(application, found.owner, db).post(rows, json={"cells": cells})
        assert created.status_code == 201, created.text
    return found, students


def _export(db: Session, person: Any, sheet_id: Any, format: str) -> ExportFile:
    return build_export(db, reader_id=person.id, worksheet_id=sheet_id, format=format)


def _csv(exported: ExportFile) -> list[list[str]]:
    return list(csv.reader(io.StringIO(exported.content.decode("utf-8"))))


def test_csv_holds_every_row_and_column_with_names_values_and_inert_text(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, _students = world
    exported = _export(integration_db, found.owner, found.sheet.id, "csv")
    assert _csv(exported) == [
        HEADER,
        ["Alice", "Alice", "'=1+1", "7", "12.5", "Pass", "Vera Viewer", "true",
         "Nov 24, 2026"],
        ["'@SUM(A1)", "", "'-2", "", "", "Fail", "", "", ""],
    ]
    assert (exported.row_count, exported.column_count) == (2, 9)
    assert exported.filename.startswith("grades-") and exported.filename.endswith(".csv")


def test_a_view_recipient_without_the_linked_module_gets_no_access_and_no_name(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, students = world
    exported = _export(integration_db, found.viewer, found.sheet.id, "csv")
    rows = _csv(exported)
    assert [row[:2] for row in rows[1:]] == [["No access", "No access"]] * 2
    assert b"Alice" not in exported.content
    assert str(students.alice.id).encode() not in exported.content


def test_excel_keeps_typed_cells_and_writes_formula_text_as_strings(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, _students = world
    exported = _export(integration_db, found.owner, found.sheet.id, "xlsx")
    with ZipFile(io.BytesIO(exported.content)) as archive:
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    cells = {cell.attrib["r"]: cell for cell in sheet.findall(".//s:c", NS)}

    def shown(address: str) -> str:
        return "".join(cells[address].itertext())

    assert [shown(f"{column}1") for column in "ABCDEFGHI"] == HEADER
    assert [shown(address) for address in ("A2", "C2", "F2", "G2")] == [
        "Alice", "=1+1", "Pass", "Vera Viewer",
    ]
    assert [cells[address].attrib["t"] for address in ("C2", "A3", "C3")] == ["inlineStr"] * 3
    assert [shown(address) for address in ("A3", "C3")] == ["@SUM(A1)", "-2"]
    assert not sheet.findall(".//s:f", NS)  # no cell is a formula
    assert cells["D2"].get("t") in (None, "n") and shown("D2") == "7"
    assert cells["H2"].attrib["t"] == "b"
    assert exported.row_count == 2


def test_a_sheet_over_the_export_row_cap_is_refused(
    integration_db: Session, world: tuple[SheetWorld, Students],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found, _students = world
    monkeypatch.setattr(sheet_export.record_export, "MAX_ROWS", 1)
    with pytest.raises(HTTPException) as refused:
        _export(integration_db, found.owner, found.sheet.id, "csv")
    assert refused.value.status_code == 422
    assert refused.value.detail["code"] == "export_limit_exceeded"


def test_a_person_the_exporter_cannot_see_exports_as_unavailable_user(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, _students = world
    found.outsider.display_name = "Hidden Person"  # shares no group or module with the owner
    integration_db.add(WorksheetRow(
        org_id=found.sheet.org_id, worksheet_id=found.sheet.id, position=9 * 1024,
        data={"c7": str(found.outsider.id)}, data_bytes=48,
    ))
    integration_db.flush()
    as_csv = _export(integration_db, found.owner, found.sheet.id, "csv")
    assert [row[6] for row in _csv(as_csv)[1:]] == ["Vera Viewer", "", "Unavailable user"]
    as_xlsx = _export(integration_db, found.owner, found.sheet.id, "xlsx")
    with ZipFile(io.BytesIO(as_xlsx.content)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
    assert "Unavailable user" in sheet
    for exported in (as_csv.content, as_xlsx.content):
        assert b"Hidden Person" not in exported
        assert str(found.outsider.id).encode() not in exported


def test_a_reader_of_an_open_sheet_exports_it(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    """X2: the owner left, so the sheet is open to readers of its record (D2)."""

    found, _students = world
    membership_of(integration_db, found.owner.id).worksheets_released_at = (
        found.sheet.created_at + timedelta(seconds=1)
    )
    integration_db.flush()
    rows = _csv(_export(integration_db, found.peer, found.sheet.id, "csv"))
    assert [row[:3] for row in rows] == [
        ["Student", "Name", "Note"], ["No access", "No access", "'=1+1"],
        ["No access", "No access", "'-2"],
    ]


def _cell(world: CommittedSheet, value: str) -> None:
    with world.owner_engine.begin() as connection:
        connection.execute(
            text("UPDATE public.worksheet_rows SET data = jsonb_build_object('c3', "
                 "CAST(:value AS text)) WHERE id = :id"),
            {"value": value, "id": world.row_id},
        )


@pytest.mark.parametrize(("format", "media_type"), [
    ("csv", "text/csv"),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("template", "application/json"),
])
def test_an_editor_exports_through_the_route_and_exactly_one_event_is_committed(
    journey: ExportJourney, format: str, media_type: str,
) -> None:
    world = journey.world
    _cell(world, "=HYPERLINK(\"x\")")
    response = journey.export(world.editor_id, format)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith('attachment; filename="race-')
    if format == "csv":
        assert list(csv.reader(io.StringIO(response.text))) == [
            ["Note"], ["'=HYPERLINK(\"x\")"],
        ]
    [event] = journey.events()
    assert (event.actor_id, event.org_id) == (world.editor_id, world.org_id)
    assert event.event_metadata == {
        "format": format, "row_count": 0 if format == "template" else 1, "column_count": 1,
    }


def test_a_person_who_cannot_see_the_sheet_gets_not_found_and_no_event(
    journey: ExportJourney,
) -> None:
    response = journey.export(journey.world.admin_id, "csv")  # no admin override (D2)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "worksheet_not_found"
    assert journey.events() == []


@pytest.mark.parametrize(("lost", "status"), [("share", 404), ("module_access", 403)])
def test_access_lost_during_the_build_releases_no_bytes_and_no_event(
    journey: ExportJourney, monkeypatch: pytest.MonkeyPatch, lost: str, status: int,
) -> None:
    world = journey.world
    _cell(world, "secret")
    original = sheet_export.export_snapshot
    built: list[bool] = []

    def revoke_after_build(*args: Any, **kwargs: Any) -> ExportFile:
        result = original(*args, **kwargs)
        statement = (
            "UPDATE public.worksheet_shares SET is_deleted = true, deleted_at = :now "
            "WHERE id = :id" if lost == "share" else
            "UPDATE public.group_access SET is_deleted = true, deleted_at = :now "
            "WHERE org_id = :org"
        )
        with world.owner_engine.begin() as connection:
            connection.execute(text(statement),
                               {"now": utc_now(), "id": world.share_id, "org": world.org_id})
        built.append(True)
        return result

    monkeypatch.setattr(sheet_export, "export_snapshot", revoke_after_build)
    response = journey.export(world.editor_id, "csv")
    assert built == [True]
    assert response.status_code == status
    assert b"secret" not in response.content
    assert journey.events() == []


@pytest.mark.parametrize("failing", ["snapshot", "event"])
def test_a_failed_build_or_event_releases_no_bytes(
    journey: ExportJourney, monkeypatch: pytest.MonkeyPatch, failing: str,
) -> None:
    _cell(journey.world, "secret")

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise OperationalError("unavailable", {}, RuntimeError("unavailable"))

    monkeypatch.setattr(
        sheet_export, "export_snapshot" if failing == "snapshot" else "append_security_event",
        unavailable,
    )
    response = journey.export(journey.world.editor_id, "csv")
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Unable to create export" if failing == "snapshot"
        else "Unable to record export authorization"
    )
    assert b"secret" not in response.content
    assert journey.events() == []
