"""keyset list indexes

Plan step 3.2, decision D1 (TASK-0041 contract, K66 and K67). Two of the three keyset lists
read one organization in creation order, and no index gave that order inside one
organization:

- The recent trigger run list read `ix_record_trigger_runs_created (created_at, id)`, which
  holds every organization's runs, so an organization with no runs read all of them before
  row-level security dropped them (114,389 pages, K66). `ix_record_trigger_runs_org_created`
  replaces it. The list was its only reader: the runner and lifecycle find runs by event and
  trigger, and retention reaches runs through their event.
- The relationship list sorted every matching link (K67). `ix_relationship_edges_org_created`
  gives the unfiltered list its order; record-scoped reads keep the record indexes.

Every statement is `CREATE` or `DROP INDEX CONCURRENTLY` inside `autocommit_block()`, so record
and link writes go on while an index builds (DBI-9). The new trigger run index is valid before
the old one is dropped. A build that stops (for example on the lock limit) leaves an INVALID
index; a rerun drops and builds it again, and keeps a valid one, as `078b17c76d8a` does.

Revision ID: 2bbcb1deeee9
Revises: 176d4af952fa
Create Date: 2026-11-09 20:40:55.304317
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2bbcb1deeee9"
down_revision: str | None = "176d4af952fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_INDEXES = {
    "ix_record_trigger_runs_org_created": ("record_trigger_runs", ["org_id", "created_at", "id"]),
    "ix_relationship_edges_org_created": ("relationship_edges", ["org_id", "created_at", "id"]),
}
OLD_INDEX = ("ix_record_trigger_runs_created", "record_trigger_runs", ["created_at", "id"])

_VALID = sa.text("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)")


def _valid(name: str) -> bool | None:
    """True or False for an existing index; None when there is none."""

    valid: bool | None = op.get_bind().scalar(_VALID, {"name": f"public.{name}"})
    return valid


def _build(name: str, table: str, columns: list[str]) -> None:
    valid = _valid(name)
    if valid:
        return
    if valid is False:
        op.drop_index(name, table_name=table, postgresql_concurrently=True)
    op.create_index(name, table, columns, postgresql_concurrently=True)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, (table, columns) in NEW_INDEXES.items():
            _build(name, table, columns)
        name, table, _columns = OLD_INDEX
        op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _build(*OLD_INDEX)
        for name, (table, _columns) in NEW_INDEXES.items():
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
