"""The installation's Compose project (plan 6.2 steps 7 to 10; W2 and space-cut carries).

Every Compose command has the same head: ``--project-name <instance ID>``,
``--env-file /etc/slateops/provider.env`` and exactly the three bundled files
(``compose.yaml``, ``compose.production.yaml``, ``compose.installer.yaml``). It runs through
the engine runner, so it gets only the minimal environment (no calling variable overrides
an ``--env-file`` value). ``config`` runs only with ``--quiet``; container states are read
with ``ps`` (names, states and health only), never with ``inspect``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.context import Context
from engine.core import Paths, failed

FILES = ("compose.yaml", "compose.production.yaml", "compose.installer.yaml")
# The customer service set (space-cut carry): providers first, then api, then caddy.
PROVIDER_SERVICES = ("db", "auth", "storage", "realtime", "api-gw")
APP_SERVICES = ("api", "caddy")
HEALTH_SECONDS = 300  # planning value, plan 10.2 (readiness time limit)
POLL_SECONDS = 3.0
# The API's own readiness reads, inside its container (the image has Python, no curl).
_READ = (
    "import sys, urllib.request, urllib.error\n"
    "try:\n"
    "    r = urllib.request.urlopen('http://127.0.0.1:8000' + sys.argv[1], timeout=5)\n"
    "    code, body = r.status, r.read(4096)\n"
    "except urllib.error.HTTPError as e:\n"
    "    code, body = e.code, e.read(4096)\n"
    "sys.stdout.write(str(code) + ' ' + body.decode('utf-8', 'replace'))\n"
)


def files(paths: Paths) -> list[Path]:
    return [paths.bundle_root / "infra" / "supabase" / name for name in FILES]


def argv(paths: Paths, project: str, *tail: str) -> list[str]:
    head = ["docker", "compose", "--project-name", project]
    head += ["--env-file", str(paths.etc / "provider.env")]
    for path in files(paths):
        head += ["-f", str(path)]
    return [*head, *tail]


def check_config(ctx: Context, step: str, project: str) -> None:
    if not all(path.is_file() for path in files(ctx.paths)):
        raise failed("bundle_incomplete")
    result = ctx.runner.run(step, argv(ctx.paths, project, "config", "--quiet"), timeout=120)
    if not result.ok:
        raise failed("compose_config_failed")


def up(ctx: Context, step: str, project: str, services: tuple[str, ...], *, deps: bool) -> None:
    tail = ["up", "--detach", "--pull", "never", *([] if deps else ["--no-deps"]), *services]
    if not ctx.runner.run(step, argv(ctx.paths, project, *tail), timeout=600).ok:
        raise failed("compose_up_failed")


def _rows(text: str) -> list[dict[str, Any]]:
    """``ps --format json``: one object per line (Compose 2.21 and later) or one array."""
    text = text.strip()
    if text.startswith("["):
        found = json.loads(text)
        return [row for row in found if isinstance(row, dict)]
    return [row for line in text.splitlines() if isinstance(row := json.loads(line), dict)]


def states(ctx: Context, step: str, project: str) -> dict[str, tuple[str, str, int]] | None:
    """Service -> (state, health, exit code); None when Compose cannot answer."""
    result = ctx.runner.run(
        step,
        argv(ctx.paths, project, "ps", "--all", "--format", "json"),
        timeout=60,
        log_output=False,
    )
    if not result.ok:
        return None
    try:
        rows = _rows(result.text())
    except ValueError:
        return None
    found: dict[str, tuple[str, str, int]] = {}
    for row in rows:
        exit_code = row.get("ExitCode")
        found[str(row.get("Service", ""))] = (
            str(row.get("State", "")),
            str(row.get("Health", "")),
            exit_code if isinstance(exit_code, int) else -1,
        )
    return found


def _ready(state: tuple[str, str, int]) -> bool:
    status, health, _ = state
    return status == "running" and health in ("healthy", "")


def wait_healthy(ctx: Context, step: str, project: str, services: tuple[str, ...]) -> None:
    """Poll until each service runs and is healthy, or stop after ``HEALTH_SECONDS``."""
    started = ctx.deps.clock()
    seen: dict[str, tuple[str, str, int]] = {}
    while True:
        seen = states(ctx, step, project) or {}
        if all(name in seen and _ready(seen[name]) for name in services):
            ctx.log.line(step, "INFO", f"healthy: {', '.join(services)}")
            return
        if (ctx.deps.clock() - started).total_seconds() > HEALTH_SECONDS:
            break
        ctx.deps.sleep(POLL_SECONDS)
    summary = "; ".join(
        f"{name} {'/'.join(map(str, seen[name])) if name in seen else 'absent'}"
        for name in sorted({*services, *seen})
    )
    ctx.log.line(step, "ERROR", f"not healthy after {HEALTH_SECONDS} s: {summary}")
    raise failed("services_not_healthy")


def api_read(ctx: Context, step: str, project: str, path: str) -> tuple[int | None, str]:
    """GET ``path`` from inside the api container (the internal path); (status, body)."""
    result = ctx.runner.run(
        step,
        argv(ctx.paths, project, "exec", "-T", "api", "python", "-c", _READ, path),
        timeout=30,
        log_output=False,
    )
    code, _, body = result.text().partition(" ")
    if not result.ok or not code.isdigit():
        return None, ""
    return int(code), body


def wait_api_ready(ctx: Context, step: str, project: str) -> None:
    started = ctx.deps.clock()
    while True:
        code, body = api_read(ctx, step, project, "/api/ready")
        if code == 200:
            ctx.log.line(step, "INFO", "internal /api/ready: 200")
            return
        if (ctx.deps.clock() - started).total_seconds() > HEALTH_SECONDS:
            ctx.log.line(step, "ERROR", f"internal /api/ready: {code} {body[:2000]}")
            raise failed("api_not_ready")
        ctx.deps.sleep(POLL_SECONDS)
