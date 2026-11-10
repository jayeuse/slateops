"""Planner profiles for plan tests: development defaults, and the production planner values.

Plan step 4.1 (A41b). The production overlay sets the planner values in the `db` command; a
plan read applies the same values with `set_config(..., true)` (`SET LOCAL`), read from that
file, never from a copy. `shared_buffers` cannot change in a session and does not change a
plan's shape, so it stays out.
"""

from typing import Any

import yaml

from tests.repository import REPOSITORY_ROOT

PROFILES = ("development", "production")
PLANNER_SETTINGS = ("random_page_cost", "effective_cache_size", "work_mem")


class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_constructor("!reset", lambda loader, node: loader.construct_sequence(node))


def production_planner_values() -> dict[str, str]:
    """The planner values of the production overlay's `db` command (`-c name=value`)."""

    overlay = yaml.load(
        (REPOSITORY_ROOT / "infra/supabase/compose.production.yaml").read_text(encoding="utf-8"),
        Loader=_ComposeLoader,
    )
    command = overlay["services"]["db"].get("command", [])
    values = dict(
        argument.split("=", 1)
        for flag, argument in zip(command, command[1:], strict=False)
        if flag == "-c" and argument.split("=", 1)[0] in PLANNER_SETTINGS
    )
    assert sorted(values) == sorted(PLANNER_SETTINGS), values
    return values


def apply_profile(cursor: Any, profile: str) -> None:
    """Apply `profile` to the open transaction of a DB-API cursor."""

    if profile == "production":
        for name, value in production_planner_values().items():
            cursor.execute("SELECT set_config(%s, %s, true)", (name, value))
            cursor.execute("SELECT current_setting(%s)", (name,))
            assert cursor.fetchone()[0] == value, name
