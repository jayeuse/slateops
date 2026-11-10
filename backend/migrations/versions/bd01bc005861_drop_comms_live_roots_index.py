"""drop comms live roots index

Plan step 4.2 (TASK-0043 contract, K80). `ix_comms_messages_live_roots` serves no query: the
history read asks for `parent_id IS NULL OR also_send_to_channel` and names no `is_deleted`
term, so its filter never implies the index predicate, and it reads
`uq_comms_messages_sequence`, which has the same three columns. The thread state reads one row
by `id`. Development counted 0 scans of the index since the statistics reset.

The drop is `DROP INDEX CONCURRENTLY` inside `autocommit_block()`, so message writes go on while
it waits (DBI-9). The downgrade builds the index again concurrently with the exact D13
definition (`65bf3d1eb512`), which `tests/migrations/test_partial_index_predicates.py` reads when
it downgrades through this revision. A downgrade build that stops leaves an INVALID index; a
rerun drops and builds it again, and keeps a valid one, as `2bbcb1deeee9` does.

Revision ID: bd01bc005861
Revises: 2bbcb1deeee9
Create Date: 2026-11-10 07:36:41.614186
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bd01bc005861"
down_revision: str | None = "2bbcb1deeee9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "ix_comms_messages_live_roots"
TABLE = "comms_messages"
_VALID = sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(NAME, table_name=TABLE, postgresql_concurrently=True, if_exists=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        valid: bool | None = op.get_bind().scalar(_VALID, {"name": f"public.{NAME}"})
        if valid:
            return
        if valid is False:
            op.drop_index(NAME, table_name=TABLE, postgresql_concurrently=True)
        op.create_index(
            NAME,
            TABLE,
            ["org_id", "conversation_id", "seq"],
            postgresql_where=sa.text("parent_id IS NULL AND is_deleted IS FALSE"),
            postgresql_concurrently=True,
        )
