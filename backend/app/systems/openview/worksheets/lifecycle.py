"""Sheets in a lifecycle purge (spec D4, F1, F2, N6).

A record or module delete, close or reopen writes nothing here: the access rule reads the
anchor's state. A purge removes the sheets of the purged records and modules with their
rows, shares, links and revisions, and marks links in other sheets that point at a purged
record as removed. The planner keeps every affected row's state in the private digest, so a
sheet made after the preview refuses the purge; the impact response shows a count only.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from app.systems.openview.worksheets.models import (
    Worksheet,
    WorksheetRow,
    WorksheetRowLink,
    WorksheetRowRevision,
    WorksheetShare,
)

# Children first: the order the purge deletes in, and the plan's scope keys.
SHEET_TABLES: tuple[tuple[str, type[Any]], ...] = (
    ("worksheet_row_revisions", WorksheetRowRevision),
    ("worksheet_row_links", WorksheetRowLink),
    ("worksheet_shares", WorksheetShare),
    ("worksheet_rows", WorksheetRow),
    ("worksheets", Worksheet),
)
STRIPPED_LINKS = "worksheet_link_strips"
# The purge's lock order for sheet rows: after the records (writes lock records first), then
# shares, sheets, rows and links, as D3.3 orders a write. Revisions are insert-only (the
# runtime has no UPDATE on them, so no FOR UPDATE either); a new one needs the sheet lock.
SHEET_LOCK_MODELS: tuple[tuple[str, type[Any]], ...] = (
    ("worksheet_shares", WorksheetShare),
    ("worksheets", Worksheet),
    ("worksheet_rows", WorksheetRow),
    ("worksheet_row_links", WorksheetRowLink),
)


@dataclass(frozen=True)
class SheetPurge:
    ids: dict[str, tuple[UUID, ...]] = field(default_factory=dict)
    state: list[list[str]] = field(default_factory=list)
    count: int = 0


def _state(row: Any) -> list[str]:
    return [type(row).__tablename__, str(row.id), str(row.updated_at), str(row.is_deleted)]


def plan_sheet_purge(
    db: Session, record_ids: Collection[UUID], module_ids: Collection[UUID],
) -> SheetPurge:
    """Every sheet row a purge of these records and modules removes or changes."""

    anchors = []
    if record_ids:
        anchors.append(Worksheet.record_id.in_(record_ids))
    if module_ids:
        anchors.append(Worksheet.module_id.in_(module_ids))
    if not anchors:
        return SheetPurge()
    sheets = db.scalars(select(Worksheet).where(or_(*anchors)).order_by(Worksheet.id)).all()
    sheet_ids = [sheet.id for sheet in sheets]
    found: dict[str, list[Any]] = {"worksheets": list(sheets)}
    for table, model in SHEET_TABLES[:-1]:
        found[table] = list(db.scalars(
            select(model).where(model.worksheet_id.in_(sheet_ids)).order_by(model.id)
        ).all()) if sheet_ids else []
    # Links elsewhere, live or deleted, still hold the record key: they lose the target.
    stripped = list(db.scalars(
        select(WorksheetRowLink).where(
            WorksheetRowLink.target_record_id.in_(record_ids),
            WorksheetRowLink.worksheet_id.not_in(sheet_ids) if sheet_ids else true(),
        ).order_by(WorksheetRowLink.id)
    ).all()) if record_ids else []
    ids = {table: tuple(row.id for row in rows) for table, rows in found.items()}
    ids["worksheet_row_links"] = tuple(sorted(
        {*ids["worksheet_row_links"], *(link.id for link in stripped)}
    ))
    ids[STRIPPED_LINKS] = tuple(link.id for link in stripped)
    state = sorted(
        [*(_state(row) for rows in found.values() for row in rows),
         *(["stripped", *_state(link)] for link in stripped)]
    )
    return SheetPurge(ids=ids, state=state, count=len(sheets))


def purge_sheets(db: Session, scope_ids: dict[str, tuple[UUID, ...]]) -> None:
    """Strip links elsewhere, then delete the sheet rows one by one, children first.

    The rows were locked and re-planned under the purge's locks; a missing row is drift.
    """

    # Imported here: the lifecycle package imports this module while it loads.
    from app.systems.sandbox.lifecycle.exceptions import LifecycleUnavailable

    for link_id in scope_ids.get(STRIPPED_LINKS, ()):
        link = db.get(WorksheetRowLink, link_id)
        if link is None:
            raise LifecycleUnavailable("Lifecycle operation row is no longer available")
        link.target_record_id, link.target_removed = None, True
    db.flush()
    stripped = set(scope_ids.get(STRIPPED_LINKS, ()))
    for table, model in SHEET_TABLES:
        for row_id in scope_ids.get(table, ()):
            if row_id in stripped:
                continue
            row = db.get(model, row_id)
            if row is None:
                raise LifecycleUnavailable("Lifecycle operation row is no longer available")
            db.delete(row)
        db.flush()
