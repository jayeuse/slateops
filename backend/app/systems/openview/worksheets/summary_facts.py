"""What My sheets shows beside each sheet (Screens, screen 7), read once for a page.

Nothing here reaches past what the viewer can see: the anchor is readable (the sheet is
listed), ``shared`` is answered only to the owner, and ``access_group`` names a group share
that gives the viewer the sheet.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.models import Group, GroupMember
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import Worksheet, WorksheetShare
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.display import record_title
from app.systems.sandbox.records.models import Record

_RANK = {"edit": 2, "view": 1}


@dataclass(frozen=True)
class SummaryFacts:
    anchor_title: str
    module_name: str
    shared: bool | None
    access_group: str | None


def _anchors(db: Session, sheets: Sequence[Worksheet]) -> dict[UUID, tuple[str, str]]:
    record_ids = {sheet.record_id for sheet in sheets if sheet.record_id is not None}
    records = {
        record.id: record
        for record in db.scalars(select(Record).where(Record.id.in_(record_ids)))
    } if record_ids else {}
    module_ids = {sheet.module_id for sheet in sheets if sheet.module_id is not None}
    module_ids |= {record.module_id for record in records.values()}
    modules = {
        module.id: module
        for module in db.scalars(select(Module).where(Module.id.in_(module_ids)))
    } if module_ids else {}
    anchors = {}
    for sheet in sheets:
        if sheet.record_id is not None:
            record = records[sheet.record_id]
            module = modules[record.module_id]
            anchors[sheet.id] = (record_title(db, record, module), module.module_name)
        elif sheet.module_id is not None:
            name = modules[sheet.module_id].module_name
            anchors[sheet.id] = (name, name)
    return anchors


def _group_access(db: Session, user: User, sheet_ids: list[UUID]) -> dict[UUID, str]:
    """For sheets the viewer gets only through a group: the group of the highest share."""

    if not sheet_ids:
        return {}
    direct = set(db.scalars(select(WorksheetShare.worksheet_id).where(
        WorksheetShare.worksheet_id.in_(sheet_ids), WorksheetShare.subject == "user",
        WorksheetShare.user_id == user.id, WorksheetShare.is_deleted.is_(False),
    )))
    rows = db.execute(
        select(WorksheetShare.worksheet_id, Group.name, WorksheetShare.level)
        .join(Group, Group.id == WorksheetShare.group_id)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(
            WorksheetShare.worksheet_id.in_(sheet_ids), WorksheetShare.subject == "group",
            WorksheetShare.is_deleted.is_(False), Group.is_deleted.is_(False),
            GroupMember.user_id == user.id, GroupMember.is_deleted.is_(False),
            Group.org_id == bound_organization_column(),
            GroupMember.org_id == bound_organization_column(),
        )
    ).tuples().all()
    best: dict[UUID, tuple[int, str]] = {}
    for sheet_id, name, level in rows:
        if sheet_id in direct:
            continue
        ranked = (-_RANK.get(level, 0), name)
        if sheet_id not in best or ranked < best[sheet_id]:
            best[sheet_id] = ranked
    return {sheet_id: ranked[1] for sheet_id, ranked in best.items()}


def summary_facts(
    db: Session, user: User, sheets: Sequence[Worksheet],
) -> dict[UUID, SummaryFacts]:
    anchors = _anchors(db, sheets)
    owned = [sheet.id for sheet in sheets if sheet.owner_id == user.id]
    shared = set(db.scalars(select(WorksheetShare.worksheet_id).where(
        WorksheetShare.worksheet_id.in_(owned), WorksheetShare.is_deleted.is_(False),
    ))) if owned else set()
    groups = _group_access(db, user, [sheet.id for sheet in sheets if sheet.id not in owned])
    return {
        sheet.id: SummaryFacts(
            anchor_title=anchors[sheet.id][0],
            module_name=anchors[sheet.id][1],
            shared=(sheet.id in shared) if sheet.owner_id == user.id else None,
            access_group=groups.get(sheet.id),
        )
        for sheet in sheets
    }
