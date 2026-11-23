"""Route 20 template export: structure only, masked per exporter (X5, D9.2, D14 S1).

SH-32: valid versioned JSON with no rows, shares or IDs. SH-70 (template part): a View
recipient who cannot read the linked module gets no module, department or field name; a
From another sheet column is always text; the owner gets every name.
"""

import json
import re
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.openview.worksheets.export import build_export
from app.systems.openview.worksheets.template import SheetTemplate
from tests.worksheets.support import (
    SheetWorld,
    Students,
    add_sheet,
    add_students,
    editable_structure,
    sheet_world,
)

pytestmark = pytest.mark.integration
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
TEXT = {"type": "text"}


@pytest.fixture
def world(integration_db: Session) -> tuple[SheetWorld, Students]:
    """Every column kind, a group, totals and a From another sheet column the owner sees."""

    db = integration_db
    found = sheet_world(db)
    students = add_students(db, found, [found.owner, found.editor])
    source = add_sheet(db, found.owner, record=found.record)
    structure: dict[str, Any] = editable_structure(students)
    structure["columns"][1]["name"] = "Student name"
    structure["columns"].append({
        "key": "ca", "name": "Grade elsewhere", "type": "sheet_lookup",
        "sheet_lookup": {"sourceWorksheetId": str(source.id), "sourceColumnKey": "c3",
                         "linkKey": "c1", "sourceLinkKey": "c1"},
    })
    structure["nextColumnSeq"] = 11
    structure["groups"] = [{"name": "Scores", "keys": ["c4", "c5"]}]
    structure["totals"] = {"c1": "count", "c2": "sum", "c4": "sum", "ca": "max"}
    found.sheet.structure = structure
    db.flush()
    return found, students


def _template(db: Session, person: Any, sheet_id: Any) -> tuple[bytes, dict[str, Any]]:
    exported = build_export(db, reader_id=person.id, worksheet_id=sheet_id, format="template")
    document = json.loads(exported.content)
    SheetTemplate.model_validate(document)  # the file reads back as a version 1 template
    assert exported.row_count == 0
    assert exported.column_count == len(document["columns"])
    assert exported.filename == "grades-template.json"
    return exported.content, document


def _columns(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {column["key"]: column for column in document["columns"]}


def test_the_owner_gets_names_for_linked_modules_and_fields_and_no_ids(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, students = world
    content, document = _template(integration_db, found.owner, found.sheet.id)
    assert set(document) == {"kind", "schemaVersion", "title", "columns", "groups", "totals"}
    assert (document["kind"], document["schemaVersion"], document["title"]) == (
        "slateops-worksheet-template", 1, "Grades",
    )
    columns = _columns(document)
    assert columns["c1"] == {"key": "c1", "name": "Student", "type": "link", "link": {
        "moduleName": "Student List", "departmentName": found.department.department_name,
    }}
    assert columns["c2"] == {"key": "c2", "name": "Student name", "type": "lookup",
                             "lookup": {"linkKey": "c1", "fieldName": "Name"}}
    assert columns["c6"]["select"]["options"] == [{"id": "o1", "label": "Pass"},
                                                  {"id": "o2", "label": "Fail"}]
    assert columns["ca"] == {"key": "ca", "name": "Grade elsewhere", **TEXT}
    assert document["groups"] == [{"name": "Scores", "keys": ["c4", "c5"]}]
    assert document["totals"] == {"c1": "count", "c2": "sum", "c4": "sum"}
    assert not UUID_TEXT.search(content.decode())
    for identifier in (found.sheet.org_id, students.module.id, students.name.id,
                       found.record.id, found.owner.id, found.viewer.id, found.sheet.id):
        assert str(identifier) not in content.decode()


def test_a_view_recipient_without_the_linked_module_gets_text_columns_and_no_names(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, _students = world
    content, document = _template(integration_db, found.viewer, found.sheet.id)
    columns = _columns(document)
    for key, name in (("c1", "Student"), ("c2", "Student name"), ("ca", "Grade elsewhere")):
        assert columns[key] == {"key": key, "name": name, **TEXT}
    assert document["totals"] == {"c1": "count", "c4": "sum"}  # no sum on a text column
    for leaked in ("Student List", found.department.department_name, "moduleName",
                   "fieldName", "sheet_lookup"):
        assert leaked not in content.decode()
    assert not UUID_TEXT.search(content.decode())


def test_a_lookup_of_a_removed_field_exports_as_text(
    integration_db: Session, world: tuple[SheetWorld, Students],
) -> None:
    found, students = world
    students.name.is_deleted, students.name.deleted_at = True, utc_now()
    integration_db.flush()
    _content, document = _template(integration_db, found.owner, found.sheet.id)
    assert _columns(document)["c2"] == {"key": "c2", "name": "Student name", **TEXT}
    assert _columns(document)["c1"]["type"] == "link"
