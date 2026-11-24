"""Sheet actions leave records alone (C2, H4, P8; SH-5, SH-51).

Every S1 sheet action (create, rename, columns, rows with a link, share, delete) runs
through its route on a sheet anchored on a record and linking another, and so do the S2
actions (an import batch, Make a copy, New sheet from this structure); the export runs
through its builder and event writer, as route 20 does after its snapshot. Neither
record changes: not its stored columns, relationship links, files, audit rows or History
tab, and the record list of each module returns the same page and total.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.systems.manage.audit.models import AuditLog
from app.systems.openview.worksheets.export import build_export, commit_export_event
from app.systems.platform.files.models import File
from app.systems.sandbox.records.models import Record
from app.systems.sandbox.relationships.models import RelationshipEdge
from tests.rbac.support import _client
from tests.worksheets.support import Students, add_students, editable_structure, sheet_world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Any:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _record_facts(db: Session, application: FastAPI, person: Any, record: Record) -> Any:
    db.refresh(record)
    columns = {column.key: getattr(record, column.key) for column in Record.__table__.columns}
    edges = db.scalar(select(func.count()).select_from(RelationshipEdge).where(or_(
        RelationshipEdge.source_record_id == record.id,
        RelationshipEdge.target_record_id == record.id,
    )))
    files = db.scalar(select(func.count()).select_from(File).where(File.record_id == record.id))
    audit = db.scalars(select(AuditLog.id).where(AuditLog.entity_id == record.id)).all()
    history = _client(application, person, db).get(
        "/api/audit-logs", params={"entity_id": str(record.id)},
    )
    listed = _client(application, person, db).post(
        "/api/records/query", json={"module_id": str(record.module_id), "definition": {}},
    )
    assert history.status_code == listed.status_code == 200, (history.text, listed.text)
    return columns, edges, files, sorted(audit), history.json(), listed.json()


def _module_facts(
    db: Session, application: FastAPI, reader: Any, admin: Any, students: Students,
) -> Any:
    """SH-51: what Charts, Reports and Dashboards (aggregate) and record import (preview)
    read from the linked module. The record export reads its own snapshot connection, which
    cannot see this test's savepoint; test_worksheet_export.py owns it on committed rows."""

    module_id = str(students.module.id)
    name = {"field_id": str(students.name.id), "expected_type": "text"}
    aggregate = _client(application, reader, db).post("/api/records/aggregate-query", json={
        "mode": "groups", "module_id": module_id, "definition": {}, "dimension": name,
    })
    preview = _client(application, admin, db).post("/api/records/import", json={
        "mode": "preview", "module_id": module_id, "headers": ["Name"],
        "mapping": [{"column_index": 0, "field_id": str(students.name.id)}],
        "rows": [{"row_number": 2, "cells": ["Carol"]}], "defaults": {},
    })
    assert aggregate.status_code == preview.status_code == 200, (aggregate.text, preview.text)
    return aggregate.json(), preview.json()


def test_every_sheet_action_leaves_the_anchor_and_linked_records_unchanged(
    integration_db: Session, application: FastAPI,
) -> None:
    db = integration_db
    world = sheet_world(db)
    students: Students = add_students(db, world, [world.owner, world.viewer])
    db.commit()
    owner = world.owner

    def facts() -> list[Any]:
        return [*(_record_facts(db, application, owner, record)
                  for record in (world.record, students.alice)),
                _module_facts(db, application, owner, world.admin, students)]

    before = facts()

    def call(method: str, path: str, **kwargs: Any) -> Any:
        response = _client(application, owner, db).request(method, f"/api{path}", **kwargs)
        assert response.status_code < 300, (method, path, response.text)
        return response

    created = call("POST", "/worksheets", json={
        "record_id": str(world.record.id), "title": "Class", "source": {"kind": "blank"},
    })
    sheet = f"/worksheets/{created.json()['id']}"
    renamed = call("PATCH", sheet, json={"title": "Class 1"},
                   headers={"If-Match": created.headers["ETag"]})
    structure = editable_structure(students)
    saved = call("PUT", f"{sheet}/structure", json={
        "columns": structure["columns"], "groups": [], "totals": {"c4": "sum"},
    }, headers={"If-Match": renamed.headers["ETag"]})
    row = call("POST", f"{sheet}/rows", json={"cells": {
        "c1": {"record_id": str(students.alice.id)}, "c3": "note", "c4": 3,
    }}).json()
    call("PATCH", f"{sheet}/rows/{row['id']}",
         json={"cells": {"c4": {"value": 4, "expected": {"value": 3}}}})
    call("POST", f"{sheet}/shares",
         json={"subject": "user", "user_id": str(world.viewer.id), "level": "view"})
    sheet_id = created.json()["id"]
    for format in ("csv", "xlsx", "template"):
        exported = build_export(db, reader_id=owner.id, worksheet_id=sheet_id, format=format)
        commit_export_event(db, owner.id, sheet_id, format, exported)
    # S2 adds import (route 14 in import mode) and the copy sources (SH-5).
    call("POST", f"{sheet}/rows/batch", json={
        "structure_revision": saved.json()["revision"], "invalid_cells": "empty",
        "creates": [{"cells": {"c1": {"record_id": str(students.alice.id)}, "c4": 5}}],
    })
    for kind in ("copy", "structure"):
        call("POST", "/worksheets", json={
            "record_id": str(world.record.id), "title": kind,
            "source": {"kind": kind, "worksheet_id": sheet_id},
        })
    assert facts() == before  # with a live sheet, a link, a share and exports (SH-51)
    current = call("GET", f"{sheet}/rows/{row['id']}")
    call("DELETE", f"{sheet}/rows/{row['id']}", headers={"If-Match": current.headers["ETag"]})
    call("DELETE", sheet, headers={"If-Match": call("GET", sheet).headers["ETag"]})
    assert saved.json()["structure"]["totals"] == {"c4": "sum"}
    assert facts() == before
