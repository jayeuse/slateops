"""worksheets

Sheets B1 (spec `docs/specs/sheets.md` D1, APR-0016): the five sheet tables and the
membership release cutoff. Every key to another organization table is the composite
`(org_id, <column>)` pair with RESTRICT (D09). Links and revisions refer to their row through
`(org_id, worksheet_id, row_id)`, so neither can point at a row of another sheet.

The `performed_by` keys are created inline: `users` exists already, so the root's deferred
`use_alter` form is not needed. Each table gets the root's `organization_rows` policy for
`slateops_app` (no `FORCE`). The installation's default privileges give `slateops_app` full
DML on new tables; sheet history is insert-only, so UPDATE on `worksheet_row_revisions` is
revoked from that role. DELETE stays for the purge. `memberships` keeps no RLS.

The revision changes no data and no `audit_logs` row (K36). The downgrade drops the five
tables, their rows, and the release times in `memberships`; only this feature writes them.

Revision ID: 37bba4c7658e
Revises: 4f8324236e1e
Create Date: 2026-11-24 02:21:54.951287
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "37bba4c7658e"
down_revision: str | None = "4f8324236e1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "worksheets", "worksheet_rows", "worksheet_shares", "worksheet_row_links",
    "worksheet_row_revisions",
)
ORGANIZATION_ROWS = """
CREATE POLICY organization_rows ON public.{table} TO slateops_app USING
    ((org_id = ( SELECT (NULLIF(current_setting('slateops.org_id'::text, true),
    ''::text))::uuid AS "nullif"))) WITH CHECK ((org_id = ( SELECT
    (NULLIF(current_setting('slateops.org_id'::text, true), ''::text))::uuid AS
    "nullif")))
"""
DELETION_STATE = (
    "(is_deleted AND deleted_at IS NOT NULL) OR (NOT is_deleted AND deleted_at IS NULL)"
)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _base_columns() -> list[sa.Column]:
    return [
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
    ]


def _base_constraints(table: str) -> list[sa.Constraint]:
    return [
        sa.CheckConstraint(DELETION_STATE, name=op.f(f"ck_{table}_deletion_state")),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name=op.f(f"fk_{table}_org_id_organizations"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.id"],
            name=op.f(f"fk_{table}_performed_by_users"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"{table}_pkey")),
        sa.UniqueConstraint("org_id", "id", name=f"uq_{table}_org_id_id"),
    ]


def _users(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["users.id"], name=op.f(f"fk_{table}_{column}_users"), ondelete="RESTRICT",
    )


def _restrict(
    table: str, columns: list[str], target: str, target_columns: list[str],
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        columns, [f"{target}.{column}" for column in target_columns],
        name=f"fk_{table}_{columns[-1]}_{target}", ondelete="RESTRICT",
    )


def _row_key(table: str) -> sa.ForeignKeyConstraint:
    return _restrict(
        table, ["org_id", "worksheet_id", "row_id"], "worksheet_rows",
        ["org_id", "worksheet_id", "id"],
    )


def _worksheets() -> None:
    table = "worksheets"
    op.create_table(
        table,
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("module_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("structure", JSONB, nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("live_row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("data_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "btrim(title) <> '' AND char_length(title) <= 200", name="ck_worksheets_title"
        ),
        sa.CheckConstraint(
            "(record_id IS NULL) <> (module_id IS NULL)", name="ck_worksheets_anchor"
        ),
        sa.CheckConstraint("data_bytes BETWEEN 0 AND 8388608", name="ck_worksheets_data_bytes"),
        sa.CheckConstraint(
            "live_row_count BETWEEN 0 AND 10000", name="ck_worksheets_live_row_count"
        ),
        sa.CheckConstraint("revision > 0", name="ck_worksheets_revision"),
        _restrict(table, ["org_id", "module_id"], "modules", ["org_id", "id"]),
        _restrict(table, ["org_id", "record_id"], "records", ["org_id", "id"]),
        _users(table, "owner_id"),
        *_base_constraints(table),
    )
    op.create_index("ix_worksheets_module", table, ["org_id", "module_id"], unique=False)
    op.create_index("ix_worksheets_owner", table, ["owner_id", "org_id"], unique=False)
    op.create_index("ix_worksheets_record", table, ["org_id", "record_id"], unique=False)


def _worksheet_rows() -> None:
    table = "worksheet_rows"
    op.create_table(
        table,
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("worksheet_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.Column("data", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("data_bytes", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_base_columns(),
        sa.CheckConstraint("jsonb_typeof(data) = 'object'", name="ck_worksheet_rows_data_object"),
        sa.CheckConstraint("data_bytes BETWEEN 0 AND 32768", name="ck_worksheet_rows_data_bytes"),
        sa.CheckConstraint("revision > 0", name="ck_worksheet_rows_revision"),
        _restrict(table, ["org_id", "worksheet_id"], "worksheets", ["org_id", "id"]),
        *_base_constraints(table),
        sa.UniqueConstraint("org_id", "worksheet_id", "id", name="uq_worksheet_rows_sheet_row"),
    )
    op.create_index(
        "ix_worksheet_rows_order", table, ["worksheet_id", "position", "id"], unique=False,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def _worksheet_shares() -> None:
    table = "worksheet_shares"
    op.create_table(
        table,
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("worksheet_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "(subject = 'user' AND user_id IS NOT NULL AND group_id IS NULL) OR "
            "(subject = 'group' AND group_id IS NOT NULL AND user_id IS NULL)",
            name="ck_worksheet_shares_subject",
        ),
        sa.CheckConstraint("level IN ('view', 'edit')", name="ck_worksheet_shares_level"),
        _users(table, "created_by"),
        _restrict(table, ["org_id", "group_id"], "groups", ["org_id", "id"]),
        _restrict(table, ["org_id", "worksheet_id"], "worksheets", ["org_id", "id"]),
        _users(table, "user_id"),
        *_base_constraints(table),
    )
    op.create_index("ix_worksheet_shares_group", table, ["org_id", "group_id"], unique=False)
    op.create_index("ix_worksheet_shares_sheet", table, ["org_id", "worksheet_id"], unique=False)
    op.create_index("ix_worksheet_shares_user", table, ["org_id", "user_id"], unique=False)
    op.create_index(
        "uq_worksheet_shares_active", table,
        ["org_id", "worksheet_id", "subject", "user_id", "group_id"], unique=True,
        postgresql_nulls_not_distinct=True, postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def _worksheet_row_links() -> None:
    table = "worksheet_row_links"
    op.create_table(
        table,
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("worksheet_id", sa.Uuid(), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=False),
        sa.Column("column_key", sa.Text(), nullable=False),
        sa.Column("target_record_id", sa.Uuid(), nullable=True),
        sa.Column(
            "target_removed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "column_key ~ '^c[0-9a-z]{1,8}$'", name="ck_worksheet_row_links_column_key"
        ),
        sa.CheckConstraint(
            "(target_record_id IS NULL) = target_removed", name="ck_worksheet_row_links_target"
        ),
        _restrict(table, ["org_id", "target_record_id"], "records", ["org_id", "id"]),
        _row_key(table),
        *_base_constraints(table),
    )
    op.create_index(
        "ix_worksheet_row_links_sheet", table, ["org_id", "worksheet_id"], unique=False
    )
    op.create_index(
        "ix_worksheet_row_links_target", table, ["target_record_id"], unique=False,
        postgresql_where=sa.text("is_deleted IS FALSE AND target_record_id IS NOT NULL"),
    )
    op.create_index(
        "ix_worksheet_row_links_target_fk", table, ["org_id", "target_record_id"], unique=False
    )
    op.create_index(
        "uq_worksheet_row_links_cell", table, ["row_id", "column_key"], unique=True,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def _worksheet_row_revisions() -> None:
    table = "worksheet_row_revisions"
    op.create_table(
        table,
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("worksheet_id", sa.Uuid(), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("changed_keys", JSONB, nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'delete', 'restore')",
            name="ck_worksheet_row_revisions_action",
        ),
        sa.CheckConstraint("revision > 0", name="ck_worksheet_row_revisions_revision"),
        _row_key(table),
        *_base_constraints(table),
        sa.UniqueConstraint("row_id", "revision", name="uq_worksheet_row_revisions_row_revision"),
    )
    op.create_index(
        "ix_worksheet_row_revisions_history", table,
        ["org_id", "worksheet_id", "created_at", "id"], unique=False,
    )


def upgrade() -> None:
    _worksheets()
    _worksheet_rows()
    _worksheet_shares()
    _worksheet_row_links()
    _worksheet_row_revisions()
    op.add_column(
        "memberships",
        sa.Column("worksheets_released_at", sa.DateTime(timezone=True), nullable=True),
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(ORGANIZATION_ROWS.format(table=table))
    # Sheet history is insert-only for the application role (spec D1.5).
    op.execute("REVOKE UPDATE ON TABLE public.worksheet_row_revisions FROM slateops_app")


def downgrade() -> None:
    op.drop_column("memberships", "worksheets_released_at")
    for table in reversed(TABLES):
        op.drop_table(table)
