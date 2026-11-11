"""workspace department setup defaults

BE-SD6 (setup spec `docs/specs/sandbox-department-setup.md`, SD2): each organization keeps the
setup items that a department added in the Sandbox starts with. The column has a constant
server default, so PostgreSQL gives every existing organization all four items without a
rewrite; nothing else changes. The CHECK repeats the `ip_allow_list` pattern (autogenerate does
not emit CHECK constraints on an existing table); the API validates the four keys.

`organizations` has table-level grants and no RLS, so no grant or policy is added. The revision
changes no `audit_logs` row (K36). The downgrade drops the column and its saved choices.

Revision ID: fcde5c2045b7
Revises: f9809993d133
Create Date: 2026-11-11 17:30:12.489696
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fcde5c2045b7"
down_revision: str | None = "f9809993d133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_workspace_profiles_department_setup_defaults"
ALL_ITEMS = """'{"groups": true, "dashboard": true, "category": true, "channel": true}'::jsonb"""


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "department_setup_defaults",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(ALL_ITEMS),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        CHECK, "organizations", "jsonb_typeof(department_setup_defaults) = 'object'"
    )


def downgrade() -> None:
    op.drop_constraint(CHECK, "organizations", type_="check")
    op.drop_column("organizations", "department_setup_defaults")
