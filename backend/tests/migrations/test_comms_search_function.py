"""`comms_search_message_ids`: the definer that lets Comms search use its index (D22)."""

from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration
SIGNATURE = "public.comms_search_message_ids(text, uuid[])"
# The body that the Security Engineer reviewed (TASK-0039 contract, D22, check 2): fixed SQL,
# `public.` on the table, `pg_catalog.` on each function and on the text search
# configuration, positional parameters, ids only, and the organization condition of the
# `organization_rows` policy. It is the contract, so it is pinned word for word.
BODY = """
  SELECT m.id FROM public.comms_messages AS m
  WHERE m.org_id = (SELECT NULLIF(pg_catalog.current_setting('slateops.org_id', true), '')::uuid)
    AND m.conversation_id = ANY ($2)
    AND m.is_deleted IS FALSE AND m.deleted_at IS NULL
    AND m.body_tsv @@ pg_catalog.plainto_tsquery('pg_catalog.simple'::pg_catalog.regconfig, $1)
"""


def test_the_function_is_an_owner_definer_that_only_the_application_role_runs(
    integration_owner_db,
):
    connection = integration_owner_db.connection()
    row = connection.execute(
        text(
            "SELECT p.prosecdef, p.provolatile, p.proleakproof, l.lanname, p.proretset, "
            "pg_get_userbyid(p.proowner), p.proconfig, pg_get_function_arguments(p.oid), "
            "pg_get_function_result(p.oid) FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang "
            f"WHERE p.oid = '{SIGNATURE}'::regprocedure"
        )
    ).one()
    assert tuple(row) == (
        True, "s", False, "sql", True, "slateops_owner", ["search_path=pg_catalog, pg_temp"],
        "text, uuid[]", "TABLE(id uuid)",
    )
    holders = connection.execute(
        text(
            "SELECT coalesce(r.rolname, 'PUBLIC') FROM pg_proc p "
            "CROSS JOIN LATERAL aclexplode(p.proacl) AS acl "
            "LEFT JOIN pg_roles r ON r.oid = acl.grantee "
            f"WHERE p.oid = '{SIGNATURE}'::regprocedure AND acl.privilege_type = 'EXECUTE' "
            "ORDER BY 1"
        )
    ).scalars().all()
    assert holders == ["slateops_app", "slateops_owner"]
    privilege = text("SELECT has_function_privilege(:role, :signature, 'EXECUTE')")
    executes = {
        role: connection.scalar(privilege, {"role": role, "signature": SIGNATURE})
        for role in ("anon", "authenticated", "service_role", "slateops_runtime")
    }
    assert executes == {
        "anon": False, "authenticated": False, "service_role": False, "slateops_runtime": True,
    }
    assert connection.scalar(
        text("SELECT count(*) FROM pg_proc WHERE proname = 'comms_search_message_ids'")
    ) == 1


def test_the_body_is_the_reviewed_fixed_sql(integration_owner_db):
    source = integration_owner_db.connection().scalar(
        text(f"SELECT prosrc FROM pg_proc WHERE oid = '{SIGNATURE}'::regprocedure")
    )
    assert " ".join(source.split()) == " ".join(BODY.split())


def test_the_application_calls_the_function_from_one_place():
    application = Path(__file__).parents[2] / "app"
    callers = {
        path.relative_to(application).as_posix(): path.read_text().count(
            "public.comms_search_message_ids"
        )
        for path in application.rglob("*.py")
        if "comms_search_message_ids" in path.read_text()
    }
    assert callers == {"systems/comms/search.py": 1}
