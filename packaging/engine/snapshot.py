"""The Linux part of the failure snapshot (plan 10.5 items 2 to 4).

Names and states only: no ``docker inspect`` (it prints container environments) and no
``docker compose config``. When the installation has a Compose project (its journal names
it), the snapshot adds ``docker compose ps`` (service, state, health) and the internal
``/api/ready`` and ``/api/health`` answers (plan 10.5 items 3 and 5; TASK-0086 AC-I14).
Container log tails pass the redactor before they are written.
"""

from __future__ import annotations

import re
from datetime import datetime

from engine import compose, journal
from engine.context import Context
from engine.core import INSTANCE_ID
from engine.logs import cap, drop_unfinished

TAIL_LINES = 200  # planning value, plan 10.5 item 4
_CONTAINER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def take(ctx: Context, since: datetime | None, folder: str | None = None) -> str:
    """Write the snapshot under the run folder; return its folder name."""
    name = folder or f"snapshot-{ctx.deps.clock().strftime('%H%M%S')}"
    step = f"{ctx.job}.99.snapshot"
    commands: list[tuple[str, list[str]]] = [
        ("failed-units", ["systemctl", "--failed", "--plain", "--no-legend", "--no-pager"]),
        ("unit-state", ["systemctl", "is-active", "docker.service", "slateops-runner.timer"]),
        (
            "containers",
            ["docker", "ps", "--all", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"],
        ),
        (
            "docker-journal",
            [
                "journalctl",
                "--unit",
                "docker.service",
                "--no-pager",
                "--lines",
                str(TAIL_LINES),
                *(["--since", since.strftime("%Y-%m-%d %H:%M:%S UTC")] if since else []),
            ],
        ),
    ]
    project = (journal.load(ctx.paths) or {}).get("project")
    if (
        isinstance(project, str)
        and INSTANCE_ID.match(project)
        and (ctx.paths.etc / "provider.env").is_file()
    ):
        commands.append(
            (
                "compose-ps",
                compose.argv(
                    ctx.paths,
                    project,
                    "ps",
                    "--all",
                    "--format",
                    "{{.Service}}\t{{.State}}\t{{.Health}}",
                ),
            )
        )
        for path in ("/api/ready", "/api/health"):
            code, body = compose.api_read(ctx, step, project, path)
            ctx.log.text(
                f"{name}/api{path.replace('/api', '').replace('/', '-')}.txt", f"{code} {body}\n"
            )
    containers: list[str] = []
    for part, argv in commands:
        result = ctx.runner.run(step, argv, timeout=60, log_output=False)
        text = result.text() + result.stderr.decode("utf-8", errors="replace")
        ctx.log.text(f"{name}/{part}.txt", text)
        if part == "containers" and result.ok:
            containers = [
                line.split("\t", 1)[0]
                for line in result.text().splitlines()
                if _CONTAINER.match(line.split("\t", 1)[0])
            ]
    for container in containers:
        argv = ["docker", "logs", "--tail", str(TAIL_LINES)]
        if since is not None:
            argv += ["--since", since.strftime("%Y-%m-%dT%H:%M:%SZ")]
        result = ctx.runner.run(step, [*argv, container], timeout=60, log_output=False)
        both = drop_unfinished(cap(result.stdout)) + b"\n" + drop_unfinished(cap(result.stderr))
        ctx.log.text(f"{name}/logs-{container}.txt", both.decode("utf-8", errors="replace"))
    return name
