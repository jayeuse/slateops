"""``prepare-uninstall`` and ``set-email`` (plan 9.1, 9.3; W9, TASK-0096 E-1 and E-3).

``prepare-uninstall`` (input ``run_id``) gives the values of ``kept.json`` and stops the services
cleanly before Windows moves the disk: first the runner timer, then Docker itself. It does not
run ``compose stop``: the containers keep their ``unless-stopped`` policy, so they start again
with Docker at the next Linux start (a failed keep path, a reinstall with kept data). The timer
is stopped, not turned off, so the next Linux start runs it again.

``set-email`` (input ``run_id``, through the secret pipe like ``smtp-test``) takes the values
that ``smtp-test`` staged, writes them into the six SMTP lines of ``provider.env`` (replaced in
place, or appended: an install writes none, DEC-0041) and keeps every other line, removes the
staged file, then recreates ``auth`` and then ``api`` (Compose gives the API its SMTP_* values
when it creates the container) and waits until each is healthy. The staged password is held
by the redactor from the job's start.

Both jobs hold the runner's host lock, so no backup copies a half-changed state.
"""

from __future__ import annotations

import json
from typing import Any

from engine import answers, backups, compose, progress, smtp_env
from engine.context import Context
from engine.core import failed, is_run_id, refused, write_private
from engine.env_templates import TemplateError

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
STOPS = (
    ["systemctl", "stop", "slateops-runner.timer"],
    ["systemctl", "stop", "docker.socket", "docker.service"],
)


def _instance(ctx: Context) -> str:
    instance = backups.installed_instance(ctx.paths)
    if instance is None or not ctx.paths.installation.is_file():
        raise refused("not_installed")
    return instance


def prepare_uninstall(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths, step = ctx.paths, ctx.step(1, "stop")
    instance = _instance(ctx)
    installation = json.loads(paths.installation.read_text())
    given = answers.load(paths)
    if given is None:
        raise failed("install_state_mismatch", part="answers")
    with backups.runner_idle(ctx, step, instance):
        for key, argv in zip(("stop_timer", "stop_docker"), STOPS, strict=True):
            progress.report(ctx, key)
            if not ctx.runner.run(step, argv, timeout=300).ok:
                raise failed("services_not_stopped")
    ctx.log.line(step, "INFO", "the timer and Docker are stopped; ready for the uninstall")
    return {
        "code": "ready_for_uninstall",
        "version": installation["version"],
        "instance_id": installation["instance_id"],
        "business_name": given["business_name"],
        "public_host": given["public_host"],
    }


def set_email(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths, step = ctx.paths, ctx.step(1, "email")
    instance = _instance(ctx)
    staged = paths.staged_smtp
    if not staged.is_file() or staged.is_symlink():
        raise refused("smtp_not_staged")
    try:
        values = smtp_env.parse(staged.read_text(encoding="utf-8"))
    except TemplateError as error:
        raise refused("smtp_not_staged") from error
    try:
        lines = {line.split("=", 1)[0]: line for line in smtp_env.lines(values)}
    except TemplateError as error:
        raise refused("smtp_not_staged") from error
    target = paths.etc / "provider.env"
    with backups.runner_idle(ctx, step, instance):
        progress.report(ctx, "write")
        written = []
        for line in target.read_text(encoding="utf-8").splitlines():
            name = line.split("=", 1)[0]
            written.append(lines.pop(name) if name in lines else line)
        written.extend(lines.values())  # an installation with no email settings yet
        write_private(target, ("\n".join(written) + "\n").encode())
        staged.unlink()
        ctx.log.line(step, "INFO", "email settings written to provider.env")
        progress.report(ctx, "auth")
        for service in ("auth", "api"):
            compose.up(ctx, step, instance, (service,), deps=False, recreate=True)
            compose.wait_healthy(ctx, step, instance, (service,))
    return {"code": "email_set"}
