"""comms search message ids

Plan step 3.8, decision D22 (REQ-0005). Under row-level security PostgreSQL may not run
the non-leakproof `@@` before the policy condition, so a Comms search could not use
`ix_comms_messages_body_search` and read every message of its organization (F29).

`comms_search_message_ids` runs the text match as `slateops_owner`, which row-level
security does not bind (`FORCE` is off), so the index works. The body applies the same
organization condition as the `organization_rows` policy, the given conversations and the
live filters, and returns ids only. A definer with a `SET` clause is never inlined.
`search.py` uses it only as a filter on its outer read, which keeps row-level security,
the organization filter and the readable filter; the second argument is always the
server-side readable set.

- Every name is schema-qualified and the parameters are positional (D22-2), because the
  body runs with `search_path = pg_catalog, pg_temp`.
- The owner's default privileges already keep `EXECUTE` from `PUBLIC`, `anon`,
  `authenticated` and `service_role` (root `e46611902f25`). The explicit `REVOKE` states it,
  as `f43c7d0ee160` does, because a schema-only dump does not show the default.
- Accepted residual risk D22-1: the index holds `body_tsv` only, so a search reads the
  matches of every organization in the installation for its words, then drops the others.
  No row, id or count of another organization reaches the caller.

Alembic does not compare functions; `tests/migrations/test_comms_search_function.py` owns
the catalog and the body.

Revision ID: 176d4af952fa
Revises: 078b17c76d8a
Create Date: 2026-11-09 15:34:10.022640
"""
from collections.abc import Sequence

from alembic import op

revision: str = "176d4af952fa"
down_revision: str | None = "078b17c76d8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNATURE = "public.comms_search_message_ids(text, uuid[])"


def upgrade() -> None:
    op.execute(
        """
CREATE FUNCTION public.comms_search_message_ids(text, uuid[])
RETURNS TABLE (id uuid)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'pg_temp'
AS $$
  SELECT m.id FROM public.comms_messages AS m
  WHERE m.org_id = (SELECT NULLIF(pg_catalog.current_setting('slateops.org_id', true), '')::uuid)
    AND m.conversation_id = ANY ($2)
    AND m.is_deleted IS FALSE AND m.deleted_at IS NULL
    AND m.body_tsv @@ pg_catalog.plainto_tsquery('pg_catalog.simple'::pg_catalog.regconfig, $1)
$$
"""
    )
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO slateops_app")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
