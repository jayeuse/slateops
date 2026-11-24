"""worksheet realtime grants

Sheets B15 presence (spec `docs/specs/sheets.md` D13, D14; APR-0016). The sixth sheet table,
`worksheet_realtime_grants`: one 60-second join grant per organization, person and sheet,
written by `POST /api/worksheets/{id}/presence-token`. It is not audited, has the
`organization_rows` RLS policy for `slateops_app` (no `FORCE`), and goes with its sheet
(CASCADE) and its person.

`can_join_realtime_topic` is replaced in place (never dropped: the Realtime policies, the
owner and the execute grant depend on it). The purpose is now checked per branch: a
`worksheet:` topic admits only a `realtime_presence` token whose `topic` claim equals the
topic exactly, with a live grant of the same person on a sheet that is not deleted; every
other topic keeps requiring `realtime`. The membership check still applies to all. Writes
stay governed by the provisioned `realtime.messages` policy (`provision_database_role.py`).

The downgrade restores the root (`e46611902f25`) function body verbatim, then drops the
table and its grants. Grant rows are transient; nothing else is lost.

Revision ID: d60adae1ec28
Revises: 04cdf06c377e
Create Date: 2026-11-24 11:27:24.811454
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d60adae1ec28"
down_revision: str | None = "04cdf06c377e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORGANIZATION_ROWS = """
CREATE POLICY organization_rows ON public.worksheet_realtime_grants TO slateops_app USING
    ((org_id = ( SELECT (NULLIF(current_setting('slateops.org_id'::text, true),
    ''::text))::uuid AS "nullif"))) WITH CHECK ((org_id = ( SELECT
    (NULLIF(current_setting('slateops.org_id'::text, true), ''::text))::uuid AS
    "nullif")))
"""
# The join function as it is after this revision, and as root e46611902f25 left it.
JOIN_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.can_join_realtime_topic(topic text) RETURNS boolean
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    claims jsonb;
    claimed_org uuid;
    claimed_user uuid;
    prefix text;
    purpose text;
BEGIN
    claims := nullif(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb;
    IF claims IS NULL OR pg_catalog.jsonb_typeof(claims) <> 'object'
       OR claims ->> 'role' IS DISTINCT FROM 'authenticated' THEN
        RETURN false;
    END IF;
    purpose := claims ->> 'purpose';
    claimed_org := (claims ->> 'org_id')::uuid;
    claimed_user := (claims ->> 'sub')::uuid;
    IF topic IS NULL OR claimed_org IS NULL OR claimed_user IS NULL THEN
        RETURN false;
    END IF;
    prefix := 'org:' || claimed_org::text || ':';
    IF NOT pg_catalog.starts_with(topic, prefix)
       OR pg_catalog.length(topic) <= pg_catalog.length(prefix) THEN
        RETURN false;
    END IF;
    IF pg_catalog.starts_with(topic, prefix || 'worksheet:') THEN
        -- Sheet presence (D13): only the presence token of exactly this topic, with a
        -- live grant of the same person on a sheet that is not deleted.
        IF purpose IS DISTINCT FROM 'realtime_presence'
           OR claims ->> 'topic' IS DISTINCT FROM topic
           OR NOT EXISTS (
            SELECT 1 FROM public.worksheet_realtime_grants AS g
             JOIN public.worksheets AS w
               ON w.org_id = g.org_id AND w.id = g.worksheet_id
            WHERE g.org_id = claimed_org AND g.user_id = claimed_user
              AND can_join_realtime_topic.topic =
                  prefix || 'worksheet:' || g.worksheet_id::text
              AND g.expires_at > pg_catalog.now()
              AND w.is_deleted IS FALSE AND w.deleted_at IS NULL
        ) THEN
            RETURN false;
        END IF;
    ELSIF purpose IS DISTINCT FROM 'realtime' THEN
        RETURN false;
    ELSIF topic = prefix || 'probe' OR topic = prefix || 'presence'
       OR topic = prefix || 'user:' || claimed_user::text THEN
        NULL;
    ELSIF pg_catalog.starts_with(topic, prefix || 'conversation:') THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.comms_realtime_grants AS g
             JOIN public.comms_conversations AS c
               ON c.org_id = g.org_id AND c.id = g.conversation_id
            WHERE g.org_id = claimed_org AND g.user_id = claimed_user
              AND can_join_realtime_topic.topic =
                  prefix || 'conversation:' || g.conversation_id::text
              AND g.expires_at > pg_catalog.now()
              AND c.is_deleted IS FALSE AND c.deleted_at IS NULL
              AND c.archived_at IS NULL
        ) THEN
            RETURN false;
        END IF;
    ELSE
        RETURN false;
    END IF;
    RETURN EXISTS (
        SELECT 1
          FROM public.memberships AS m
          JOIN public.users AS u ON u.id = m.user_id
          JOIN public.organizations AS o ON o.id = m.org_id
         WHERE m.org_id = claimed_org
           AND m.user_id = claimed_user
           AND m.is_deleted IS FALSE
           AND m.status = 'active'
           AND (m.invitation_accepted_at IS NOT NULL OR m.invitation_sent_at IS NULL)
           AND (m.expires_at IS NULL OR m.expires_at > pg_catalog.now())
           AND u.status = 'active'
           AND u.is_deleted IS FALSE
           AND o.is_deleted IS FALSE
    );
EXCEPTION
    WHEN invalid_text_representation THEN
        RETURN false;
END;
$$;
ALTER FUNCTION public.can_join_realtime_topic(topic text) OWNER TO slateops_owner;
"""
ROOT_JOIN_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.can_join_realtime_topic(topic text) RETURNS boolean
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    claims jsonb;
    claimed_org uuid;
    claimed_user uuid;
    prefix text;
BEGIN
    claims := nullif(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb;
    IF claims IS NULL OR pg_catalog.jsonb_typeof(claims) <> 'object'
       OR claims ->> 'purpose' IS DISTINCT FROM 'realtime'
       OR claims ->> 'role' IS DISTINCT FROM 'authenticated' THEN
        RETURN false;
    END IF;
    claimed_org := (claims ->> 'org_id')::uuid;
    claimed_user := (claims ->> 'sub')::uuid;
    IF topic IS NULL OR claimed_org IS NULL OR claimed_user IS NULL THEN
        RETURN false;
    END IF;
    prefix := 'org:' || claimed_org::text || ':';
    IF NOT pg_catalog.starts_with(topic, prefix)
       OR pg_catalog.length(topic) <= pg_catalog.length(prefix) THEN
        RETURN false;
    END IF;
    IF topic = prefix || 'probe' OR topic = prefix || 'presence'
       OR topic = prefix || 'user:' || claimed_user::text THEN
        NULL;
    ELSIF pg_catalog.starts_with(topic, prefix || 'conversation:') THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.comms_realtime_grants AS g
             JOIN public.comms_conversations AS c
               ON c.org_id = g.org_id AND c.id = g.conversation_id
            WHERE g.org_id = claimed_org AND g.user_id = claimed_user
              AND can_join_realtime_topic.topic =
                  prefix || 'conversation:' || g.conversation_id::text
              AND g.expires_at > pg_catalog.now()
              AND c.is_deleted IS FALSE AND c.deleted_at IS NULL
              AND c.archived_at IS NULL
        ) THEN
            RETURN false;
        END IF;
    ELSE
        RETURN false;
    END IF;
    RETURN EXISTS (
        SELECT 1
          FROM public.memberships AS m
          JOIN public.users AS u ON u.id = m.user_id
          JOIN public.organizations AS o ON o.id = m.org_id
         WHERE m.org_id = claimed_org
           AND m.user_id = claimed_user
           AND m.is_deleted IS FALSE
           AND m.status = 'active'
           AND (m.invitation_accepted_at IS NOT NULL OR m.invitation_sent_at IS NULL)
           AND (m.expires_at IS NULL OR m.expires_at > pg_catalog.now())
           AND u.status = 'active'
           AND u.is_deleted IS FALSE
           AND o.is_deleted IS FALSE
    );
EXCEPTION
    WHEN invalid_text_representation THEN
        RETURN false;
END;
$$;
ALTER FUNCTION public.can_join_realtime_topic(topic text) OWNER TO slateops_owner;
"""



def upgrade() -> None:
    op.create_table(
        "worksheet_realtime_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("worksheet_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "worksheet_id"], ["worksheets.org_id", "worksheets.id"],
            name="fk_worksheet_realtime_grants_worksheet", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name=op.f("fk_worksheet_realtime_grants_org_id_organizations"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_worksheet_realtime_grants_user_id_users"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("worksheet_realtime_grants_pkey")),
        sa.UniqueConstraint("org_id", "id", name="uq_worksheet_realtime_grants_org_id_id"),
        sa.UniqueConstraint(
            "org_id", "user_id", "worksheet_id", name="uq_worksheet_realtime_grants_subject"
        ),
    )
    op.create_index(
        "ix_worksheet_realtime_grants_sheet", "worksheet_realtime_grants",
        ["org_id", "worksheet_id"], unique=False,
    )
    op.create_index(
        "ix_worksheet_realtime_grants_user", "worksheet_realtime_grants", ["user_id"],
        unique=False,
    )
    op.execute("ALTER TABLE public.worksheet_realtime_grants ENABLE ROW LEVEL SECURITY")
    op.execute(ORGANIZATION_ROWS)
    op.execute(JOIN_FUNCTION)


def downgrade() -> None:
    op.execute(ROOT_JOIN_FUNCTION)
    op.drop_index("ix_worksheet_realtime_grants_user", table_name="worksheet_realtime_grants")
    op.drop_index("ix_worksheet_realtime_grants_sheet", table_name="worksheet_realtime_grants")
    op.drop_table("worksheet_realtime_grants")
