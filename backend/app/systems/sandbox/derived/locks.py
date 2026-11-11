"""The publish's locks on linked items whose department it renames, closes or reopens (SD19).

Step 2: the linked groups ``FOR UPDATE`` in id order, before ``lock_module_access`` takes every
live group ``FOR SHARE``. A row already held ``FOR UPDATE`` is never upgraded later, so a
member's access check (share locks on its groups) waits here and holds nothing the publish
needs. Step 4: the linked dashboards, categories and conversations ``FOR UPDATE``, in that
order and each in id order, after the structure locks and before the locked plan.

The departments are read after ``_locked_document`` and under ``lock_projection``; every
writer of link rows and of department names or states holds one of them, so the set cannot
change before the plan. ``covers`` checks that anyway, as a guard and not as the guarantee.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group
from app.systems.comms.conversations.models import CommsCategory, CommsConversation
from app.systems.openview.dashboards.models import Dashboard
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.actions import GROUP_LEVELS
from app.systems.sandbox.derived.models import SandboxDerivedObject
from app.systems.sandbox.derived.sync import FOLLOW_KINDS
from app.systems.sandbox.publications.models import SandboxBinding
from app.systems.sandbox.publications.schemas import PublicationChange

_TARGET_LOCKS: tuple[tuple[str, type[Dashboard | CommsCategory | CommsConversation]], ...] = (
    ("dashboard_id", Dashboard),
    ("category_id", CommsCategory),
    ("conversation_id", CommsConversation),
)


@dataclass
class DerivedLocks:
    groups: frozenset[UUID]
    targets: set[UUID] = field(default_factory=set)

    def lock_targets(self, db: Session, document: Any) -> None:
        """SD19 step 4: dashboards, then categories, then conversations, each in id order."""

        links = _links(db, followed_departments(db, document))
        for column, model in _TARGET_LOCKS:
            ids = sorted({getattr(link, column) for link in links} - {None})
            if ids:
                db.scalars(
                    select(model.id).where(model.id.in_(ids)).order_by(model.id).with_for_update()
                ).all()
                self.targets.update(ids)

    def covers(self, db: Session, changes: Iterable[PublicationChange]) -> bool:
        """True when every follow change of the plan targets a row locked above."""

        follow = [
            change
            for change in changes
            if change.kind in FOLLOW_KINDS and change.action != "create"
        ]
        if not follow:
            return True
        keys = {
            key: identity
            for key, identity in db.execute(
                select(SandboxBinding.sandbox_id, SandboxBinding.department_id).where(
                    SandboxBinding.kind == "department", SandboxBinding.is_deleted.is_(False)
                )
            ).tuples()
        }
        links = {
            (link.department_id, link.role): link
            for link in _links(db, [value for value in keys.values() if value is not None])
        }
        for change in follow:
            key, role = change.sandbox_id.rsplit("#", 1)
            link = links.get((keys.get(key), role))  # type: ignore[arg-type]
            target = (
                None
                if link is None
                else link.group_id or link.dashboard_id or link.category_id or link.conversation_id
            )
            locked = self.groups if role in GROUP_LEVELS else self.targets
            if target is None or target not in locked:
                return False
        return True


def lock_followed_groups(db: Session, document: Any) -> DerivedLocks:
    """SD19 step 2: call it directly before ``lock_operational_rows``, whose first step is
    ``lock_module_access``'s ``FOR SHARE`` pass over every live group."""

    ids = sorted(
        {
            link.group_id
            for link in _links(db, followed_departments(db, document))
            if link.group_id is not None
        }
    )
    if ids:
        db.scalars(
            select(Group.id).where(Group.id.in_(ids)).order_by(Group.id).with_for_update()
        ).all()
    return DerivedLocks(frozenset(ids))


def followed_departments(db: Session, document: Any) -> list[UUID]:
    """Bound departments whose draft name or state differs from the live one (SD9)."""

    draft = {item.id: item for item in document.design.departments}
    followed: list[UUID] = []
    for key, identity, name, deleted in db.execute(
        select(
            SandboxBinding.sandbox_id,
            Department.id,
            Department.department_name,
            Department.is_deleted,
        )
        .join(Department, Department.id == SandboxBinding.department_id)
        .where(SandboxBinding.kind == "department", SandboxBinding.is_deleted.is_(False))
        .order_by(Department.id)
    ).tuples():
        desired = draft.get(key)
        if (desired is None and not deleted) or (
            desired is not None and (desired.name != name or desired.closed != deleted)
        ):
            followed.append(identity)
    return followed


def _links(db: Session, department_ids: list[UUID]) -> list[SandboxDerivedObject]:
    if not department_ids:
        return []
    return list(
        db.scalars(
            select(SandboxDerivedObject).where(
                SandboxDerivedObject.org_id == bound_organization_column(),
                SandboxDerivedObject.department_id.in_(department_ids),
            )
        )
    )
