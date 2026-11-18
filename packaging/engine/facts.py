"""The Linux environment facts of a run (plan 10.4: kernel, Docker and the image digests,
the app version and the manifests, the disk, the clock). Safe values only; the file is
redacted like every other file of the run folder.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

from engine.context import Context
from engine.core import engine_version


def _json_file(path: os.PathLike[str]) -> Any:
    try:
        with open(path) as file:
            return json.load(file)
    except (OSError, ValueError):
        return None


def collect(ctx: Context) -> dict[str, Any]:
    paths = ctx.paths
    step = ctx.step(98, "facts")
    docker = ctx.runner.run(
        step,
        ["docker", "version", "--format", "{{.Client.Version}} {{.Server.Version}}"],
        timeout=30,
        log_output=False,
    )
    images = ctx.runner.run(
        step,
        ["docker", "image", "ls", "--digests", "--format", "{{.Repository}}:{{.Tag}} {{.Digest}}"],
        timeout=30,
        log_output=False,
    )
    clock = ctx.runner.run(
        step, ["timedatectl", "show", "--property=NTPSynchronized"], timeout=10, log_output=False
    )
    usage = shutil.disk_usage(paths.state) if paths.state.is_dir() else None
    releases = sorted(p.name for p in paths.releases.iterdir()) if paths.releases.is_dir() else []
    return {
        "at": ctx.deps.clock().isoformat(),
        "kernel": os.uname().release,
        "engine_version": engine_version(paths),
        "image_record": _json_file(paths.image_record),
        "installation": _json_file(paths.state / "installation.json"),
        "docker_versions": docker.text().strip() if docker.ok else None,
        "images": images.text().splitlines() if images.ok else None,
        "ntp_synchronized": clock.text().strip() if clock.ok else None,
        "disk_bytes": usage._asdict() if usage else None,
        "received_releases": releases,
    }


def record(ctx: Context) -> dict[str, Any]:
    """Collect the facts and write them as ``facts.json`` in the run folder."""
    found = collect(ctx)
    ctx.log.text("facts.json", json.dumps(found, indent=2, sort_keys=True) + "\n")
    return found
