"""``restore``: put the newest backup back (plan 8.4; owner decision 2026-11-24, the
one-click "Restore the latest backup" in M01).

Input: ``run_id``. Steps (``restore.NN.<name>``, journal ``/var/lib/slateops/update/<run
ID>.json`` with ``kind`` ``restore``):

1. ``lock``: the runner's host lock, as ``update`` step 1; refuse while a runner journal is
   active (``recovery_required``).
2. ``snapshot``: mount the backup drive and choose the newest Restic snapshot. The restore tool
   accepts it only when it was made by this installation.
3. to 8.: the update rollback's steps (7.5) with this snapshot: the project's containers and
   networks go and its volumes stay, the snapshot goes into ``<base>-r<n>``, the env files get
   the new instance ID, finalization revokes every session, the services start, and the
   restored project becomes the installation.

A failure before the env files change starts the old project again (``failed``); a later one
closes ``needs_support``. A finished restore also closes every update journal that waits for
support (``resolved``), because the installation runs again on a known backup.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from engine import backups, drive, progress, update
from engine.context import Context
from engine.core import FAILED, JobError, failed, is_run_id, private_dir, refused, write_private

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
ENV_FILES = ("provider.env", "app.env", "provision.env")
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def newest_snapshot(ctx: Context, step: str) -> str:
    paths = ctx.paths
    target = drive.load_target(paths)
    if target is None or not drive.mount(ctx, step, target):
        raise failed("backup_target_missing")
    result = ctx.runner.run(step, drive.restic(paths, "snapshots", "--json"),
                            timeout=drive.RESTIC_SECONDS)  # fmt: skip
    try:
        rows = json.loads(result.text()) if result.ok else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        raise failed("snapshots_unreadable")
    found: list[tuple[datetime, str]] = []
    for row in rows:
        try:
            when = datetime.fromisoformat(str(row["time"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if _HEX.match(str(row.get("id", ""))) and when.tzinfo is not None:
            found.append((when, row["id"]))
    if not found:
        raise failed("no_backup")
    when, snapshot = max(found)
    ctx.log.line(step, "INFO", f"newest of {len(found)} snapshots: {snapshot} ({when.isoformat()})")
    return snapshot


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths = ctx.paths
    update.resume(ctx)
    instance = backups.installed_instance(paths)
    if instance is None:
        raise refused("not_installed")
    record: dict[str, Any] = {
        "schema": 1, "kind": "restore", "run_id": ctx.run_id, "project": instance,
        "state": "running", "started_at": ctx.deps.clock().isoformat(), "steps": {},
        "boundary": True, "stopped": True,
    }  # fmt: skip
    step = ctx.step(1, "lock")
    with backups.runner_idle(ctx, step, instance):
        if backups.active_journal(paths, instance).exists():
            raise refused("recovery_required")
        before = {name: (paths.etc / name).read_bytes() for name in ENV_FILES}
        try:
            step = ctx.step(2, "snapshot")
            progress.report(ctx, "snapshot")
            record["snapshot_id"] = newest_snapshot(ctx, step)
            # The restore tool reads the source installation from this config (update step 5).
            config = update.backup_config(paths, record)
            private_dir(config.parent)
            write_private(config, backups.config_path(paths).read_bytes())
            update._save(paths, record)
            update._rollback(ctx, record, "restore")
        except Exception as error:
            known = error if isinstance(error, JobError) else JobError("engine_failed", FAILED)
            state = _undo(ctx, record, instance, before, known.code)
            raise JobError(known.code, known.exit_code, **known.fields, restore=state) from error
        record["state"], record["finished_at"] = "restored", ctx.deps.clock().isoformat()
        update._save(paths, record)
        for other in update.journals(paths):
            if other.get("state") == "needs_support":
                other["state"], other["resolved_by"] = "resolved", ctx.run_id
                update._save(paths, other)
        ctx.log.line(ctx.step(9, "close"), "INFO", f"restored {record['snapshot_id']}")
    return {"code": "restored", "project": record["restored_project"]}


def _undo(
    ctx: Context, record: dict[str, Any], instance: str, before: dict[str, bytes], code: str
) -> str:
    """Before the env files change, the old project and its volumes are as they were: start it
    again. After that, support takes over."""
    paths, step = ctx.paths, ctx.step(9, "close")
    record["failure_code"] = code
    state = "needs_support"
    unchanged = all((paths.etc / name).read_bytes() == data for name, data in before.items())
    if unchanged and backups.installed_instance(paths) == instance:
        try:
            update.start_all(ctx, step, instance)
            state = "failed"
        except Exception as error:  # the services stay as they are; support takes over
            found = error.code if isinstance(error, JobError) else "engine_failed"
            ctx.log.line(step, "ERROR", f"the old installation did not start: {found}")
    record["state"], record["finished_at"] = state, ctx.deps.clock().isoformat()
    if "snapshot_id" in record:
        update._save(paths, record)
    ctx.log.line(step, "ERROR", f"restore closed {state}: {code}")
    return state
