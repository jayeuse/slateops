"""Route 15: the row history of a sheet (H3, D5.3, N4; SH-46).

Anyone who can see the sheet reads each row change with its values, author and time; a
person who cannot see it gets the sheet's 404. A link shows the record's name only to a
reader of its module; anyone else sees No access with no ID and no name.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.systems.manage.audit.context import set_audit_actor
from tests.rbac.support import _client
from tests.worksheets.support import (
    SheetWorld,
    Students,
    add_sheet,
    add_students,
    editable_structure,
    sheet_world,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Any:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


class History:
    def __init__(self, application: FastAPI, db: Session, world: SheetWorld,
                 students: Students) -> None:
        self.application, self.db, self.world, self.students = application, db, world, students
        self.rows = f"/api/worksheets/{world.sheet.id}/rows"

    def _as(self, person: Any) -> Any:
        set_audit_actor(self.db, person.id)  # the real auth dependency names the author
        return _client(self.application, person, self.db)

    def write(self) -> str:
        """A row created by the owner, changed by the editor, then deleted by the owner."""

        owner, editor = self.world.owner, self.world.editor
        created = self._as(owner).post(self.rows, json={"cells": {
            "c1": {"record_id": str(self.students.alice.id)}, "c3": "first",
        }})
        assert created.status_code == 201, created.text
        row = created.json()
        changed = self._as(editor).patch(
            f"{self.rows}/{row['id']}",
            json={"cells": {"c3": {"value": "second", "expected": {"value": "first"}}}},
        )
        assert changed.status_code == 200, changed.text
        deleted = self._as(owner).delete(
            f"{self.rows}/{row['id']}", headers={"If-Match": changed.json()["etag"]},
        )
        assert deleted.status_code == 204, deleted.text
        return str(row["id"])

    def read(self, person: Any, **params: Any) -> Any:
        return _client(self.application, person, self.db).get(
            f"/api/worksheets/{self.world.sheet.id}/history", params=params,
        )


@pytest.fixture
def history(application: FastAPI, integration_db: Session) -> History:
    world = sheet_world(integration_db)
    world.owner.display_name, world.editor.display_name = "Olive Owner", "Eddie Editor"
    students = add_students(integration_db, world, [world.owner, world.editor])
    world.sheet.structure = editable_structure(students)
    integration_db.flush()
    return History(application, integration_db, world, students)


def test_a_reader_sees_each_change_with_values_author_and_time_newest_first(
    history: History,
) -> None:
    row_id = history.write()
    response = history.read(history.world.viewer)  # a View recipient can read history
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    items = response.json()["items"]
    assert [(item["action"], item["revision"], item["author"]["display_name"])
            for item in items] == [
        ("delete", 3, "Olive Owner"), ("update", 2, "Eddie Editor"), ("create", 1, "Olive Owner"),
    ]
    assert {item["row_id"] for item in items} == {row_id}
    assert [item["changed_keys"] for item in items] == [[], ["c3"], ["c1", "c3"]]
    assert items[1]["cells"]["c3"] == {"value": "second"}
    assert all(item["created_at"] for item in items)
    assert response.json()["pagination"]["total"] == 3


def test_a_link_shows_its_name_only_to_a_reader_of_its_module(history: History) -> None:
    history.write()
    alice = history.students.alice
    owner = history.read(history.world.owner).json()["items"]
    assert owner[-1]["cells"]["c1"] == {"link": {"record_id": str(alice.id), "label": "Alice"}}
    viewer = history.read(history.world.viewer)
    assert [item["cells"]["c1"] for item in viewer.json()["items"]] == [
        {"state": "no_access"},
    ] * 3
    assert str(alice.id) not in viewer.text and "Alice" not in viewer.text


def test_a_link_of_a_removed_column_still_hides_an_unreadable_record(
    integration_db: Session, history: History,
) -> None:
    history.write()
    structure = dict(history.world.sheet.structure)
    structure["columns"] = [column for column in structure["columns"]
                            if column["key"] not in {"c1", "c2"}]
    history.world.sheet.structure = structure
    integration_db.flush()
    viewer = history.read(history.world.viewer)
    assert viewer.json()["items"][-1]["cells"]["c1"] == {"state": "no_access"}
    assert str(history.students.alice.id) not in viewer.text
    owner = history.read(history.world.owner).json()["items"]
    assert owner[-1]["cells"]["c1"]["link"]["label"] == "Alice"


def test_a_person_who_cannot_see_the_sheet_gets_not_found(history: History) -> None:
    history.write()
    for person in (history.world.peer, history.world.admin, history.world.outsider):
        response = history.read(person)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "worksheet_not_found"


def test_the_row_filter_keeps_one_row_and_never_reaches_another_sheet(
    integration_db: Session, application: FastAPI, history: History,
) -> None:
    row_id = history.write()
    other = add_sheet(integration_db, history.world.owner, record=history.world.record)
    other.structure = dict(history.world.sheet.structure)
    integration_db.flush()
    created = _client(application, history.world.owner, integration_db).post(
        f"/api/worksheets/{other.id}/rows", json={"cells": {"c3": "elsewhere"}},
    )
    assert created.status_code == 201, created.text
    mine = history.read(history.world.owner, row_id=row_id).json()
    assert {item["row_id"] for item in mine["items"]} == {row_id}
    elsewhere = history.read(history.world.owner, row_id=created.json()["id"]).json()
    assert elsewhere["items"] == [] and elsewhere["pagination"]["total"] == 0
    paged = history.read(history.world.owner, limit=1, offset=1).json()
    assert [item["action"] for item in paged["items"]] == ["update"]
    assert paged["pagination"]["has_more"] is True
