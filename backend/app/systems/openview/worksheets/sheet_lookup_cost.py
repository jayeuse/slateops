"""What a From another sheet column reads, and the budget of one read (security review S-11).

A From another sheet column needs only the source column it shows and the columns that
column reads (its closure): a lookup needs its link column, a computed column its
operands, a From another sheet column its link column. One read of a sheet spends from one
budget: one unit per source sheet it opens and one per source column it projects. Route 6
refuses a structure whose reads could cost more than the budget; a read that runs out
anyway marks the rest ``too_complex``.
"""

from collections.abc import Callable, Mapping
from uuid import UUID

from app.systems.openview.worksheets.expression import ExpressionError, parse_stored, references
from app.systems.openview.worksheets.structure import (
    Column,
    SheetComputedColumn,
    SheetFromSheetColumn,
    SheetLookupColumn,
    WorksheetStructure,
)

# Measured on 2026-11-24 as the runtime role (RLS on), 10,000-row sheets with fresh
# statistics, load about 4: a sheet that spends the whole budget (20 columns each reading
# a computed source column, or 12 columns three sheets deep) answers route 9 with a count
# in 2 ms, a page in 67 ms, totals in 1.6 s and a page sorted by such a column in 3.2 s;
# the statement timeout is 15 s. At 200 units the sorted page took 6.3 s.
READ_BUDGET = 100


class Budget:
    """The units one read may still spend across every nested source projection."""

    def __init__(self, units: int) -> None:
        self.units = units
        self.scopes = 0

    def scope(self) -> str:
        """A new alias prefix for one nested source projection."""

        self.scopes += 1
        return f"s{self.scopes}_"

    def take(self, units: int) -> bool:
        if units > self.units:
            self.units = 0
            return False
        self.units -= units
        return True


def _needs(column: Column) -> list[str]:
    if isinstance(column, SheetLookupColumn):
        return [column.lookup.linkKey]
    if isinstance(column, SheetFromSheetColumn):
        return [column.sheet_lookup.linkKey]
    if isinstance(column, SheetComputedColumn):
        try:
            return references(parse_stored(column.computed.expression).node)
        except ExpressionError:
            return []
    return []


def closure(columns: Mapping[str, Column], key: str) -> set[str]:
    """``key`` and every column it reads, directly or through others."""

    found: set[str] = set()
    pending = [key]
    while pending:
        current = pending.pop()
        column = columns.get(current)
        if current in found or column is None:
            continue
        found.add(current)
        pending.extend(_needs(column))
    return found


def pruned(structure: WorksheetStructure, key: str) -> WorksheetStructure:
    """The structure with only ``key`` and its closure; no groups and no totals."""

    keep = closure({column.key: column for column in structure.columns}, key)
    return WorksheetStructure.model_validate({
        "structureVersion": 1, "nextColumnSeq": structure.nextColumnSeq, "groups": [],
        "totals": {},
        "columns": [column.model_dump(mode="json") for column in structure.columns
                    if column.key in keep],
    })


def read_cost(columns: Mapping[str, Column],
              structure_of: Callable[[UUID], Mapping[str, Column] | None],
              depth: int = 0) -> int:
    """The units a read of these columns can spend at most (route 6, S-11)."""

    total = 0
    for column in columns.values():
        if not isinstance(column, SheetFromSheetColumn) or depth > 10:
            continue
        total += 1
        source = structure_of(column.sheet_lookup.sourceWorksheetId)
        if source is None:
            continue
        keep = closure(source, column.sheet_lookup.sourceColumnKey)
        total += len(keep)
        total += read_cost({key: source[key] for key in keep if key in source},
                           structure_of, depth + 1)
        if total > READ_BUDGET:
            break  # enough to refuse
    return total
