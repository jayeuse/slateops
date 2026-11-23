"""Per-viewer sheet responses.

Every response that carries a structure goes through :func:`structure_view` (spec D14 S1):
a From another sheet column whose source the viewer cannot see keeps only its key and name.
"""

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.openview.worksheets.access import (
    WorksheetLevel,
    visible_worksheet_clause,
    worksheet_states,
)
from app.systems.openview.worksheets.models import Worksheet
from app.systems.openview.worksheets.schemas import (
    SheetHiddenSourceColumn,
    SheetPersonRef,
    SheetStructureView,
    WorksheetDetail,
    WorksheetSummary,
)
from app.systems.openview.worksheets.structure import (
    Column,
    SheetFromSheetColumn,
    WorksheetStructure,
)


def worksheet_etag(sheet: Worksheet) -> str:
    return f'"{sheet.id}:{sheet.revision}"'


def person_refs(db: Session, user_ids: Iterable[UUID]) -> dict[UUID, SheetPersonRef]:
    ids = set(user_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(User.id, User.display_name, User.username).where(User.id.in_(ids))
    ).tuples()
    return {
        user_id: SheetPersonRef(id=user_id, display_name=display_name or username)
        for user_id, display_name, username in rows
    }


def structure_view(db: Session, user: User, sheet: Worksheet) -> SheetStructureView:
    stored = WorksheetStructure.model_validate(sheet.structure)
    sources = {
        column.sheet_lookup.sourceWorksheetId
        for column in stored.columns
        if isinstance(column, SheetFromSheetColumn)
    }
    visible = set(
        db.scalars(
            select(Worksheet.id).where(
                Worksheet.id.in_(sources), visible_worksheet_clause(db, user)
            )
        ).all()
    ) if sources else set()
    columns: list[Column | SheetHiddenSourceColumn] = [
        SheetHiddenSourceColumn(
            key=column.key, name=column.name, type="sheet_lookup", state="no_access"
        )
        if isinstance(column, SheetFromSheetColumn)
        and column.sheet_lookup.sourceWorksheetId not in visible
        else column
        for column in stored.columns
    ]
    return SheetStructureView(
        structureVersion=stored.structureVersion,
        nextColumnSeq=stored.nextColumnSeq,
        columns=columns,
        groups=stored.groups,
        totals=dict(stored.totals),
    )


def _summary(
    sheet: Worksheet, owner: SheetPersonRef, present: bool, level: WorksheetLevel
) -> WorksheetSummary:
    return WorksheetSummary(
        id=sheet.id,
        record_id=sheet.record_id,
        module_id=sheet.module_id,
        title=sheet.title,
        owner=owner,
        state="private" if present else "open",
        my_level=level,
        live_row_count=sheet.live_row_count,
        revision=sheet.revision,
        updated_at=sheet.updated_at,
        is_deleted=sheet.is_deleted,
    )


def summaries(db: Session, user: User, sheets: Sequence[Worksheet]) -> list[WorksheetSummary]:
    """List items in two statements for the whole page: states and owner names."""

    states = worksheet_states(db, user, list(sheets))
    owners = person_refs(db, (sheet.owner_id for sheet in sheets))
    return [
        _summary(sheet, owners[sheet.owner_id], *states[sheet.id])
        for sheet in sheets
        if sheet.id in states
    ]


def detail(db: Session, user: User, sheet: Worksheet) -> WorksheetDetail:
    present, level = worksheet_states(db, user, [sheet])[sheet.id]
    owner = person_refs(db, [sheet.owner_id])[sheet.owner_id]
    return WorksheetDetail(
        **_summary(sheet, owner, present, level).model_dump(),
        structure=structure_view(db, user, sheet),
        etag=worksheet_etag(sheet),
        created_at=sheet.created_at,
    )
