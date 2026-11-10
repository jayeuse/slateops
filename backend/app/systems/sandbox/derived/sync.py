"""Follow a department's name and state on its linked items (setup spec R6 to R10, SD10).

Both paths call ``sync_derived_objects`` beside the Board sync. It applies only the follow
steps that the path's plan computed with ``follow_steps`` (R15): the publish plan's derived
changes, or the lifecycle plan's ``derived_changes``. It never creates an item (R1), and it
changes only names, the channel's archive state, and the link rows' close record (R6, R8, R9).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group
from app.systems.comms.conversations.models import CommsCategory, CommsConversation
from app.systems.comms.realtime.events import organization_event
from app.systems.comms.realtime.grants import revoke_stale
from app.systems.manage.audit.context import get_audit_context
from app.systems.openview.dashboards.models import Dashboard
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.actions import (
    GROUP_LEVELS,
    FollowStep,
    LinkedItem,
    derived_name,
    follow_change,
)
from app.systems.sandbox.derived.models import SandboxDerivedObject
from app.systems.sandbox.publications.schemas import PublicationChange

FOLLOW_KINDS = ("group", "dashboard", "category", "channel")
_STAGED = "__sandbox_publish_"
Target = Group | Dashboard | CommsCategory | CommsConversation


def department_links(
    db: Session, department_ids: Collection[UUID]
) -> dict[UUID, list[SandboxDerivedObject]]:
    """The link rows of the departments, in id order."""

    links: dict[UUID, list[SandboxDerivedObject]] = {}
    if not department_ids:
        return links
    for link in db.scalars(
        select(SandboxDerivedObject)
        .where(
            SandboxDerivedObject.org_id == bound_organization_column(),
            SandboxDerivedObject.department_id.in_(department_ids),
        )
        .order_by(SandboxDerivedObject.id)
    ):
        links.setdefault(link.department_id, []).append(link)
    return links


def link_target(db: Session, link: SandboxDerivedObject) -> Target | None:
    for identity, model in (
        (link.group_id, Group),
        (link.dashboard_id, Dashboard),
        (link.category_id, CommsCategory),
        (link.conversation_id, CommsConversation),
    ):
        if identity is not None:
            return cast(Target | None, db.get(model, identity))
    return None


def linked_item(db: Session, link: SandboxDerivedObject) -> LinkedItem:
    """A link and its target's live state, as ``follow_steps`` reads them."""

    target = link_target(db, link)
    if target is None:
        return LinkedItem(link.role, None, "", removed=True, moved=False)
    department = getattr(target, "department_id", link.department_id)
    return LinkedItem(
        link.role,
        target.id,
        target.name,
        removed=target.is_deleted,
        moved=isinstance(target, CommsCategory | CommsConversation)
        and department != link.department_id,
        archived_at=getattr(target, "archived_at", None),
        archived_by_close=link.archived_by_close,
        close_archived_at=link.close_archived_at,
    )


def sync_derived_objects(
    db: Session, department: Department, steps: Iterable[FollowStep], actor_id: UUID | None
) -> list[FollowStep]:
    """Apply one department's planned follow steps; record its close or reopen on every link.

    No commit (R4). Renames run before the channel's archive or unarchive. Returns the steps
    as the rows read after the change, so the publish can compare them with its plan (SD25).
    The caller holds ``lock_projection`` and calls ``revoke_stale`` before its commit (SD27).
    """

    links = {
        link.role: link for link in department_links(db, [department.id]).get(department.id, [])
    }
    now = utc_now()
    made: list[FollowStep] = []
    for step in sorted(steps, key=lambda item: item.action != "update"):
        link = links.get(step.role)
        row = link_target(db, link) if link is not None else None
        if link is None or row is None or row.id != step.target_id:
            continue  # the plan was computed under the same locks; the caller compares
        if step.action == "update":
            row.name = step.name
            if isinstance(row, Group | Dashboard):
                row.revision += 1
        elif isinstance(row, CommsConversation):
            # The archive route's state change; the close records its exact archive time (R8).
            row.archived_at = now if step.action == "close" else None
            link.archived_by_close = step.action == "close"
            link.close_archived_at = row.archived_at
        else:
            continue
        row.updated_at = now
        if actor_id is not None:
            row.performed_by = actor_id
        made.append(FollowStep(step.role, row.id, step.action, row.name))
    _record_state(department, links.values(), now, actor_id)
    db.flush()
    comms = any(step.role in ("category", "channel") for step in made)
    # An operator path has no app actor and cannot forge a request event (as revoke_stale).
    if comms and get_audit_context(db).performed_by is not None:
        organization_event(db, "structure")
    return made


def _record_state(
    department: Department, links: Iterable[SandboxDerivedObject], now: Any, actor_id: UUID | None
) -> None:
    """R8 and R9: every link row records the close, and a reopen clears the whole record."""

    for link in links:
        if department.is_deleted and link.closed_at is None:
            link.closed_at = now
        elif not department.is_deleted and link.closed_at is not None:
            link.closed_at = None
            link.archived_by_close = False
            link.close_archived_at = None
        else:
            continue
        if actor_id is not None:
            link.performed_by = actor_id


def follow_derived_items(
    db: Session, changes: Iterable[PublicationChange], bindings: Any, actor_id: UUID
) -> list[PublicationChange]:
    """The publish path: apply the plan's follow changes and return them as made (SD25).

    Renamed derived group names are staged first, as department names are, so a swap of
    two department names publishes (R12, SD-C27). A publish that closes or reopens any
    department, or archives or unarchives a derived channel, revokes stale grants (SD27).
    """

    changes = list(changes)
    planned: dict[str, list[PublicationChange]] = {}
    for change in changes:
        if change.kind in FOLLOW_KINDS and change.action != "create":
            planned.setdefault(change.sandbox_id.rsplit("#", 1)[0], []).append(change)
    states = {
        change.sandbox_id
        for change in changes
        if change.kind == "department" and change.action in ("close", "reopen")
    }
    work: list[tuple[str, Department, list[FollowStep]]] = []
    for key in sorted(set(planned) | states):
        binding = bindings["department"].get(key)
        department = db.get(Department, binding.department_id) if binding is not None else None
        if department is None:
            continue
        work.append((key, department, _planned_steps(db, department, planned.get(key, []))))
    _stage_group_names(db, [step for _, _, steps in work for step in steps])
    made: list[PublicationChange] = []
    for key, department, steps in work:
        made += [
            follow_change(key, step)
            for step in sync_derived_objects(db, department, steps, actor_id)
        ]
    if states or any(change.kind == "channel" for change in made if change.action != "update"):
        revoke_stale(db)
    return made


def _planned_steps(
    db: Session, department: Department, changes: Iterable[PublicationChange]
) -> list[FollowStep]:
    links = {
        link.role: link for link in department_links(db, [department.id]).get(department.id, [])
    }
    steps: list[FollowStep] = []
    for change in changes:
        role = change.sandbox_id.rsplit("#", 1)[1]
        link = links.get(role)
        row = link_target(db, link) if link is not None else None
        if row is None:
            continue
        name = (
            derived_name(role, department.department_name)
            if change.action == "update"
            else row.name
        )
        action = cast(Any, change.action)
        steps.append(FollowStep(role, row.id, action, name))
    return steps


def _stage_group_names(db: Session, steps: Iterable[FollowStep]) -> None:
    """Free the active names of renamed derived groups before any takes its new name."""

    staged = False
    for step in steps:
        if step.action == "update" and step.role in GROUP_LEVELS:
            group = db.get(Group, step.target_id)
            if group is not None:
                group.name = f"{_STAGED}{group.id}"
                staged = True
    if staged:
        db.flush()


__all__ = [
    "department_links",
    "follow_derived_items",
    "linked_item",
    "sync_derived_objects",
]
