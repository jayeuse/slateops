"""A publish's derived items: the review half and the creation half (setup spec slice 1).

The review lists every derived change (SD7), blocks a derived group name that cannot be used
(R12, BE-SD3), and digests the links of departments whose name or state the publish changes
(SD25). The creation half applies exactly the planned creates through each system's no-commit
helper (R3) and returns what it made, so the executor can compare it with the plan (R15).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group
from app.systems.access.policy.staging import stage_group
from app.systems.access.users.models import User
from app.systems.comms.conversations.models import CommsCategory, CommsConversation
from app.systems.comms.conversations.mutations import stage_category, stage_department_channel
from app.systems.comms.realtime.events import organization_event
from app.systems.manage.audit.context import get_audit_context
from app.systems.openview.dashboards.models import Dashboard
from app.systems.openview.dashboards.service import stage_dashboard
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.actions import (
    GROUP_LEVELS,
    DepartmentOutcome,
    derived_changes,
    derived_label,
    derived_name,
    role_kind,
)
from app.systems.sandbox.derived.models import DERIVED_ROLES, SandboxDerivedObject
from app.systems.sandbox.publications.schemas import PublicationBlocker, PublicationChange
from app.systems.sandbox.publications.structure_mutations import department_outcomes

DerivedRow = Group | Dashboard | CommsCategory | CommsConversation
_TARGETS: tuple[tuple[str, type[DerivedRow]], ...] = (
    ("group_id", Group),
    ("dashboard_id", Dashboard),
    ("category_id", CommsCategory),
    ("conversation_id", CommsConversation),
)


@dataclass(frozen=True, slots=True)
class DerivedPlan:
    changes: list[PublicationChange]
    blockers: list[PublicationBlocker]
    followed: list[UUID]


def plan_derived(
    db: Session, document: Any, bindings: Any, changes: Iterable[PublicationChange]
) -> DerivedPlan:
    """The derived changes, blockers, and digested departments of one publication plan."""

    created: set[str] = set()
    followed: set[UUID] = set()
    for change in changes:
        if change.kind != "department":
            continue
        if change.action == "create":
            created.add(change.sandbox_id)
        elif (binding := bindings["department"].get(change.sandbox_id)) is not None:
            followed.add(binding.department_id)
    outcomes = department_outcomes(db, document, bindings, created)
    return DerivedPlan(
        changes=derived_changes(outcomes),
        blockers=_name_blockers(db, outcomes),
        followed=sorted(followed),
    )


def _name_blockers(db: Session, outcomes: list[DepartmentOutcome]) -> list[PublicationBlocker]:
    """R12: a derived group name equal, ignoring case, to an active group or another one."""

    wanted = [
        (outcome, derived_name(role, outcome.name))
        for outcome in outcomes
        if outcome.created and not outcome.closed
        for role in GROUP_LEVELS
    ]
    if not wanted:
        return []
    active = {
        name.lower(): name
        for name in db.scalars(
            select(Group.name).where(
                Group.org_id == bound_organization_column(),
                Group.is_deleted.is_(False),
                func.lower(Group.name).in_({name.lower() for _, name in wanted}),
            )
        )
    }
    blockers: list[PublicationBlocker] = []
    same: dict[str, list[tuple[DepartmentOutcome, str]]] = {}
    for outcome, name in wanted:
        same.setdefault(name.lower(), []).append((outcome, name))
        if name.lower() in active:
            blockers.append(
                _blocker(
                    outcome.key,
                    f'{outcome.name} needs the group name "{name}", '
                    f'which "{active[name.lower()]}" already uses',
                )
            )
    for group in same.values():
        if len(group) > 1:
            departments = [outcome.name for outcome, _ in group]
            together = ", ".join(departments[:-1]) + " and " + departments[-1]
            blockers.append(
                _blocker(group[1][0].key, f'{together} need the same group name "{group[0][1]}"')
            )
    return blockers


def _blocker(target_id: str, message: str) -> PublicationBlocker:
    return PublicationBlocker(code="derived_name_unavailable", message=message, target_id=target_id)


def followed_digest_rows(db: Session, department_ids: list[UUID]) -> list[list[object]]:
    """SD25: the link rows and live targets of the departments this publish renames,
    closes, or reopens, so a change to any of them after the review refuses the publish."""

    if not department_ids:
        return []
    rows: list[list[object]] = []
    for link in db.scalars(
        select(SandboxDerivedObject)
        .where(
            SandboxDerivedObject.org_id == bound_organization_column(),
            SandboxDerivedObject.department_id.in_(department_ids),
        )
        .order_by(SandboxDerivedObject.id)
    ):
        row: list[object] = [
            str(link.id),
            str(link.department_id),
            link.role,
            link.archived_by_close,
            _iso(link.closed_at),
            _iso(link.close_archived_at),
            _iso(link.updated_at),
        ]
        for column, model in _TARGETS:
            identity = getattr(link, column)
            target = db.get(model, identity) if identity is not None else None
            row.append(None if target is None else _target_state(target))
        rows.append(row)
    return rows


def _target_state(target: Any) -> list[object]:
    return [
        str(target.id),
        target.name,
        target.is_deleted,
        _iso(target.updated_at),
        str(getattr(target, "department_id", None)),
        _iso(getattr(target, "archived_at", None)),
    ]


def _iso(value: Any) -> str | None:
    return None if value is None else str(value.isoformat())


def create_derived_items(
    db: Session,
    changes: Iterable[PublicationChange],
    departments: Mapping[str, Department],
    actor_id: UUID,
) -> list[PublicationChange]:
    """Apply the plan's derived creates and return the changes made, read from the rows.

    No commit (R4). Every row goes through its system's helper and the audited session (R3);
    each item gets one link row (R5). Comms creation sends the Comms route events (R17).
    """

    roles: dict[str, set[str]] = {}
    for change in changes:
        if change.kind in ("group", "dashboard", "category", "channel") and (
            change.action == "create"
        ):
            key, role = change.sandbox_id.rsplit("#", 1)
            roles.setdefault(key, set()).add(role)
    if not roles:
        return []
    actor = db.get(User, actor_id)
    if actor is None:
        raise ValueError("The publishing administrator is unavailable")
    made: list[PublicationChange] = []
    for key in sorted(roles):
        department = departments[key]
        category: CommsCategory | None = None
        for role in DERIVED_ROLES:
            if role not in roles[key]:
                continue
            row = _stage(db, role, department, actor, category)
            if isinstance(row, CommsCategory):
                category = row
            column = next(name for name, model in _TARGETS if isinstance(row, model))
            db.add(
                SandboxDerivedObject(
                    org_id=department.org_id,
                    department_id=department.id,
                    role=role,
                    performed_by=actor_id,
                    **{column: row.id},
                )
            )
            made.append(made_change(key, role, row))
    db.flush()
    comms = any(change.kind in ("category", "channel") for change in made)
    # An operator path has no app actor and cannot forge a request event (as revoke_stale).
    if comms and get_audit_context(db).performed_by is not None:
        organization_event(db, "structure")
        organization_event(db, "grants")
    return made


def made_change(key: str, role: str, row: DerivedRow) -> PublicationChange:
    """The change a created row is, named from the row itself (SD25 comparison)."""

    kind = (
        "group"
        if isinstance(row, Group)
        else "dashboard"
        if isinstance(row, Dashboard)
        else "category"
        if isinstance(row, CommsCategory)
        else "channel"
    )
    label = derived_label(role, row.name) if kind == "group" else row.name
    return PublicationChange.model_validate(
        {"kind": kind, "action": "create", "sandboxId": f"{key}#{role}", "label": label}
    )


def _stage(
    db: Session, role: str, department: Department, actor: User, category: CommsCategory | None
) -> DerivedRow:
    name = derived_name(role, department.department_name)
    kind = role_kind(role)
    if kind == "group":
        return stage_group(
            db,
            department_id=department.id,
            name=name,
            level=GROUP_LEVELS[role],
            actor_id=actor.id,
        )
    if kind == "dashboard":
        return stage_dashboard(db, department_id=department.id, name=name)
    if kind == "category":
        return stage_category(db, department_id=department.id, name=name)
    if category is None:
        raise ValueError("A derived channel needs its department's category")
    return stage_department_channel(
        db, actor, department_id=department.id, category_id=category.id, name=name
    )
