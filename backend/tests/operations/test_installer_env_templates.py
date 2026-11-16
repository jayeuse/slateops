"""Production env templates (plan W2, TASK-0081): rendered files load the backend settings."""

import importlib
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy.engine import make_url

from app.core.config.environment import with_realtime_publisher
from app.core.config.settings import (
    AdminSettings,
    InstanceSettings,
    MigrationSettings,
    ProvisionSettings,
    Settings,
)
from operations.supabase_keys import installer_secrets

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "packaging" / "engine" / "templates"
# The server image ENV (infra/docker/backend.Dockerfile); never in an env file (A-3).
IMAGE_ENV = {
    "SLATEOPS_ENV_SOURCE": "process", "WEB_ASSETS_ROOT": "/app/web", "SLATEOPS_VERSION": "1.2.3",
}
ANSWERS = {
    "PUBLIC_HOST": "frontdesk.local",
    "SLATEOPS_SERVER_IMAGE": "ghcr.io/example/slateops-server@sha256:" + "a" * 64,
    "SLATEOPS_CADDY_IMAGE": "ghcr.io/example/slateops-caddy@sha256:" + "b" * 64,
    "SLATEOPS_APP_PRIVATE_SUBNET": "172.31.248.0/28",
    "SLATEOPS_BACKUP_EXPORT_ROOT": "/mnt/slateops-backup/backup-exports",
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    "SMTP_ADMIN_EMAIL": "office@example.test",
    "SMTP_USER": "office@example.test",
    "SMTP_PASS": "p@ss $word #1",
    "SMTP_SENDER_NAME": "Front Desk",
}


def engine_templates() -> ModuleType:
    path = str(ROOT / "packaging")
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("engine.env_templates")


def literal_lines(text: str) -> dict[str, str]:
    """Docker's env-file reader: split at the first '=', skip blank and '#' lines."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            name, separator, value = line.partition("=")
            assert separator and name not in values, name
            values[name] = value
    return values


@pytest.fixture(scope="module")
def rendered() -> dict[str, Any]:
    generated, _password = installer_secrets()
    values = {**generated, **ANSWERS}
    module = engine_templates()
    return {
        name: module.render((TEMPLATES / name).read_text(encoding="utf-8"), values)
        for name in ("provider.env", "app.env", "provision.env")
    } | {"generated": generated}


def test_w2_1_app_env_alone_loads_settings_and_admin_settings(rendered) -> None:
    app = literal_lines(rendered["app.env"])
    settings = Settings.model_validate(with_realtime_publisher({**app, **IMAGE_ENV}))
    assert settings.public_origin == "https://frontdesk.local"
    assert settings.supabase_auth_issuer == "https://frontdesk.local/auth/v1"
    assert settings.realtime_publish_url == "http://api-gw:8001/realtime/v1/api/broadcast"
    InstanceSettings.model_validate(app)
    AdminSettings.model_validate(
        {**app, "ADMIN_EMAIL": "owner@example.test", "ADMIN_USERNAME": "owner"}
    )


def test_w2_1_p_4_provisioning_env_loads_and_builds_urls_from_generated_passwords(
    rendered,
) -> None:
    provision = literal_lines(rendered["provision.env"])
    generated = rendered["generated"]
    ProvisionSettings.model_validate(provision)
    MigrationSettings.model_validate(provision)
    InstanceSettings.model_validate(provision)
    assert provision.keys() == {
        "ENVIRONMENT", "SLATEOPS_INSTANCE_ID", "POSTGRES_HOST", "POSTGRES_PORT",
        "POSTGRES_DATABASE", "DATABASE_BOOTSTRAP_URL", "MIGRATION_DATABASE_URL", "DATABASE_URL",
        "SUPABASE_URL", "SUPABASE_AUTH_ISSUER", "SUPABASE_SECRET_KEY",
    }
    for name, user, password in (
        ("DATABASE_BOOTSTRAP_URL", "supabase_admin", "POSTGRES_PASSWORD"),
        ("MIGRATION_DATABASE_URL", "slateops_owner", "SLATEOPS_OWNER_DB_PASSWORD"),
        ("DATABASE_URL", "slateops_runtime", "SLATEOPS_RUNTIME_DB_PASSWORD"),
    ):
        url = make_url(provision[name])
        assert (url.drivername, url.host, url.port, url.database) == (
            "postgresql+psycopg", "db", 5432, "postgres",
        )
        assert (url.username, url.password) == (user, generated[password])
    assert literal_lines(rendered["app.env"])["DATABASE_URL"] == provision["DATABASE_URL"]


def test_a_3_app_env_holds_exactly_the_application_names(rendered) -> None:
    app = literal_lines(rendered["app.env"])
    assert app.keys() == {
        "ENVIRONMENT", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DATABASE",
        "BACKEND_BIND_HOST", "BACKEND_PORT", "SUPABASE_URL", "SUPABASE_AUTH_ISSUER", "LOG_DIR",
        "SLATEOPS_INSTANCE_ID", "PUBLIC_ORIGIN", "DATABASE_URL", "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY", "SUPABASE_SESSION_ENCRYPTION_KEY", "PUBLICATION_SIGNING_KEY",
        "REALTIME_TOKEN_SIGNING_KEY", "SECURITY_EVENT_SERVER_KEY", "LIFECYCLE_PURGE_ENABLED",
        "AUTH_REFRESH_TOKEN_DAYS", "SUPABASE_TIMEOUT_SECONDS", "REQUEST_BODY_MAX_BYTES",
        "DATABASE_POOL_SIZE", "DATABASE_MAX_OVERFLOW", "DATABASE_POOL_TIMEOUT_SECONDS",
        "DATABASE_CONNECT_TIMEOUT_SECONDS", "DATABASE_STATEMENT_TIMEOUT_MS",
        "READINESS_POOL_TIMEOUT_SECONDS", "READINESS_CONNECT_TIMEOUT_SECONDS",
        "READINESS_STATEMENT_TIMEOUT_MS", "READINESS_CALLER_TIMEOUT_SECONDS",
        "SERVER_MAX_CONCURRENCY", "SERVER_KEEP_ALIVE_SECONDS",
    }
    # The bridge loads app.env alone, so these must equal the production overlay values.
    assert {name: app[name] for name in (
        "ENVIRONMENT", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DATABASE",
        "BACKEND_BIND_HOST", "BACKEND_PORT", "SUPABASE_URL", "LOG_DIR",
    )} == {
        "ENVIRONMENT": "production", "POSTGRES_HOST": "db", "POSTGRES_PORT": "5432",
        "POSTGRES_DATABASE": "postgres", "BACKEND_BIND_HOST": "0.0.0.0", "BACKEND_PORT": "8000",
        "SUPABASE_URL": "http://api-gw:8000", "LOG_DIR": "/var/log/slateops/api",
    }


def test_a_3_no_env_file_names_an_image_env_value() -> None:
    for path in TEMPLATES.iterdir():
        names = set(literal_lines(path.read_text(encoding="utf-8")))
        assert not names & {"SLATEOPS_VERSION", "SLATEOPS_ENV_SOURCE", "WEB_ASSETS_ROOT"}, path


def test_w2_1_provider_env_sets_every_required_compose_variable(rendered) -> None:
    provider = literal_lines(rendered["provider.env"])
    required: set[str] = set()
    for name in ("compose.yaml", "compose.production.yaml"):
        text = (ROOT / "infra" / "supabase" / name).read_text(encoding="utf-8")
        required |= set(re.findall(r"\$\{([A-Z0-9_]+):\?", text))
    assert required <= provider.keys()
    assert all(provider[name] for name in required if not provider[name].startswith('"'))
    # The backup runner reads these two keys literally (export_files.py).
    for name in ("SLATEOPS_BACKUP_EXPORT_ROOT", "SLATEOPS_LOG_ROOT"):
        lines = [line for line in rendered["provider.env"].splitlines() if line.startswith(name)]
        assert len(lines) == 1 and Path(lines[0].partition("=")[2]).is_absolute()


def test_w2_2_only_provider_smtp_text_is_quoted(rendered) -> None:
    quoted = {
        name for name, value in literal_lines(rendered["provider.env"]).items()
        if value.startswith('"')
    }
    assert quoted == {"SMTP_ADMIN_EMAIL", "SMTP_USER", "SMTP_PASS", "SMTP_SENDER_NAME"}
    for name in ("app.env", "provision.env"):
        values = literal_lines(rendered[name]).values()
        assert not any(value.startswith(("'", '"')) for value in values)
    assert "{{" not in "".join(
        line for name in ("provider.env", "app.env", "provision.env")
        for line in rendered[name].splitlines() if not line.startswith("#")
    )


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        ("a${b} $ #c ' \" ", '"a$${b} $$ #c \' \\" "'),
        ("x\\", '"x\\\\"'),
        (" lead and trail ", '" lead and trail "'),
        ("", '""'),
    ],
    ids=["dollar-hash-quotes", "trailing-backslash", "edge-spaces", "empty"],
)
def test_p_2_customer_text_uses_compose_double_quotes(value: str, encoded: str) -> None:
    assert engine_templates().compose_quoted(value) == encoded


@pytest.mark.parametrize("value", ["line\nbreak", "carriage\rreturn", "nul\x00byte"])
def test_p_2_customer_text_refuses_line_breaks_and_nul(value: str) -> None:
    module = engine_templates()
    with pytest.raises(module.TemplateError) as raised:
        module.render("SMTP_PASS={{SMTP_PASS|compose}}\n", {"SMTP_PASS": value})
    assert value not in str(raised.value)


@pytest.mark.parametrize(
    ("template", "values"),
    [
        ("A={{B}}\n", {}),
        ("A={{B}}\n", {"B": "x$y"}),
        ("A={{B}}\n", {"B": "x#y"}),
        ("A={{B}}\n", {"B": "x'y"}),
        ("A={{B}}\n", {"B": "x`y"}),
        ("A={{B}}\n", {"B": "x\\y"}),
        ("A={{B}}\n", {"B": "x y"}),
        ("A={{B}}\n", {"B": '"x'}),
        ("A={{B}}\n", {"B": ""}),
        ("A={{B}}\n", {"B": "café"}),
        ("A={{B|raw}}\n", {"B": "x"}),
        ("A={{ B }}\n", {"B": "x"}),
        ("A=x\nA=y\n", {}),
        ("not a binding\n", {}),
    ],
    ids=[
        "missing", "dollar", "hash", "quote", "backquote", "backslash", "space",
        "leading-double-quote", "empty", "non-ascii", "unknown-filter", "loose-placeholder",
        "duplicate-name", "no-equals",
    ],
)
def test_w2_2_render_refuses_values_and_templates_outside_the_format(
    template: str, values: dict[str, str]
) -> None:
    module = engine_templates()
    with pytest.raises(module.TemplateError) as raised:
        module.render(template, values)
    for value in values.values():
        if value:
            assert value not in str(raised.value)


# Every character that str.splitlines() breaks on, plus samples of the other C0 and C1
# control characters and DEL.
LINE_AND_CONTROL = [
    "\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029",
    "\x00", "\x01", "\t", "\x1b", "\x1f", "\x7f", "\x80", "\x9f",
]


@pytest.mark.parametrize(
    "character", LINE_AND_CONTROL, ids=[f"U+{ord(c):04X}" for c in LINE_AND_CONTROL]
)
def test_p_2_w81_2_customer_text_refuses_line_boundaries_and_controls(character: str) -> None:
    module = engine_templates()
    value = f"pass{character}word"
    with pytest.raises(module.TemplateError) as raised:
        module.render("SMTP_PASS={{SMTP_PASS|compose}}\n", {"SMTP_PASS": value})
    assert value not in str(raised.value)


def test_w2_1_n_5_operator_gateway_url_uses_the_compose_default_port(rendered) -> None:
    provider = literal_lines(rendered["provider.env"])
    compose = (ROOT / "infra" / "supabase" / "compose.yaml").read_text(encoding="utf-8")
    defaults = set(re.findall(r"\$\{SUPABASE_API_PORT:-([0-9]+)\}", compose))
    assert len(defaults) == 1
    assert "SUPABASE_API_PORT" not in provider
    assert provider["SUPABASE_PUBLIC_URL"] == f"http://127.0.0.1:{defaults.pop()}"
