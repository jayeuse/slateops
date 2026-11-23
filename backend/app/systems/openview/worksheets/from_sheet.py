"""From another sheet columns as SQL over one row (spec K9, D7.3a).

For each row, the source rows are those whose ``sourceLinkKey`` link points to the record
this row's ``linkKey`` link points to. The source cell is the source sheet's own projection
for the same viewer, pruned to the source column and the columns it reads, so a computed,
lookup or chained source shows what that sheet shows. Every nested projection spends from
the read's budget; a column past it reads ``too_complex`` (security review S-11).
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
from app.systems.openview.worksheets.sheet_lookup_cost import READ_BUDGET as _BUDGET
from app.systems.openview.worksheets.sheet_lookup_cost import Budget, pruned
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


READ_BUDGET = _BUDGET  # read at each top-level projection; tests may lower it
# Matches counted per row; a record with more source rows than this shows this count, so
# a row never pays for every duplicate in a large source sheet (S-11).
MAX_COUNTED = 100


def _state(key: str, state: str) -> ColumnProjection:
    return ColumnProjection(
        key, literal(state), _no_value(), _no_text(), _no_text(), _no_text(),
        _no_number(), false(), false(),
    )


def _removed(key: str) -> ColumnProjection:
    return _state(key, "column_removed")


def project_sheet_lookup(
    db: Session, user: User, projection: RowProjection, column: SheetFromSheetColumn,
    link: Link | None, sources: frozenset[UUID], budget: Budget,
) -> ColumnProjection:
    """The column for ``user``; joins one LATERAL that picks the matching source row."""

    key, options = column.key, column.sheet_lookup
    if link is None:  # this sheet's link column is hidden from the viewer (N4)
        return hidden_column(key)
    if options.sourceWorksheetId in sources or len(sources) >= MAX_CHAIN:
        return blank_column(key)  # a loop or a chain refused on save; never read again
    if not budget.take(1):
        return _state(key, "too_complex")
    source = load_visible_worksheet(db, user, options.sourceWorksheetId)
    if source is None:
        return hidden_column(key)
    structure = WorksheetStructure.model_validate(source.structure)
    found = {item.key: item for item in structure.columns}
    target, source_link = found.get(options.sourceColumnKey), found.get(options.sourceLinkKey)
    if target is None or not isinstance(source_link, SheetLinkColumn):
        return _removed(key)
    reads = pruned(structure, options.sourceColumnKey)
    if not budget.take(len(reads.columns)):
        return _state(key, "too_complex")
    here = f"{projection.scope}{key}"

    def matching(name: str) -> tuple[Any, Any, list[Any]]:
        """Live source rows whose link column points to this row's record."""

        found_link = aliased(WorksheetRowLink, name=f"{name}_link_{here}")
        found_row = aliased(WorksheetRow, name=f"{name}_row_{here}")
        return found_link, found_row, [
            found_link.target_record_id == link.target,
            found_link.org_id == source.org_id,
            found_link.worksheet_id == source.id,
            found_link.column_key == options.sourceLinkKey,
            found_link.is_deleted.is_(False),
            found_row.org_id == found_link.org_id,
            found_row.id == found_link.row_id,
            found_row.worksheet_id == source.id,
            found_row.is_deleted.is_(False),
        ]

    # The count reads only links, at most MAX_COUNTED of them; the value projects one
    # source row, found by its ID first, so each level of a chain costs one row (S-11).
    count_link, count_row, counting = matching("count")
    capped = (
        select(literal(1).label("one")).select_from(count_link).join(count_row, true())
        .where(*counting).limit(MAX_COUNTED)
        .correlate_except(count_link, count_row)  # this row's link, two levels out
        .lateral(f"found_{here}")
    )
    counted = (
        select(func.count().label("matches")).select_from(capped)
        .lateral(f"matches_{here}")
    )
    first_link, first_row, firsting = matching("first")
    first = (
        select(first_link.row_id.label("row_id")).select_from(first_link)
        .join(first_row, true()).where(*firsting).limit(1)
        .correlate_except(first_link, first_row)
        .lateral(f"first_{here}")
    )
    inner = project_rows(db, user, reads, sources | {source.id}, budget, budget.scope())
    shown = inner.column(options.sourceColumnKey)
    # A choice shows its label: this sheet does not hold the source's options.
    value = func.to_jsonb(shown.text) if isinstance(target, SheetSelectColumn) else shown.value
    pick = (
        select(shown.state.label("state"), value.label("value"), shown.label.label("label"),
               shown.text.label("text"), shown.number.label("number"),
               shown.shown.label("shown"))
        .select_from(inner.source)
        .where(WorksheetRow.id == first.c.row_id, WorksheetRow.org_id == source.org_id)
        .correlate_except(WorksheetRow.__table__)
        .limit(1)
        .lateral(f"from_sheet_{here}")
    )
    projection.source = (
        projection.source.outerjoin(counted, true()).outerjoin(first, true())
        .outerjoin(pick, true())
    )
    linked = func.coalesce(link.state == "link", false())
    single = and_(linked, counted.c.matches == 1)
    many = and_(linked, counted.c.matches > 1)
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
        value=case((many, func.to_jsonb(counted.c.matches)), (single, pick.c.value),
                   else_=_no_value()),
        label=case((single, pick.c.label), else_=_no_text()),
        text=case((single, pick.c.text), else_=_no_text()),
        sort=sort,
        number=case((single, pick.c.number), else_=_no_number()),
        hidden=func.coalesce(state == "no_access", false()),
        shown=func.coalesce(and_(single, pick.c.shown), false()),
    )
