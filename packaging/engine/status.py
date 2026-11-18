"""``status``: safe codes for the Windows side (plan 3.2 rule 2, 7.4, 10.2).

Input: the run ID, the Windows-part version and the installed WSL version. Output:
``engine_idle`` (the only value Windows acts on: it waits before the WSL install), a state
code, the prefetch code and whole-number progress for display, and (W10b, TASK-0093) the
backup state of the last tick (``backup``: ``not_set_up``, ``ok``, ``backup_target_missing``
or ``runner_layout_stale``) and the last Linux start with its ready time (``linux_start``,
W7-6). TASK-0097 AC-B6 (DEC-0041): ``email_configured`` (``set-email`` wrote the SMTP
lines) and ``admin_email``, the stored first-administrator address that ``smtp-test`` mails
(personal data: the Windows side shows it and keeps it out of its logs). It keeps no run log
(the setup program polls it); it records version changes in ``report.json``.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from engine import answers, backups, packages, prefetch, release, report, smtp_env, tick, update
from engine.context import Context
from engine.core import INSTANCE_ID, engine_version, is_run_id, is_version, lock_state

# The four-part form that `wsl --version` prints, for the input and the known-bad list.
WSL_VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,6}){3}\Z")
KEYS = {
    "run_id": is_run_id,
    "windows_part_version": is_version,
    "wsl_version": lambda value: isinstance(value, str) and WSL_VERSION.match(value) is not None,
}
REQUIRED = frozenset(KEYS)


def engine_idle(ctx: Context) -> bool:
    """No state-changing engine job, no pull and no backup runner runs (the runner's host
    lock, TASK-0093 AC-8), and no update is open: one that a restart interrupted stays open
    until the next tick closes it (W13b, plan section 12). A lock state that cannot be read
    counts as busy: Windows waits rather than install WSL during a job."""
    paths = ctx.paths
    locks = [paths.engine_lock, paths.prefetch_lock]
    instance = backups.installed_instance(paths)
    if instance is not None:
        locks.append(backups.runner_lock(paths, instance))
    idle = all(lock_state(lock, paths.proc) is False for lock in locks)
    return idle and not update.is_open(paths)


def _backup(ctx: Context) -> str:
    try:
        found = json.loads(tick.tick_state(ctx.paths).read_text()).get("backup")
    except (OSError, ValueError, AttributeError):
        return "not_set_up"
    known = ("ok", "backup_target_missing", "runner_layout_stale")
    return found if found in known else "not_set_up"


def _instance_id(ctx: Context) -> str | None:
    """W9 F3: the instance ID of the installation, which kept data must match (plan 9.2)."""
    try:
        found = json.loads(ctx.paths.installation.read_text()).get("instance_id")
    except (OSError, ValueError, AttributeError):
        return None
    return found if isinstance(found, str) and INSTANCE_ID.match(found) else None


def _linux_start(ctx: Context) -> dict[str, Any] | None:
    starts = report.load(ctx.paths).get("starts")
    last = starts[-1] if isinstance(starts, list) and starts else None
    if not isinstance(last, dict):
        return None
    return {"started_at": last.get("started_at"), "ready_at": last.get("ready_at")}


def _email_configured(ctx: Context) -> bool:
    try:
        text = (ctx.paths.etc / "provider.env").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return smtp_env.configured(text)


def _admin_email(ctx: Context) -> str | None:
    stored = answers.load(ctx.paths)
    return None if stored is None else str(stored["admin_email"])


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
    if (
        wsl in known_bad
        or packages.last_result(paths) == "needs_support"
        or update.needs_support(paths)
    ):
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
        "backup": _backup(ctx),
        "linux_start": _linux_start(ctx),
        "instance_id": _instance_id(ctx),
        "email_configured": _email_configured(ctx),
        "admin_email": _admin_email(ctx),
    }
