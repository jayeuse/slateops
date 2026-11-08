"""Comms access results at Harbor size: one literal owner for the relation's outputs.

The expected sets are worked out by hand from the world in ``harbor_scale_support``;
they guard a performance-only change to the access relation (D36, D43, D44, D45).
"""

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.core.base_model import utc_now
from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import AccessLevel, Group, GroupAccess, GroupMember
from app.systems.access.policy.readers import active_account_clause
from app.systems.access.policy.scope import department_level_clause
from app.systems.access.users.membership import bound_membership_join
from app.systems.access.users.models import Membership, User
from app.systems.access.users.person_visibility import visible_person_ids
from app.systems.comms.access import (
    _conversation_access_statement,
    conversation_reader_counts,
    explain_conversation_access,
    readable_conversation_ids,
)
from app.systems.comms.conversations.models import (
    CommsChannelAccess,
    CommsConversation,
    CommsMember,
)
from app.systems.sandbox.departments.models import Department
from tests.comms.harbor_scale_support import HarborScale, build_harbor_scale

pytestmark = pytest.mark.integration


def test_harbor_scale_access_relation_results(policy_case):
    c, db = policy_case, policy_case.db
    world = build_harbor_scale(db, c.org.id, c.admin, c.peer)
    names = {identity: name for name, identity in world.conversations.items()}
    accounts, teams, guests = world.accounts, world.teams, world.guests

    def readable(user):
        return {names[identity] for identity in readable_conversation_ids(db, user)}

    organization = {"O0", "O1", "O2"}
    assert readable(accounts["writer"]) == organization | {
        "K0", "K1", "Grp0", "Grp1", "Grp2", "Grp3", "Dir1", "Dir3", "Dir5",
    }
    assert readable(accounts["guest"]) == organization | {"K3"}
    assert readable(guests[0]) == organization | {"K0", "K1", "K2", "K3", "K4", "K5"}
    assert readable(accounts["manager"]) == organization | {"K2", "GG0", "GG1"}
    assert readable(accounts["admin"]) == organization | {
        "K0", "K1", "K2", "K3", "K4", "K5", "Dir0", "Dir2", "Dir4",
    }
    assert readable(accounts["noaccess"]) == organization
    assert readable(teams[4][2]) == organization | {"K4", "GG0"}

    counts = conversation_reader_counts(db, world.channel_ids())
    assert {names[identity]: count for identity, count in counts.items()} == {
        "K0": 18, "K1": 18, "K2": 18, "K3": 18, "K4": 20, "K5": 19,
        "O0": 44, "O1": 44, "O2": 44,
    }

    explained = {
        (account, channel): explain_conversation_access(db, user, world.conversations[channel])
        for account, user, channel in (
            ("writer", accounts["writer"], "K0"),
            ("writer", accounts["writer"], "K1"),
            ("manager", accounts["manager"], "K2"),
            ("guest", accounts["guest"], "K3"),
            ("guest0", guests[0], "K2"),
            ("lead", teams[2][0], "K2"),
            ("admin", accounts["admin"], "K3"),
            ("noaccess", accounts["noaccess"], "K0"),
        )
    }
    assert {key: (row.level, row.manager_source, row.source) for key, row in explained.items()} == {
        ("writer", "K0"): ("post", None, {"kind": "grant"}),
        ("writer", "K1"): (
            "read", None, {"kind": "department", "department_id": db.get(
                CommsConversation, world.conversations["K1"]).department_id},
        ),
        ("manager", "K2"): (
            "manage", "department_manager",
            {"kind": "manager", "reason": "department_manager"},
        ),
        ("guest", "K3"): ("read", None, {"kind": "guest_cap"}),
        ("guest0", "K2"): ("read", None, {"kind": "guest_cap"}),
        ("lead", "K2"): (
            "manage", "department_manager",
            {"kind": "manager", "reason": "department_manager"},
        ),
        ("admin", "K3"): ("manage", None, {"kind": "admin"}),
        ("noaccess", "K0"): ("none", None, {"kind": "none", "reason": "no_access"}),
    }

    everyone = {person.id for person in world.people} | {c.actor.id}
    active = everyone - {person.id for person in world.inactive}
    # Organization channels make every active person visible to every other one.
    assert visible_person_ids(db, accounts["writer"], everyone) == active
    for name in organization:
        soft_deleted = db.get(CommsConversation, world.conversations[name])
        soft_deleted.is_deleted, soft_deleted.deleted_at = True, utc_now()
    db.flush()
    writer_peers = {
        *(person for n in (0, 1, 2, 3, 5) for person in teams[n]), teams[4][0], *guests,
        accounts["writer"], accounts["admin"],
    }
    assert visible_person_ids(db, accounts["writer"], everyone) == {
        person.id for person in writer_peers
    }
    guest_peers = {
        *teams[2], *teams[3], *(team[0] for team in teams), *guests,
        accounts["admin"], accounts["guest"],
    }
    assert visible_person_ids(db, accounts["guest"], everyone) == {
        person.id for person in guest_peers
    }

    # Department-row edges, organization channels still deleted: a deleted group, a
    # deleted group membership and a deleted department each remove only their path.
    def soft_delete(row):
        row.is_deleted, row.deleted_at = True, datetime(2000, 1, 1, tzinfo=UTC)
        db.flush()

    assert readable(teams[1][2]) == {"K1", "Grp1"}
    soft_delete(world.groups["Team 1"])
    assert readable(teams[1][2]) == {"Grp1"}
    assert readable(accounts["guest"]) == {"K3"}
    soft_delete(db.scalar(select(GroupMember).where(
        GroupMember.group_id == world.groups["Guest"].id,
        GroupMember.user_id == accounts["guest"].id,
    )))
    assert readable(accounts["guest"]) == set()
    assert readable(teams[4][2]) == {"K4", "GG0"}
    soft_delete(world.departments[4])
    assert readable(teams[4][2]) == {"GG0"}
    assert readable(guests[0]) == {"K0", "K1", "K2", "K3", "K5"}
    # An administrator keeps a department channel whose department is deleted.
    assert readable(accounts["admin"]) == {
        "K0", "K1", "K2", "K3", "K4", "K5", "Dir0", "Dir2", "Dir4",
    }


# Plan step 3.3: the relation reads its three inputs once each instead of once for each
# (conversation, person) pair. These cases pin today's values row by row (B5), keep every
# filter and case of the inputs (B6) and every conversation kind in the counts (B1).


def _soft_delete(row: Any) -> None:
    row.is_deleted, row.deleted_at = True, datetime(2000, 1, 1, tzinfo=UTC)


def _extend(case: Any, world: HarborScale) -> dict[str, UUID]:
    """Every filter and case the rewritten inputs must keep (B6, R4, B1)."""

    db, org_id, admin = case.db, case.org.id, case.admin
    accounts, teams, guests = world.accounts, world.teams, world.guests

    def channel(name: str, scope: str, department: Department | None = None,
                creator: Any = admin, members: tuple[Any, ...] = ()) -> UUID:
        kind = "group" if scope == "members" else "channel"
        row = CommsConversation(org_id=org_id, kind=kind, scope=scope,
                                name=f"Harbor {name}", created_by=creator.id,
                                department_id=department.id if department else None)
        db.add(row)
        db.flush()
        db.add_all(CommsMember(org_id=org_id, conversation_id=row.id, user_id=person.id,
                               role="member") for person in members)
        db.flush()
        world.conversations[name] = row.id
        return row.id

    def grant(conversation: str, level: str, *, user: Any = None, group: Any = None) -> None:
        db.add(CommsChannelAccess(
            org_id=org_id, conversation_id=world.conversations[conversation],
            subject="user" if user is not None else "group",
            user_id=user.id if user is not None else None,
            group_id=group.id if group is not None else None,
            level=level, created_by=admin.id,
        ))

    # A deleted department keeps its channel and its rows; only administrators read it.
    closed = Department(org_id=org_id, department_name="Harbor closed")
    db.add(closed)
    db.flush()
    db.add(GroupAccess(org_id=org_id, group_id=world.groups["Team 0"].id,
                       department_id=closed.id, level="manage"))
    channel("K6", "department", closed)
    _soft_delete(closed)
    # A deleted group and a deleted group member give nothing, through rows or grants.
    gone = Group(org_id=org_id, name="Harbor gone")
    db.add(gone)
    db.flush()
    db.add(GroupMember(org_id=org_id, group_id=gone.id, user_id=accounts["noaccess"].id))
    db.add(GroupAccess(org_id=org_id, group_id=gone.id,
                       department_id=world.departments[2].id, level="write"))
    grant("K5", "post", group=gone)
    _soft_delete(gone)
    left = GroupMember(org_id=org_id, group_id=world.groups["Reader"].id,
                       user_id=teams[5][4].id)
    db.add(left)
    db.flush()
    _soft_delete(left)
    # A deleted conversation membership is no membership.
    removed = CommsMember(org_id=org_id, conversation_id=world.conversations["Grp0"],
                          user_id=accounts["reader"].id, role="manager")
    db.add(removed)
    db.flush()
    _soft_delete(removed)
    # A guest with a post grant still only reads.
    grant("K1", "post", user=guests[0])
    # R4: two grant sources for one pair: a category user grant (post, from the world) and
    # a channel group grant; and a user grant beside a group grant on another channel.
    grant("K0", "read", group=world.groups["Writer"])
    grant("K2", "read", user=accounts["reader"])
    grant("K2", "post", group=world.groups["Reader"])
    # B1: a members conversation (the administrator has no membership row there), and a
    # department channel whose creator lost department read.
    channel("M0", "members", members=(accounts["writer"], teams[0][1]))
    channel("K7", "department", world.departments[1], creator=teams[2][1],
            members=(teams[2][1],))
    db.flush()
    return world.conversations


def test_the_relation_has_one_row_for_each_pair_with_todays_values(policy_case):
    c, db = policy_case, policy_case.db
    world = build_harbor_scale(db, c.org.id, c.admin, c.peer)
    _extend(c, world)
    conversations = select(CommsConversation.id).where(CommsConversation.org_id == c.org.id)
    people = [person.id for person in world.people] + [c.actor.id]

    def rows(statement: Select[Any]) -> list[tuple[Any, ...]]:
        return sorted(
            (row.conversation_id, row.user_id, row.level, row.role, row.manager, row.from_grant)
            for row in db.execute(statement)
        )

    rewritten = rows(_conversation_access_statement(conversations, people))
    today = rows(_todays_statement(conversations, people))

    pairs = [(row[0], row[1]) for row in rewritten]
    assert len(pairs) == len(set(pairs)) > 0
    assert rewritten == today


def test_counts_and_reads_cover_every_conversation_kind(policy_case):
    c, db = policy_case, policy_case.db
    world = build_harbor_scale(db, c.org.id, c.admin, c.peer)
    _extend(c, world)
    names = {identity: name for name, identity in world.conversations.items()}
    accounts, teams, guests = world.accounts, world.teams, world.guests

    def readable(user: Any) -> set[str]:
        return {names[identity] for identity in readable_conversation_ids(db, user)}

    counts = conversation_reader_counts(
        db, [world.conversations[name] for name in ("M0", "K6", "K7")]
    )
    assert {names[identity]: count for identity, count in counts.items()}["M0"] == 2
    assert "M0" not in readable(accounts["admin"])
    assert "K6" in readable(accounts["admin"])
    assert "K6" not in readable(teams[0][1])
    assert "K7" not in readable(teams[2][1])
    # Two grant sources on K2 (a user grant and a group grant); the department row gives K4.
    assert readable(accounts["reader"]) == {"O0", "O1", "O2", "K2", "K4"}
    assert explain_conversation_access(db, accounts["reader"], world.conversations["K2"]).level == (
        "post"
    )
    assert explain_conversation_access(db, guests[0], world.conversations["K1"]).level == "read"
    assert readable(accounts["noaccess"]) == {"O0", "O1", "O2"}
    assert "K2" not in readable(teams[5][4])
    assert "Grp0" not in readable(accounts["reader"])
    assert explain_conversation_access(db, accounts["writer"], world.conversations["K0"]).level == (
        "post"
    )


def _todays_statement(
    conversation_ids: Select[tuple[UUID]],
    user_ids: Collection[UUID],
) -> Select[Any]:
    """Today's relation, copied from `comms/access.py` before plan step 3.3 (B5)."""
    c, member = CommsConversation, CommsMember
    membership_role = (
        select(member.role)
        .where(
            member.org_id == bound_organization_column(),
            member.conversation_id == c.id,
            member.user_id == User.id,
            member.is_deleted.is_(False),
            member.deleted_at.is_(None),
        )
        .correlate(c, User)
        .scalar_subquery()
    )
    # The per-person form of department_level_reader_statement: it reads only this
    # person's group rows instead of rebuilding the department's whole reader set for
    # every (conversation, person) pair, which planned per pair and dominated cold reads.
    def department_level(minimum: AccessLevel) -> ColumnElement[bool]:
        return department_level_clause(
            User.id.expression, Membership.role.expression, c.department_id.expression, minimum,
        )

    department_rank = case(
        (department_level(AccessLevel.WRITE), 2),
        (department_level(AccessLevel.READ), 1),
        else_=0,
    )
    # D45: the best added grant of this channel or of its current category, for the person
    # or one of their live groups; read 1, post 2, never manage. An organization channel
    # already gives post, and direct or group messages have no category, so only the
    # department arm reads it.
    groups = (
        select(GroupMember.group_id)
        .join(Group, Group.id == GroupMember.group_id)
        .where(
            GroupMember.org_id == bound_organization_column(),
            Group.org_id == bound_organization_column(),
            GroupMember.user_id == User.id,
            GroupMember.is_deleted.is_(False),
            Group.is_deleted.is_(False),
        )
        .correlate(User)
    )
    grant = CommsChannelAccess
    granted = func.coalesce(
        select(func.max(case((grant.level == "post", 2), else_=1)))
        .where(
            grant.org_id == bound_organization_column(),
            grant.is_deleted.is_(False),
            grant.deleted_at.is_(None),
            or_(
                grant.conversation_id == c.id,
                and_(c.category_id.is_not(None), grant.category_id == c.category_id),
            ),
            or_(
                and_(grant.subject == "user", grant.user_id == User.id),
                and_(grant.subject == "group", grant.group_id.in_(groups)),
            ),
        )
        .correlate(c, User)
        .scalar_subquery(),
        0,
    )
    # Spec deviation 7: on a department channel a creator or roster manager row counts only
    # while the person still reads the channel by department role or D45 grant.
    current_reader = or_(
        c.scope != "department", department_level(AccessLevel.READ), granted > 0,
    )
    manager = case(
        (
            and_(membership_role.is_not(None), c.created_by == User.id, current_reader),
            "creator",
        ),
        (and_(membership_role == "manager", current_reader), "membership_manager"),
        (department_level(AccessLevel.MANAGE), "department_manager"),
        else_=None,
    )
    ordinary = case(
        (c.scope == "organization", 2),
        (c.scope == "department", func.greatest(department_rank, granted)),
        (and_(c.scope == "members", membership_role.is_not(None)), 2),
        else_=0,
    )
    uncapped = case(
        (
            and_(
                Membership.role == "admin",
                or_(
                    c.scope != "members",
                    membership_role.is_not(None),
                ),
            ),
            3,
        ),
        (manager.is_not(None), 3),
        else_=ordinary,
    )
    level = case((Membership.role == "guest", func.least(uncapped, 1)), else_=uncapped)
    return (
        select(
            c.id.label("conversation_id"),
            User.id.label("user_id"),
            level.label("level"),
            Membership.role.label("role"),
            manager.label("manager"),
            and_(c.scope == "department", granted > department_rank).label("from_grant"),
            c.scope,
            c.department_id,
        )
        .select_from(c)
        .join(User, User.id.in_(user_ids))
        .join(
            Membership,
            bound_membership_join(),
        )
        .where(
            c.org_id == bound_organization_column(),
            c.id.in_(conversation_ids),
            c.is_deleted.is_(False),
            c.deleted_at.is_(None),
            active_account_clause(),
        )
    )
