"""The three per-pair inputs of the Comms access relation, read once each (plan step 3.3).

Each input is filtered by the requested conversations and the requested people, grouped by
its join key, and never correlated to the outer (conversation, person) pair. The relation in
:mod:`app.systems.comms.access` joins them once, so C conversations and N people read each
table once (C + N reads), not once for each pair (C x N).

Each input is a ``MATERIALIZED`` CTE, so PostgreSQL computes it once for the statement. As
a plain derived table the planner may run it again for each outer row when its estimates
are low, and an input that embeds another relation (``visible_person_ids``) then grows
with every nesting. A caller's conversation set must therefore not be correlated to an
outer query; none is.
"""

from collections.abc import Collection
from typing import Any
from uuid import UUID

from sqlalchemy import CTE, Select, and_, case, func, or_, select, union_all
from sqlalchemy.orm import aliased

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group, GroupAccess, GroupMember
from app.systems.access.policy.readers import active_account_clause
from app.systems.access.users.membership import bound_membership_join
from app.systems.access.users.models import Membership, User
from app.systems.comms.conversations.models import (
    CommsChannelAccess,
    CommsConversation,
    CommsMember,
)
from app.systems.sandbox.departments.models import Department


def materialized(statement: Select[Any]) -> CTE:
    """``WITH <anonymous> AS MATERIALIZED (...)``: PostgreSQL computes it once.

    ``prefix_with`` returns a copy that keeps the anonymous name of the first CTE, and
    that name holds the first object's ``id()``. The copy keeps the first object alive,
    so no later CTE can reuse the address and with it the name.
    """

    plain = statement.cte()
    cte = plain.prefix_with("MATERIALIZED")
    cte._slateops_named_by = plain  # type: ignore[attr-defined]
    return cte


# Department-row ranks, as `department_level_clause` compares them: read 1, write 2, manage 3.
DEPARTMENT_RANK = {"read": 1, "write": 2, "manage": 3}


def requested_people(user_ids: Collection[UUID]) -> CTE:
    """The requested people who are active in the bound organization, with their role."""

    return materialized(
        select(User.id.label("user_id"), Membership.role.label("role"))
        .join(Membership, bound_membership_join())
        .where(User.id.in_(user_ids), active_account_clause())
    )


def live_departments(conversation_ids: Select[Any]) -> CTE:
    """The requested conversations' departments that are live in the bound organization."""

    conversation, department = aliased(CommsConversation), aliased(Department)
    org = bound_organization_column()
    return materialized(
        select(department.id)
        .where(
            department.org_id == org,
            department.is_deleted.is_(False),
            department.id.in_(
                select(conversation.department_id).where(
                    conversation.org_id == org, conversation.id.in_(conversation_ids)
                )
            ),
        )
    )


def member_roles(conversation_ids: Select[Any], user_ids: Collection[UUID]) -> CTE:
    """The live conversation role of each requested pair.

    `uq_comms_members_active` allows one row with `is_deleted IS FALSE` for each pair, so
    the input has at most one row for each pair without grouping.
    """

    member = aliased(CommsMember)
    return materialized(
        select(member.conversation_id, member.user_id, member.role)
        .where(
            member.org_id == bound_organization_column(),
            member.conversation_id.in_(conversation_ids),
            member.user_id.in_(user_ids),
            member.is_deleted.is_(False),
            member.deleted_at.is_(None),
        )
    )


def department_ranks(conversation_ids: Select[Any], user_ids: Collection[UUID]) -> CTE:
    """Each person's best live department row for the requested conversations' departments.

    The caller keeps the live-department check, the administrator arm and the guest cap.
    """

    conversation = aliased(CommsConversation)
    access, group, member = aliased(GroupAccess), aliased(Group), aliased(GroupMember)
    org = bound_organization_column()
    rank = case(
        *((access.level == level, value) for level, value in DEPARTMENT_RANK.items()), else_=0
    )
    departments = select(conversation.department_id).where(
        conversation.org_id == org, conversation.id.in_(conversation_ids)
    )
    return materialized(
        select(access.department_id, member.user_id, func.max(rank).label("best"))
        .join(group, group.id == access.group_id)
        .join(member, member.group_id == group.id)
        .where(
            access.org_id == org,
            group.org_id == org,
            member.org_id == org,
            access.is_deleted.is_(False),
            group.is_deleted.is_(False),
            member.is_deleted.is_(False),
            access.module_id.is_(None),
            access.department_id.in_(departments),
            member.user_id.in_(user_ids),
        )
        .group_by(access.department_id, member.user_id)
    )


def added_grants(conversation_ids: Select[Any], user_ids: Collection[UUID]) -> CTE:
    """D45: each person's best added grant on a requested conversation or its category.

    A grant to the person or to one of their live groups; read 1, post 2.
    """

    conversation, grant = aliased(CommsConversation), aliased(CommsChannelAccess)
    group, member = aliased(Group), aliased(GroupMember)
    org = bound_organization_column()
    rank = case((grant.level == "post", 2), else_=1)
    on_conversation = or_(
        grant.conversation_id == conversation.id,
        and_(conversation.category_id.is_not(None), grant.category_id == conversation.category_id),
    )
    live = (
        conversation.org_id == org,
        conversation.id.in_(conversation_ids),
        grant.org_id == org,
        grant.is_deleted.is_(False),
        grant.deleted_at.is_(None),
    )
    to_people = (
        select(conversation.id.label("conversation_id"), grant.user_id.label("user_id"),
               rank.label("rank"))
        .join(grant, on_conversation)
        .where(*live, grant.subject == "user", grant.user_id.in_(user_ids))
    )
    to_groups = (
        select(conversation.id, member.user_id, rank)
        .join(grant, on_conversation)
        .join(member, member.group_id == grant.group_id)
        .join(group, group.id == member.group_id)
        .where(
            *live,
            grant.subject == "group",
            member.org_id == org,
            group.org_id == org,
            member.is_deleted.is_(False),
            group.is_deleted.is_(False),
            member.user_id.in_(user_ids),
        )
    )
    every = union_all(to_people, to_groups).subquery("grant_sources")
    return materialized(
        select(every.c.conversation_id, every.c.user_id, func.max(every.c.rank).label("best"))
        .group_by(every.c.conversation_id, every.c.user_id)
    )
