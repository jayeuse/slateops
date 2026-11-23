"""Security outcomes of user-administration actions, written after their commit."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database.organization_scope import session_organization
from app.systems.access.users.coordination import InvitationError, unavailable
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.audit.security_events import (
    SecurityEventPersistenceError,
    append_committed_security_event,
)


def record_security_event(
    *,
    event_type: str,
    outcome: SecurityEventOutcome,
    operation_id: UUID,
    actor_id: UUID | None = None,
    subject_id: UUID | None = None,
    reason: str | None = None,
    org_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        append_committed_security_event(
            SecurityEventIngestRequest(
                event_type=event_type,
                outcome=outcome,
                source="users.router",
                operation_id=operation_id,
                actor_id=actor_id,
                subject_id=subject_id,
                reason=reason,
                metadata=metadata or {},
            ),
            org_id=org_id,
        )
    except SecurityEventPersistenceError as error:
        raise unavailable("Unable to record security event") from error


def record_outcome(
    db: Session,
    event_type: str,
    outcome: SecurityEventOutcome,
    operation_id: UUID,
    actor_id: UUID,
    target_id: UUID,
    reason: str | None = None,
    *,
    metadata: dict[str, Any] | None = None,
    record: Callable[..., None] = record_security_event,
) -> None:
    """The event in the request's organization; ``metadata`` only when given."""

    record(
        event_type=event_type,
        outcome=outcome,
        operation_id=operation_id,
        actor_id=actor_id,
        subject_id=target_id,
        reason=reason,
        org_id=session_organization(db),
        **({"metadata": metadata} if metadata else {}),
    )


def invitation_security_event(
    *,
    event_type: str,
    outcome: SecurityEventOutcome,
    operation_id: UUID,
    actor_id: UUID | None = None,
    subject_id: UUID | None = None,
    reason: str | None = None,
    org_id: UUID | None = None,
    append: Callable[..., Any] = append_committed_security_event,
) -> None:
    """An invitation outcome, committed on its own session (source ``users.service``)."""

    try:
        append(
            SecurityEventIngestRequest(
                event_type=event_type,
                outcome=outcome,
                source="users.service",
                operation_id=operation_id,
                actor_id=actor_id,
                subject_id=subject_id,
                reason=reason,
            ),
            org_id=org_id,
        )
    except SecurityEventPersistenceError as error:
        raise InvitationError("Unable to record security event") from error


def record_invitation_failure(
    operation_id: UUID,
    actor_id: UUID | None,
    *,
    event_type: str = "user.invitation",
    subject_id: UUID | None = None,
    org_id: UUID | None = None,
    event: Callable[..., None] = invitation_security_event,
) -> None:
    """Record a secondary failure event without replacing the primary safe error."""

    try:
        event(
            event_type=event_type,
            outcome=SecurityEventOutcome.FAILURE,
            operation_id=operation_id,
            actor_id=actor_id,
            subject_id=subject_id,
            org_id=org_id,
        )
    except InvitationError:
        pass
