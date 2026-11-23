"""``admin-password``: set the first administrator's password from the settings program on the
server PC (TASK-0097 AC-B8, DEC-0042: without email, the admin signs in again this way).

Input, through the secret pipe only: ``run_id`` and ``admin_password`` (the install's rule:
``invitation.valid_password``). The engine holds the password in memory, masks it in every
log line from the job's start, and gives it only to the standard input of
``operations/reset_admin_password.py`` in a one-shot server-image container
(``invitation.operation_argv``). The operation finds the stored first administrator (the
install answers' email), sets the password in Auth, ends that person's sessions and writes a
security event. Results: ``reset`` (exit 0); ``not_installed`` (no finished install, nothing
runs), ``invalid_input`` and ``admin_missing`` (exit 2); ``reset_failed`` (exit 3).
"""

from __future__ import annotations

import json
from typing import Any

from engine import answers, invitation, journal, progress
from engine.context import Context
from engine.core import failed, is_run_id, refused

KEYS = {"run_id": is_run_id, "admin_password": invitation.valid_password}
REQUIRED = frozenset(KEYS)


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    password = request["admin_password"]
    ctx.redactor = ctx.redactor.with_values([password], [], words=[password])
    ctx.log.redact = ctx.redactor
    state = journal.load(ctx.paths)
    given = answers.load(ctx.paths)
    if state is None or given is None or not journal.done(state, 13):
        raise refused("not_installed")
    step = ctx.step(1, "reset")
    progress.report(ctx, "reset")
    result = ctx.runner.run(
        step,
        invitation.operation_argv(
            ctx, str(state["project"]), str(state["server_image"]),
            "operations/reset_admin_password.py", "--confirm", "--json", "--password-stdin",
        ),
        timeout=invitation.TIMEOUT_SECONDS,
        extra_env={"ADMIN_EMAIL": given["admin_email"], "ADMIN_USERNAME": given["admin_username"]},
        input=password.encode("utf-8") + b"\n",
    )  # fmt: skip
    try:
        output = json.loads(result.text().strip().splitlines()[-1])
    except (IndexError, ValueError):
        output = {}
    if not isinstance(output, dict):
        output = {}
    if result.ok and output.get("result") == "reset":
        ctx.log.line(step, "INFO", "first administrator password set; sessions ended")
        return {"code": "reset"}
    if result.returncode == 2 and output.get("code") in ("admin_missing", "invalid_input"):
        raise refused(str(output["code"]))
    raise failed("reset_failed")
