"""worksheet row links match index

A From another sheet column finds a source sheet's live links in one column to one record
(the first match and the capped match count). Without this index the lookup scanned every
link to the record across all sheets (security review S-11, owner decision 2026-11-24).

Revision ID: 04cdf06c377e
Revises: 37bba4c7658e
Create Date: 2026-11-24 09:22:35.467289
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "04cdf06c377e"
down_revision: str | None = "37bba4c7658e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_worksheet_row_links_match", "worksheet_row_links",
        ["worksheet_id", "column_key", "target_record_id"], unique=False,
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worksheet_row_links_match", table_name="worksheet_row_links",
        postgresql_where=sa.text("is_deleted IS FALSE"),
    )
