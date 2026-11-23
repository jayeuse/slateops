"""My sheets, the record Sheets tab and the module sheet list (routes 1, 2, 2a; P2, P4, R6)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.users.models import User, UserStatus
from app.systems.openview.worksheets.models import Worksheet
from tests.conftest import membership_of
from tests.rbac.support import _client, add_user
from tests.worksheets.support import SheetWorld, add_sheet, share, sheet_world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _as(application: FastAPI, db: Session, person: User) -> TestClient:
    return _client(application, person, db)


def _ids(response: Any) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def _deleted(sheet: Worksheet) -> None:
    sheet.is_deleted, sheet.deleted_at = True, utc_now()


@pytest.fixture
def world(integration_db: Session) -> SheetWorld:
    return sheet_world(integration_db)


def test_my_sheets_lists_owned_and_shared_sheets_but_not_an_open_sheet_never_shared(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    # The editor's own sheet, then the editor leaves: it opens to every record reader.
    left = add_sheet(db, world.editor, record=world.record)
    membership_of(db, world.editor.id).status = UserStatus.DISABLED.value
    db.flush()
    sheet, opened = str(world.sheet.id), str(left.id)
    for person, expected in (
        (world.owner, {sheet}),
        (world.viewer, {sheet}),
        (world.group_member, {sheet}),
        (world.guest, {sheet}),
        (world.peer, set()),
        (world.manager, set()),
        (world.admin, set()),
    ):
        client = _as(application, db, person)
        assert _ids(client.get("/api/worksheets")) == expected, person.username
        tab = _ids(client.get(f"/api/records/{world.record.id}/worksheets"))
        assert tab == expected | {opened}, person.username


def test_my_sheets_deleted_only_lists_own_deleted_sheets_on_live_readable_records(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    gone = add_sheet(db, world.owner, record=world.record)
    on_module = add_sheet(db, world.owner, module=world.module)
    someone_elses = add_sheet(db, world.viewer, record=world.record)
    share(db, someone_elses, "edit", user=world.owner)
    for row in (gone, on_module, someone_elses):
        _deleted(row)
    db.flush()
    owner = _as(application, db, world.owner)
    assert _ids(owner.get("/api/worksheets", params={"deleted": "only"})) == {
        str(gone.id), str(on_module.id),
    }
    assert _ids(owner.get("/api/worksheets")) == {str(world.sheet.id)}
    assert owner.get("/api/worksheets", params={"deleted": "include"}).status_code == 422
    # The record goes: its deleted sheets cannot be restored, so they leave the list (R6).
    _deleted(world.record)
    db.flush()
    assert _ids(owner.get("/api/worksheets", params={"deleted": "only"})) == {str(on_module.id)}


def test_my_sheets_searches_and_sorts_titles(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    second = add_sheet(db, world.owner, record=world.record)
    second.title = "Attendance"
    db.flush()
    owner = _as(application, db, world.owner)
    listed = owner.get("/api/worksheets", params={"sort_by": "title"}).json()
    assert [item["title"] for item in listed["items"]] == ["Attendance", "Grades"]
    assert listed["pagination"]["total"] == 2
    found = owner.get("/api/worksheets", params={"search": "attend"}).json()["items"]
    assert [item["id"] for item in found] == [str(second.id)]
    assert found[0]["state"] == "private" and found[0]["my_level"] == "owner"
    assert found[0]["owner"] == {"id": str(world.owner.id), "display_name": world.owner.username}


def test_the_module_list_shows_visible_module_sheets_and_hides_an_unreadable_module(
    application: FastAPI, integration_db: Session,
) -> None:
    db = integration_db
    world = sheet_world(db, "module")
    path = f"/api/modules/{world.module.id}/worksheets"
    owner = _as(application, db, world.owner)
    listed = owner.get(path).json()
    assert [item["id"] for item in listed["items"]] == [str(world.sheet.id)]
    assert listed["items"][0]["module_id"] == str(world.module.id)
    assert _ids(_as(application, db, world.peer).get(path)) == set()
    stranger = _as(application, db, add_user(db))
    for listed_path in (path, f"/api/modules/{uuid7()}/worksheets"):
        hidden = stranger.get(listed_path)
        assert (hidden.status_code, hidden.json()["detail"]["code"]) == (404, "module_not_found")


def test_the_sheets_tab_hides_an_unreadable_record_like_a_missing_one(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    stranger = _as(application, integration_db, add_user(integration_db))
    for record_id in (world.record.id, uuid7()):
        hidden = stranger.get(f"/api/records/{record_id}/worksheets")
        assert (hidden.status_code, hidden.json()["detail"]["code"]) == (404, "record_not_found")


def test_my_sheets_items_name_their_anchor_sharing_group_and_deletion(
    application: FastAPI, integration_db: Session, world: SheetWorld,
) -> None:
    db = integration_db
    on_module = add_sheet(db, world.owner, module=world.module)
    gone = add_sheet(db, world.owner, record=world.record)
    _deleted(gone)
    db.flush()

    def items(person: User, **params: str) -> dict[str, dict[str, Any]]:
        listed = _as(application, db, person).get("/api/worksheets", params=params).json()
        return {item["id"]: item for item in listed["items"]}

    facts = ("anchor_title", "module_name", "shared", "access_group")
    record_title = f"Record {str(world.record.id)[:8]}"
    owner = items(world.owner)
    assert {key: owner[str(world.sheet.id)][key] for key in facts} == {
        "anchor_title": record_title, "module_name": world.module.module_name,
        "shared": True, "access_group": None,
    }
    assert {key: owner[str(on_module.id)][key] for key in facts} == {
        "anchor_title": world.module.module_name, "module_name": world.module.module_name,
        "shared": False, "access_group": None,
    }
    assert owner[str(world.sheet.id)]["deleted_at"] is None
    for person, group in ((world.viewer, None), (world.group_member, world.share_group.name)):
        item = items(person)[str(world.sheet.id)]
        assert (item["shared"], item["access_group"]) == (None, group)
    deleted = items(world.owner, deleted="only")[str(gone.id)]
    assert deleted["deleted_at"] is not None
