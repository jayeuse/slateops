"""users password change required

DEC-0042 (APR-0013): an administrator's temporary password sets
`users.password_change_required_at`; the person's own new password clears it. While it is set,
the person's sessions reach only their identity, the password change, MFA completion and
sign-out. The column is nullable with no default, so every existing account stays as it is
and PostgreSQL adds it without a rewrite.

`users` has table-level grants and no RLS, so no grant or policy is added. The revision
changes no `audit_logs` row (K36). The downgrade drops the column and any marks in it.

Revision ID: 4f8324236e1e
Revises: fcde5c2045b7
Create Date: 2026-11-23 19:09:52.065911
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f8324236e1e"
down_revision: str | None = "fcde5c2045b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_change_required_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_change_required_at")
