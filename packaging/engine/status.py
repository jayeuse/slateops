"""``status``: safe codes for the Windows side (plan 3.2 rule 2, 7.4, 10.2).

Input: the run ID, the Windows-part version and the installed WSL version. Output:
``engine_idle`` (the only value Windows acts on: it waits before the WSL install), a state
code, the prefetch code and whole-number progress for display. It keeps no run log
(the setup program polls it); it records version changes in ``report.json``.
"""

from __future__ import annotations

import os
import re
from typing import Any

from engine import prefetch, release, report
from engine.context import Context
from engine.core import engine_version, is_run_id, is_version, lock_state

# The four-part form that `wsl --version` prints, for the input and the known-bad list.
WSL_VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,6}){3}\Z")
KEYS = {
    "run_id": is_run_id,
    "windows_part_version": is_version,
    "wsl_version": lambda value: isinstance(value, str) and WSL_VERSION.match(value) is not None,
}
REQUIRED = frozenset(KEYS)


def engine_idle(ctx: Context) -> bool:
    """No state-changing engine job and no pull runs (W10b and W13b add their locks).
    A lock state that cannot be read counts as busy: Windows waits rather than install WSL
    during a job."""
    paths = ctx.paths
    return all(
        lock_state(lock, paths.proc) is False for lock in (paths.engine_lock, paths.prefetch_lock)
    )


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths = ctx.paths
    wsl = request["wsl_version"]
    report.record_versions(
        paths,
        ctx.deps.clock(),
        {
            "windows_part": request["windows_part_version"],
            "wsl": wsl,
            "kernel": os.uname().release,
        },
    )
    manifest = release.load(paths, engine_version(paths))
    known_bad = [item for item in release.known_bad_wsl(manifest) if WSL_VERSION.match(item)]
    if wsl in known_bad:
        state = "needs_support"
    elif (paths.state / "installation.json").exists():
        state = "installed"
    else:
        state = "not_installed"
    progress = prefetch.progress(paths)
    return {
        "code": "ok",
        "engine_idle": engine_idle(ctx),
        "state": state,
        "prefetch": progress.pop("code"),
        "progress": progress,
    }
