"""The first administrator (plan 6.2 step 11; DEC-0041).

Step 11 runs ``bootstrap_admin.py --confirm --json --password-stdin`` in a one-shot
server-image container on the provider network, with ``app.env``: the account gets the
password that setup asked for, with no invitation and no email. The password goes only to the
container's standard input (``docker run --interactive`` and the runner's ``input``), never
into an argument, an environment value or a file. The email and user name reach the container
through ``docker run -e NAME`` from the child environment, so they are never an argument or a
log value (TASK-0081 A-3); the name, slug and time zone are fixed arguments from the stored
answers, and ``--provider-user-id`` is never passed (TASK-0080 Security Engineer list).

Bootstrap results: ``{"result": "created" | "already_active"}`` (exit 0; ``already_active`` on
a rerun), ``{"code": "bootstrap_refused"}`` (exit 2) or ``{"code": "bootstrap_failed"}``
(exit 3). ``resend-invitation`` is gone with DEC-0041: the installer sends no invitation.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from engine.context import Context
from engine.core import failed, refused

TIMEOUT_SECONDS = 300
# The product's shortest password (PasswordChangeRequest) and the pinned GoTrue's longest
# ("Password cannot be longer than 72 characters", counted in bytes: bcrypt).
PASSWORD_MIN_CHARACTERS, PASSWORD_MAX_BYTES = 12, 72


def valid_password(value: Any) -> bool:
    """The rule of ``bootstrap_admin.py --password-stdin``, checked again here so a bad
    password stops the install before step 1."""
    return (
        isinstance(value, str)
        and len(value) >= PASSWORD_MIN_CHARACTERS
        and len(value.encode("utf-8")) <= PASSWORD_MAX_BYTES
        and "".join(value.splitlines()) == value
        and not any(unicodedata.category(character) == "Cc" for character in value)
    )


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
        "--interactive",
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
        "--password-stdin",
    ]


def create_admin(
    ctx: Context, step: str, project: str, server_image: str, given: dict[str, Any], password: str
) -> str:
    """Return ``created`` or ``already_active`` (a rerun); raise bootstrap's refusal or
    failure."""
    result = ctx.runner.run(
        step,
        bootstrap_argv(ctx, project, server_image, given),
        timeout=TIMEOUT_SECONDS,
        extra_env={"ADMIN_EMAIL": given["admin_email"], "ADMIN_USERNAME": given["admin_username"]},
        input=password.encode("utf-8") + b"\n",
    )
    try:
        last = result.text().strip().splitlines()[-1]
        output = json.loads(last)
    except (IndexError, ValueError):
        output = {}
    if not isinstance(output, dict):
        output = {}
    if result.ok and output.get("result") in ("created", "already_active"):
        ctx.log.line(step, "INFO", f"first administrator: {output['result']}")
        return str(output["result"])
    if result.returncode == 2 and output.get("code") == "bootstrap_refused":
        raise refused("bootstrap_refused")
    raise failed("bootstrap_failed")
