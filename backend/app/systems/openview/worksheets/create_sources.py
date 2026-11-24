"""Route 3 sources: structure, copy and template (spec D9.5, D9.2; L6, X6, X7; D14 S1).

The new sheet's columns are what the creator could save themselves: a link column on a
module they cannot read, a From another sheet column on a sheet they cannot see, an
unmapped template link column and a template lookup whose field is not found become
``text``, and so does every lookup, From another sheet or computed column that reads one.
Columns get new keys ``c1`` to ``cN`` in order; groups, totals and expressions follow.
A copy also takes the rows, the links and the unlinked text, with one ``create`` revision
per row, and never the shares or the history.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.access.policy.checks import module_level
from app.systems.access.users.models import User
from app.systems.openview.worksheets.access import load_visible_worksheet, worksheet_states
from app.systems.openview.worksheets.cells import row_bytes
from app.systems.openview.worksheets.expression import (
    NUMERIC_TYPES,
    ExpressionError,
    check_expressions,
    parse_stored,
    references,
    renamed,
    stored_text,
)
from app.systems.openview.worksheets.models import (
    Worksheet,
    WorksheetRow,
    WorksheetRowLink,
    WorksheetRowRevision,
)
from app.systems.openview.worksheets.row_writes import GAP, error
from app.systems.openview.worksheets.schemas import SheetTemplateSource, WorksheetCreate
from app.systems.openview.worksheets.sheet_lookup_save import check_sheet_graph
from app.systems.openview.worksheets.structure import (
    Column,
    SheetColumnGroup,
    SheetComputedColumn,
    SheetFromSheetColumn,
    SheetLinkColumn,
    SheetLinkOptions,
    SheetLookupColumn,
    SheetLookupOptions,
    SheetPlainColumn,
    WorksheetStructure,
)
from app.systems.openview.worksheets.template_schema import (
    SheetTemplateLinkColumn,
    SheetTemplateLookupColumn,
)
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.modules.models import Module

# Rows one copy request takes: 10,000 rows with two link columns took 11.7 s as the runtime
# role (load 6), past the ~10 s a request may hold (Decision 5); 5,000 leave room.
MAX_COPY_ROWS = 5_000
# The columns whose values a row stores; the others are read per request.
_STORED = frozenset({"link", "text", "long_text", "email", "url", "number", "int", "boolean",
                     "date", "datetime", "user", "decimal", "select"})


@dataclass
class Draft:
    """A structure before new keys: its columns and the keys that became text."""

    columns: list[Column]
    groups: list[SheetColumnGroup]
    totals: dict[str, Any]
    text: set[str] = field(default_factory=set)
    keys: dict[str, str] = field(default_factory=dict)


def module_not_found() -> Any:
    return error(status.HTTP_404_NOT_FOUND, "module_not_found", "Module not found")


def check_copy(db: Session, user: User, payload: WorksheetCreate, sheet: Worksheet) -> None:
    """The owner, or any reader of an open sheet, on the same record or module (L6), and
    no more rows than one request copies in time (Decision 5)."""

    if (payload.record_id, payload.module_id) != (sheet.record_id, sheet.module_id):
        raise error(status.HTTP_422_UNPROCESSABLE_CONTENT, "copy_anchor_mismatch",
                    "A copy stays on the record or module of its sheet")
    present, level = worksheet_states(db, user, [sheet])[sheet.id]
    if present and level != "owner":
        raise error(status.HTTP_403_FORBIDDEN, "worksheet_copy_forbidden",
                    "Only the owner can copy a private sheet")
    if sheet.live_row_count > MAX_COPY_ROWS:
        raise error(status.HTTP_422_UNPROCESSABLE_CONTENT, "copy_too_large",
                    f"A copy holds at most {MAX_COPY_ROWS:,} rows; export and import instead",
                    limit=MAX_COPY_ROWS)


def check_mapping(db: Session, user: User, source: SheetTemplateSource) -> None:
    """Each mapped module is live and readable; otherwise the same 404 as a missing one."""

    for module_id in source.module_mapping.values():
        if module_id is None:
            continue
        module = db.get(Module, module_id)
        if module is None or module.is_deleted or module_level(db, user, module_id) is None:
            raise module_not_found()


def _text(column: Column) -> SheetPlainColumn:
    return SheetPlainColumn(key=column.key, name=column.name, type="text")


def _reads(column: Column) -> list[str]:
    if isinstance(column, SheetLookupColumn):
        return [column.lookup.linkKey]
    if isinstance(column, SheetFromSheetColumn):
        return [column.sheet_lookup.linkKey]
    if isinstance(column, SheetComputedColumn):
        try:
            return references(parse_stored(column.computed.expression).node)
        except ExpressionError:
            return []  # refused by `finish`
    return []


def _cascade(draft: Draft) -> None:
    """Every column that reads a column turned into text turns into text too."""

    changed = True
    while changed:
        changed = False
        for column in draft.columns:
            if column.key not in draft.text and set(_reads(column)) & draft.text:
                draft.text.add(column.key)
                changed = True


def from_sheet(db: Session, user: User, sheet: Worksheet) -> Draft:
    """The sheet's columns as ``user`` could save them (structure and copy)."""

    stored = WorksheetStructure.model_validate(sheet.structure)
    draft = Draft(list(stored.columns), list(stored.groups), dict(stored.totals))
    for column in stored.columns:
        if isinstance(column, SheetLinkColumn) and module_level(
            db, user, column.link.moduleId,
        ) is None:
            draft.text.add(column.key)
        if isinstance(column, SheetFromSheetColumn) and load_visible_worksheet(
            db, user, column.sheet_lookup.sourceWorksheetId,
        ) is None:
            draft.text.add(column.key)
    _cascade(draft)
    return draft


def from_template(db: Session, source: SheetTemplateSource) -> Draft:
    """The template's columns on the mapped modules (X6); the mapping is checked already."""

    template = source.template
    modules: dict[str, UUID] = {}
    draft = Draft([], list(template.groups), dict(template.totals))
    for item in template.columns:
        column: Column
        if isinstance(item, SheetTemplateLinkColumn):
            module_id = source.module_mapping.get(item.key)
            column = SheetLinkColumn(key=item.key, name=item.name, type="link",
                                     link=SheetLinkOptions(moduleId=module_id or uuid7()))
            if module_id is None:
                draft.text.add(item.key)
            else:
                modules[item.key] = module_id
        elif isinstance(item, SheetTemplateLookupColumn):
            module_id = modules.get(item.lookup.linkKey)
            found = None if module_id is None else db.scalar(select(Field.id).where(
                Field.module_id == module_id, Field.name == item.lookup.fieldName,
                Field.is_deleted.is_(False), Field.type != FieldType.RELATIONSHIP.value,
            ).limit(1))
            column = SheetLookupColumn(key=item.key, name=item.name, type="lookup",
                                       lookup=SheetLookupOptions(linkKey=item.lookup.linkKey,
                                                                 fieldId=found or uuid7()))
            if found is None:
                draft.text.add(item.key)
        else:
            column = item
        draft.columns.append(column)
    _cascade(draft)
    return draft


def _rekeyed(column: Column, keys: dict[str, str]) -> Column:
    key = keys[column.key]
    if isinstance(column, SheetLookupColumn):
        lookup = column.lookup.model_copy(update={"linkKey": keys[column.lookup.linkKey]})
        return column.model_copy(update={"key": key, "lookup": lookup})
    if isinstance(column, SheetFromSheetColumn):
        source = column.sheet_lookup.model_copy(
            update={"linkKey": keys[column.sheet_lookup.linkKey]},
        )
        return column.model_copy(update={"key": key, "sheet_lookup": source})
    if isinstance(column, SheetComputedColumn):
        tree = renamed(parse_stored(column.computed.expression).node, keys)
        computed = column.computed.model_copy(update={"expression": stored_text(tree)})
        return column.model_copy(update={"key": key, "computed": computed})
    return column.model_copy(update={"key": key})


def finish(db: Session, draft: Draft) -> WorksheetStructure:
    """New keys in column order, then the route 6 structure and expression checks.

    Expressions arrive in the stored form (keys, ``.`` and ``,``) in every locale.
    """

    draft.keys = {column.key: f"c{index}" for index, column in enumerate(draft.columns, 1)}
    try:
        columns = [
            _rekeyed(_text(column) if column.key in draft.text else column, draft.keys)
            for column in draft.columns
        ]
        totals = {
            draft.keys[key]: function for key, function in draft.totals.items()
            if key in draft.keys and (function == "count" or key not in draft.text)
        }
        groups = [{"name": group.name, "keys": [draft.keys[key] for key in group.keys]}
                  for group in draft.groups if all(key in draft.keys for key in group.keys)]
        structure = WorksheetStructure.model_validate({
            "structureVersion": 1, "nextColumnSeq": len(columns) + 1,
            "columns": [column.model_dump(mode="json") for column in columns],
            "groups": groups, "totals": totals,
        })
    except (ValidationError, ExpressionError, KeyError) as failure:
        raise error(status.HTTP_422_UNPROCESSABLE_CONTENT, "structure_invalid",
                    "The columns of this source cannot make a sheet") from failure
    numeric = set()
    for column in structure.columns:
        if isinstance(column, SheetLookupColumn):
            found = db.get(Field, column.lookup.fieldId)
            if found is not None and found.type in NUMERIC_TYPES:
                numeric.add(column.key)
        elif isinstance(column, SheetFromSheetColumn):
            numeric.add(column.key)
    computed = {column.key for column in structure.columns
                if isinstance(column, SheetComputedColumn)}
    try:
        check_expressions(list(structure.columns), numeric_lookups=numeric,
                          unchanged=computed, decimal_mark=".")
        check_sheet_graph(db, uuid7(), list(structure.columns))  # security review R-2
    except ExpressionError as refused:
        raise error(status.HTTP_422_UNPROCESSABLE_CONTENT, "expression_invalid",
                    refused.message, key=refused.key, reason=refused.reason) from refused
    return structure


def copy_rows(db: Session, source: Worksheet, target: Worksheet, draft: Draft) -> None:
    """The source's live rows, links and unlinked text under the new keys (L6)."""

    kept = {
        column.key: draft.keys[column.key] for column in draft.columns
        if column.key not in draft.text and column.type in _STORED
    }
    rows = db.scalars(select(WorksheetRow).where(
        WorksheetRow.org_id == source.org_id, WorksheetRow.worksheet_id == source.id,
        WorksheetRow.is_deleted.is_(False),
    ).order_by(WorksheetRow.position, WorksheetRow.id)).all()
    links: dict[UUID, list[WorksheetRowLink]] = {}
    for link in db.scalars(select(WorksheetRowLink).where(
        WorksheetRowLink.org_id == source.org_id, WorksheetRowLink.worksheet_id == source.id,
        WorksheetRowLink.is_deleted.is_(False), WorksheetRowLink.column_key.in_(kept),
    )):
        links.setdefault(link.row_id, []).append(link)
    total = 0
    for index, row in enumerate(rows, start=1):
        data = {kept[key]: value for key, value in row.data.items() if key in kept}
        size = row_bytes(data)
        total += size
        copy = WorksheetRow(id=uuid7(), org_id=target.org_id, worksheet_id=target.id,
                            position=index * GAP, data=data, data_bytes=size, revision=1)
        db.add(copy)
        targets: dict[str, Any] = {}
        for link in links.get(row.id, []):
            key = kept[link.column_key]
            db.add(WorksheetRowLink(
                org_id=target.org_id, worksheet_id=target.id, row_id=copy.id, column_key=key,
                target_record_id=link.target_record_id, target_removed=link.target_removed,
            ))
            if link.target_record_id is not None:
                targets[key] = {"record_id": str(link.target_record_id)}
        db.add(WorksheetRowRevision(
            org_id=target.org_id, worksheet_id=target.id, row_id=copy.id, revision=1,
            action="create", data={**data, **targets},
            changed_keys=sorted({*data, *(kept[link.column_key] for link in
                                          links.get(row.id, []))}),
        ))
    target.live_row_count = len(rows)
    target.data_bytes = total
