"""Edition checks at each point where use grows (spec editions.md, ED-3 to ED-9).

A check refuses only an action that adds an item above a limit; what exists
keeps working and nothing is deleted (DEC-0029 item 5).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.systems.access.users.models import Membership, UserRole
from app.systems.manage.licensing import usage
from app.systems.manage.licensing.editions import Edition, Feature, Limit
from app.systems.manage.licensing.state import current_state, is_read_only
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.record_triggers.models import RecordTrigger

LICENSING_PAGE = "Manage → Updates & licensing"
_FEATURE_NAMES = {
    Feature.OPENCOMMS: "OpenComms",
    Feature.DASHBOARDS: "Dashboards",
    Feature.REPORTS: "Reports",
    Feature.AUTOMATIONS: "Automations",
    Feature.GANTT: "Gantt view",
    Feature.AUDIT_VIEWER: "Audit viewer",
}
_LIMIT_WORDS = {
    Limit.SEATS: "{n} people (administrators and members)",
    Limit.GUESTS: "{n} guests",
    Limit.DEPARTMENTS: "{n} published departments",
    Limit.MODULES: "{n} modules in a department",
    Limit.RECORDS: "{n} records in a module",
    Limit.SHEETS: "{n} sheets",
    Limit.SHEET_ROWS: "{n} rows in a sheet",
}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def edition_limit(limit: Limit, allowed: int, edition_name: str) -> HTTPException:
    words = _LIMIT_WORDS[limit].format(n=f"{allowed:,}")
    return HTTPException(
        status_code=403,
        detail={
            "code": "edition_limit", "limit": limit.value, "allowed": allowed,
            "message": f"{edition_name} allows {words}. To add more, upgrade in "
            f"{LICENSING_PAGE}.",
        },
    )


def edition_required(feature: Feature) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": "edition_required", "feature": feature.value,
            "message": f"{_FEATURE_NAMES[feature]}: available in Office and Headquarters.",
        },
    )


def require_room(db: Session, limit: Limit, *, used: int, adding: int = 1) -> None:
    terms = current_state(db).terms
    allowed = terms.limits[limit]
    if allowed is not None and adding > 0 and used + adding > allowed:
        raise edition_limit(limit, allowed, terms.name)


def limited(db: Session, limit: Limit) -> bool:
    return current_state(db).terms.limits[limit] is not None


def require_person(db: Session, role: str) -> None:
    """One more admin or member (a seat), or one more guest."""

    guest = role == UserRole.GUEST.value
    limit = Limit.GUESTS if guest else Limit.SEATS
    if limited(db, limit):
        require_room(db, limit, used=usage.people(db, guests=guest))


def require_records(db: Session, module_id: UUID, adding: int = 1) -> None:
    if limited(db, Limit.RECORDS):
        require_room(db, Limit.RECORDS, used=usage.records_in(db, module_id), adding=adding)


def require_sheet(db: Session) -> None:
    if limited(db, Limit.SHEETS):
        require_room(db, Limit.SHEETS, used=usage.sheets(db))


def require_sheet_rows(db: Session, rows: int, adding: int) -> None:
    if limited(db, Limit.SHEET_ROWS):
        require_room(db, Limit.SHEET_ROWS, used=rows, adding=adding)


def require_first_organization(db: Session) -> None:
    """Every edition holds one organization (DEC-0050); development and test hold any number."""

    if current_state(db).terms.edition is Edition.DEVELOPMENT:
        return
    existing = db.scalar(
        select(func.count(WorkspaceProfile.id)).where(WorkspaceProfile.is_deleted.is_(False))
    )
    if existing:
        raise ValueError("Each Slate Operations edition holds one organization")


def has_feature(db: Session, feature: Feature) -> bool:
    return feature in current_state(db).terms.features


def require_feature(db: Session, feature: Feature) -> None:
    if not has_feature(db, feature):
        raise edition_required(feature)


def feature_gate(feature: Feature) -> Callable[..., Any]:
    """A router dependency: every route of an Office feature answers 403 on Desk (ED-7)."""

    def gate(db: Annotated[Session, Depends(get_db)]) -> None:
        require_feature(db, feature)

    return gate


@dataclass(frozen=True)
class StructureCounts:
    departments: int
    modules: dict[UUID, int]
    triggers: int


def structure_counts(db: Session) -> StructureCounts:
    modules = db.execute(
        select(Module.department_id, func.count(Module.id))
        .where(Module.is_deleted.is_(False))
        .group_by(Module.department_id)
    ).all()
    triggers = db.scalar(
        select(func.count(RecordTrigger.id)).where(RecordTrigger.is_deleted.is_(False))
    )
    return StructureCounts(
        usage.departments(db), {row[0]: row[1] for row in modules}, triggers or 0
    )


def require_publish_growth(db: Session, before: StructureCounts) -> None:
    """A publish may not create a department, module or automation above the edition (ED-4)."""

    db.flush()
    after = structure_counts(db)
    if after.triggers > before.triggers:
        require_feature(db, Feature.AUTOMATIONS)
    if after.departments > before.departments:
        require_room(db, Limit.DEPARTMENTS, used=before.departments,
                     adding=after.departments - before.departments)
    for department_id, count in after.modules.items():
        had = before.modules.get(department_id, 0)
        if count > had:
            require_room(db, Limit.MODULES, used=had, adding=count - had)


def refuse_read_only_write(request: Request, db: Session, membership: Membership) -> None:
    """In the read-only state, only administrators change anything (ED-9)."""

    if (request.method not in _SAFE_METHODS and membership.role != UserRole.ADMIN.value
            and not request.url.path.startswith("/api/auth/") and is_read_only(db)):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "license_read_only",
                "message": "Slate Operations is read-only until your administrator renews "
                "the license.",
            },
        )
