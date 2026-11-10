"""Security events: the organization filter, writes and the list (moved from service.py)."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, and_, literal, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from uuid6 import uuid7

from app.common.listing import (
    ListQueryResult,
    ListQuerySpec,
    StandardListRequest,
    execute_standard_list,
)
from app.core.base_model import utc_now
from app.core.database.organization_scope import bound_organization_column
from app.core.database.session import AuditSession, get_engine
from app.core.middleware.request_context import get_current_request_context
from app.core.observability import log_event
from app.systems.access.users.membership import is_platform_operator
from app.systems.access.users.models import Membership, User
from app.systems.manage.audit.models import SecurityEvent, SecurityEventOutcome
from app.systems.manage.audit.reference import reference_condition
from app.systems.manage.audit.schemas import SecurityEventIngestRequest


class SecurityEventPersistenceError(RuntimeError):
    """A security event could not be committed durably."""


def bound_members() -> Select[tuple[UUID]]:
    return select(Membership.user_id).where(Membership.org_id == bound_organization_column())


def security_events_of_bound_organization(*, operator: bool = False) -> ColumnElement[bool]:
    """Events of the bound organization, and account events about its own people."""

    return or_(
        SecurityEvent.org_id == bound_organization_column(),
        and_(
            SecurityEvent.org_id.is_(None),
            SecurityEvent.event_type != "workspace.security_policy_change",
            or_(
                SecurityEvent.actor_id.in_(bound_members()),
                SecurityEvent.subject_id.in_(bound_members()),
            ),
        ),
        and_(
            SecurityEvent.org_id.is_(None),
            SecurityEvent.event_type == "workspace.security_policy_change",
            literal(operator),
        ),
    )


class SecurityEventSortField(StrEnum):
    EVENT_TYPE = "event_type"
    OCCURRED_AT = "occurred_at"
    OUTCOME = "outcome"
    SOURCE = "source"


SECURITY_EVENT_LIST_SPEC = ListQuerySpec(
    sort_fields={
        SecurityEventSortField.EVENT_TYPE: cast(ColumnElement[Any], SecurityEvent.event_type),
        SecurityEventSortField.OCCURRED_AT: cast(ColumnElement[Any], SecurityEvent.occurred_at),
        SecurityEventSortField.OUTCOME: cast(ColumnElement[Any], SecurityEvent.outcome),
        SecurityEventSortField.SOURCE: cast(ColumnElement[Any], SecurityEvent.source),
    },
    default_sort=SecurityEventSortField.OCCURRED_AT,
    tie_breaker=cast(ColumnElement[Any], SecurityEvent.id),
    search_fields=(
        cast(ColumnElement[str], SecurityEvent.event_type),
        cast(ColumnElement[str], SecurityEvent.source),
        cast(ColumnElement[str], SecurityEvent.reason),
        cast(ColumnElement[str], SecurityEvent.request_path),
    ),
)


def append_security_event(
    db: Session, payload: SecurityEventIngestRequest, *, org_id: UUID | None = None
) -> SecurityEvent:
    """Add one security event; ``org_id`` records the organization it happened in.

    Producers pass it explicitly: an organization-only event names its organization,
    while account and installation events (sign-in, platform policy) stay ``None``.
    """
    context = get_current_request_context()
    event = SecurityEvent(
        id=uuid7(),
        org_id=org_id,
        occurred_at=payload.occurred_at or utc_now(),
        event_type=payload.event_type,
        outcome=payload.outcome,
        source=payload.source,
        operation_id=payload.operation_id,
        actor_id=payload.actor_id,
        subject_id=payload.subject_id,
        labels=dict(payload.labels),
        fingerprint=payload.fingerprint,
        reason=payload.reason,
        request_id=payload.request_id or (context.request_id if context else None),
        request_method=payload.request_method or (context.method if context else None),
        request_path=payload.request_path or (context.path if context else None),
        event_metadata=dict(payload.metadata),
    )
    object.__setattr__(event, "_security_event_internal", True)
    db.add(event)
    return event


def append_committed_security_event(
    payload: SecurityEventIngestRequest, *, org_id: UUID | None = None
) -> None:
    """Commit one security event through a session independent of the request transaction."""

    session = AuditSession(bind=get_engine())
    try:
        append_security_event(session, payload, org_id=org_id)
        session.commit()
    except SQLAlchemyError as error:
        log_event(
            "security_event_ingestion_failed",
            level=logging.ERROR,
            operation_id=payload.operation_id,
            reason_code="persistence_failed",
        )
        session.rollback()
        raise SecurityEventPersistenceError("Unable to commit security event") from error
    finally:
        session.close()


def list_security_events(
    db: Session,
    params: StandardListRequest[SecurityEventSortField],
    *,
    reader: User | None = None,
    operation_id: UUID | None = None,
    event_type: str | None = None,
    outcome: SecurityEventOutcome | None = None,
    person_id: UUID | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    reference: str | None = None,
) -> ListQueryResult[SecurityEvent]:
    conditions: list[ColumnElement[bool]] = [security_events_of_bound_organization(
        operator=reader is not None and is_platform_operator(db, reader.id),
    )]
    if operation_id is not None:
        conditions.append(SecurityEvent.operation_id == operation_id)
    if event_type is not None:
        conditions.append(SecurityEvent.event_type == event_type)
    if outcome is not None:
        conditions.append(SecurityEvent.outcome == outcome)
    if person_id is not None:
        conditions.append(
            or_(SecurityEvent.actor_id == person_id, SecurityEvent.subject_id == person_id)
        )
    if occurred_after is not None:
        conditions.append(SecurityEvent.occurred_at >= occurred_after)
    if occurred_before is not None:
        conditions.append(SecurityEvent.occurred_at < occurred_before)
    if reference is not None:
        conditions.append(reference_condition(SecurityEvent.request_id, reference))

    statement = select(SecurityEvent).where(*conditions)
    return execute_standard_list(db, statement, params, SECURITY_EVENT_LIST_SPEC)
