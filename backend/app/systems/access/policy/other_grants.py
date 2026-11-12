"""Groups whose membership gives something beside their department and module access.

Three tables give a group's members more than ``group_access``: Board levels
(``board_groups``), Comms channel grants (``comms_channel_access``) and Comms
capability grants (``comms_capability_grants``). A group with a live row in any of
them must never be treated as "exactly this department access". The rule is the
loosest live rule of their readers (``is_deleted`` only), and it ignores whether the
Board, channel or category is live: a false "true" is harmless, a false "false" is not.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select, union
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import CompoundSelect

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.service import unavailable
from app.systems.boards.models import BoardGroup
from app.systems.comms.conversations.models import CommsChannelAccess
from app.systems.comms.settings.models import CommsCapabilityGrant


def groups_with_other_grants(db: Session, group_ids: Iterable[UUID]) -> frozenset[UUID]:
    """The given groups that have a live Board, channel or capability grant, in one query."""

    ids = sorted(set(group_ids))
    if not ids:
        return frozenset()
    org = bound_organization_column()
    sources: CompoundSelect[tuple[UUID | None]] = union(
        select(BoardGroup.group_id).where(
            BoardGroup.org_id == org,
            BoardGroup.group_id.in_(ids),
            BoardGroup.is_deleted.is_(False),
        ),
        select(CommsChannelAccess.group_id).where(
            CommsChannelAccess.org_id == org,
            CommsChannelAccess.subject == "group",
            CommsChannelAccess.group_id.in_(ids),
            CommsChannelAccess.is_deleted.is_(False),
        ),
        select(CommsCapabilityGrant.group_id).where(
            CommsCapabilityGrant.org_id == org,
            CommsCapabilityGrant.subject == "group",
            CommsCapabilityGrant.group_id.in_(ids),
            CommsCapabilityGrant.is_deleted.is_(False),
        ),
    )
    try:
        found = db.scalars(sources).all()
    except SQLAlchemyError as error:
        raise unavailable(db) from error
    return frozenset(group_id for group_id in found if isinstance(group_id, UUID))
