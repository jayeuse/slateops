"""The package night (plan 7.4; W13b-8, TASK-0095; TASK-0083 carries).

Once a week, on Sunday after the nightly backup (local 03:00 to 06:00 in the installation's
time zone, planning values after the default 02:00 backup), and only on a night with no update
(no update journal started in the last 24 hours), the tick upgrades the Debian packages. It
holds the runner's host lock, so no backup or export runs. apt reads only the security stanza
of the image's Debian sources and Docker's source (its apt preferences keep the Docker major
versions, W4-2); the image's own source files do not change. ``--force-confold`` keeps our
changed conffiles (``/etc/chrony/chrony.conf``). ``upgrade`` removes no package and holds back
an upgrade that needs one. Afterwards (a Docker Engine upgrade restarts the containers) the
engine checks readiness, ``caddy`` last. A failure shows ``needs_support`` in ``status``.

Support job ``package-night`` (not on the Windows ``Exec`` allow-list) runs it at once.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from engine import answers, backups, update
from engine.context import Context
from engine.core import JobError, Paths, is_run_id, private_dir, refused, write_private

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
WINDOW = (3, 6)  # planning values: local hours after the default 02:00 backup
SUNDAY = 6
APT_SECONDS = 3600


def state_path(paths: Paths) -> Path:
    return paths.state / "package-night.json"


def last_result(paths: Paths) -> str | None:
    try:
        found = json.loads(state_path(paths).read_text())
    except (OSError, ValueError):
        return None
    return found.get("result") if isinstance(found, dict) else None


def _local(ctx: Context, now: datetime) -> datetime:
    given = answers.load(ctx.paths) or {}
    zone: tzinfo
    try:
        zone = ZoneInfo(str(given.get("time_zone", "UTC")))
    except (ZoneInfoNotFoundError, ValueError):
        ctx.log.line(ctx.step(10, "packages"), "WARN", "time zone not found; using UTC")
        zone = UTC
    return now.astimezone(zone)


def _due(ctx: Context, now: datetime) -> bool:
    local = _local(ctx, now)
    if local.weekday() != SUNDAY or not WINDOW[0] <= local.hour < WINDOW[1]:
        return False
    try:
        last = json.loads(state_path(ctx.paths).read_text()).get("date")
    except (OSError, ValueError, AttributeError):
        last = None
    if last == local.date().isoformat():
        return False
    if update.needs_support(ctx.paths):  # S95-1: never start a failed project again
        return False
    return not update.started_since(ctx.paths, now - timedelta(hours=24))


def _sources(ctx: Context) -> Path:
    """A folder with only the security stanza of ``debian.sources`` and ``docker.sources``."""
    paths = ctx.paths
    folder = paths.run / "package-night"
    shutil.rmtree(folder, ignore_errors=True)
    private_dir(folder)
    debian = (paths.apt_sources / "debian.sources").read_text(encoding="utf-8")
    security = [
        stanza.strip()
        for stanza in debian.split("\n\n")
        if any(
            line.startswith("Suites:")
            and all(suite.endswith("-security") for suite in line.split()[1:])
            for line in stanza.splitlines()
        )
    ]
    if len(security) != 1:
        raise refused("package_sources_invalid")
    write_private(folder / "security.sources", (security[0] + "\n").encode())
    write_private(folder / "docker.sources", (paths.apt_sources / "docker.sources").read_bytes())
    return folder


def run(ctx: Context, instance: str) -> str:
    """Upgrade, then readiness with ``caddy`` last; ``ok`` or ``needs_support``."""
    step, now = ctx.step(10, "packages"), ctx.deps.clock()
    environment = {"DEBIAN_FRONTEND": "noninteractive"}
    with backups.runner_idle(ctx, step, instance):
        try:
            sources = _sources(ctx)
            options = ["-o", "Dir::Etc::SourceList=/dev/null",
                       "-o", f"Dir::Etc::SourceParts={sources}"]  # fmt: skip
            done = ctx.runner.run(step, ["apt-get", "-q", *options, "update"],
                                  timeout=APT_SECONDS, extra_env=environment).ok  # fmt: skip
            keep = ["-o", "Dpkg::Options::=--force-confold"]  # our conffiles (TASK-0083)
            upgrade = ["apt-get", "-q", "-y", *options, *keep, "upgrade"]
            done = (
                done
                and ctx.runner.run(step, upgrade, timeout=APT_SECONDS, extra_env=environment).ok
            )
        except (JobError, OSError):
            done = False
        try:
            update.start_all(ctx, step, instance)
        except JobError:
            done = False
    result = "ok" if done else "needs_support"
    record = {"date": _local(ctx, now).date().isoformat(), "result": result, "at": now.isoformat()}
    write_private(state_path(ctx.paths), (json.dumps(record, sort_keys=True) + "\n").encode())
    ctx.log.line(step, "INFO" if done else "ERROR", f"package night: {result}")
    return result


def night_if_due(ctx: Context, instance: str) -> str | None:
    """The tick's call: the result when the night ran, else None."""
    return run(ctx, instance) if _due(ctx, ctx.deps.clock()) else None


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    instance = backups.installed_instance(ctx.paths)
    if instance is None:
        raise refused("not_installed")
    return {"code": "package_night", "result": run(ctx, instance)}
