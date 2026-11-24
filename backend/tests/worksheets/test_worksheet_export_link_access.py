"""Route 20 rechecks the linked modules after the build (security review item 2, D9.1).

The file names the records of each link column whose module the exporter could read in the
snapshot. If that read ends during the build, the export is refused and writes no event,
even when the sheet's own module is still readable.
"""

from typing import Any

import pytest
from sqlalchemy import text
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.policy.models import Group, GroupAccess, GroupMember
from app.systems.openview.worksheets import export as sheet_export
from app.systems.openview.worksheets.export import ExportFile
from app.systems.openview.worksheets.models import Worksheet
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from tests.worksheets.export_support import ExportJourney
from tests.worksheets.export_support import committed_sheet as committed_sheet
from tests.worksheets.export_support import journey as journey

pytestmark = pytest.mark.integration


def _link_column_on_another_module(journey: ExportJourney) -> Any:
    """A Staff module that only the editor reads, and a link column of the sheet on it."""

    world = journey.world
    department_id, module_id, group_id, access_id = (uuid7() for _ in range(4))
    with world.owner_engine.begin() as connection:
        connection.execute(Department.__table__.insert().values(
            id=department_id, org_id=world.org_id, department_name="Staff",
        ))
        connection.execute(Module.__table__.insert().values(
            id=module_id, org_id=world.org_id, department_id=department_id,
            module_name="Staff",
        ))
        connection.execute(Group.__table__.insert().values(
            id=group_id, org_id=world.org_id, name="Staff readers",
        ))
        connection.execute(GroupMember.__table__.insert().values(
            id=uuid7(), org_id=world.org_id, group_id=group_id, user_id=world.editor_id,
        ))
        connection.execute(GroupAccess.__table__.insert().values(
            id=access_id, org_id=world.org_id, group_id=group_id,
            department_id=department_id, module_id=module_id, level="read",
        ))
        connection.execute(Worksheet.__table__.update().where(
            Worksheet.id == world.sheet_id,
        ).values(structure={
            "structureVersion": 1, "nextColumnSeq": 5, "groups": [], "totals": {},
            "columns": [{"key": "c3", "name": "Note", "type": "text"},
                        {"key": "c4", "name": "Colleague", "type": "link",
                         "link": {"moduleId": str(module_id)}}],
        }))
    return access_id


@pytest.mark.parametrize("format", ["csv", "template"])
def test_a_linked_module_lost_during_the_build_refuses_the_export(
    journey: ExportJourney, monkeypatch: pytest.MonkeyPatch, format: str,
) -> None:
    world = journey.world
    access_id = _link_column_on_another_module(journey)
    original = sheet_export.export_snapshot
    built: list[bool] = []

    def revoke_after_build(*args: Any, **kwargs: Any) -> ExportFile:
        result = original(*args, **kwargs)
        with world.owner_engine.begin() as connection:
            connection.execute(
                text("UPDATE public.group_access SET is_deleted = true, deleted_at = :now "
                     "WHERE id = :id"), {"now": utc_now(), "id": access_id},
            )
        built.append(True)
        return result

    monkeypatch.setattr(sheet_export, "export_snapshot", revoke_after_build)
    response = journey.export(world.editor_id, format)
    assert built == [True]
    assert response.status_code == 403, response.text
    assert b"Staff" not in response.content
    assert journey.events() == []
