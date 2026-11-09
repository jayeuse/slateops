"""Relationship list loading and response projection."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, asc, desc, exists, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, aliased, joinedload
from sqlalchemy.sql.elements import ColumnElement

from app.common.listing import (
    ListQuerySpec,
    SortOrder,
    build_standard_list_statements,
    list_pagination,
)
from app.systems.access.users.models import User
from app.systems.sandbox.fields.models import Field
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from app.systems.sandbox.relationships.access import readable_link_clause
from app.systems.sandbox.relationships.errors import RelationshipNotFound
from app.systems.sandbox.relationships.models import RelationshipEdge
from app.systems.sandbox.relationships.schemas import (
    RelationshipAvailability,
    RelationshipHiddenReason,
    RelationshipListRequest,
    RelationshipResponse,
    RelationshipSortField,
    RelationshipVisibility,
)


def get_relationship(db: Session, relationship_id: UUID) -> RelationshipEdge:
    edge = db.get(
        RelationshipEdge,
        relationship_id,
        options=(
            joinedload(RelationshipEdge.field).joinedload(Field.module),
            joinedload(RelationshipEdge.field).joinedload(Field.relationship_target_module),
            joinedload(RelationshipEdge.source_record).joinedload(Record.module),
            joinedload(RelationshipEdge.target_record).joinedload(Record.module),
        ),
    )
    if edge is None:
        raise RelationshipNotFound("Relationship not found")
    return edge


def _edge_hidden_reasons(edge: RelationshipEdge) -> list[RelationshipHiddenReason]:
    field = edge.field
    source = edge.source_record
    target = edge.target_record
    source_module = getattr(source, "module", None)
    target_module = getattr(target, "module", None)
    return _hidden_reasons(
        field.is_deleted,
        source.is_deleted,
        target.is_deleted,
        source_module.is_deleted if source_module is not None else False,
        target_module.is_deleted if target_module is not None else False,
    )


def _hidden_reasons(
    field_is_deleted: bool,
    source_is_deleted: bool,
    target_is_deleted: bool,
    source_module_is_deleted: bool,
    target_module_is_deleted: bool,
) -> list[RelationshipHiddenReason]:
    reasons: list[RelationshipHiddenReason] = []
    if field_is_deleted:
        reasons.append(RelationshipHiddenReason.FIELD_ARCHIVED)
    if source_is_deleted:
        reasons.append(RelationshipHiddenReason.SOURCE_RECORD_ARCHIVED)
    if target_is_deleted:
        reasons.append(RelationshipHiddenReason.TARGET_RECORD_ARCHIVED)
    if source_module_is_deleted:
        reasons.append(RelationshipHiddenReason.SOURCE_MODULE_ARCHIVED)
    if target_module_is_deleted:
        reasons.append(RelationshipHiddenReason.TARGET_MODULE_ARCHIVED)
    return reasons


def relationship_response(edge: RelationshipEdge) -> RelationshipResponse:
    reasons = _edge_hidden_reasons(edge)
    return RelationshipResponse.model_validate(
        {
            "id": edge.id,
            "field_id": edge.field_id,
            "source_record_id": edge.source_record_id,
            "target_record_id": edge.target_record_id,
            "created_at": edge.created_at,
            "updated_at": edge.updated_at,
            "deleted_at": edge.deleted_at,
            "is_deleted": edge.is_deleted,
            "performed_by": edge.performed_by,
            "visibility": (
                RelationshipVisibility.HIDDEN if reasons else RelationshipVisibility.AVAILABLE
            ),
            "hidden_reasons": reasons,
        }
    )


def _listed_edges(db: Session, params: RelationshipListRequest, reader: User) -> Select[Any]:
    """The edges that the list shows, decided on `relationship_edges` alone.

    Every condition that decides whether an edge is listed sits on the edge or in one EXISTS
    correlated to it, so the page can be read from the edge index in creation order (K67).
    """

    field = aliased(Field)
    source, target = aliased(Record), aliased(Record)
    source_module, target_module = aliased(Module), aliased(Module)
    source_record_module, target_record_module = aliased(Module), aliased(Module)
    linked = (
        select(field.id)
        .join(source, source.id == RelationshipEdge.source_record_id)
        .join(target, target.id == RelationshipEdge.target_record_id)
        .join(source_module, field.module_id == source_module.id)
        .join(target_module, field.relationship_target_module_id == target_module.id)
        .join(source_record_module, source.module_id == source_record_module.id)
        .join(target_record_module, target.module_id == target_record_module.id)
        .where(
            field.id == RelationshipEdge.field_id,
            readable_link_clause(db, reader, source.module_id, target.module_id),
        )
    )
    if params.source_module_id is not None:
        linked = linked.where(field.module_id == params.source_module_id)
    if params.target_module_id is not None:
        linked = linked.where(field.relationship_target_module_id == params.target_module_id)
    hidden = or_(
        field.is_deleted.is_(True),
        source.is_deleted.is_(True),
        target.is_deleted.is_(True),
        source_module.is_deleted.is_(True),
        target_module.is_deleted.is_(True),
    )
    if params.availability is RelationshipAvailability.AVAILABLE:
        linked = linked.where(~hidden)
    elif params.availability is RelationshipAvailability.HIDDEN:
        linked = linked.where(hidden)

    statement = select(
        RelationshipEdge.id, RelationshipEdge.created_at, RelationshipEdge.updated_at
    ).where(exists(linked.correlate(RelationshipEdge)))
    if params.field_id is not None:
        statement = statement.where(RelationshipEdge.field_id == params.field_id)
    if params.source_record_id is not None:
        statement = statement.where(RelationshipEdge.source_record_id == params.source_record_id)
    if params.target_record_id is not None:
        statement = statement.where(RelationshipEdge.target_record_id == params.target_record_id)
    if params.incident_record_id is not None:
        statement = statement.where(
            or_(
                RelationshipEdge.source_record_id == params.incident_record_id,
                RelationshipEdge.target_record_id == params.incident_record_id,
            )
        )
    return statement


RELATIONSHIP_LIST_SPEC = ListQuerySpec(
    sort_fields={
        RelationshipSortField.CREATED_AT: cast(ColumnElement[Any], RelationshipEdge.created_at),
        RelationshipSortField.UPDATED_AT: cast(ColumnElement[Any], RelationshipEdge.updated_at),
    },
    default_sort=RelationshipSortField.CREATED_AT,
    tie_breaker=cast(ColumnElement[Any], RelationshipEdge.id),
    deleted_field=cast(ColumnElement[bool], RelationshipEdge.is_deleted),
    keyset=True,
)


def list_relationships(
    db: Session, params: RelationshipListRequest, *, reader: User
) -> tuple[list[RelationshipResponse], Any]:
    spec = RELATIONSHIP_LIST_SPEC
    page_ids, count_statement = build_standard_list_statements(
        _listed_edges(db, params, reader), params, spec
    )
    # Join the records, the field and the modules only for the rows of the page.
    page = page_ids.subquery("page")
    source_record, target_record = aliased(Record), aliased(Record)
    source_record_module, target_record_module = aliased(Module), aliased(Module)
    direction = asc if params.sort_order is SortOrder.ASC else desc
    sort_name = (params.sort_by or spec.default_sort).value
    item_statement = (
        select(
            RelationshipEdge.id.label("id"),
            RelationshipEdge.field_id.label("field_id"),
            RelationshipEdge.source_record_id.label("source_record_id"),
            RelationshipEdge.target_record_id.label("target_record_id"),
            RelationshipEdge.created_at.label("created_at"),
            RelationshipEdge.updated_at.label("updated_at"),
            RelationshipEdge.deleted_at.label("deleted_at"),
            RelationshipEdge.is_deleted.label("is_deleted"),
            RelationshipEdge.performed_by.label("performed_by"),
            Field.is_deleted.label("field_is_deleted"),
            source_record.is_deleted.label("source_record_is_deleted"),
            target_record.is_deleted.label("target_record_is_deleted"),
            source_record_module.is_deleted.label("source_module_is_deleted"),
            target_record_module.is_deleted.label("target_module_is_deleted"),
        )
        .join(page, page.c.id == RelationshipEdge.id)
        .join(Field, RelationshipEdge.field_id == Field.id)
        .join(source_record, RelationshipEdge.source_record_id == source_record.id)
        .join(target_record, RelationshipEdge.target_record_id == target_record.id)
        .join(source_record_module, source_record.module_id == source_record_module.id)
        .join(target_record_module, target_record.module_id == target_record_module.id)
        .order_by(direction(page.c[sort_name]), direction(page.c.id))
    )
    counted = int(db.scalar(count_statement) or 0)
    rows, pagination = list_pagination(params, spec, db.execute(item_statement).all(), counted)
    return [_projected_relationship_response(row) for row in rows], pagination


def _projected_relationship_response(row: Row[tuple[Any, ...]]) -> RelationshipResponse:
    reasons = _hidden_reasons(
        row.field_is_deleted,
        row.source_record_is_deleted,
        row.target_record_is_deleted,
        row.source_module_is_deleted,
        row.target_module_is_deleted,
    )
    return RelationshipResponse.model_validate(
        {
            "id": row.id,
            "field_id": row.field_id,
            "source_record_id": row.source_record_id,
            "target_record_id": row.target_record_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
            "is_deleted": row.is_deleted,
            "performed_by": row.performed_by,
            "visibility": (
                RelationshipVisibility.HIDDEN if reasons else RelationshipVisibility.AVAILABLE
            ),
            "hidden_reasons": reasons,
        }
    )


__all__ = [
    "get_relationship",
    "list_relationships",
    "relationship_response",
]
