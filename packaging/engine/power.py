"""``stop`` and ``start``: the owner's Stop and Start in the settings program (owner request
2026-11-25, scope 1a).

``stop`` takes the runner's lock (no backup, update or restore runs), stops the backup timer,
then stops Docker itself (``docker.socket`` and ``docker.service``). It never stops the
containers one by one: a container that Docker stopped at its own shutdown starts again when
Docker starts, so the next start of Linux (a PC restart) brings Slate Operations back, and a
``docker`` command cannot wake Docker through its socket in between. The marker
``/run/slateops/stopped`` lives in memory, so it goes with that restart too.

``start`` removes the marker, starts Docker and the backup timer, then waits as an update does:
the providers, ``api`` until ready, ``caddy`` last with HTTPS through loopback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine import backups, progress, update
from engine.context import Context
from engine.core import Paths, failed, is_run_id, refused, write_private

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
TIMER = "slateops-runner.timer"
DOCKER = ("docker.socket", "docker.service")


def marker(paths: Paths) -> Path:
    return paths.run / "stopped"


def stopped(paths: Paths) -> bool:
    return marker(paths).exists()


def _installed(ctx: Context) -> str:
    instance = backups.installed_instance(ctx.paths)
    if instance is None:
        raise refused("not_installed")
    if update.is_open(ctx.paths):
        raise refused("update_running")
    return instance


def stop(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    instance = _installed(ctx)
    if stopped(ctx.paths):
        return {"code": "stopped"}
    step = ctx.step(1, "lock")
    progress.report(ctx, "lock")
    with backups.runner_idle(ctx, step, instance):
        if backups.active_journal(ctx.paths, instance).exists():
            raise refused("recovery_required")
        step = ctx.step(2, "stop")
        progress.report(ctx, "stop")
        if not ctx.runner.run(step, ["systemctl", "stop", TIMER], timeout=60).ok:
            raise failed("stop_failed")
        write_private(marker(ctx.paths), b"stopped\n")
        if not ctx.runner.run(step, ["systemctl", "stop", *DOCKER], timeout=300).ok:
            raise failed("stop_failed")
    ctx.log.line(step, "INFO", "Slate Operations stopped until Start or the next start of Linux")
    return {"code": "stopped"}


def start(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    instance = _installed(ctx)
    step = ctx.step(1, "docker")
    progress.report(ctx, "docker")
    if not ctx.runner.run(step, ["systemctl", "start", *DOCKER], timeout=300).ok:
        raise failed("start_failed")
    marker(ctx.paths).unlink(missing_ok=True)
    if not ctx.runner.run(step, ["systemctl", "start", TIMER], timeout=60).ok:
        raise failed("start_failed")
    step = ctx.step(2, "services")
    progress.report(ctx, "services")
    update.start_all(ctx, step, instance)
    return {"code": "started"}
