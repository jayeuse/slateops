"""The sheet access rule (spec D2): one SQL clause for every list, count and event set.

A sheet is private to its owner and its share recipients while the owner is present in its
organization. When the owner leaves, it opens read-only to every reader of its record or
module (spec D0: derived on each read, never stored). Administrators get no override.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy import Select, and_, case, exists, func, or_, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CompoundSelect, ScalarSelect

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.checks import module_filter
from app.systems.access.policy.models import AccessLevel, Group, GroupMember
from app.systems.access.policy.readers import active_account_clause
from app.systems.access.users.membership import current_membership
from app.systems.access.users.models import Membership, User, UserRole
from app.systems.openview.worksheets.models import Worksheet, WorksheetShare
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record

WorksheetLevel = Literal["owner", "edit", "view"]
_EDIT_RANK = 2


def worksheet_present_clause() -> ColumnElement[bool]:
    """The owner can act in the sheet's organization, and no release cutoff opened it.

    It needs a bound organization: ``active_account_clause`` compares the membership with
    ``slateops.org_id``, so an unbound transaction finds no owner present (every sheet open).
    Callers always run inside a bound request, worker or test transaction.
    """

    return exists(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(
            User.id == Worksheet.owner_id,
            Membership.org_id == Worksheet.org_id,
            active_account_clause(),
            or_(
                Membership.worksheets_released_at.is_(None),
                Membership.worksheets_released_at <= Worksheet.created_at,
            ),
        )
    )


def _anchor_clause(db: Session, user: User) -> ColumnElement[bool]:
    """A sheet of the bound organization on a live record or module the person can read."""

    readable_record = exists(
        select(Record.id).where(
            Record.id == Worksheet.record_id,
            Record.org_id == Worksheet.org_id,
            Record.is_deleted.is_(False),
            module_filter(db, user, AccessLevel.READ, Record.module_id),
        )
    )
    readable_module = exists(
        select(Module.id).where(
            Module.id == Worksheet.module_id,
            Module.org_id == Worksheet.org_id,
            Module.is_deleted.is_(False),
            module_filter(db, user, AccessLevel.READ, Module.id),
        )
    )
    return and_(
        Worksheet.org_id == bound_organization_column(),
        or_(readable_record, readable_module),
    )


def _base_clause(db: Session, user: User) -> ColumnElement[bool]:
    """A live sheet on a live record or module that the person can read."""

    return and_(Worksheet.is_deleted.is_(False), _anchor_clause(db, user))


def _share_clause(user_id: UUID) -> ColumnElement[bool]:
    """A live share of the sheet to the person, or to a live group they live-belong to."""

    groups = (
        select(GroupMember.group_id)
        .join(Group, Group.id == GroupMember.group_id)
        .where(
            GroupMember.user_id == user_id,
            GroupMember.org_id == bound_organization_column(),
            GroupMember.is_deleted.is_(False),
            Group.is_deleted.is_(False),
        )
    )
    return and_(
        WorksheetShare.worksheet_id == Worksheet.id,
        WorksheetShare.org_id == Worksheet.org_id,
        WorksheetShare.is_deleted.is_(False),
        or_(
            and_(WorksheetShare.subject == "user", WorksheetShare.user_id == user_id),
            and_(WorksheetShare.subject == "group", WorksheetShare.group_id.in_(groups)),
        ),
    )


def visible_worksheet_clause(db: Session, user: User) -> ColumnElement[bool]:
    """``visible(S, U)`` of spec D2, as a condition on ``Worksheet``."""

    return and_(
        _base_clause(db, user),
        or_(
            ~worksheet_present_clause(),
            Worksheet.owner_id == user.id,
            exists(select(WorksheetShare.id).where(_share_clause(user.id))),
        ),
    )


def my_worksheets_clause(db: Session, user: User) -> ColumnElement[bool]:
    """My sheets (P4): visible, and owned or shared; never an open sheet never shared."""

    return and_(
        visible_worksheet_clause(db, user),
        or_(
            Worksheet.owner_id == user.id,
            exists(select(WorksheetShare.id).where(_share_clause(user.id))),
        ),
    )


def own_deleted_worksheet_clause(db: Session, user: User) -> ColumnElement[bool]:
    """The person's own deleted sheets: every ``base`` condition but the deleted flag (R6)."""

    return and_(
        Worksheet.is_deleted.is_(True),
        Worksheet.owner_id == user.id,
        _anchor_clause(db, user),
    )


def _candidate_ids(user: User, org_id: UUID) -> CompoundSelect[UUID]:
    """Every sheet the person could see, found through indexes (B2 review N-2).

    Owned sheets (``ix_worksheets_owner``), sheets shared with the person or their groups
    (the share indexes), and the sheets of owners who may have left (their memberships in
    the organization). It is a superset: the exact rule still filters it.
    """

    groups = select(GroupMember.group_id).where(
        GroupMember.org_id == org_id,
        GroupMember.user_id == user.id,
        GroupMember.is_deleted.is_(False),
    )
    shared = select(WorksheetShare.worksheet_id).where(
        WorksheetShare.org_id == org_id,
        WorksheetShare.is_deleted.is_(False),
        or_(
            and_(WorksheetShare.subject == "user", WorksheetShare.user_id == user.id),
            and_(WorksheetShare.subject == "group", WorksheetShare.group_id.in_(groups)),
        ),
    )
    # An owner who is not present has a membership here that fails the account rule, or a
    # release cutoff. A sheet is only made by a member, so its owner always has one.
    departed = (
        select(Membership.user_id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.org_id == org_id,
            or_(~active_account_clause(), Membership.worksheets_released_at.is_not(None)),
        )
    )
    return union_all(
        select(Worksheet.id).where(Worksheet.owner_id == user.id, Worksheet.org_id == org_id),
        shared,
        select(Worksheet.id).where(
            Worksheet.owner_id.in_(departed), Worksheet.org_id == org_id
        ),
    )


def visible_worksheet_statement(db: Session, user: User, org_id: UUID) -> Select[UUID]:
    """The IDs of every sheet of the organization the person can see.

    It reads only the person's candidate sheets, so its cost does not grow with the private
    sheets of other people (the SSE snapshot runs for every subscriber on every event).
    """

    return select(Worksheet.id).where(
        Worksheet.org_id == org_id,
        Worksheet.id.in_(_candidate_ids(user, org_id)),
        visible_worksheet_clause(db, user),
    )


def visible_worksheet_ids(db: Session, user: User, org_id: UUID) -> frozenset[UUID]:
    """Every sheet of the organization the person can see, for the SSE snapshot."""

    return frozenset(db.scalars(visible_worksheet_statement(db, user, org_id)).all())


def load_visible_worksheet(db: Session, user: User, worksheet_id: UUID) -> Worksheet | None:
    """The sheet, or None alike for a missing, deleted or hidden one (one 404)."""

    return db.scalars(
        select(Worksheet).where(
            Worksheet.id == worksheet_id, visible_worksheet_clause(db, user)
        )
    ).one_or_none()


def _share_rank(user_id: UUID) -> ScalarSelect[int]:
    return (
        select(func.max(case((WorksheetShare.level == "edit", _EDIT_RANK), else_=1)))
        .where(_share_clause(user_id))
        .scalar_subquery()
    )


def _level(present: bool, owned: bool, rank: int | None, guest: bool) -> WorksheetLevel:
    if not present:
        return "view"
    if owned:
        return "owner"
    if rank == _EDIT_RANK and not guest:
        return "edit"
    return "view"


def worksheet_level(db: Session, user: User, worksheet: Worksheet) -> WorksheetLevel | None:
    """``level(S, U)`` of spec D2: None when hidden; an open sheet is View for everyone."""

    membership = current_membership(db, user)
    if membership is None:
        return None
    found = db.execute(
        select(worksheet_present_clause(), _share_rank(user.id)).select_from(Worksheet).where(
            Worksheet.id == worksheet.id, visible_worksheet_clause(db, user)
        )
    ).one_or_none()
    if found is None:
        return None
    present, rank = found
    return _level(
        present, worksheet.owner_id == user.id, rank, membership.role == UserRole.GUEST.value
    )


def worksheet_states(
    db: Session, user: User, worksheets: list[Worksheet]
) -> dict[UUID, tuple[bool, WorksheetLevel]]:
    """Present flag and level of each listed sheet in one statement.

    The caller lists only sheets the person may see (visible, or their own deleted ones).
    """

    membership = current_membership(db, user)
    if membership is None or not worksheets:
        return {}
    guest = membership.role == UserRole.GUEST.value
    owners = {sheet.id: sheet.owner_id == user.id for sheet in worksheets}
    rows = db.execute(
        select(Worksheet.id, worksheet_present_clause(), _share_rank(user.id)).where(
            Worksheet.id.in_(owners)
        )
    ).tuples()
    return {
        sheet_id: (present, _level(present, owners[sheet_id], rank, guest))
        for sheet_id, present, rank in rows
    }
