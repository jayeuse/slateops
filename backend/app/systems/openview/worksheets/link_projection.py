"""Link columns as SQL over one row (spec N1, N4, N6): one LATERAL per link column.

Each cell reads its live link, the target record, its module and its title field, and
yields a state: ``removed``, ``no_access``, ``unavailable``, ``deleted`` or ``link``, or
``unlinked`` for kept import text. Moved from ``projection`` (B12 review N-2).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, and_, case, func, literal, null, or_, select, true
from sqlalchemy import cast as sql_cast
from sqlalchemy import column as sql_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, aliased

from app.systems.access.policy.checks import module_filter
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import WorksheetRow, WorksheetRowLink
from app.systems.openview.worksheets.projection import (
    ColumnProjection,
    Expression,
    RowProjection,
    _no_number,
)
from app.systems.sandbox.fields.models import Field
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record

# Title fields whose stored value is its own label (a choice-list title falls back).
_TITLE_TYPES = ("text", "long_text", "email", "url", "int", "number", "decimal", "select")


@dataclass(frozen=True)
class Link:
    """A link column's per-row state, its target record's data and the target's ID."""

    state: Expression
    data: Any
    target: Expression


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


def join_link(
    db: Session, user: User, projection: RowProjection, key: str
) -> tuple[Link, ColumnProjection]:
    """One LATERAL read of the cell's live link, its record, module and title field."""

    named = f"{projection.scope}{key}"
    link = aliased(WorksheetRowLink, name=f"row_link_{named}")
    target = aliased(Record, name=f"target_{named}")
    module = aliased(Module, name=f"target_module_{named}")
    title = aliased(Field, name=f"title_{named}")
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
        .lateral(f"link_{named}")
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
    return Link(state, cell.c.data, cell.c.target_id), column
