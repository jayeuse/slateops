"""Database rules of the five sheet tables and the membership release cutoff (spec D1).

The rows are written with plain SQL as the runtime role, so each test proves what the
database itself refuses, whatever the application code later checks.
"""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.access.policy.models import Group
from app.systems.sandbox.records.models import Record
from tests.rbac.support import add_department, add_module, add_user, organization

pytestmark = pytest.mark.integration

STRUCTURE = {"structureVersion": 1, "nextColumnSeq": 1, "columns": [], "groups": [], "totals": {}}


@dataclass(frozen=True)
class _World:
    owner: UUID
    reader: UUID
    module: UUID
    record: UUID
    group: UUID


@pytest.fixture
def world(integration_db: Session) -> _World:
    db = integration_db
    module = add_module(db, add_department(db))
    record = Record(org_id=module.org_id, module_id=module.id, data={})
    group = Group(org_id=module.org_id, name=f"Sheet readers {uuid7().hex}")
    db.add_all([record, group])
    db.flush()
    return _World(add_user(db).id, add_user(db).id, module.id, record.id, group.id)


def _insert(db: Session, table: str, values: dict[str, Any]) -> UUID:
    row = {"id": uuid7(), "org_id": organization(db).id, **values}
    placeholders = [
        f"CAST(:{name} AS jsonb)" if isinstance(value, (dict, list)) else f":{name}"
        for name, value in row.items()
    ]
    db.connection().execute(
        text(f"INSERT INTO public.{table} ({', '.join(row)}) VALUES ({', '.join(placeholders)})"),
        {
            name: json.dumps(value) if isinstance(value, (dict, list)) else value
            for name, value in row.items()
        },
    )
    return row["id"]


def _refused(db: Session, constraint: str, table: str, values: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError, match=f'"{constraint}"'), db.begin_nested():
        _insert(db, table, values)


def _sheet(db: Session, world: _World, **values: Any) -> dict[str, Any]:
    return {
        "owner_id": world.owner, "title": "Grades", "structure": STRUCTURE,
        "record_id": world.record, **values,
    }


def _soft_delete(db: Session, table: str, row_id: UUID) -> None:
    db.connection().execute(
        text(f"UPDATE public.{table} SET is_deleted = true, deleted_at = now() WHERE id = :id"),
        {"id": row_id},
    )


def test_a_sheet_belongs_to_exactly_one_record_or_one_module(
    integration_db: Session, world: _World,
) -> None:
    db = integration_db
    _insert(db, "worksheets", _sheet(db, world))
    _insert(db, "worksheets", _sheet(db, world, record_id=None, module_id=world.module))
    _refused(db, "ck_worksheets_anchor", "worksheets", _sheet(db, world, module_id=world.module))
    _refused(db, "ck_worksheets_anchor", "worksheets", _sheet(db, world, record_id=None))


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"title": "   "}, "ck_worksheets_title"),
        ({"title": "x" * 201}, "ck_worksheets_title"),
        ({"revision": 0}, "ck_worksheets_revision"),
        ({"live_row_count": 10001}, "ck_worksheets_live_row_count"),
        ({"live_row_count": -1}, "ck_worksheets_live_row_count"),
        ({"data_bytes": 8388609}, "ck_worksheets_data_bytes"),
        ({"record_id": uuid7()}, "fk_worksheets_record_id_records"),
        ({"record_id": None, "module_id": uuid7()}, "fk_worksheets_module_id_modules"),
    ],
    ids=[
        "blank-title", "long-title", "zero-revision", "row-limit", "negative-rows",
        "size-limit", "unknown-record", "unknown-module",
    ],
)
def test_a_sheet_refuses_values_past_its_limits(
    integration_db: Session, world: _World, values: dict[str, Any], constraint: str,
) -> None:
    _refused(integration_db, constraint, "worksheets", _sheet(integration_db, world, **values))


def test_a_sheet_and_a_row_accept_the_values_at_their_limits(
    integration_db: Session, world: _World,
) -> None:
    db = integration_db
    sheet = _insert(db, "worksheets", _sheet(
        db, world, title="x" * 200, live_row_count=10000, data_bytes=8388608,
    ))
    _insert(db, "worksheet_rows", {
        "worksheet_id": sheet, "position": 1024, "data": {"c1": "x"}, "data_bytes": 32768,
    })


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"data": ["c1"]}, "ck_worksheet_rows_data_object"),
        ({"data_bytes": 32769}, "ck_worksheet_rows_data_bytes"),
        ({"revision": 0}, "ck_worksheet_rows_revision"),
        ({"worksheet_id": uuid7()}, "fk_worksheet_rows_worksheet_id_worksheets"),
    ],
    ids=["data-not-an-object", "row-size-limit", "zero-revision", "unknown-sheet"],
)
def test_a_row_refuses_invalid_values(
    integration_db: Session, world: _World, values: dict[str, Any], constraint: str,
) -> None:
    db = integration_db
    sheet = _insert(db, "worksheets", _sheet(db, world))
    row = {"worksheet_id": sheet, "position": 1024, "data": {}, "data_bytes": 2, **values}
    _refused(db, constraint, "worksheet_rows", row)


def test_a_share_names_one_person_or_one_group_at_view_or_edit(
    integration_db: Session, world: _World,
) -> None:
    db = integration_db
    sheet = _insert(db, "worksheets", _sheet(db, world))
    share = {"worksheet_id": sheet, "created_by": world.owner, "level": "view"}
    for subject in (
        {"subject": "user", "user_id": None, "group_id": world.group},
        {"subject": "group", "user_id": world.reader, "group_id": None},
        {"subject": "user", "user_id": world.reader, "group_id": world.group},
    ):
        _refused(db, "ck_worksheet_shares_subject", "worksheet_shares", {**share, **subject})
    _refused(db, "ck_worksheet_shares_level", "worksheet_shares", {
        **share, "subject": "user", "user_id": world.reader, "level": "manage",
    })
    _refused(db, "fk_worksheet_shares_group_id_groups", "worksheet_shares", {
        **share, "subject": "group", "group_id": uuid7(),
    })


@pytest.mark.parametrize(
    "subject",
    [{"subject": "user", "user": True}, {"subject": "group", "user": False}],
    ids=["person", "group"],
)
def test_a_sheet_has_one_live_share_per_person_or_group(
    integration_db: Session, world: _World, subject: dict[str, Any],
) -> None:
    db = integration_db
    sheet = _insert(db, "worksheets", _sheet(db, world))
    share = {
        "worksheet_id": sheet, "created_by": world.owner, "subject": subject["subject"],
        "user_id": world.reader if subject["user"] else None,
        "group_id": None if subject["user"] else world.group,
    }
    first = _insert(db, "worksheet_shares", {**share, "level": "view"})
    # The NULL of the unused subject column must not make a second live share distinct.
    _refused(db, "uq_worksheet_shares_active", "worksheet_shares", {**share, "level": "edit"})
    _soft_delete(db, "worksheet_shares", first)
    _insert(db, "worksheet_shares", {**share, "level": "edit"})


def _row(db: Session, sheet: UUID) -> UUID:
    return _insert(db, "worksheet_rows", {
        "worksheet_id": sheet, "position": 1024, "data": {}, "data_bytes": 2,
    })


def test_a_link_cell_holds_one_live_link_to_a_record_or_a_removed_mark(
    integration_db: Session, world: _World,
) -> None:
    db = integration_db
    sheet = _insert(db, "worksheets", _sheet(db, world))
    row = _row(db, sheet)
    link = {"worksheet_id": sheet, "row_id": row, "column_key": "c1"}
    _refused(db, "ck_worksheet_row_links_target", "worksheet_row_links", {
        **link, "target_record_id": None, "target_removed": False,
    })
    _refused(db, "ck_worksheet_row_links_target", "worksheet_row_links", {
        **link, "target_record_id": world.record, "target_removed": True,
    })
    _refused(db, "ck_worksheet_row_links_column_key", "worksheet_row_links", {
        **link, "column_key": "C1", "target_record_id": world.record,
    })
    first = _insert(db, "worksheet_row_links", {**link, "target_record_id": world.record})
    _refused(db, "uq_worksheet_row_links_cell", "worksheet_row_links", {
        **link, "target_record_id": None, "target_removed": True,
    })
    _soft_delete(db, "worksheet_row_links", first)
    _insert(db, "worksheet_row_links", {**link, "target_record_id": None, "target_removed": True})


def test_a_link_and_a_revision_cannot_point_at_a_row_of_another_sheet(
    integration_db: Session, world: _World,
) -> None:
    db = integration_db
    first = _insert(db, "worksheets", _sheet(db, world))
    second = _insert(db, "worksheets", _sheet(db, world))
    row_of_first = _row(db, first)
    _refused(db, "fk_worksheet_row_links_row_id_worksheet_rows", "worksheet_row_links", {
        "worksheet_id": second, "row_id": row_of_first, "column_key": "c1",
        "target_record_id": world.record,
    })
    _refused(db, "fk_worksheet_row_revisions_row_id_worksheet_rows", "worksheet_row_revisions", {
        "worksheet_id": second, "row_id": row_of_first, "revision": 1, "action": "create",
        "data": {}, "changed_keys": [],
    })


def test_a_row_revision_is_numbered_once_and_never_changed_by_the_runtime(
    integration_db: Session, world: _World,
) -> None:
    db = integration_db
    sheet = _insert(db, "worksheets", _sheet(db, world))
    row = _row(db, sheet)
    revision = {
        "worksheet_id": sheet, "row_id": row, "revision": 1, "action": "create",
        "data": {"c1": "x"}, "changed_keys": ["c1"],
    }
    first = _insert(db, "worksheet_row_revisions", revision)
    _refused(db, "uq_worksheet_row_revisions_row_revision", "worksheet_row_revisions", revision)
    _refused(db, "ck_worksheet_row_revisions_revision", "worksheet_row_revisions", {
        **revision, "revision": 0,
    })
    _refused(db, "ck_worksheet_row_revisions_action", "worksheet_row_revisions", {
        **revision, "revision": 2, "action": "move",
    })
    refused = "permission denied for table worksheet_row_revisions"
    with pytest.raises(ProgrammingError, match=refused), db.begin_nested():
        db.connection().execute(
            text("UPDATE public.worksheet_row_revisions SET action = 'update' WHERE id = :id"),
            {"id": first},
        )
    # The purge deletes history with its sheet, so DELETE stays.
    deleted = db.connection().execute(
        text("DELETE FROM public.worksheet_row_revisions WHERE id = :id"), {"id": first},
    )
    assert deleted.rowcount == 1


def test_a_membership_carries_an_optional_sheet_release_time(integration_db: Session) -> None:
    column = integration_db.connection().execute(text(
        "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'memberships' "
        "AND column_name = 'worksheets_released_at'"
    )).one()
    assert tuple(column) == ("timestamp with time zone", "YES", None)
