"""Production PostgreSQL settings live in the production overlay only (plan step 4.1, K81 to K83).

Compose replaces a `command` list in an overlay; it does not append. So the overlay repeats the
base command and adds the six settings, and development keeps PostgreSQL's defaults.
"""

from typing import Any

import yaml

from tests.repository import REPOSITORY_ROOT

SUPABASE = REPOSITORY_ROOT / "infra/supabase"
PRODUCTION_SETTINGS = [
    "-c", "shared_buffers=2GB",
    "-c", "effective_cache_size=8GB",
    "-c", "work_mem=16MB",
    "-c", "maintenance_work_mem=512MB",
    "-c", "random_page_cost=1.1",
    "-c", "effective_io_concurrency=200",
]


class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_constructor("!reset", lambda loader, node: loader.construct_sequence(node))


def _db(name: str) -> dict[str, Any]:
    document = yaml.load((SUPABASE / name).read_text(encoding="utf-8"), Loader=_ComposeLoader)
    service: dict[str, Any] = document["services"]["db"]
    return service


def test_the_production_db_command_is_the_base_command_plus_six_settings_a41a() -> None:
    base = _db("compose.yaml")["command"]

    assert _db("compose.production.yaml").get("command") == base + PRODUCTION_SETTINGS
    assert "command" not in _db("compose.dev.yaml")
