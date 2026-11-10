"""Auth ends idle provider sessions after Slate Operations' longest idle limit (plan step 4.6).

The inactivity limit must outlast every idle option a workspace can choose, plus two access
token lifetimes: the provider's last refresh trails the local one by up to one lifetime. The
test reads the idle options from the model's CHECK and the token lifetime from Compose, so a
new idle option cannot outgrow the Auth limit. No Compose file adds a timebox or another
session rule (contract K87, C15, C16, C19).
"""

import re
from pathlib import Path
from typing import Any

import yaml

from app.systems.manage.workspace.models import PlatformSettings
from tests.postgres_runtime import DisposablePostgres
from tests.repository import REPOSITORY_ROOT

SUPABASE = REPOSITORY_ROOT / "infra/supabase"
FORBIDDEN = re.compile(
    r"^GOTRUE_(SESSIONS_TIMEBOX|SESSIONS_ALLOW_LOW_AAL|SESSIONS_SINGLE_PER_USER|SAML_\w+)$"
)
LIMIT_SETTINGS = ("GOTRUE_SESSIONS_INACTIVITY_TIMEOUT", "GOTRUE_DB_CLEANUP_ENABLED")
# Only the base file sets these; an overlay that sets one could undo it (C19, C22 for D26).
BASE_ONLY = (*LIMIT_SETTINGS, "GOTRUE_AUDIT_LOG_DISABLE_POSTGRES")


class _ComposeLoader(yaml.SafeLoader):
    pass


_ComposeLoader.add_constructor("!reset", lambda loader, node: loader.construct_sequence(node))


def _auth_environment(path: Path) -> dict[str, Any]:
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)
    environment = document.get("services", {}).get("auth", {}).get("environment", {})
    if isinstance(environment, list):
        environment = dict(item.split("=", 1) for item in environment)
    named: dict[str, Any] = environment
    return named


def _minutes(duration: str) -> float:
    """A Go duration of hours, minutes and seconds (`9h`, `540m`, `8h30m`) in minutes."""

    parts = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", duration)
    assert parts and any(parts.groups()), duration
    hours, minutes, seconds = (int(part or 0) for part in parts.groups())
    return hours * 60 + minutes + seconds / 60


def _longest_idle_option() -> int:
    [check] = [
        constraint.sqltext.text
        for constraint in PlatformSettings.__table__.constraints
        if constraint.name == "ck_platform_settings_session_timeout_minutes"
    ]
    return max(int(value) for value in re.findall(r"\d+", check))


def test_auth_ends_idle_sessions_after_the_longest_idle_limit_and_cleans_up_a46a() -> None:
    environment = _auth_environment(SUPABASE / "compose.yaml")
    token_seconds = re.fullmatch(r"\$\{JWT_EXPIRY:-(\d+)\}", environment["GOTRUE_JWT_EXP"])
    assert token_seconds is not None

    assert {name: environment.get(name) for name in LIMIT_SETTINGS} == {
        "GOTRUE_SESSIONS_INACTIVITY_TIMEOUT": "9h",
        "GOTRUE_DB_CLEANUP_ENABLED": "true",
    }
    assert _minutes(environment["GOTRUE_SESSIONS_INACTIVITY_TIMEOUT"]) >= (
        _longest_idle_option() + 2 * int(token_seconds.group(1)) / 60
    )


def test_no_compose_file_adds_a_timebox_or_overrides_the_limits_a46a(tmp_path: Path) -> None:
    with (tmp_path / "process.log").open("w") as log:
        runtime = DisposablePostgres(tmp_path, "a" * 32, {"PATH": "test"}, log)
        runtime.port, runtime.api_port, runtime.mail_port = 49152, 49153, 49154
        runtime.template_port, runtime.network_block = 29007, 7
        runtime._write_inputs()
    files = {
        name: SUPABASE / name
        for name in ("compose.yaml", "compose.dev.yaml", "compose.production.yaml")
    }
    files["runner overlay"] = runtime.overlay_file

    named = {label: sorted(_auth_environment(path)) for label, path in files.items()}

    assert {label: [n for n in names if FORBIDDEN.match(n)] for label, names in named.items()} == (
        dict.fromkeys(files, [])
    )
    overlays = {label: names for label, names in named.items() if label != "compose.yaml"}
    overridden = {
        label: [name for name in names if name in BASE_ONLY]
        for label, names in overlays.items()
    }
    assert overridden == dict.fromkeys(overlays, [])
