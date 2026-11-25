"""Counts of what an installation uses against the edition limits.

One installation holds one organization (DEC-0050), so the organization-bound
counts below are the installation's counts.
"""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.users.models import Membership, User, UserRole, UserStatus
from app.systems.manage.licensing.editions import Limit
from app.systems.openview.worksheets.models import Worksheet
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record


def people(db: Session, *, guests: bool) -> int:
    """Admins and members (or guests), active or invited, not disabled, removed or expired."""

    roles = [UserRole.GUEST.value] if guests else [UserRole.ADMIN.value, UserRole.MEMBER.value]
    statement = (
        select(func.count(func.distinct(Membership.user_id)))
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.is_deleted.is_(False),
            Membership.role.in_(roles),
            Membership.status.in_([UserStatus.ACTIVE.value, UserStatus.PENDING.value]),
            User.is_deleted.is_(False),
            User.status != UserStatus.DISABLED.value,
            or_(Membership.expires_at.is_(None), Membership.expires_at > utc_now()),
        )
    )
    return db.scalar(statement) or 0


def departments(db: Session) -> int:
    return db.scalar(select(func.count(Department.id)).where(Department.is_deleted.is_(False))) or 0


def modules_in(db: Session, department_id: UUID) -> int:
    return db.scalar(
        select(func.count(Module.id)).where(
            Module.department_id == department_id, Module.is_deleted.is_(False)
        )
    ) or 0


def most_modules(db: Session) -> int:
    counts = (
        select(func.count(Module.id).label("n"))
        .where(Module.is_deleted.is_(False))
        .group_by(Module.department_id)
        .subquery()
    )
    return db.scalar(select(func.coalesce(func.max(counts.c.n), 0))) or 0


def records_in(db: Session, module_id: UUID) -> int:
    return db.scalar(
        select(func.count(Record.id)).where(
            Record.module_id == module_id, Record.is_deleted.is_(False)
        )
    ) or 0


def most_records(db: Session) -> int:
    counts = (
        select(func.count(Record.id).label("n"))
        .where(Record.is_deleted.is_(False))
        .group_by(Record.module_id)
        .subquery()
    )
    return db.scalar(select(func.coalesce(func.max(counts.c.n), 0))) or 0


def sheets(db: Session) -> int:
    return db.scalar(select(func.count(Worksheet.id)).where(Worksheet.is_deleted.is_(False))) or 0


def most_sheet_rows(db: Session) -> int:
    return db.scalar(
        select(func.coalesce(func.max(Worksheet.live_row_count), 0)).where(
            Worksheet.is_deleted.is_(False)
        )
    ) or 0


def all_usage(db: Session, only: set[Limit] | None = None) -> dict[Limit, int]:
    """The installation's use of each limit (or of `only`); per-container limits report the
    fullest container."""

    counters: dict[Limit, Callable[[], int]] = {
        Limit.SEATS: lambda: people(db, guests=False),
        Limit.GUESTS: lambda: people(db, guests=True),
        Limit.DEPARTMENTS: lambda: departments(db),
        Limit.MODULES: lambda: most_modules(db),
        Limit.RECORDS: lambda: most_records(db),
        Limit.SHEETS: lambda: sheets(db),
        Limit.SHEET_ROWS: lambda: most_sheet_rows(db),
    }
    return {limit: count() for limit, count in counters.items() if only is None or limit in only}
