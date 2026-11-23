"""From another sheet columns as SQL over one row (spec K9, D7.3a).

For each row, the source rows are those whose ``sourceLinkKey`` link points to the record
this row's ``linkKey`` link points to. The source cell is the source sheet's own projection
for the same viewer, so a computed, lookup or chained source shows what that sheet shows.
A viewer who cannot see the source sheet gets ``no_access`` in the whole column; a source
column that is gone reads ``column_removed``; two or more live matches read
``multiple_matches`` with their count. Nothing is stored (K6).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Numeric, Text, and_, case, false, func, literal, null, select, true
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, aliased

from app.systems.access.users.models import User
from app.systems.openview.worksheets.access import load_visible_worksheet
from app.systems.openview.worksheets.expression import MAX_CHAIN
from app.systems.openview.worksheets.models import WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.projection import (
    ColumnProjection,
    Link,
    RowProjection,
    blank_column,
    hidden_column,
    project_rows,
)
from app.systems.openview.worksheets.structure import (
    SheetFromSheetColumn,
    SheetLinkColumn,
    SheetSelectColumn,
    WorksheetStructure,
)


def _no_text() -> Any:
    return sql_cast(null(), Text)


def _no_value() -> Any:
    return sql_cast(null(), JSONB)


def _no_number() -> Any:
    return sql_cast(null(), Numeric)


def _removed(key: str) -> ColumnProjection:
    return ColumnProjection(
        key, literal("column_removed"), _no_value(), _no_text(), _no_text(), _no_text(),
        _no_number(), false(), false(),
    )


def project_sheet_lookup(
    db: Session, user: User, projection: RowProjection, column: SheetFromSheetColumn,
    link: Link | None, sources: frozenset[UUID],
) -> ColumnProjection:
    """The column for ``user``; joins one LATERAL that picks the matching source row."""

    key, options = column.key, column.sheet_lookup
    if link is None:  # this sheet's link column is hidden from the viewer (N4)
        return hidden_column(key)
    if options.sourceWorksheetId in sources or len(sources) >= MAX_CHAIN:
        return blank_column(key)  # a loop or a chain refused on save; never read again
    source = load_visible_worksheet(db, user, options.sourceWorksheetId)
    if source is None:
        return hidden_column(key)
    structure = WorksheetStructure.model_validate(source.structure)
    found = {item.key: item for item in structure.columns}
    target, source_link = found.get(options.sourceColumnKey), found.get(options.sourceLinkKey)
    if target is None or not isinstance(source_link, SheetLinkColumn):
        return _removed(key)
    inner = project_rows(db, user, structure, sources | {source.id})
    shown = inner.column(options.sourceColumnKey)
    # A choice shows its label: this sheet does not hold the source's options.
    value = func.to_jsonb(shown.text) if isinstance(target, SheetSelectColumn) else shown.value
    matched = aliased(WorksheetRowLink, name=f"match_{key}")
    rows = (
        select(
            WorksheetRow.id.label("row_id"), matched.target_record_id.label("target"),
            shown.state.label("state"), value.label("value"), shown.label.label("label"),
            shown.text.label("text"), shown.number.label("number"),
            shown.shown.label("shown"),
        )
        .select_from(inner.source.join(matched, and_(
            matched.org_id == WorksheetRow.org_id,
            matched.worksheet_id == WorksheetRow.worksheet_id,
            matched.row_id == WorksheetRow.id,
            matched.column_key == options.sourceLinkKey,
            matched.is_deleted.is_(False),
        )))
        .where(
            WorksheetRow.org_id == source.org_id,
            WorksheetRow.worksheet_id == source.id,
            WorksheetRow.is_deleted.is_(False),
        )
        .subquery(f"source_{key}")
    )
    pick = (
        select(rows, func.count().over().label("matches"))
        .where(rows.c.target == link.target)
        .order_by(rows.c.row_id)
        .limit(1)
        .correlate_except(rows)
        .lateral(f"from_sheet_{key}")
    )
    projection.source = projection.source.outerjoin(pick, true())
    linked = func.coalesce(link.state == "link", false())
    single = and_(linked, pick.c.matches == 1)
    many = and_(linked, pick.c.matches > 1)
    state = case((link.state == "no_access", literal("no_access")),
                 (many, literal("multiple_matches")), (single, pick.c.state),
                 else_=_no_text())
    # The source's own sort order: by number where it sorts numbers, else by its text.
    sort = (case((single, pick.c.number), else_=_no_number())
            if isinstance(shown.sort.type, Numeric)
            else func.lower(case((single, pick.c.text), else_=_no_text())))
    return ColumnProjection(
        key=key,
        state=state,
        value=case((many, func.to_jsonb(pick.c.matches)), (single, pick.c.value),
                   else_=_no_value()),
        label=case((single, pick.c.label), else_=_no_text()),
        text=case((single, pick.c.text), else_=_no_text()),
        sort=sort,
        number=case((single, pick.c.number), else_=_no_number()),
        hidden=func.coalesce(state == "no_access", false()),
        shown=func.coalesce(and_(single, pick.c.shown), false()),
    )
