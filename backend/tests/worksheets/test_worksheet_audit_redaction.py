"""Sheet changes are audited with IDs only and no department (H1, H2, D5.1, D5.2; SH-45)."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.manage.audit.models import AuditLog
from tests.rbac.support import _client
from tests.worksheets.support import add_students, editable_structure, sheet_world

pytestmark = pytest.mark.integration
SHEET_TABLES = (
    "worksheets", "worksheet_rows", "worksheet_row_links", "worksheet_row_revisions",
)


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def test_sheet_audit_rows_show_ids_but_no_title_values_columns_or_targets(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db)
    students = add_students(db, world, [world.owner])
    owner = _client(application, world.owner, db)
    created = owner.post("/api/worksheets", json={
        "record_id": str(world.record.id), "title": "Secret grades",
        "source": {"kind": "blank"},
    }).json()
    sheet_id = created["id"]
    structure = editable_structure(students)
    structure["columns"][2]["name"] = "Private note"
    saved = owner.put(
        f"/api/worksheets/{sheet_id}/structure",
        json={key: structure[key] for key in ("columns", "groups", "totals")},
        headers={"If-Match": f'"{sheet_id}:1"'},
    )
    assert saved.status_code == 200, saved.text
    row = owner.post(f"/api/worksheets/{sheet_id}/rows", json={"cells": {
        "c1": {"record_id": str(students.alice.id)}, "c3": "confidential remark",
    }})
    assert row.status_code == 201, row.text
    rows = db.scalars(select(AuditLog).where(
        AuditLog.entity_type.in_(SHEET_TABLES), AuditLog.org_id == world.sheet.org_id,
    )).all()
    assert {entry.entity_type for entry in rows} == set(SHEET_TABLES)
    assert {entry.department_id for entry in rows} == {None}
    snapshots = " ".join(str(entry.before) + str(entry.after) for entry in rows)
    for secret in (
        "Secret grades", "Private note", "confidential remark", str(students.alice.id),
        str(world.record.id), str(students.module.id),
    ):
        assert secret not in snapshots, secret
    # The world's own sheet is audited too; the created one shows by its ID.
    sheet_rows = [entry for entry in rows if entry.entity_type == "worksheets"]
    assert sheet_id in {str(entry.entity_id) for entry in sheet_rows}
    assert any(
        entry.entity_type == "worksheet_rows" and str(entry.entity_id) == row.json()["id"]
        for entry in rows
    )
