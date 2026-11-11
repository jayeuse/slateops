"""The setup-defaults revision gives every existing organization all four items, and its
downgrade removes only the column (BE-SD6)."""

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
            with pytest.raises(IntegrityError, match="ck_workspace_profiles_department_setup"):
                connection.execute(
                    text(
                        "UPDATE public.organizations SET department_setup_defaults = '[]' "
                        "WHERE id = :id"
                    ),
                    {"id": org_id},
                )

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
