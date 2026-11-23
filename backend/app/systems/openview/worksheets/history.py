"""Route 15: the row history of a sheet, with values, as the reader may see them (H3, D5.3).

A revision stores a row's cells after the change, with each link as its record ID. The
reader sees a link as the record's name only when they can read its module now (N4): any
other link shows ``no_access`` with no ID and no name. A link column whose module they
cannot read shows ``no_access`` in every revision, whether a value was there or not, and
is never named as changed. Unlinked text shows only under a link column the reader sees
now. An author is named only when the reader can see that person. A stored value of an
unknown shape fails closed.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.access.policy.checks import module_level
from app.systems.access.users.models import User
from app.systems.access.users.person_visibility import visible_person_ids
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


def _cell(value: Any, linked: bool, targets: dict[UUID, Cell]) -> Cell:
    """One stored value; ``linked`` says the key is a link column the reader sees now."""

    target = _link_target(value)
    if target is not None:
        return targets[target]
    if isinstance(value, dict):
        unlinked = value.get("unlinked")
        if linked and set(value) == {"unlinked"} and isinstance(unlinked, str):
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
    links = {column.key: column.link.moduleId for column in structure.columns
             if isinstance(column, SheetLinkColumn)}
    hidden = {key for key, module_id in links.items()
              if link_column_hidden(db, user, module_id)}
    seen = set(links) - hidden
    named = {
        target for revision in revisions for key, value in revision.data.items()
        if key not in hidden and (target := _link_target(value)) is not None
    }
    targets = _targets(db, user, named)
    named = {revision.performed_by for revision in revisions if revision.performed_by}
    visible = visible_person_ids(db, user, named) | ({sheet.owner_id} & named)
    authors = person_refs(db, visible)
    return [
        SheetRowRevision(
            id=revision.id, row_id=revision.row_id, revision=revision.revision,
            action=revision.action,
            changed_keys=[key for key in revision.changed_keys if key not in hidden],
            cells={
                **{key: _cell(value, key in seen, targets)
                   for key, value in revision.data.items() if key not in hidden},
                **dict.fromkeys(sorted(hidden), _NO_ACCESS),
            },
            author=authors.get(revision.performed_by) if revision.performed_by else None,
            created_at=revision.created_at,
        )
        for revision in revisions
    ]
