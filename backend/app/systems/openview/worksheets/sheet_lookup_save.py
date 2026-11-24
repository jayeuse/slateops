"""Route 6 rules for From another sheet columns (spec K9, D7.3a, D7.4, D14 S1 and S3).

A new or changed column needs a source sheet the saver can see now; a hidden and a missing
source give the same answer. Its link column and the source's link column point to the
same module, and the source column exists. Across sheets, the column graph has no loop,
no chain deeper than ten steps and no expansion above 2,000 parts: each step through
another sheet counts, and the other sheets are read as stored.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.openview.worksheets import sheet_lookup_cost
from app.systems.openview.worksheets.access import load_visible_worksheet
from app.systems.openview.worksheets.expression import (
    MAX_CHAIN,
    MAX_EXPANDED_NODES,
    NUMERIC_TYPES,
    ExpressionError,
    parse_stored,
    references,
)
from app.systems.openview.worksheets.models import Worksheet
from app.systems.openview.worksheets.row_writes import error
from app.systems.openview.worksheets.schemas import SheetHiddenSourceColumn
from app.systems.openview.worksheets.structure import (
    Column,
    SheetComputedColumn,
    SheetFromSheetColumn,
    SheetLinkColumn,
    SheetLookupColumn,
    WorksheetStructure,
)
from app.systems.sandbox.fields.models import Field


def _invalid(column: Column, message: str) -> Any:
    return error(status.HTTP_422_UNPROCESSABLE_CONTENT, "sheet_lookup_invalid",
                 f"{column.name}: {message}", key=column.key)


def kept_columns(db: Session, user: User, sheet: Worksheet, old: Mapping[str, Column],
                 columns: list[Any]) -> list[Column]:
    """The request's columns with each masked From another sheet column kept as stored.

    A person who cannot see a column's source can neither change nor remove it; the owner
    can.
    """

    hidden = {
        key: stored for key, stored in old.items()
        if isinstance(stored, SheetFromSheetColumn) and user.id != sheet.owner_id
        and load_visible_worksheet(db, user, stored.sheet_lookup.sourceWorksheetId) is None
    }

    def not_visible(stored: Column) -> Any:
        return error(status.HTTP_422_UNPROCESSABLE_CONTENT, "column_not_visible",
                     f"{stored.name}: only the owner can change or remove a column whose "
                     "source you cannot see", key=stored.key)

    kept: list[Column] = []
    for column in columns:
        if isinstance(column, SheetHiddenSourceColumn):
            stored = old.get(column.key)
            if not isinstance(stored, SheetFromSheetColumn):
                raise error(status.HTTP_422_UNPROCESSABLE_CONTENT, "structure_invalid",
                            f"{column.name}: the sheet has no such column")
            kept.append(stored)
        elif column.key in hidden and column != hidden[column.key]:
            raise not_visible(hidden[column.key])  # security review R-1
        else:
            kept.append(column)
    present = {column.key for column in kept}
    for key, stored in hidden.items():
        if key not in present:
            raise not_visible(stored)
    return kept


def check_sources(db: Session, user: User, sheet: Worksheet, old: Mapping[str, Column],
                  columns: list[Column]) -> None:
    """Each new or changed From another sheet column reads a sheet the saver can see."""

    own = {column.key: column for column in columns}
    for column in columns:
        if not isinstance(column, SheetFromSheetColumn) or old.get(column.key) == column:
            continue
        options = column.sheet_lookup
        if options.sourceWorksheetId == sheet.id:
            raise _invalid(column, "choose another sheet")
        source = load_visible_worksheet(db, user, options.sourceWorksheetId)
        if source is None:  # hidden and missing alike (S1)
            raise _invalid(column, "choose a sheet you can see")
        found = {item.key: item for item in
                 WorksheetStructure.model_validate(source.structure).columns}
        if options.sourceColumnKey not in found:
            raise _invalid(column, "the source sheet has no such column")
        mine, theirs = own.get(options.linkKey), found.get(options.sourceLinkKey)
        if not (isinstance(mine, SheetLinkColumn) and isinstance(theirs, SheetLinkColumn)
                and mine.link.moduleId == theirs.link.moduleId):
            raise _invalid(column, "both link columns must point to the same module")


@dataclass(frozen=True)
class Fact:
    """What one column costs to read: its expanded parts, its chain depth, numbers."""

    size: int
    depth: int
    numeric: bool


class _Loop(Exception):
    def __init__(self, path: list[tuple[UUID, str]]) -> None:
        super().__init__("loop")
        self.path = path


class _Graph:
    def __init__(self, db: Session, sheet_id: UUID, columns: list[Column]) -> None:
        self.db, self.sheet_id = db, sheet_id
        self.columns: dict[UUID, dict[str, Column] | None] = {
            sheet_id: {column.key: column for column in columns},
        }
        self.facts: dict[tuple[UUID, str], Fact] = {}

    def structure(self, sheet_id: UUID) -> dict[str, Column] | None:
        if sheet_id not in self.columns:
            sheet = self.db.get(Worksheet, sheet_id)
            try:
                stored = (None if sheet is None or sheet.is_deleted
                          else WorksheetStructure.model_validate(sheet.structure))
            except ValidationError:
                stored = None
            self.columns[sheet_id] = (
                None if stored is None else {column.key: column for column in stored.columns}
            )
        return self.columns[sheet_id]

    def fact(self, sheet_id: UUID, key: str, path: list[tuple[UUID, str]]) -> Fact:
        node = (sheet_id, key)
        if node in path:
            raise _Loop(path[path.index(node):])
        if node in self.facts:
            return self.facts[node]
        column = (self.structure(sheet_id) or {}).get(key)
        here = [*path, node]
        if isinstance(column, SheetComputedColumn):
            tree = parse_stored(column.computed.expression)
            parts = [self.fact(sheet_id, ref, here) for ref in references(tree.node)]
            found = Fact(tree.node_count + sum(part.size - 1 for part in parts),
                         1 + max((part.depth for part in parts), default=0), True)
        elif isinstance(column, SheetFromSheetColumn):
            options = column.sheet_lookup
            source = self.fact(options.sourceWorksheetId, options.sourceColumnKey, here)
            found = Fact(source.size + 1, source.depth + 1, source.numeric)
        elif isinstance(column, SheetLookupColumn):
            field = self.db.get(Field, column.lookup.fieldId)
            found = Fact(1, 0, field is not None and field.type in NUMERIC_TYPES)
        else:
            found = Fact(1, 0, column is not None and column.type in NUMERIC_TYPES)
        self.facts[node] = found
        return found


def check_sheet_graph(db: Session, sheet_id: UUID, columns: list[Column]) -> None:
    """Loops, chain depth and expanded size across sheets; computed columns read numbers.

    ``columns`` hold their computed expressions in the stored form already.
    """

    graph = _Graph(db, sheet_id, columns)
    names = {column.key: column.name for column in columns}
    for column in columns:
        if not isinstance(column, SheetComputedColumn | SheetFromSheetColumn):
            continue
        try:
            fact = graph.fact(sheet_id, column.key, [])
        except _Loop as loop:
            named = [names[key] if sheet == sheet_id else "a column of another sheet"
                     for sheet, key in loop.path]
            raise ExpressionError(column.key, "loop", f"{column.name}: the columns "
                                  f"{', '.join(dict.fromkeys(named))} use each other") from loop
        if fact.depth > MAX_CHAIN:
            raise ExpressionError(column.key, "chain_too_deep", f"{column.name}: at most "
                                  f"{MAX_CHAIN} columns can build on each other")
        if fact.size > MAX_EXPANDED_NODES:
            raise ExpressionError(column.key, "too_large", f"{column.name}: with the columns "
                                  f"it uses, it is above {MAX_EXPANDED_NODES:,} parts")
        if isinstance(column, SheetComputedColumn):
            for ref in references(parse_stored(column.computed.expression).node):
                if not graph.fact(sheet_id, ref, []).numeric:
                    raise ExpressionError(column.key, "not_numeric",
                                          f"{column.name}: {names[ref]} does not hold numbers")
    spent: dict[str, Column] = {}
    for column in columns:
        if not isinstance(column, SheetFromSheetColumn):
            continue
        spent[column.key] = column
        if sheet_lookup_cost.read_cost(spent, graph.structure) > sheet_lookup_cost.READ_BUDGET:
            raise ExpressionError(column.key, "too_complex", f"{column.name}: the columns of "
                                  "this sheet would read too much of other sheets")
