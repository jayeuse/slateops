"""Guarded Alembic helpers for disposable PostgreSQL migration regressions.

``run_alembic`` runs Alembic in this test process instead of a child ``python -m alembic``.
A child paid for a new interpreter and a fresh import of the application models on every
call. ``migrations/env.py`` still runs in full for every command, so its runner-ownership
guard, owner-role checks, migration scope, and advisory lock keep their meaning. A failure
raises ``subprocess.CalledProcessError``, as the child process did.
"""

import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from tests.conftest import _guard_integration_database

_SCRIPT_LOCATION = str(Path(__file__).resolve().parents[2] / "migrations")
# alembic.ini's console format for the ``alembic`` logger.
_LOG_FORMAT = "%(levelname)-5.5s [%(name)s] %(message)s"
_REVISION_COMMANDS = {"upgrade": command.upgrade, "downgrade": command.downgrade}


# The current models map these columns from later revisions on: `User` from 4f8324236e1e,
# `Membership` from 37bba4c7658e. A test that runs application code below those revisions
# adds them first and drops them before an upgrade adds them.
_LATER_COLUMNS = (
    ("users", "password_change_required_at"),
    ("memberships", "worksheets_released_at"),
)


_LATER_LICENSE_TABLE = """
CREATE TABLE IF NOT EXISTS public.installation_licenses (
    id uuid PRIMARY KEY, singleton_key boolean NOT NULL DEFAULT true,
    license_text text NOT NULL, imported_at timestamptz NOT NULL, seen_through date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz, is_deleted boolean NOT NULL DEFAULT false, performed_by uuid
)
"""


def add_later_user_column(owner: Engine) -> None:
    """Let the current `User` and `Membership` models load rows at an older revision.

    The current app also reads the installation's license row (edition gates), so an empty
    `installation_licenses` table stands in for the later revision that creates it.
    """
    with owner.begin() as connection:
        for table, column in _LATER_COLUMNS:
            connection.execute(
                text(f"ALTER TABLE public.{table} ADD COLUMN {column} timestamptz")
            )
        connection.execute(text(_LATER_LICENSE_TABLE))


def drop_later_user_column(owner: Engine) -> None:
    """Undo `add_later_user_column` before the upgrade that adds the columns."""
    with owner.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS public.installation_licenses"))
        for table, column in _LATER_COLUMNS:
            connection.execute(
                text(f"ALTER TABLE public.{table} DROP COLUMN IF EXISTS {column}")
            )


def guarded_migration_environment() -> dict[str, str]:
    runtime_url = os.getenv("TEST_DATABASE_URL", "")
    owner_url = os.getenv("MIGRATION_DATABASE_URL", "")
    _guard_integration_database(runtime_url)
    _guard_integration_database(owner_url)
    return {**os.environ, "SLATEOPS_ENV_SOURCE": "process"}


@contextmanager
def _process_environment(environment: dict[str, str]) -> Iterator[None]:
    """Give env.py exactly the environment a child process would have received."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(environment)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@contextmanager
def _alembic_console() -> Iterator[None]:
    """Keep the child's ``Running upgrade ...`` lines on stderr.

    The config has no ini file, so env.py skips ``logging.fileConfig``; in this process that
    call would disable every logger that other tests already created.
    """
    logger = logging.getLogger("alembic")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def run_alembic(environment: dict[str, str], operation: str, revision: str | None = None) -> None:
    """Run ``alembic upgrade|downgrade <revision>`` or ``alembic check``."""
    config = Config()
    config.set_main_option("script_location", _SCRIPT_LOCATION)
    call: Callable[[], object]
    if operation == "check" and revision is None:
        arguments = [operation]
        call = partial(command.check, config)
    elif operation in _REVISION_COMMANDS and revision is not None:
        arguments = [operation, revision]
        call = partial(_REVISION_COMMANDS[operation], config, revision)
    else:
        raise ValueError(f"Unsupported Alembic call: {operation} {revision}")
    try:
        with _process_environment(environment), _alembic_console():
            call()
    except Exception as error:
        raise subprocess.CalledProcessError(
            1, [sys.executable, "-m", "alembic", *arguments], stderr=str(error)
        ) from error
