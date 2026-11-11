"""The setup-defaults revision gives every existing organization all four items, refuses any
other shape at the database, and its downgrade removes only the column (BE-SD6)."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from uuid6 import uuid7

from tests.conftest import alembic_heads, guarded_create_engine
from tests.database_pool import dispose_process_engines
from tests.operations.migration_support import guarded_migration_environment, run_alembic

pytestmark = pytest.mark.integration

REVISION = "fcde5c2045b7"
PREVIOUS = "f9809993d133"
# Each value takes a different branch of the CHECK: not an object, a missing item, a value
# that is a string, a number, or a JSON null.
REFUSED_VALUES = (
    "[]",
    '{"groups": true, "dashboard": true, "category": true}',
    '{"groups": "yes", "dashboard": true, "category": true, "channel": true}',
    '{"groups": true, "dashboard": 1, "category": true, "channel": true}',
    '{"groups": true, "dashboard": true, "category": true, "channel": null}',
)


@pytest.fixture
def migration() -> Iterator[tuple[dict[str, str], Engine]]:
    """The test starts at the previous revision and hands the database back at the head."""
    environment = guarded_migration_environment()
    [head] = alembic_heads()
    dispose_process_engines()
    engine = guarded_create_engine(os.environ["MIGRATION_DATABASE_URL"], poolclass=NullPool)
    run_alembic(environment, "downgrade", PREVIOUS)
    try:
        yield environment, engine
    finally:
        run_alembic(environment, "upgrade", head)
        run_alembic(environment, "check")
        engine.dispose()


def _defaults(connection: Connection, org_id: object) -> object:
    has_column = connection.scalar(
        text(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'organizations' AND column_name = 'department_setup_defaults'"
        )
    )
    if not has_column:
        return None
    return connection.scalar(
        text("SELECT department_setup_defaults FROM public.organizations WHERE id = :id"),
        {"id": org_id},
    )


def test_upgrade_sets_all_four_items_on_existing_organizations_and_downgrade_drops_them(
    migration: tuple[dict[str, str], Engine],
) -> None:
    environment, engine = migration
    org_id = uuid7()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.organizations (id, slug, display_name, timezone, locale) "
                "VALUES (:id, :slug, 'Setup defaults migration', 'UTC', 'en-US')"
            ),
            {"id": org_id, "slug": f"setup-defaults-{org_id}"},
        )
    try:
        run_alembic(environment, "upgrade", REVISION)

        with engine.connect() as connection:
            assert _defaults(connection, org_id) == {
                "groups": True, "dashboard": True, "category": True, "channel": True,
            }
        for refused in REFUSED_VALUES:
            refused_id = uuid7()
            insert = text(
                "INSERT INTO public.organizations (id, slug, display_name, timezone, locale, "
                "department_setup_defaults) VALUES (:id, :slug, 'Refused', 'UTC', 'en-US', "
                "CAST(:value AS jsonb))"
            )
            values = {"id": refused_id, "slug": f"setup-refused-{refused_id}", "value": refused}
            # Never committed: the connection rolls back when it closes.
            with engine.connect() as connection:
                with pytest.raises(IntegrityError, match="ck_workspace_profiles_department_setup"):
                    connection.execute(insert, values)

        run_alembic(environment, "downgrade", PREVIOUS)

        with engine.connect() as connection:
            assert _defaults(connection, org_id) is None
            assert connection.scalar(
                text("SELECT display_name FROM public.organizations WHERE id = :id"),
                {"id": org_id},
            ) == "Setup defaults migration"
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.organizations WHERE id = :id"), {"id": org_id}
            )
