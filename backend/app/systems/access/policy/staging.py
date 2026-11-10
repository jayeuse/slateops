"""No-commit Access writes that another system's transaction calls (setup spec SD11, R3)."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.systems.access.policy.models import AccessLevel, Group, GroupAccess
from app.systems.access.policy.schemas import GroupAccessEntry, GroupCreate
from app.systems.access.policy.service import _validate_access_targets
from app.systems.access.users.membership import bound_organization


def stage_group(
    db: Session, *, department_id: UUID, name: str, level: AccessLevel, actor_id: UUID,
) -> Group:
    """Add a group with one access row on the whole department, and no members.

    The caller holds ``lock_projection`` and owns the actor's authority, the commit, and the
    rollback. The group route's input rules and target check apply; a name that an active
    group already uses fails at the flush on ``uq_groups_name_active_ci``.
    """
    payload = GroupCreate(name=name)
    entry = GroupAccessEntry(department_id=department_id, level=level)
    _validate_access_targets(db, [entry])
    group = Group(
        org_id=bound_organization(db),
        name=payload.name,
        description=payload.description,
        performed_by=actor_id,
    )
    db.add(group)
    db.flush()
    db.add(
        GroupAccess(
            org_id=group.org_id,
            group_id=group.id,
            department_id=entry.department_id,
            module_id=None,
            level=entry.level.value,
            performed_by=actor_id,
        )
    )
    db.flush()
    return group
