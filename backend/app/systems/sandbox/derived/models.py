"""The stable link from a department to each item that its publish derived (SD8, BE-SD1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseModel

# One target column per kind of item; the group roles carry the group's access level.
GROUP_ROLES = ("managers", "members", "viewers")
DERIVED_ROLES = (*GROUP_ROLES, "dashboard", "category", "channel")


def _restrict(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["org_id", column], [f"{table}.org_id", f"{table}.id"],
        name=f"fk_sandbox_derived_objects_{column}_{table}", ondelete="RESTRICT",
    )


class SandboxDerivedObject(BaseModel):
    """One derived item of a department, found by this link and never by name (R5).

    The link outlives its target: a removed target leaves every target column NULL (R7).
    Link rows are never soft-deleted; ``closed_at`` records the department's close (R8).
    """

    __tablename__ = "sandbox_derived_objects"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_sandbox_derived_objects_org_id_id"),
        _restrict("department_id", "departments"),
        _restrict("group_id", "groups"),
        _restrict("dashboard_id", "dashboards"),
        _restrict("category_id", "comms_categories"),
        _restrict("conversation_id", "comms_conversations"),
        CheckConstraint(
            "role IN ('managers', 'members', 'viewers', 'dashboard', 'category', 'channel')",
            name="ck_sandbox_derived_objects_role",
        ),
        # At most one target, and a set target matches the role; all NULL is a released link.
        CheckConstraint(
            "num_nonnulls(group_id, dashboard_id, category_id, conversation_id) <= 1 "
            "AND (group_id IS NULL OR role IN ('managers', 'members', 'viewers')) "
            "AND (dashboard_id IS NULL OR role = 'dashboard') "
            "AND (category_id IS NULL OR role = 'category') "
            "AND (conversation_id IS NULL OR role = 'channel')",
            name="ck_sandbox_derived_objects_target",
        ),
        # Only a close that archived the channel records it, with the exact archive time (R8).
        CheckConstraint(
            "(NOT archived_by_close OR role = 'channel') "
            "AND (archived_by_close = (close_archived_at IS NOT NULL))",
            name="ck_sandbox_derived_objects_close_archive",
        ),
        UniqueConstraint(
            "org_id", "department_id", "role", name="uq_sandbox_derived_objects_department_role"
        ),
        UniqueConstraint("org_id", "group_id", name="uq_sandbox_derived_objects_group_id"),
        UniqueConstraint("org_id", "dashboard_id", name="uq_sandbox_derived_objects_dashboard_id"),
        UniqueConstraint("org_id", "category_id", name="uq_sandbox_derived_objects_category_id"),
        UniqueConstraint(
            "org_id", "conversation_id", name="uq_sandbox_derived_objects_conversation_id"
        ),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[UUID] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(nullable=True)
    dashboard_id: Mapped[UUID | None] = mapped_column(nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_close: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    close_archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
