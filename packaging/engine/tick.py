"""``tick``, ``runner-recover`` and ``runner-adopt``: the backup runner, the standard way
(plan W10b-1, 8.1, 8.2; TASK-0092 (a*); TASK-0093 AC-1 to AC-3, AC-7 to AC-11).

``slateops-runner.timer`` runs ``slateops-engine --timer tick`` each minute. A tick:

1. does nothing until install step 12 is complete;
2. records the Linux start and, until it is ready, its ready time (W7-6, plan 10.2);
3. removes an orphan ``slateops-runner`` older than the time limit and starts no runner, or
   refuses with ``runner_busy`` while a younger one or the runner's host lock exists;
4. checks the pair: ``engine/VERSION``, the ``installation.json`` version and the image label
   ``org.opencontainers.image.version`` are equal, the image ID is the signed manifest digest,
   and the config's ``compose_root`` is this bundle's; otherwise ``runner_layout_stale``;
5. mounts the backup drive when ``mountinfo`` shows no mount (``backup_target_missing`` when
   it fails; the runner still runs, so a backup fails as ``backup_failed`` and fail-open
   restarts the services);
6. runs the unchanged ``backup_runner.py run`` in the container, then removes the container
   and confirms that it is gone; after a time limit, exit 3 or ``admission_failed`` (a stale
   mount), it unmounts with a plain ``umount``, so the next tick mounts again;
7. runs the daily certificate renewal when it is due and no runner journal is active.
"""

from __future__ import annotations

import dataclasses
import json
import os
import secrets
import string
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine import answers, backups, drive, renewal, report
from engine.context import Context
from engine.core import (
    JobError,
    Paths,
    engine_version,
    failed,
    is_run_id,
    lock_state,
    refused,
    write_private,
)

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
TIMER = "--timer"
RENEW_AFTER, RETRY_AFTER = timedelta(hours=24), timedelta(hours=1)
STARTS_KEPT = 50
_SAFE = frozenset(string.ascii_lowercase + string.digits + "_")
_LABEL = '{{.Id}} {{index .Config.Labels "org.opencontainers.image.version"}}'


def timer_request(now: datetime) -> bytes:
    """The request of ``slateops-engine --timer tick``: a fresh ``backup`` run ID (10.1)."""
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    run_id = f"backup-{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}-{suffix}"
    return json.dumps({"run_id": run_id}).encode()


def tick_state(paths: Paths) -> Path:
    return paths.state / "runner-tick.json"


def marker(paths: Paths) -> Path:
    """The restore-finalized marker that ``runner-adopt`` passes (W13b writes it)."""
    return backups.runner_state(paths) / "restore-finalized.json"


def _safe(value: Any) -> str:
    return value if isinstance(value, str) and set(value) <= _SAFE and value else "unknown"


def _json_tail(text: str) -> dict[str, Any]:
    try:
        found = json.loads(text.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


# The pair check and the runner ---------------------------------------------------------------


def _record(paths: Paths, now: datetime, **values: Any) -> None:
    try:
        current = json.loads(tick_state(paths).read_text())
    except (OSError, ValueError):
        current = {}
    current = current if isinstance(current, dict) else {}
    current.update(values, at=now.isoformat())
    write_private(tick_state(paths), (json.dumps(current, sort_keys=True) + "\n").encode())


def pair_check(ctx: Context, step: str) -> str:
    """The server image ID when the bundle, the installation and the image are one release."""
    paths = ctx.paths
    try:
        version = str(json.loads(paths.installation.read_text())["version"])
        root = json.loads(backups.config_path(paths).read_text())["compose_root"]
        image = backups.server_image(paths, version)
    except (OSError, ValueError, KeyError, TypeError, JobError):
        version, root, image = "", "", ""
    seen = ["", ""]
    if image:
        found = ctx.runner.run(step, ["docker", "image", "inspect", "--format", _LABEL, image],
                               timeout=60)  # fmt: skip
        seen = (found.text().split() + ["", ""])[:2] if found.ok else seen
    bundle = engine_version(paths)
    if not (
        image
        and version == bundle == seen[1]
        and seen[0] == image
        and root == str(paths.bundle_root / "infra" / "supabase")
    ):
        matches = seen[0] == image and bool(image)
        ctx.log.line(
            step,
            "ERROR",
            f"pair: bundle {bundle}, installation {version or '?'}, "
            f"image {seen[1] or '?'}; image id matches: {matches}",
        )
        _record(paths, ctx.deps.clock(), backup="runner_layout_stale")
        raise refused("runner_layout_stale")
    return image


def run_runner(ctx: Context, step: str, image: str, action: list[str]) -> dict[str, Any]:
    """Mount, run the runner container, remove it on every path, unmount after a failure."""
    paths = ctx.paths
    target = drive.load_target(paths)
    present = target is not None and drive.mount(ctx, step, target)
    code = "ok" if present else "backup_target_missing"
    _record(paths, ctx.deps.clock(), backup=code)
    tail = [
        str(paths.bundle_root / "backend" / "operations" / "backup_runner.py"), *action[:1],
        "--backup-config", str(backups.config_path(paths)),
        "--state-directory", str(backups.runner_state(paths)), *action[1:],
    ]  # fmt: skip
    argv = backups.container_argv(ctx, image, tail)
    try:
        result = ctx.runner.run(step, argv, timeout=backups.RUNNER_SECONDS)
    finally:
        backups.remove_container(ctx, step)
    output = _json_tail(result.text())
    runner = _safe(output.get("state") or output.get("code"))
    if result.returncode in (None, 3) or runner == "admission_failed":
        drive.unmount(ctx, step)
    exit_code = -1 if result.returncode is None else result.returncode
    _record(paths, ctx.deps.clock(), runner=runner, runner_exit=exit_code)
    return {"runner": runner, "runner_exit": exit_code, "backup": code}


# Linux starts and the daily renewal ---------------------------------------------------------


def record_start(ctx: Context, step: str) -> bool:
    """W7-6 (plan 10.2): each Linux start (boot ID and PID 1 start) and its ready time, the
    first tick at which ``https://<host>/api/ready`` answers 200. True when it wrote."""
    proc = ctx.paths.proc
    try:
        boot = (proc / "sys/kernel/random/boot_id").read_text().strip()
        btime = next(
            int(line.split()[1])
            for line in (proc / "stat").read_text().splitlines()
            if line.startswith("btime ")
        )
        ticks = int((proc / "1/stat").read_text().rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError, StopIteration):
        return False
    started = datetime.fromtimestamp(btime + ticks / os.sysconf("SC_CLK_TCK"), UTC)
    key = f"{boot}:{ticks}"
    starts = report.load(ctx.paths).get("starts")
    last = starts[-1] if isinstance(starts, list) and starts else {}
    if isinstance(last, dict) and last.get("key") == key and last.get("ready_at"):
        return False
    now = ctx.deps.clock()
    ready = None
    given = answers.load(ctx.paths)
    if given is not None:
        root = ctx.paths.etc / "ca" / "current" / "root.crt"
        try:
            code, _ = ctx.deps.https_get(given["public_host"], "/api/ready", root, 5.0)
        except OSError:
            code = 0
        ready = now.isoformat() if code == 200 else None
    new = not (isinstance(last, dict) and last.get("key") == key)
    if not new and ready is None:
        return False

    def mutate(data: dict[str, Any]) -> None:
        found = data.get("starts")
        found = found if isinstance(found, list) else []
        if new:
            found.append({"key": key, "started_at": started.isoformat(), "ready_at": None})
        if ready is not None:
            found[-1]["ready_at"] = ready
            found[-1]["ready_seconds"] = round((now - started).total_seconds())
        data["starts"] = found[-STARTS_KEPT:]

    report.update(ctx.paths, mutate)
    ctx.log.line(step, "INFO", "Linux start recorded" if new else "Linux start ready")
    return True


def _renewal_due(paths: Paths, now: datetime) -> bool:
    try:
        data = json.loads((paths.state / "renewal.json").read_text())
    except (OSError, ValueError):
        return True
    data = data if isinstance(data, dict) else {}

    def moment(name: str) -> datetime | None:
        try:
            return datetime.fromisoformat(str(data[name]))
        except (KeyError, ValueError):
            return None

    succeeded, failed_at = moment("succeeded_at"), moment("failed_at")
    if failed_at is not None and (succeeded is None or failed_at > succeeded):
        return now - failed_at >= RETRY_AFTER
    return succeeded is None or now - succeeded >= RENEW_AFTER


def renew_if_due(ctx: Context, instance: str) -> str | None:
    """AC-9: due 24 h after the last success, at least 1 h after a failure; skipped while a
    runner journal is active (the runner owns Caddy's state)."""
    paths, now = ctx.paths, ctx.deps.clock()
    if not _renewal_due(paths, now):
        return None
    if backups.active_journal(paths, instance).exists():
        return "skipped"
    sub = dataclasses.replace(ctx, job="renew-certificate")
    try:
        code = str(renewal.handle(sub, {"run_id": ctx.run_id})["code"])
        record = {"succeeded_at": now.isoformat()}
    except Exception as error:  # a failed renewal must not fail the backup tick
        code = error.code if isinstance(error, JobError) else "renewal_failed"
        ctx.log.line(ctx.step(9, "renewal"), "WARN", f"renewal failed: {type(error).__name__}")
        record = {"failed_at": now.isoformat()}
    try:
        previous = json.loads((paths.state / "renewal.json").read_text())
    except (OSError, ValueError):
        previous = {}
    previous = previous if isinstance(previous, dict) else {}
    write_private(paths.state / "renewal.json",
                  (json.dumps({**previous, **record}, sort_keys=True) + "\n").encode())  # fmt: skip
    return code


# Jobs ----------------------------------------------------------------------------------------


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths, step = ctx.paths, ctx.step(1, "runner")
    instance = backups.installed_instance(paths)
    if instance is None:
        return {"code": "not_set_up"}
    started = record_start(ctx, ctx.step(2, "start"))
    created = backups.container_created(ctx, step)
    if created is not None:
        if ctx.deps.clock() - created <= timedelta(seconds=backups.RUNNER_SECONDS):
            raise refused("runner_busy")
        ctx.log.line(step, "WARN", f"removing an orphan runner container from {created}")
        backups.remove_container(ctx, step)
        return {"code": "orphan_removed"}
    if lock_state(backups.runner_lock(paths, instance), paths.proc) is not False:
        raise refused("runner_busy")
    image = pair_check(ctx, step)
    mounted = drive.mounted(paths)
    outcome = run_runner(ctx, step, image, ["run"])
    renewed = renew_if_due(ctx, instance)
    # A tick that did nothing (no claim, no mount, no renewal, no refusal) keeps no log.
    ctx.keep_log = (
        started or not mounted or renewed is not None or outcome["runner"] != "idle"
        or outcome["runner_exit"] != 0
    )  # fmt: skip
    return {"code": "ran", **outcome, "renewal": renewed or "not_due"}


def _support(ctx: Context, action: list[str]) -> dict[str, Any]:
    step = ctx.step(1, "runner")
    instance = backups.installed_instance(ctx.paths)
    if instance is None:
        raise refused("not_installed")
    if backups.busy(ctx, step, instance):
        raise refused("runner_busy")
    image = pair_check(ctx, step)
    outcome = run_runner(ctx, step, image, action)
    if outcome["runner_exit"] not in (0, 2):
        raise failed("runner_failed", runner=outcome["runner"])
    return {"code": "ran", **outcome}


def recover(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    """``runner-recover``: the runner's ``recover`` (support, plan 8.1 item 2)."""
    return _support(ctx, ["recover"])


def adopt(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    """``runner-adopt``: ``recover --restore-finalized`` with the fixed marker (plan 7.5 step
    6; W13b writes the marker)."""
    return _support(ctx, ["recover", "--restore-finalized", str(marker(ctx.paths))])
