"""The per-viewer projection of sheet rows into SQL (spec D7.3, N2, N4, N6-N8).

Each column compiles to SQL expressions over one row: what the cell shows (a value, a link,
unlinked text or a state), the text that search matches, the key that sort uses and the
number that totals add. A value the viewer cannot read never leaves the database: the
expressions are already masked, so sort, search and totals see only readable values.

A link column whose target module the viewer cannot read shows ``no_access`` in every cell,
with its lookups (N4 is per column). Computed columns are blank until B10 compiles their
expressions here; ``sheet_lookup`` columns are blank until B11.
"""

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    Numeric,
    String,
    Text,
    and_,
    case,
    false,
    func,
    literal,
    null,
    or_,
    select,
    true,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy import column as sql_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import FromClause

from app.systems.access.policy.checks import module_filter, module_level
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.structure import (
    SheetDecimalColumn,
    SheetLinkColumn,
    SheetLookupColumn,
    SheetPlainColumn,
    SheetSelectColumn,
    WorksheetStructure,
)
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record

CellState = Literal[
    "no_access", "deleted", "removed", "unavailable", "field_removed", "link", "unlinked",
]
NUMERIC_TYPES = frozenset({"int", "number", "decimal"})
# A record decimal field stores a canonical decimal string; only that shape is read as a number.
_DECIMAL_TEXT = r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"
Expression = ColumnElement[Any]


def _no_number() -> Expression:
    return sql_cast(null(), Numeric)


def _no_text() -> Expression:
    return sql_cast(null(), Text)


def _no_value() -> Expression:
    return sql_cast(null(), JSONB)


# Title fields whose stored value is its own label (a choice-list title falls back).
_TITLE_TYPES = ("text", "long_text", "email", "url", "int", "number", "decimal", "select")
# As records: a person or checkbox value is no search text (`SEARCHABLE_FIELD_TYPES`).
_UNSEARCHED = frozenset({"user", "boolean"})


@dataclass(frozen=True)
class ColumnProjection:
    """The SQL of one column. ``state`` is NULL for a cell that shows ``value``."""

    key: str
    state: Expression
    value: Expression
    label: Expression
    text: Expression
    sort: Expression
    number: Expression
    hidden: Expression
    shown: Expression


@dataclass
class RowProjection:
    source: FromClause
    columns: list[ColumnProjection] = field(default_factory=list)

    def column(self, key: str) -> ColumnProjection:
        return next(column for column in self.columns if column.key == key)


def _number(value: Expression, *, decimal_text: bool = False) -> Expression:
    """A JSON number (or a canonical decimal string) as ``numeric``; anything else is NULL.

    The type guard comes first, so a stored string never reaches a cast (H5).
    """

    whens = [(func.jsonb_typeof(value) == "number", value.astext.cast(Numeric))]
    if decimal_text:
        whens.append((
            and_(func.jsonb_typeof(value) == "string", value.astext.op("~")(_DECIMAL_TEXT)),
            value.astext.cast(Numeric),
        ))
    return case(*whens, else_=null())


def _scalar_text(value: Expression) -> Expression:
    """Text of a JSON string, number or boolean; NULL for objects, arrays and null."""

    return case(
        (func.jsonb_typeof(value).in_(("string", "number", "boolean")), value.astext),
        else_=null(),
    )


def _option_label(value: Expression, options: dict[str, str]) -> Expression:
    if not options:
        return _no_text()
    return case(
        *((value.astext == option_id, literal(label)) for option_id, label in options.items()),
        else_=null(),
    )


def _plain(
    key: str, column: SheetPlainColumn | SheetSelectColumn | SheetDecimalColumn,
) -> ColumnProjection:
    value = WorksheetRow.data[key]
    kind = column.type
    if kind in NUMERIC_TYPES:
        number = _number(value, decimal_text=kind == "decimal")
        text, sort = _scalar_text(value), number
    elif isinstance(column, SheetSelectColumn):
        labels = {option.id: option.label for option in column.select.options}
        text = _option_label(value, labels)
        sort, number = func.lower(text), _no_number()
    else:
        # A person sorts by the stored ID, as on record pages (B4 review item 3).
        sort, number = func.lower(_scalar_text(value)), _no_number()
        text = _no_text() if kind in _UNSEARCHED else _scalar_text(value)
    present = and_(value.is_not(None), func.jsonb_typeof(value) != "null")
    return ColumnProjection(
        key, _no_text(), value, _no_text(), text, sort, number, false(), present,
    )


def _blank(key: str) -> ColumnProjection:
    return ColumnProjection(
        key, _no_text(), _no_value(), _no_text(), _no_text(), _no_text(), _no_number(),
        false(), false(),
    )


def _hidden(key: str) -> ColumnProjection:
    return ColumnProjection(
        key, literal("no_access"), _no_value(), _no_text(), _no_text(), _no_text(),
        _no_number(), true(), false(),
    )


@dataclass(frozen=True)
class _Link:
    state: Expression
    data: Any


def _title_option_label(title: Any, raw: Expression) -> Expression:
    """The label of a choice-list title, as `record_title` and platform search show it."""

    options = title.config["options"]
    rows = (
        func.jsonb_array_elements(
            case(
                (func.jsonb_typeof(options) == "array", options),
                else_=sql_cast(literal("[]"), JSONB),
            )
        )
        .table_valued(sql_column("value", JSONB), with_ordinality="ordinality")
        .render_derived()
    )
    return (
        select(rows.c.value["label"].astext)
        .where(
            func.jsonb_typeof(rows.c.value["id"]) == "string",
            func.jsonb_typeof(rows.c.value["label"]) == "string",
            rows.c.value["id"].astext == raw,
        )
        .order_by(rows.c.ordinality.desc())
        .limit(1)
        .scalar_subquery()
    )


def _record_label(target: Any, title: Any) -> Expression:
    raw = target.data.op("->>")(func.cast(title.id, String))
    label = case((title.type == "select", _title_option_label(title, raw)), else_=raw)
    named = func.nullif(func.btrim(label), "")
    fallback = literal("Record ") + func.left(func.cast(target.id, String), 8)
    return func.coalesce(named, fallback)


def _join_link(
    db: Session, user: User, projection: RowProjection, key: str
) -> tuple[_Link, ColumnProjection]:
    """One LATERAL read of the cell's live link, its record, module and title field."""

    link = aliased(WorksheetRowLink, name=f"row_link_{key}")
    target = aliased(Record, name=f"target_{key}")
    module = aliased(Module, name=f"target_module_{key}")
    title = aliased(Field, name=f"title_{key}")
    linked_state = case(
        (link.target_removed.is_(True), literal("removed")),
        (~module_filter(db, user, AccessLevel.READ, target.module_id), literal("no_access")),
        (
            or_(
                module.is_deleted.is_(True),
                and_(target.is_deleted.is_(True), target.lifecycle_close_operation_id.is_not(None)),
            ),
            literal("unavailable"),
        ),
        (target.is_deleted.is_(True), literal("deleted")),
        else_=literal("link"),
    )
    cell = (
        select(
            linked_state.label("state"),
            target.id.label("target_id"),
            target.data.label("data"),
            _record_label(target, title).label("title"),
        )
        .select_from(link)
        .outerjoin(target, and_(target.org_id == link.org_id, target.id == link.target_record_id))
        .outerjoin(module, module.id == target.module_id)
        .outerjoin(
            title,
            and_(
                title.id == module.title_field_id,
                title.module_id == module.id,
                title.is_deleted.is_(False),
                title.type.in_(_TITLE_TYPES),
            ),
        )
        .where(
            link.org_id == WorksheetRow.org_id,
            link.worksheet_id == WorksheetRow.worksheet_id,
            link.row_id == WorksheetRow.id,
            link.column_key == key,
            link.is_deleted.is_(False),
        )
        .lateral(f"link_{key}")
    )
    projection.source = projection.source.outerjoin(cell, true())
    unlinked = WorksheetRow.data[key]["unlinked"]
    state = case(
        (
            cell.c.state.is_(None),
            case((func.jsonb_typeof(unlinked) == "string", literal("unlinked")), else_=null()),
        ),
        else_=cell.c.state,
    )
    label = case(
        (state == "link", cell.c.title),
        (state == "unlinked", unlinked.astext),
        else_=null(),
    )
    column = ColumnProjection(
        key=key,
        state=state,
        value=case((state == "link", func.to_jsonb(cell.c.target_id)), else_=null()),
        label=label,
        text=label,
        sort=func.lower(label),
        number=_no_number(),
        hidden=state == "no_access",
        shown=state.in_(("link", "unlinked")),
    )
    return _Link(state, cell.c.data), column


def _lookup(db: Session, key: str, column: SheetLookupColumn, link: _Link,
            target_module: UUID) -> ColumnProjection:
    source = db.get(Field, column.lookup.fieldId)
    live = (
        source is not None and not source.is_deleted and source.module_id == target_module
        and FieldType(source.type) is not FieldType.RELATIONSHIP
    )
    state = case(
        (link.state.in_(("no_access", "unavailable")), link.state),
        # Beside a deleted, purged, unlinked or missing link: blank (Decision 17).
        (link.state.is_distinct_from("link"), null()),
        else_=literal("link" if live else "field_removed"),
    )
    readable = state == "link"
    value, text, number = _no_value(), _no_text(), _no_number()
    sorted_text = text
    numeric = False
    if live and source is not None:
        raw = link.data[str(source.id)]
        kind = FieldType(source.type)
        if kind is FieldType.SELECT:
            options = {
                option["id"]: option["label"] for option in source.config.get("options", [])
                if isinstance(option, dict) and isinstance(option.get("id"), str)
                and isinstance(option.get("label"), str)
            }
            text = _option_label(raw, options)
            value = func.to_jsonb(text) if options else _no_value()
        elif kind.value in NUMERIC_TYPES:
            numeric = True
            number = _number(raw, decimal_text=kind is FieldType.DECIMAL)
            value, text = raw, _scalar_text(raw)
        else:
            value, text = raw, _scalar_text(raw)
        sorted_text = text
        if kind.value in _UNSEARCHED:
            sorted_text, text = _scalar_text(raw), _no_text()
    masked_text = case((readable, text), else_=null())
    masked_number = case((readable, number), else_=null())
    masked_value = case((readable, value), else_=null())
    return ColumnProjection(
        key=key,
        state=case((readable, null()), else_=state),
        value=masked_value,
        label=_no_text(),
        text=masked_text,
        sort=masked_number if numeric else func.lower(case((readable, sorted_text), else_=null())),
        number=masked_number,
        hidden=link.state == "no_access",
        shown=func.coalesce(func.jsonb_typeof(masked_value) != "null", false()),
    )


def link_column_hidden(db: Session, user: User, module_id: UUID) -> bool:
    """A link column is hidden when its target module exists and the person cannot read it.

    After a module or department purge the module row is gone with its grants, so no one
    has a level on it; its cells then show their own state (``removed`` for a stripped link,
    unlinked text as typed), never a whole-column ``no_access`` (B8-B1, N6, SH-29).
    """

    return module_level(db, user, module_id) is None and db.get(Module, module_id) is not None


def project_rows(db: Session, user: User, structure: WorksheetStructure) -> RowProjection:
    """Compile every column of ``structure`` for ``user`` over ``worksheet_rows``."""

    projection = RowProjection(source=WorksheetRow.__table__)
    links: dict[str, tuple[_Link, UUID] | None] = {}
    for column in structure.columns:
        if isinstance(column, SheetLinkColumn):
            if link_column_hidden(db, user, column.link.moduleId):
                links[column.key] = None
                projection.columns.append(_hidden(column.key))
                continue
            joined, projected = _join_link(db, user, projection, column.key)
            links[column.key] = (joined, column.link.moduleId)
            projection.columns.append(projected)
    for column in structure.columns:
        if isinstance(column, SheetLinkColumn):
            continue
        if isinstance(column, SheetLookupColumn):
            found = links.get(column.lookup.linkKey)
            projection.columns.append(
                _hidden(column.key) if found is None
                else _lookup(db, column.key, column, found[0], found[1])
            )
        elif isinstance(column, SheetPlainColumn | SheetSelectColumn | SheetDecimalColumn):
            projection.columns.append(_plain(column.key, column))
        else:
            projection.columns.append(_blank(column.key))  # computed (B10), sheet_lookup (B11)
    order = {column.key: index for index, column in enumerate(structure.columns)}
    projection.columns.sort(key=lambda item: order[item.key])
    return projection

