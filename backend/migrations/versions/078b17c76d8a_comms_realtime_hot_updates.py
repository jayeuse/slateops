"""comms realtime hot updates

Plan step 3.6, decision D11. A grant renewal changes only `expires_at`, and a presence
heartbeat changes `last_seen_at` (and sometimes `state`). One index on each table holds
that column, so every renewal and heartbeat wrote the heap row and every index entry. This
revision drops those two indexes, so the updates can be HOT, and gives both tables room for
new row versions on their pages.

- Without `ix_comms_realtime_grants_expiry`, the expiry sweep reads its organization's rows
  through `uq_comms_realtime_grants_subject`, which starts with `org_id`. Realtime
  authorization never read the dropped index: `can_join_realtime_topic` (root
  `e46611902f25`) looks a grant up by `(org_id, user_id)` and the topic (K55).
- Without `ix_comms_presence_seen`, the presence sweep reads its organization's rows through
  `uq_comms_presence_user`; that is one row for each person.
- `DROP INDEX CONCURRENTLY` runs outside a transaction (`autocommit_block`), so writes go on.
  `SET (fillfactor = 80)` takes SHARE UPDATE EXCLUSIVE and rewrites nothing: only pages
  written later keep the space, and both tables are small and rewritten often.

Alembic sees the index drops; it does not compare storage parameters, so
`tests/migrations/test_table_storage_parameters.py` owns them.

A concurrent build that stops (for example on the lock limit) leaves an INVALID index
behind. The downgrade keeps a valid index, and drops and rebuilds an invalid one, as
`65bf3d1eb512` does (N6).

Revision ID: 078b17c76d8a
Revises: b1b3908e844b
Create Date: 2026-11-08 10:17:04.266620
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "078b17c76d8a"
down_revision: str | None = "b1b3908e844b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Each index holds the one column that the frequent update changes, so it blocks HOT.
INDEXES = {
    "ix_comms_realtime_grants_expiry": ("comms_realtime_grants", ["org_id", "expires_at"]),
    "ix_comms_presence_seen": ("comms_presence", ["org_id", "last_seen_at"]),
}
TABLES = ("comms_realtime_grants", "comms_presence")


_VALID = sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)")


def _valid(name: str) -> bool | None:
    """True or False for an existing index; None when there is none."""

    valid: bool | None = op.get_bind().scalar(_VALID, {"name": f"public.{name}"})
    return valid


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, (table, _columns) in INDEXES.items():
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} SET (fillfactor = 80)")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} RESET (fillfactor)")
    with op.get_context().autocommit_block():
        for name, (table, columns) in INDEXES.items():
            valid = _valid(name)
            if valid:
                continue
            if valid is False:
                op.drop_index(name, table_name=table, postgresql_concurrently=True)
            op.create_index(name, table, columns, postgresql_concurrently=True)
