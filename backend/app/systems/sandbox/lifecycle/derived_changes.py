"""The derived items of a department lifecycle plan (setup spec R8 to R11, SD17, SD19, SD20).

A department close previews the derived channel's archive and names the department's other
open channels, which stay postable (BE-SD7, DQ1 a). A reopen does only what R9 defines and
reports it in its result. A purge lists the link rows it deletes and is blocked while any
OpenComms category or channel references the department (BE-SD4, OQ2 a).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.core.database.organization_scope import bound_organization_column
from app.systems.comms.conversations.models import CommsCategory, CommsConversation
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.actions import FollowStep, follow_steps
from app.systems.sandbox.derived.sync import department_links, linked_item
from app.systems.sandbox.lifecycle.purge_support import purge_row_state
from app.systems.sandbox.lifecycle.schemas import (
    DerivedChange,
    LifecycleBlocker,
    LifecycleBlockerCode,
    LifecycleOperation,
    LifecycleRowState,
)


@dataclass(frozen=True)
class LifecycleDerived:
    changes: tuple[DerivedChange, ...] = ()
    rows: tuple[LifecycleRowState, ...] = ()
    blockers: tuple[LifecycleBlocker, ...] = ()
    scope_ids: dict[str, tuple[UUID, ...]] = field(default_factory=dict)


def department_derived(
    db: Session, department: Department, operation: LifecycleOperation
) -> LifecycleDerived:
    """The derived part of a department plan; link rows and the channel join its lock scope."""

    links = department_links(db, [department.id]).get(department.id, [])
    link_ids = tuple(sorted(link.id for link in links))
    if operation is LifecycleOperation.PURGE:
        return LifecycleDerived(
            rows=tuple(purge_row_state(link) for link in links),
            blockers=tuple(_content_blockers(db, department)),
            scope_ids={"sandbox_derived_objects": link_ids},
        )
    steps = follow_steps(
        [linked_item(db, link) for link in links],
        renamed_to=None,
        transition="close" if operation is LifecycleOperation.CLOSE else "reopen",
    )
    changes = [
        DerivedChange(role=step.role, target_id=step.target_id, name=step.name, action=step.action)
        for step in steps
        if step.action != "update"
    ]
    if operation is LifecycleOperation.CLOSE:
        changes += _kept_channels(db, department, {change.target_id for change in changes})
    return LifecycleDerived(
        changes=tuple(changes),
        scope_ids={
            "sandbox_derived_objects": link_ids,
            "comms_conversations": tuple(
                sorted(link.conversation_id for link in links if link.conversation_id is not None)
            ),
        },
    )


def planned_steps(changes: tuple[DerivedChange, ...]) -> list[FollowStep]:
    """The steps that execution applies: every change except the ``keep`` rows."""

    return [
        FollowStep(change.role, change.target_id, change.action, change.name)
        for change in changes
        if change.action != "keep"
    ]


def _kept_channels(
    db: Session, department: Department, archived: set[UUID]
) -> list[DerivedChange]:
    """The department's other open channels, which stay postable (SD17), in Comms order."""

    return [
        DerivedChange(role="channel", target_id=row.id, name=row.name, action="keep")
        for row in db.scalars(
            select(CommsConversation)
            .where(
                CommsConversation.org_id == bound_organization_column(),
                CommsConversation.kind == "channel",
                CommsConversation.department_id == department.id,
                CommsConversation.is_deleted.is_(False),
                CommsConversation.archived_at.is_(None),
                CommsConversation.id.not_in(archived) if archived else true(),
            )
            .order_by(CommsConversation.position, CommsConversation.id)
        )
    ]


def _content_blockers(db: Session, department: Department) -> list[LifecycleBlocker]:
    """SD20: categories and channels that reference the department block its purge.

    Every row counts, archived and soft-deleted ones too: the foreign key refuses them all.
    """

    parts: list[str] = []
    for org, owner, one, many in (
        (CommsCategory.org_id, CommsCategory.department_id, "category", "categories"),
        (CommsConversation.org_id, CommsConversation.department_id, "channel", "channels"),
    ):
        count = int(
            db.scalar(
                select(func.count())
                .select_from(owner.class_)
                .where(org == bound_organization_column(), owner == department.id)
            )
            or 0
        )
        if count:
            parts.append(f"{count} {one if count == 1 else many}")
    if not parts:
        return []
    return [
        LifecycleBlocker(
            code=LifecycleBlockerCode.COMMS_DEPARTMENT_CONTENT,
            entity_type="departments",
            entity_id=department.id,
            detail=(
                f"{department.department_name} has {' and '.join(parts)} in OpenComms, "
                "so it stays closed"
            ),
            department_id=department.id,
            department_name=department.department_name,
        )
    ]
