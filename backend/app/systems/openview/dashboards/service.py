"""One active home Dashboard per department (BE3).

The partial unique index ``uq_dashboards_department_home`` is the arbiter; these helpers
keep a department that has active Dashboards pointed at one of them. They only mutate:
the calling route commits. Changing which Dashboard is home does not change any
Dashboard's revision, since no one edits the promoted Dashboard.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.openview.dashboards.models import Dashboard
from app.systems.openview.dashboards.schemas import DashboardCreate
from app.systems.sandbox.departments.models import Department


def claim_home_if_missing(db: Session, dashboard: Dashboard) -> None:
    """Make an active Dashboard its department's home when the department has none.

    No autoflush: the flag joins the caller's pending insert or update, so the audit log
    records one change, not a second update for the flag.
    """
    with db.no_autoflush:
        current = db.scalar(
            select(Dashboard.id).where(
                Dashboard.department_id == dashboard.department_id,
                Dashboard.is_home.is_(True),
                Dashboard.is_deleted.is_(False),
                Dashboard.id != dashboard.id,
            )
        )
    if current is None:
        dashboard.is_home = True


def stage_dashboard(db: Session, *, department_id: UUID, name: str) -> Dashboard:
    """Add an empty, manual-refresh Dashboard at position 0; it is home if none exists.

    No commit (setup spec SD11): the caller owns the actor's authority, the department lock
    order, the commit, and the rollback. The create route's input rules and its open
    department check apply.
    """
    payload = DashboardCreate(department_id=department_id, name=name)
    department = db.scalar(
        select(Department).where(
            Department.id == payload.department_id, Department.is_deleted.is_(False)
        )
    )
    if department is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "dashboard_invalid", "message": "The department is unavailable"},
        )
    dashboard = Dashboard(
        org_id=department.org_id,
        department_id=department.id,
        position=payload.position,
        name=payload.name,
        refresh_cadence=payload.refresh_cadence,
    )
    db.add(dashboard)
    claim_home_if_missing(db, dashboard)
    db.flush()
    return dashboard


def hand_over_home(db: Session, archived: Dashboard) -> None:
    """After archiving the home, make the next active Dashboard by position the home."""
    if not archived.is_home:
        return
    archived.is_home = False
    # The archived row leaves the index first, so the promotion never meets a second home.
    db.flush()
    successor = db.scalar(
        select(Dashboard)
        .where(
            Dashboard.department_id == archived.department_id,
            Dashboard.is_deleted.is_(False),
            Dashboard.id != archived.id,
        )
        .order_by(Dashboard.position, Dashboard.id)
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if successor is not None:
        successor.is_home = True
