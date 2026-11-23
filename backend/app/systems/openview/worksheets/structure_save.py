"""Route 6: saving a sheet's columns, groups and totals (K1, K2, F4, F6).

The rules the stored model cannot check need the database: a new or changed link column
targets a live module the saver can read; a new or changed lookup reads a live field of its
link column's module; a column with values keeps its type; a key is never used twice
(``nextColumnSeq`` only grows). Computed and From another sheet columns are saved by B10
and B11, which compile and check them; until then a new or changed one is refused.
"""

import re
from typing import Any
from uuid import UUID

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.policy.checks import module_level
from app.systems.access.users.models import User
from app.systems.openview.worksheets.cells import worksheet_limit
from app.systems.openview.worksheets.models import Worksheet, WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.row_writes import (
    authorize_edit,
    error,
    lock_and_recheck,
)
from app.systems.openview.worksheets.schemas import SheetStructureUpdate
from app.systems.openview.worksheets.serializers import worksheet_etag
from app.systems.openview.worksheets.structure import (
    MAX_COLUMNS,
    Column,
    SheetLinkColumn,
    SheetLookupColumn,
    WorksheetStructure,
)
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.modules.models import Module

_SEQUENCED_KEY = re.compile(r"^c([0-9]{1,8})$")
_LATER_UNITS = frozenset({"computed", "sheet_lookup"})


def _invalid(code: str, message: str) -> Any:
    return error(status.HTTP_422_UNPROCESSABLE_CONTENT, code, message)


def _next_sequence(old: WorksheetStructure, columns: list[Column]) -> int:
    """The new ``nextColumnSeq``; a new key must be ``c<n>`` with ``n`` not yet issued."""

    old_keys = {column.key for column in old.columns}
    sequence = old.nextColumnSeq
    for column in columns:
        if column.key in old_keys:
            continue
        found = _SEQUENCED_KEY.fullmatch(column.key)
        if found is None or int(found.group(1)) < old.nextColumnSeq:
            raise _invalid(
                "column_key_reused",
                f"A new column needs a key from c{old.nextColumnSeq} on; keys are never reused",
            )
        sequence = max(sequence, int(found.group(1)) + 1)
    return sequence


def _check_links(db: Session, user: User, old: dict[str, Column], columns: list[Column]) -> None:
    modules = {
        column.key: column.link.moduleId for column in columns
        if isinstance(column, SheetLinkColumn)
    }
    for column in columns:
        previous = old.get(column.key)
        changed = previous is None or previous != column
        if column.type in _LATER_UNITS and changed:
            raise _invalid("column_type_unavailable",
                           f"{column.name}: this column type is not available yet")
        if isinstance(column, SheetLinkColumn) and changed:
            module = db.get(Module, column.link.moduleId)
            if (module is None or module.is_deleted
                    or module_level(db, user, column.link.moduleId) is None):
                raise _invalid("link_module_invalid",
                               f"{column.name}: choose a module you can read")
        if isinstance(column, SheetLookupColumn):
            target = modules.get(column.lookup.linkKey)
            link_changed = target != _old_module(old, column.lookup.linkKey)
            if changed or link_changed:
                field = db.get(Field, column.lookup.fieldId)
                if (field is None or field.is_deleted or field.module_id != target
                        or FieldType(field.type) is FieldType.RELATIONSHIP
                        or module_level(db, user, field.module_id) is None):
                    raise _invalid("lookup_field_invalid",
                                   f"{column.name}: choose a field of the linked module")


def _old_module(old: dict[str, Column], key: str) -> UUID | None:
    column = old.get(key)
    return column.link.moduleId if isinstance(column, SheetLinkColumn) else None


def _has_values(db: Session, sheet: Worksheet, key: str) -> bool:
    live = [WorksheetRow.worksheet_id == sheet.id, WorksheetRow.is_deleted.is_(False)]
    value = WorksheetRow.data.op("->")(key)
    stored = exists(select(WorksheetRow.id).where(
        *live, func.coalesce(func.jsonb_typeof(value), "null") != "null",
    ))
    linked = exists(select(WorksheetRowLink.id).join(
        WorksheetRow, WorksheetRow.id == WorksheetRowLink.row_id,
    ).where(
        *live, WorksheetRowLink.column_key == key, WorksheetRowLink.is_deleted.is_(False),
    ))
    return bool(db.scalar(select(stored | linked)))


def _drop_removed_links(
    db: Session, sheet: Worksheet, before: list[Column], after: list[Column],
) -> None:
    """A removed link column takes its links along, so nothing reads them as live."""

    kept = {column.key for column in after}
    removed = [
        column.key for column in before
        if isinstance(column, SheetLinkColumn) and column.key not in kept
    ]
    if not removed:
        return
    for link in db.scalars(select(WorksheetRowLink).where(
        WorksheetRowLink.worksheet_id == sheet.id,
        WorksheetRowLink.column_key.in_(removed),
        WorksheetRowLink.is_deleted.is_(False),
    )):
        link.is_deleted, link.deleted_at = True, utc_now()


def save_structure(
    db: Session, user: User, worksheet_id: UUID, payload: SheetStructureUpdate,
    if_match: str | None,
) -> Worksheet:
    sheet = authorize_edit(db, user, worksheet_id)
    if if_match is None:
        raise error(status.HTTP_428_PRECONDITION_REQUIRED, "precondition_required",
                    "If-Match is required")
    sheet = lock_and_recheck(db, user, sheet, set())
    if if_match != worksheet_etag(sheet):
        raise error(status.HTTP_412_PRECONDITION_FAILED, "worksheet_changed",
                    "The sheet changed; reload it")
    if len(payload.columns) > MAX_COLUMNS:
        raise worksheet_limit("columns", MAX_COLUMNS, "A sheet holds at most 100 columns")
    old = WorksheetStructure.model_validate(sheet.structure)
    old_columns = {column.key: column for column in old.columns}
    sequence = _next_sequence(old, payload.columns)
    _check_links(db, user, old_columns, payload.columns)
    try:
        structure = WorksheetStructure.model_validate({
            "structureVersion": 1, "nextColumnSeq": sequence,
            "columns": [column.model_dump(mode="json") for column in payload.columns],
            "groups": [group.model_dump(mode="json") for group in payload.groups],
            "totals": payload.totals,
        })
    except ValidationError as failure:
        message = "; ".join(str(item["msg"]) for item in failure.errors())
        raise _invalid("structure_invalid", message) from failure
    for column in structure.columns:
        previous = old_columns.get(column.key)
        retargeted = (
            isinstance(previous, SheetLinkColumn) and isinstance(column, SheetLinkColumn)
            and previous.link.moduleId != column.link.moduleId
        )
        if previous is not None and (previous.type != column.type or retargeted) and (
            _has_values(db, sheet, column.key)
        ):
            raise error(status.HTTP_409_CONFLICT, "column_has_values",
                        f"{column.name} has values; clear them before changing it")
    _drop_removed_links(db, sheet, old.columns, structure.columns)
    # A new dict: `structure` is plain JSONB, so only a new value marks it changed.
    sheet.structure = structure.model_dump(mode="json")
    sheet.revision += 1
    return sheet
