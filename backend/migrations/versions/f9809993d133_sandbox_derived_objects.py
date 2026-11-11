"""sandbox derived objects

BE-SD1 (setup spec `docs/specs/sandbox-department-setup.md`, SD8): the link table from a
department to each item that its publish derives in Access, OpenView and Comms. Every key to
another organization table is the composite `(org_id, <column>)` pair with RESTRICT (D09); a
removed target leaves its column NULL through `release_derived_target`, never `SET NULL`.

The `performed_by` key is created inline: `users` exists already, so the root's deferred
`use_alter` form is not needed. The RLS policy repeats the root's `organization_rows` policy
of `sandbox_bindings` (no `FORCE`). The installation's default privileges give `slateops_app`
the same DML on the new table as on every other application table, so no GRANT is added.

The revision changes no data and no `audit_logs` row (SD5, K36). The downgrade drops the table
and its link rows, which only this feature writes.

Revision ID: f9809993d133
Revises: bd01bc005861
Create Date: 2026-11-10 23:29:06.651410
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9809993d133"
down_revision: str | None = "bd01bc005861"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "sandbox_derived_objects"
ROW_SECURITY = (
    f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY",
    f"""
CREATE POLICY organization_rows ON public.{TABLE} TO slateops_app USING
    ((org_id = ( SELECT (NULLIF(current_setting('slateops.org_id'::text, true),
    ''::text))::uuid AS "nullif"))) WITH CHECK ((org_id = ( SELECT
    (NULLIF(current_setting('slateops.org_id'::text, true), ''::text))::uuid AS
    "nullif")))
""",
)


def _restrict(column: str, table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["org_id", column], [f"{table}.org_id", f"{table}.id"],
        name=f"fk_{TABLE}_{column}_{table}", ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("dashboard_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "archived_by_close", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("close_archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("performed_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "(NOT archived_by_close OR role = 'channel') "
            "AND (archived_by_close = (close_archived_at IS NOT NULL))",
            name="ck_sandbox_derived_objects_close_archive",
        ),
        sa.CheckConstraint(
            "num_nonnulls(group_id, dashboard_id, category_id, conversation_id) <= 1 "
            "AND (group_id IS NULL OR role IN ('managers', 'members', 'viewers')) "
            "AND (dashboard_id IS NULL OR role = 'dashboard') "
            "AND (category_id IS NULL OR role = 'category') "
            "AND (conversation_id IS NULL OR role = 'channel')",
            name="ck_sandbox_derived_objects_target",
        ),
        sa.CheckConstraint(
            "role IN ('managers', 'members', 'viewers', 'dashboard', 'category', 'channel')",
            name="ck_sandbox_derived_objects_role",
        ),
        sa.CheckConstraint(
            "(is_deleted AND deleted_at IS NOT NULL) OR (NOT is_deleted AND deleted_at IS NULL)",
            name=op.f("ck_sandbox_derived_objects_deletion_state"),
        ),
        _restrict("category_id", "comms_categories"),
        _restrict("conversation_id", "comms_conversations"),
        _restrict("dashboard_id", "dashboards"),
        _restrict("department_id", "departments"),
        _restrict("group_id", "groups"),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name=op.f("fk_sandbox_derived_objects_org_id_organizations"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.id"],
            name=op.f("fk_sandbox_derived_objects_performed_by_users"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("sandbox_derived_objects_pkey")),
        sa.UniqueConstraint("org_id", "category_id", name="uq_sandbox_derived_objects_category_id"),
        sa.UniqueConstraint(
            "org_id", "conversation_id", name="uq_sandbox_derived_objects_conversation_id"
        ),
        sa.UniqueConstraint(
            "org_id", "dashboard_id", name="uq_sandbox_derived_objects_dashboard_id"
        ),
        sa.UniqueConstraint(
            "org_id", "department_id", "role", name="uq_sandbox_derived_objects_department_role"
        ),
        sa.UniqueConstraint("org_id", "group_id", name="uq_sandbox_derived_objects_group_id"),
        sa.UniqueConstraint("org_id", "id", name="uq_sandbox_derived_objects_org_id_id"),
    )
    for statement in ROW_SECURITY:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table(TABLE)
