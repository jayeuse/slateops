"""The people a sheet editor can put in a person cell (route 3 of the queue; R1 rules).

Owner and Edit recipients list active members of the organization whom they can see,
themselves included; a read-only person gets 403 and a person who cannot see the sheet 404.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from tests.rbac.support import _client
from tests.worksheets.support import SheetWorld, sheet_world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def application() -> Iterator[FastAPI]:
    from app.main import create_app

    built = create_app()
    yield built
    built.dependency_overrides.clear()


def _people(application: FastAPI, db: Session, world: SheetWorld, person: User,
            q: str | None = None) -> Any:
    params = {} if q is None else {"q": q}
    return _client(application, person, db).get(
        f"/api/worksheets/{world.sheet.id}/people", params=params,
    )


def test_an_editor_lists_the_people_they_can_see_and_searches_by_name(
    application: FastAPI, integration_db: Session,
) -> None:
    world = sheet_world(integration_db)
    world.viewer.display_name, world.outsider.display_name = "Vera Viewer", "Otto Outside"
    integration_db.flush()
    listed = _people(application, integration_db, world, world.editor)
    assert listed.status_code == 200, listed.text
    assert listed.headers["cache-control"] == "no-store"
    ids = {person["id"] for person in listed.json()["people"]}
    assert {str(world.owner.id), str(world.editor.id), str(world.viewer.id)} <= ids
    assert str(world.outsider.id) not in ids  # shares no group or module with the editor
    found = _people(application, integration_db, world, world.owner, "vera").json()["people"]
    assert found == [{"id": str(world.viewer.id), "display_name": "Vera Viewer"}]


def test_read_only_people_are_refused_and_others_do_not_find_the_sheet(
    application: FastAPI, integration_db: Session,
) -> None:
    world = sheet_world(integration_db)
    for person, status, code in (
        (world.viewer, 403, "worksheet_read_only"),
        (world.guest, 403, "worksheet_read_only"),
        (world.peer, 404, "worksheet_not_found"),
        (world.admin, 404, "worksheet_not_found"),
    ):
        response = _people(application, integration_db, world, person)
        assert (response.status_code, response.json()["detail"]["code"]) == (status, code)
