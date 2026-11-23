"""People a sheet person can see: share candidates (route 25) and the people list.

Route 25 gives the owner the people they can see and their own groups; the people list
gives an owner or Edit recipient the people they can put in a person cell, themselves
included.
"""

from uuid import UUID

from sqlalchemy import func, literal, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group, GroupMember
from app.systems.access.policy.readers import active_account_clause
from app.systems.access.users.membership import bound_membership_join
from app.systems.access.users.models import Membership, User
from app.systems.access.users.person_visibility import visible_person_ids
from app.systems.openview.worksheets.schemas import (
    SheetGroupRef,
    SheetPersonRef,
    SheetShareCandidates,
)

# One page of each list; the search narrows it.
CANDIDATE_LIMIT = 20
# Members read per page before the visibility rule, so the rule gets bounded input.
_PAGE = 200


def like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def visible_people(db: Session, actor: User, pattern: str, *,
                   include_self: bool = False) -> list[SheetPersonRef]:
    """Matching active members in keyset pages, filtered by the visibility rule, until a
    page of visible people is full or the members run out (B3 review B-1)."""

    owner = actor

    name = func.coalesce(func.nullif(User.display_name, ""), User.username)
    members = (
        select(name.label("name"), User.id)
        .join(Membership, bound_membership_join())
        .where(
            active_account_clause(),
            *([] if include_self else [User.id != owner.id]),
            or_(
                User.display_name.ilike(pattern, escape="\\"),
                User.username.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(name, User.id)
        .limit(_PAGE)
    )
    people: list[SheetPersonRef] = []
    after: tuple[str, UUID] | None = None
    while len(people) < CANDIDATE_LIMIT:
        page = members if after is None else members.where(
            tuple_(name, User.id) > tuple_(literal(after[0]), literal(after[1]))
        )
        rows = db.execute(page).tuples().all()
        visible = visible_person_ids(db, owner, [user_id for _name, user_id in rows])
        if include_self:
            visible |= {owner.id}
        people += [
            SheetPersonRef(id=user_id, display_name=label)
            for label, user_id in rows if user_id in visible
        ]
        if len(rows) < _PAGE:
            break
        after = rows[-1]
    return people[:CANDIDATE_LIMIT]


def share_candidates(db: Session, owner: User, text: str) -> SheetShareCandidates:
    pattern = like(text)
    people = visible_people(db, owner, pattern)
    groups = db.execute(
        select(Group.id, Group.name)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(
            Group.org_id == bound_organization_column(),
            Group.is_deleted.is_(False),
            GroupMember.user_id == owner.id,
            GroupMember.is_deleted.is_(False),
            Group.name.ilike(pattern, escape="\\"),
        )
        .order_by(Group.name, Group.id)
        .limit(CANDIDATE_LIMIT)
    ).tuples().all()
    return SheetShareCandidates(
        people=people, groups=[SheetGroupRef(id=group_id, name=name) for group_id, name in groups]
    )


