"""Release a derived link before a person's hard delete removes its target (SD8, R7).

This module imports only the link model, so any system can call it before a delete.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.organization_scope import bound_organization_column
from app.systems.sandbox.derived.models import SandboxDerivedObject


def release_derived_target(db: Session, *, conversation_id: UUID) -> None:
    """Set the link's target to NULL through the ORM, so the audit log records it.

    No commit: the caller's transaction owns it. The flush puts the link UPDATE before
    the caller's DELETE of the conversation at the database.
    """
    link = db.scalar(
        select(SandboxDerivedObject)
        .where(
            SandboxDerivedObject.org_id == bound_organization_column(),
            SandboxDerivedObject.conversation_id == conversation_id,
        )
    )
    if link is None:
        return
    link.conversation_id = None
    db.flush()
