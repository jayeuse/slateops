"""Route 15: the row history of a sheet, with values, as the reader may see them (H3, D5.3).

A revision stores a row's cells after the change, with each link as its record ID. The
reader sees a link as the record's name only when they can read its module now (N4): any
other link shows ``no_access`` with no ID and no name, and so does every cell of a link
column whose module they cannot read. A stored value of an unknown shape fails closed.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.access.policy.checks import module_level
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import Worksheet, WorksheetRowRevision
from app.systems.openview.worksheets.projection import link_column_hidden
from app.systems.openview.worksheets.schemas import (
    Cell,
    SheetLinkCell,
    SheetLinkTarget,
    SheetRowRevision,
    SheetStateCell,
    SheetUnlinkedCell,
    SheetValueCell,
)
from app.systems.openview.worksheets.serializers import person_refs
from app.systems.openview.worksheets.structure import SheetLinkColumn, WorksheetStructure
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.display import record_title
from app.systems.sandbox.records.models import Record

_NO_ACCESS = SheetStateCell(state="no_access")


def _link_target(value: Any) -> UUID | None:
    if isinstance(value, dict) and set(value) == {"record_id"}:
        try:
            return UUID(str(value["record_id"]))
        except ValueError:
            return None
    return None


def _targets(db: Session, user: User, ids: set[UUID]) -> dict[UUID, Cell]:
    """Each named record as the reader may see it; a missing record reads ``removed``."""

    shown: dict[UUID, Cell] = dict.fromkeys(ids, SheetStateCell(state="removed"))
    if not ids:
        return shown
    found = db.execute(
        select(Record, Module).join(Module, Module.id == Record.module_id)
        .where(Record.id.in_(ids))
    ).tuples()
    for record, module in found:
        if module_level(db, user, module.id) is None:
            shown[record.id] = _NO_ACCESS
        elif module.is_deleted or (
            record.is_deleted and record.lifecycle_close_operation_id is not None
        ):
            shown[record.id] = SheetStateCell(state="unavailable")
        elif record.is_deleted:
            shown[record.id] = SheetStateCell(state="deleted")
        else:
            shown[record.id] = SheetLinkCell(link=SheetLinkTarget(
                record_id=record.id, label=record_title(db, record, module),
            ))
    return shown


def _cell(value: Any, hidden: bool, targets: dict[UUID, Cell]) -> Cell:
    if hidden:
        return _NO_ACCESS
    target = _link_target(value)
    if target is not None:
        return targets[target]
    if isinstance(value, dict):
        unlinked = value.get("unlinked")
        if set(value) == {"unlinked"} and isinstance(unlinked, str):
            return SheetUnlinkedCell(unlinked=unlinked)
        return _NO_ACCESS
    if value is None or isinstance(value, str | int | float | bool):
        return SheetValueCell(value=value)
    return _NO_ACCESS


def history_items(
    db: Session, user: User, sheet: Worksheet, revisions: list[WorksheetRowRevision],
) -> list[SheetRowRevision]:
    """One page of revisions, masked for ``user``, in a fixed number of statements."""

    structure = WorksheetStructure.model_validate(sheet.structure)
    hidden = {
        column.key for column in structure.columns
        if isinstance(column, SheetLinkColumn)
        and link_column_hidden(db, user, column.link.moduleId)
    }
    named = {
        target for revision in revisions for key, value in revision.data.items()
        if key not in hidden and (target := _link_target(value)) is not None
    }
    targets = _targets(db, user, named)
    authors = person_refs(
        db, (revision.performed_by for revision in revisions if revision.performed_by)
    )
    return [
        SheetRowRevision(
            id=revision.id, row_id=revision.row_id, revision=revision.revision,
            action=revision.action, changed_keys=list(revision.changed_keys),
            cells={
                key: _cell(value, key in hidden, targets)
                for key, value in revision.data.items()
            },
            author=authors.get(revision.performed_by) if revision.performed_by else None,
            created_at=revision.created_at,
        )
        for revision in revisions
    ]
