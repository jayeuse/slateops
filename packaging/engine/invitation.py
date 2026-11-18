"""The first administrator (plan 6.2 step 11) and ``resend-invitation`` (TASK-0080 item 11).

Both run ``bootstrap_admin.py --confirm --json`` in a one-shot server-image container on the
provider network, with ``app.env``. The email and user name reach the container through
``docker run -e NAME`` from the child environment, so they are never an argument or a log
value (TASK-0081 A-3); the name, slug and time zone are fixed arguments from the stored
answers, and ``--provider-user-id`` is never passed (TASK-0080 Security Engineer list).

Bootstrap results (W5a): ``{"result": "sent" | "already_active"}`` (exit 0),
``{"code": "bootstrap_refused"}`` (exit 2) or ``{"code": "bootstrap_failed"}`` (exit 3). A rerun
on a pending administrator sends the same invitation again; on an active one it sends
nothing and writes no row (W5a-4). ``rate_limited`` has no source in bootstrap (W5a D-6): a
provider rate limit is ``bootstrap_failed``.
"""

from __future__ import annotations

import json
from typing import Any

from engine import answers, journal, progress
from engine.context import Context
from engine.core import failed, is_run_id, refused

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
TIMEOUT_SECONDS = 300
ONE_SHOT = [
    "--user",
    "10001:10001",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--no-healthcheck",
]


def bootstrap_argv(
    ctx: Context, project: str, server_image: str, given: dict[str, Any]
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        f"{project}_provider",
        "--env-file",
        str(ctx.paths.etc / "app.env"),
        "--env",
        "ADMIN_EMAIL",
        "--env",
        "ADMIN_USERNAME",
        "--env",
        f"SLATEOPS_RUN_ID={ctx.run_id}",
        *ONE_SHOT,
        "--entrypoint",
        "python",
        server_image,
        "operations/bootstrap_admin.py",
        "--confirm",
        "--json",
        # One argument per value ("--name=<value>"): a name that starts with "-" stays the
        # value of --name and never becomes an option of its own.
        f"--name={given['business_name']}",
        f"--slug={given['slug']}",
        f"--time-zone={given['time_zone']}",
    ]


def bootstrap(
    ctx: Context, step: str, project: str, server_image: str, given: dict[str, Any]
) -> str:
    """Run bootstrap; return ``sent`` or ``already_active``; raise its refusal or failure."""
    result = ctx.runner.run(
        step,
        bootstrap_argv(ctx, project, server_image, given),
        timeout=TIMEOUT_SECONDS,
        extra_env={"ADMIN_EMAIL": given["admin_email"], "ADMIN_USERNAME": given["admin_username"]},
    )
    try:
        last = result.text().strip().splitlines()[-1]
        output = json.loads(last)
    except (IndexError, ValueError):
        output = {}
    if not isinstance(output, dict):
        output = {}
    if result.ok and output.get("result") in ("sent", "already_active"):
        ctx.log.line(step, "INFO", f"first administrator: {output['result']}")
        return str(output["result"])
    if result.returncode == 2 and output.get("code") == "bootstrap_refused":
        raise refused("bootstrap_refused")
    raise failed("bootstrap_failed")


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    state = journal.load(ctx.paths)
    given = answers.load(ctx.paths)
    if state is None or given is None or not journal.done(state, 11):
        raise refused("not_installed")
    progress.report(ctx, "resend")
    code = bootstrap(
        ctx, ctx.step(1, "resend"), str(state["project"]), str(state["server_image"]), given
    )
    return {"code": code}
