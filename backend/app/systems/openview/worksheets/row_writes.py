"""Row writes: create, update, delete and batch (routes 10, 12, 13, 14).

Every write follows D3.3: the 404 and level checks, the locks (owner, records, shares,
sheet, rows), the same checks again with fresh reads (R4), then the change. A changed cell
names the cell as the person saw it; the server compares it with the person's masked cell
now (D14 R2), so a cell the person sees as No access is refused before any comparison and
its value is never revealed by the answer.
"""

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session, object_session

from app.core.base_model import utc_now
from app.systems.access.policy.checks import module_level
from app.systems.access.policy.transaction_access import forget_access
from app.systems.access.users.models import User
from app.systems.access.users.person_visibility import visible_person_ids
from app.systems.manage.licensing.limits import require_sheet_rows
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.access import load_visible_worksheet, worksheet_level
from app.systems.openview.worksheets.cells import (
    READ_ONLY_TYPES,
    LinkValue,
    UnlinkedValue,
    cell_error,
    check_row_size,
    convert_cell,
    worksheet_limit,
)
from app.systems.openview.worksheets.locking import lock_for_write, lock_rows
from app.systems.openview.worksheets.models import (
    Worksheet,
    WorksheetRow,
    WorksheetRowLink,
    WorksheetRowRevision,
)
from app.systems.openview.worksheets.projection import link_column_hidden
from app.systems.openview.worksheets.query import read_rows
from app.systems.openview.worksheets.schemas import (
    SheetCellChange,
    SheetLinkCell,
    SheetRow,
    SheetRowBatchUpdate,
    SheetRowCreate,
    SheetStateCell,
    SheetUnlinkedCell,
    SheetValueCell,
)
from app.systems.openview.worksheets.serializers import person_refs
from app.systems.openview.worksheets.structure import (
    MAX_ROWS,
    MAX_SHEET_BYTES,
    Column,
    SheetLinkColumn,
    WorksheetStructure,
)
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record

GAP = 1024
Conflict = Literal["cell_changed", "row_changed"]


def error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message, **extra})


def _not_found() -> HTTPException:
    return error(status.HTTP_404_NOT_FOUND, "worksheet_not_found", "Sheet not found")


def row_not_found() -> HTTPException:
    return error(status.HTTP_404_NOT_FOUND, "worksheet_row_not_found", "Row not found")


def authorize_edit(db: Session, user: User, worksheet_id: UUID) -> Worksheet:
    """The sheet for an owner or Edit recipient: 404 when hidden, 403 when read-only."""

    sheet = load_visible_worksheet(db, user, worksheet_id)
    if sheet is None:
        raise _not_found()
    if worksheet_level(db, user, sheet) not in {"owner", "edit"}:
        raise error(
            status.HTTP_403_FORBIDDEN, "worksheet_read_only", "You can only read this sheet"
        )
    return sheet


def lock_and_recheck(
    db: Session, user: User, sheet: Worksheet, record_ids: set[UUID],
) -> Worksheet:
    locked = lock_for_write(db, sheet, user.id, record_ids)
    forget_access(db, user.id)  # R4: the level again, from fresh reads
    return authorize_edit(db, user, locked.id)


@dataclass
class Context:
    sheet: Worksheet
    structure: WorksheetStructure
    columns: dict[str, Column]
    locale: str
    hidden: frozenset[str]
    links: dict[UUID, dict[str, WorksheetRowLink]] = field(default_factory=dict)
    # The records this write holds FOR SHARE; a link to any other record is refused (N-1).
    locked: frozenset[UUID] = frozenset()
    # Import (route 14 `invalid_cells: "empty"`): a create cell that fails its column's
    # rule is stored empty and counted, instead of refusing the batch.
    empty_invalid: bool = False
    emptied: int = 0

    @classmethod
    def read(cls, db: Session, user: User, sheet: Worksheet) -> "Context":
        structure = WorksheetStructure.model_validate(sheet.structure)
        columns = {column.key: column for column in structure.columns}
        hidden_links = {
            column.key for column in structure.columns
            if isinstance(column, SheetLinkColumn)
            and link_column_hidden(db, user, column.link.moduleId)
        }
        organization = db.get(WorkspaceProfile, sheet.org_id)
        locale = organization.locale if organization and organization.locale else "en-US"
        return cls(sheet, structure, columns, locale, frozenset(hidden_links))


def raw_targets(cells: dict[str, Any]) -> set[UUID]:
    """The record IDs a request names, read loosely before the locks; checked after them."""

    found = set()
    for value in cells.values():
        candidate = value.value if isinstance(value, SheetCellChange) else value
        record_id = candidate.get("record_id") if isinstance(candidate, dict) else None
        if isinstance(record_id, str):
            try:
                found.add(UUID(record_id))
            except ValueError:
                continue
    return found


def readable_records(db: Session, user: User, record_ids: set[UUID]) -> set[UUID]:
    """The named records in a module the person can read (Security review F5)."""

    if not record_ids:
        return set()
    rows = db.execute(select(Record.id, Record.module_id).where(Record.id.in_(record_ids)))
    return {record_id for record_id, module_id in rows if module_level(db, user, module_id)}


def live_links(db: Session, row_ids: list[UUID]) -> dict[UUID, dict[str, WorksheetRowLink]]:
    links: dict[UUID, dict[str, WorksheetRowLink]] = {row_id: {} for row_id in row_ids}
    for link in db.scalars(select(WorksheetRowLink).where(
        WorksheetRowLink.row_id.in_(row_ids), WorksheetRowLink.is_deleted.is_(False),
    )):
        links[link.row_id][link.column_key] = link
    return links


def _convert(db: Session, user: User, context: Context, key: str, value: Any) -> Any:
    column = context.columns.get(key)
    if column is None:
        raise cell_error("cell_invalid", key, "The sheet has no such column")
    if key in context.hidden:
        raise error(status.HTTP_403_FORBIDDEN, "cell_no_access", "This cell cannot be changed")
    converted = convert_cell(db, user, key, column, value, context.locale)
    if isinstance(converted, LinkValue) and isinstance(column, SheetLinkColumn):
        record = db.get(Record, converted.record_id)
        module = db.get(Module, record.module_id) if record is not None else None
        if (
            converted.record_id not in context.locked
            or record is None or module is None or record.org_id != context.sheet.org_id
            or record.is_deleted or module.is_deleted
            or record.module_id != column.link.moduleId
            or module_level(db, user, record.module_id) is None
        ):
            raise cell_error("link_target_invalid", key, "Choose a live record you can read")
    return converted


def _changed_by(db: Session, user: User, row_id: UUID, keys: list[str]) -> Any:
    """The author of the latest change to one of ``keys``, when ``user`` can see them."""

    author = db.scalar(
        select(WorksheetRowRevision.performed_by)
        .where(WorksheetRowRevision.row_id == row_id,
               WorksheetRowRevision.changed_keys.op("?|")(array(keys)))
        .order_by(WorksheetRowRevision.revision.desc())
        .limit(1)
    )
    if author is None or (author != user.id and not visible_person_ids(db, user, [author])):
        return None
    found = person_refs(db, [author]).get(author)
    return None if found is None else found.model_dump(mode="json")


def _canonical(cell: Any) -> tuple[str, Any]:
    if isinstance(cell, SheetLinkCell):
        return "link", cell.link.record_id
    if isinstance(cell, SheetUnlinkedCell):
        return "unlinked", cell.unlinked
    if isinstance(cell, SheetStateCell):
        return "state", cell.state
    value = cell.value if isinstance(cell, SheetValueCell) else None
    kind = type(value).__name__ if isinstance(value, bool | str | type(None)) else "json"
    return kind, value


def _apply(
    db: Session, context: Context, row: WorksheetRow, changes: dict[str, Any],
) -> None:
    data = {key: value for key, value in row.data.items() if key in context.columns}
    links = context.links.setdefault(row.id, {})
    for key, value in changes.items():
        if isinstance(context.columns[key], SheetLinkColumn):
            data.pop(key, None)
            existing = links.get(key)
            if isinstance(value, LinkValue):
                if existing is None:
                    existing = WorksheetRowLink(
                        org_id=row.org_id, worksheet_id=row.worksheet_id, row_id=row.id,
                        column_key=key,
                    )
                    db.add(existing)
                    links[key] = existing
                existing.target_record_id, existing.target_removed = value.record_id, False
                continue
            if existing is not None:
                existing.is_deleted, existing.deleted_at = True, utc_now()
                links.pop(key)
            if isinstance(value, UnlinkedValue):
                data[key] = {"unlinked": value.text}
        elif value is None:
            data.pop(key, None)
        else:
            data[key] = value
    row.data = data


def _sized(context: Context, row: WorksheetRow, rows_added: int) -> None:
    new_size = check_row_size(row.data)
    sheet = context.sheet
    total = sheet.data_bytes - (row.data_bytes or 0) + new_size
    if total > MAX_SHEET_BYTES:
        raise worksheet_limit("sheet_size", MAX_SHEET_BYTES, "A sheet holds at most 8 MiB")
    if sheet.live_row_count + rows_added > MAX_ROWS:
        raise worksheet_limit("rows", MAX_ROWS, "A sheet holds at most 10,000 rows")
    if rows_added and (db := object_session(sheet)) is not None:  # spec editions.md ED-6
        require_sheet_rows(db, sheet.live_row_count, rows_added)
    sheet.data_bytes = total
    sheet.live_row_count += rows_added
    row.data_bytes = new_size


def _revision(db: Session, context: Context, row: WorksheetRow, action: str,
              keys: set[str]) -> None:
    targets = {
        key: {"record_id": str(link.target_record_id)}
        for key, link in context.links.get(row.id, {}).items()
        if link.target_record_id is not None
    }
    db.add(WorksheetRowRevision(
        org_id=row.org_id, worksheet_id=row.worksheet_id, row_id=row.id,
        revision=row.revision, action=action, data={**row.data, **targets},
        changed_keys=sorted(keys),
    ))


def _position(db: Session, sheet: Worksheet, place: Literal["end", "top", "after"],
              after_id: UUID | None, moving: UUID | None = None) -> int:
    live = [
        WorksheetRow.worksheet_id == sheet.id, WorksheetRow.is_deleted.is_(False),
        *([WorksheetRow.id != moving] if moving else []),
    ]
    if place == "end":
        last = db.scalar(select(func.max(WorksheetRow.position)).where(*live))
        return GAP if last is None else int(last) + GAP
    if place == "top":
        first = db.scalar(select(func.min(WorksheetRow.position)).where(*live))
        return GAP if first is None else int(first) - GAP
    after = db.get(WorksheetRow, after_id)
    if after is None or after.worksheet_id != sheet.id or after.is_deleted:
        raise cell_error("row_invalid", "after_row_id", "The row to insert after is gone")
    following = db.scalar(select(func.min(WorksheetRow.position)).where(
        *live, WorksheetRow.position > after.position,
    ))
    if following is None:
        return after.position + GAP
    if following - after.position >= 2:
        return (after.position + int(following)) // 2
    ordered = db.scalars(select(WorksheetRow).where(*live).order_by(
        WorksheetRow.position, WorksheetRow.id)).all()
    for index, item in enumerate(ordered, start=1):
        item.position = index * GAP  # the sheet lock serializes renumbering
    db.flush()
    return after.position + GAP // 2


def _placement(model: SheetRowCreate | Any) -> tuple[Literal["end", "top", "after"], UUID | None]:
    if "after_row_id" not in model.model_fields_set:
        return "end", None
    return ("top", None) if model.after_row_id is None else ("after", model.after_row_id)


def _cell_problem(detail: dict[str, Any]) -> bool:
    """A problem of the cell alone (D9.3): its column's rule, or its own length limit. The
    row size, sheet size and row count limits are not cell problems."""

    code = detail.get("code")
    return code == "cell_invalid" or (code == "worksheet_limit" and detail.get("limit") == "cell")


def _create_cell(db: Session, user: User, context: Context, key: str, value: Any) -> Any:
    """The converted cell, or ``_EMPTIED`` when import mode empties a value with a cell
    problem. Links, unknown and hidden columns and the other limits still refuse."""

    try:
        return _convert(db, user, context, key, value)
    except HTTPException as refused:
        detail: dict[str, Any] = refused.detail if isinstance(refused.detail, dict) else {}
        column = context.columns.get(key)
        if (not context.empty_invalid or not _cell_problem(detail)
                or column is None or isinstance(column, SheetLinkColumn)):
            raise
        context.emptied += 1
        return _EMPTIED


_EMPTIED = object()


def create_row(db: Session, user: User, context: Context, create: SheetRowCreate) -> UUID:
    converted = {
        key: _create_cell(db, user, context, key, value) for key, value in create.cells.items()
    }
    changes = {key: value for key, value in converted.items() if value is not _EMPTIED}
    place, after_id = _placement(create)
    row = WorksheetRow(
        org_id=context.sheet.org_id, worksheet_id=context.sheet.id,
        position=_position(db, context.sheet, place, after_id), data={}, data_bytes=0,
        revision=1,
    )
    db.add(row)
    db.flush()
    context.links[row.id] = {}
    _apply(db, context, row, changes)
    _sized(context, row, rows_added=1)
    _revision(db, context, row, "create", set(changes))
    return row.id


def update_row(
    db: Session, user: User, context: Context, row: WorksheetRow,
    cells: dict[str, SheetCellChange], conflict: Conflict, current: SheetRow | None,
) -> None:
    for key in cells:
        column = context.columns.get(key)
        if column is None:
            raise cell_error("cell_invalid", key, "The sheet has no such column")
    if current is None:
        raise row_not_found()
    for key in cells:
        shown = current.cells.get(key)
        if key in context.hidden or (
            isinstance(shown, SheetStateCell) and shown.state == "no_access"
        ):
            raise error(status.HTTP_403_FORBIDDEN, "cell_no_access", "This cell cannot be changed")
        if context.columns[key].type in READ_ONLY_TYPES:
            raise cell_error("column_read_only", key, "This column cannot be edited")
    changed = sorted(
        key for key, change in cells.items()
        if _canonical(change.expected) != _canonical(current.cells.get(key))
    )
    if changed and conflict == "cell_changed":
        raise error(status.HTTP_412_PRECONDITION_FAILED, "cell_changed",
                    "Someone changed these cells", keys=changed,
                    current=current.model_dump(mode="json"),
                    changed_by=_changed_by(db, user, row.id, changed))
    if changed:
        raise error(status.HTTP_409_CONFLICT, "row_changed", "Someone changed this row",
                    row_id=str(row.id), keys=changed)
    changes = {key: _convert(db, user, context, key, change.value) for key, change in cells.items()}
    _apply(db, context, row, changes)
    _sized(context, row, rows_added=0)
    row.revision += 1
    _revision(db, context, row, "update", set(changes))


def locked_rows(
    db: Session, context: Context, row_ids: list[UUID], seen: dict[UUID, dict[str, UUID | None]],
) -> dict[UUID, WorksheetRow]:
    """Step 5 and the link re-read: a link that changed since the first read is a conflict."""

    rows = {row.id: row for row in lock_rows(db, row_ids)}
    for row_id in row_ids:
        row = rows.get(row_id)
        if row is None or row.worksheet_id != context.sheet.id or row.is_deleted:
            raise row_not_found()
    context.links.update(live_links(db, row_ids))
    for row_id, before in seen.items():
        after = {key: link.target_record_id for key, link in context.links[row_id].items()}
        if after != before:
            raise error(status.HTTP_409_CONFLICT, "row_changed", "Someone changed this row",
                        row_id=str(row_id), keys=sorted(set(after) ^ set(before)))
    return rows


def link_targets(db: Session, row_ids: list[UUID]) -> dict[UUID, dict[str, UUID | None]]:
    return {
        row_id: {key: link.target_record_id for key, link in links.items()}
        for row_id, links in live_links(db, row_ids).items()
    }


def write_rows(
    db: Session, user: User, worksheet_id: UUID, creates: list[SheetRowCreate],
    updates: list[SheetRowBatchUpdate], *, structure_revision: int | None = None,
    conflict: Conflict = "row_changed", move: Any = None,
    invalid_cells: Literal["refuse", "empty"] = "refuse",
) -> tuple[list[UUID], int]:
    """Creates and updates in one transaction, and the number of emptied create cells; the
    caller commits."""

    sheet = authorize_edit(db, user, worksheet_id)
    row_ids = [update.row_id for update in updates]
    seen = link_targets(db, row_ids)
    targets = {target for links in seen.values() for target in links.values() if target}
    named: set[UUID] = set()
    for create in creates:
        named |= raw_targets(dict(create.cells))
    for update in updates:
        named |= raw_targets(dict(update.cells))
    targets |= readable_records(db, user, named)  # an unreadable one is refused, never locked
    sheet = lock_and_recheck(db, user, sheet, targets)
    if structure_revision is not None and structure_revision != sheet.revision:
        raise error(status.HTTP_409_CONFLICT, "structure_changed",
                    "The columns changed; reload the sheet")
    context = Context.read(db, user, sheet)
    context.locked = frozenset(targets)
    context.empty_invalid = invalid_cells == "empty"
    rows = locked_rows(db, context, row_ids, seen)
    written = []
    shown = read_rows(db, user, sheet, row_ids)  # one statement for every updated row
    for update in updates:
        update_row(db, user, context, rows[update.row_id], update.cells, conflict,
                   shown.get(update.row_id))
        if move is not None:
            move_row(db, context, rows[update.row_id], move)
        written.append(update.row_id)
    created = [create_row(db, user, context, create) for create in creates]
    db.flush()
    return [*created, *written], context.emptied


def move_row(db: Session, context: Context, row: WorksheetRow, model: Any) -> None:
    """Route 12's ``after_row_id``: present moves the row; absent leaves it."""

    if "after_row_id" in model.model_fields_set:
        place, after_id = _placement(model)
        row.position = _position(db, context.sheet, place, after_id, moving=row.id)


def delete_row(db: Session, user: User, worksheet_id: UUID, row_id: UUID,
               if_match: str | None) -> None:
    sheet = authorize_edit(db, user, worksheet_id)
    found = db.get(WorksheetRow, row_id)
    if found is None or found.worksheet_id != sheet.id or found.is_deleted:
        raise row_not_found()
    if if_match is None:
        raise error(status.HTTP_428_PRECONDITION_REQUIRED, "precondition_required",
                    "If-Match is required")
    seen = link_targets(db, [row_id])
    sheet = lock_and_recheck(db, user, sheet, {t for t in seen[row_id].values() if t})
    context = Context.read(db, user, sheet)
    row = locked_rows(db, context, [row_id], seen)[row_id]
    if if_match != f'"{row.id}:{row.revision}"':
        raise error(status.HTTP_412_PRECONDITION_FAILED, "row_changed",
                    "The row changed; reload it")
    row.is_deleted, row.deleted_at = True, utc_now()
    row.revision += 1
    sheet.live_row_count -= 1
    sheet.data_bytes -= row.data_bytes
    _revision(db, context, row, "delete", set())

