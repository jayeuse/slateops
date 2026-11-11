"""Which departments' Dashboards a user reads, for Dashboard routes and Chart usage."""

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.systems.access.policy.checks import department_filter
from app.systems.access.policy.scope import effective_levels
from app.systems.access.users.models import User
from app.systems.sandbox.departments.models import Department


def dashboard_departments(
    db: Session, user: User, column: ColumnElement[Any] | Any
) -> ColumnElement[bool]:
    """Departments whose Dashboards the user reads: open ones, or every one for an administrator.

    A closed department answers like an unreadable one: Dashboard routes answer 404, and
    Chart usage lists only Dashboards of open departments for non-administrators.

    A write that passed this check just before a department close commits is accepted:
    it equals the same write landing just before the close, and it exposes no read. No
    department lock is taken, so the lock order of create and purge stays unchanged.
    """

    readable = department_filter(db, user, column)
    if effective_levels(db, user).unrestricted:
        return readable
    open_departments = select(Department.id).where(Department.is_deleted.is_(False))
    return and_(readable, column.in_(open_departments))
