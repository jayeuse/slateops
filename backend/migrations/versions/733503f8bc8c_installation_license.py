"""installation license

The installation's one imported license file (spec `docs/specs/editions.md`). The table is
installation-wide like `update_statuses`, so it has no `org_id` and no RLS. The API reads it,
adds it and replaces it; it never deletes it.

Revision ID: 733503f8bc8c
Revises: d60adae1ec28
Create Date: 2026-11-25 12:34:02.321026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "733503f8bc8c"
down_revision: str | None = "d60adae1ec28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# An installation-wide table writes audit rows without an organization; the audit check lists
# each such table (the fresh root's `ck_audit_logs_organization`, plus this table).
ORGANIZATION_CHECK = """org_id IS NOT NULL OR entity_type IN ('users','platform_settings',
'platform_operators','backup_policies','backup_runs','backup_export_operations',
'update_statuses'{extra}) OR COALESCE((
COALESCE(NULLIF("after", 'null'::jsonb), "before") -> 'org_id' = 'null'::jsonb
AND ((entity_type = 'files' AND COALESCE(NULLIF("after", 'null'::jsonb),
"before") ->> 'purpose' = 'user_avatar') OR
(entity_type = 'in_app_notifications' AND COALESCE(NULLIF("after", 'null'::jsonb),
"before") ->> 'kind' = 'backup-failed'))), false)"""


def _organization_check(extra: str) -> None:
    op.drop_constraint("ck_audit_logs_organization", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_organization", "audit_logs", ORGANIZATION_CHECK.format(extra=extra)
    )


# The installation's default privileges grant every new table full DML; narrow it.
PRIVILEGES = (
    "REVOKE ALL ON TABLE public.installation_licenses FROM slateops_app",
    "GRANT SELECT, INSERT, UPDATE ON TABLE public.installation_licenses TO slateops_app",
)


def upgrade() -> None:
    op.create_table(
        "installation_licenses",
        sa.Column("singleton_key", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("license_text", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_through", sa.Date(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("performed_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "(is_deleted AND deleted_at IS NOT NULL) OR (NOT is_deleted AND deleted_at IS NULL)",
            name=op.f("ck_installation_licenses_deletion_state"),
        ),
        sa.CheckConstraint(
            "NOT is_deleted AND deleted_at IS NULL", name="ck_installation_licenses_live"
        ),
        sa.CheckConstraint(
            "length(license_text) BETWEEN 1 AND 4000", name="ck_installation_licenses_text"
        ),
        sa.CheckConstraint("singleton_key = true", name="ck_installation_licenses_singleton"),
        sa.PrimaryKeyConstraint("id", name=op.f("installation_licenses_pkey")),
        sa.UniqueConstraint("singleton_key", name="uq_installation_licenses_singleton"),
    )
    op.create_foreign_key(
        op.f("fk_installation_licenses_performed_by_users"),
        "installation_licenses",
        "users",
        ["performed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    for statement in PRIVILEGES:
        op.execute(statement)
    _organization_check(",'installation_licenses'")


def downgrade() -> None:
    _organization_check("")
    op.drop_table("installation_licenses")
