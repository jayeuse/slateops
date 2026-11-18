"""The backup runner's container and install step 12 (plan 6.2 step 12, 8.1 to 8.3; TASK-0092
(a*); TASK-0093 AC-4 to AC-8, AC-10).

The runner and the backup tool run unchanged, from the active engine bundle, in a one-shot
container of the release server image named ``slateops-runner`` (``container_argv``, the one
builder). It runs as root with the Docker socket, as the Linux operator runner does
(APR-0012, G-1): CAP_CHOWN for the export group, CAP_DAC_OVERRIDE for the two files that Caddy
(UID 1000) owns; every other capability is dropped. Every mount uses its host path, because
the runner passes host paths to the Docker daemon. ``/etc/slateops/ca`` and ``new`` are
covered by empty read-only folders.

Nothing changes while the runner works: a job that changes the target, the keys, the config
or the certificate refuses with ``runner_busy`` while the runner's host lock is held or a
``slateops-runner`` container exists, and takes the same lock for its own work.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine import compose, drive, journal, progress, release
from engine.context import Context
from engine.core import (
    Paths,
    failed,
    held_lock,
    is_run_id,
    lock_state,
    private_dir,
    refused,
    write_private,
)

RUNNER = "slateops-runner"
# The tick's time limit: the runner's 1,800 s child budget, its 3,600 s prune limit, and
# 1,800 s for the stop, the restart, the forgets and the bridge calls (planning value).
RUNNER_SECONDS = 1800 + 3600 + 1800
DOCKER_CLI, RESTIC_CLI = "/usr/bin/docker", "/usr/bin/restic"
CLI_PLUGINS = "/usr/libexec/docker/cli-plugins"
UNITS = ("slateops-runner.service", "slateops-runner.timer")
EXPORT_GID = 10001  # the API user that reads finished exports (backup-exports, 0750)
_CREATED = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})\Z")
TARGET_KEYS = {"run_id": is_run_id, "backup_target": drive.valid_target}
KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
TARGET_REQUIRED = frozenset(TARGET_KEYS)


def runner_state(paths: Paths) -> Path:
    return paths.state / "runner"


def config_path(paths: Paths) -> Path:
    return paths.etc / "backup.json"


def runner_lock(paths: Paths, instance: str) -> Path:
    """The runner's host lock (``host.py`` ``locked``): the engine takes the same file."""
    return runner_state(paths) / instance / "lock"


def active_journal(paths: Paths, instance: str) -> Path:
    return runner_state(paths) / instance / "active.json"


def installed_instance(paths: Paths) -> str | None:
    """The Compose project of an installation whose step 12 is done."""
    state = journal.load(paths)
    project = (state or {}).get("project")
    if state is None or not journal.done(state, 12) or not isinstance(project, str):
        return None
    return project


def server_image(paths: Paths, version: str) -> str:
    """The server image by its ID: the signed manifest digest (AC-1)."""
    manifest = release.require(paths, version)
    entry = (manifest.get("images") or {}).get("server") or {}
    match = release.REFERENCE.match(str(entry.get("ref", "")))
    if match is None:
        raise refused("manifest_invalid", part="server")
    return match.group("digest")


# The container -----------------------------------------------------------------------------------


def container_argv(ctx: Context, image: str, tail: list[str]) -> list[str]:
    """The tick container of TASK-0092 (a*) step 3 (AC-10)."""
    paths = ctx.paths
    bundle, logs = paths.bundle_root, paths.logs / "app"
    backup, state = drive.backup_root(paths), runner_state(paths)
    hidden = "ro,noexec,nosuid,nodev,size=4k,mode=0000"
    return [
        "docker", "run", "--rm", "--init", "--name", RUNNER, "--pull=never",
        "--user", "0:0", "--read-only", "--tmpfs", "/tmp",  # Restic's temporary packs
        "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE",
        "--security-opt", "no-new-privileges", "--no-healthcheck",
        "--mount", f"type=bind,source={paths.docker_socket},target=/var/run/docker.sock",
        "--mount", f"type=bind,source={DOCKER_CLI},target=/usr/local/bin/docker,readonly",
        "--mount", f"type=bind,source={RESTIC_CLI},target=/usr/local/bin/restic,readonly",
        "--mount", f"type=bind,source={CLI_PLUGINS},target={CLI_PLUGINS},readonly",
        "--mount", f"type=bind,source={bundle},target={bundle},readonly",
        "--mount", f"type=bind,source={paths.etc},target={paths.etc},readonly",
        "--mount", f"type=bind,source={logs},target={logs},readonly",
        "--mount", f"type=bind,source={backup},target={backup}",
        "--mount", f"type=bind,source={state},target={state}",
        "--tmpfs", f"{paths.etc / 'ca'}:{hidden}",
        "--tmpfs", f"{paths.etc / 'new'}:{hidden}",
        "--env", f"SLATEOPS_RUN_ID={ctx.run_id}",
        "--entrypoint", "python", image, *tail,
    ]  # fmt: skip


def container_created(ctx: Context, step: str) -> datetime | None:
    """The creation time of ``slateops-runner``, or None when there is none."""
    listing = ctx.runner.run(
        step,
        ["docker", "ps", "--all", "--filter", f"name={RUNNER}", "--format", "{{.Names}}"],
        timeout=60,
    )
    if not listing.ok:
        raise failed("docker_unavailable")
    if RUNNER not in listing.text().split():
        return None
    found = ctx.runner.run(
        step, ["docker", "container", "inspect", "--format", "{{.Created}}", RUNNER], timeout=60
    )
    match = _CREATED.match(found.text().strip()) if found.ok else None
    if match is None:
        return ctx.deps.clock()  # unreadable: count it as new, so nothing removes it
    zone = "+00:00" if match.group(2) == "Z" else match.group(2)
    return datetime.fromisoformat(match.group(1) + zone).astimezone(UTC)


def remove_container(ctx: Context, step: str) -> None:
    """``docker rm --force slateops-runner``, then confirm that it is gone (AC-7)."""
    ctx.runner.run(step, ["docker", "rm", "--force", RUNNER], timeout=60)
    for _ in range(30):
        if container_created(ctx, step) is None:
            return
        ctx.deps.sleep(1.0)
    raise failed("runner_not_removed")


def busy(ctx: Context, step: str, instance: str) -> bool:
    return (
        lock_state(runner_lock(ctx.paths, instance), ctx.paths.proc) is not False
        or container_created(ctx, step) is not None
    )


@contextmanager
def runner_idle(ctx: Context, step: str, instance: str) -> Iterator[None]:
    """Hold the runner's host lock with no runner container (AC-8), or refuse."""
    if busy(ctx, step, instance):
        raise refused("runner_busy")
    with held_lock(runner_lock(ctx.paths, instance), "runner_busy"):
        if container_created(ctx, step) is not None:
            raise refused("runner_busy")
        yield


# Install step 12 ---------------------------------------------------------------------------------


def _folder(ctx: Context, path: Path, mode: int, owner: tuple[int, int] = (0, 0)) -> None:
    if path.is_symlink():
        raise failed("unsafe_path", part=path.name)
    path.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path, mode)
    ctx.deps.chown(path, *owner)


def make_export_root(ctx: Context) -> Path:
    """Steps 2 and 5: the export root next to the repository, before the API starts (the
    runner requires ``restic_repository.parent/backup-exports``, TASK-0081 O-2)."""
    root = drive.backup_root(ctx.paths)
    _folder(ctx, root, 0o700)
    exports = root / "backup-exports"
    _folder(ctx, exports, 0o750, (0, EXPORT_GID))
    return exports


def _folders(ctx: Context) -> None:
    root = drive.backup_root(ctx.paths)
    if not drive.mounted(ctx.paths):  # never change the owner or mode of the drive itself
        _folder(ctx, drive.mount_point(ctx.paths), 0o700)
    for name in ("staging", "markers"):
        _folder(ctx, root / name, 0o700)
    private_dir(runner_state(ctx.paths))
    _folder(ctx, runner_state(ctx.paths), 0o700)


def write_config(ctx: Context, step: str, instance: str) -> None:
    """The version-3 backup config (TASK-0092 D-1, C-2): one writer, under the runner's lock
    and only with no active runner journal (a changed config makes it ``journal_invalid``).
    The update (W13b) calls it again to point ``compose_root`` at the new bundle."""
    paths = ctx.paths
    with runner_idle(ctx, step, instance):
        if active_journal(paths, instance).exists():
            raise refused("runner_busy")
        write_private(config_path(paths), config_bytes(paths, instance, paths.bundle_root))
    root = paths.bundle_root / "infra" / "supabase"
    ctx.log.line(step, "INFO", f"backup config written; compose_root {root}")


def config_bytes(paths: Paths, instance: str, bundle_root: Path) -> bytes:
    """The version-3 config of ``instance`` with the Compose root of ``bundle_root``; the
    update writes it while it holds the runner's lock itself (C-2)."""
    backup = drive.backup_root(paths)
    config = {
        "version": 3,
        "installation_id": instance,
        "project_name": instance,
        "deployment": "production",
        "compose_layout": "installer",
        "compose_root": str(bundle_root / "infra" / "supabase"),
        "provider_env_file": str(paths.etc / "provider.env"),
        "app_env_file": str(paths.etc / "app.env"),
        "caddy_config_file": str(paths.etc / "Caddyfile"),
        "tls_directory": str(paths.etc / "tls"),
        "restic_repository": str(drive.mount_point(paths)),
        "restic_password_file": str(paths.etc / "restic-password"),
        "staging_directory": str(backup / "staging"),
        "completion_marker": str(backup / "markers" / "backup-complete.json"),
    }
    return (json.dumps(config, indent=2, sort_keys=True) + "\n").encode()


def _policy_default(ctx: Context, step: str, instance: str, image: str) -> None:
    """``policy_default`` through the bridge, with the runner's bridge command line
    (``host.py`` ``bridge``): before the timer and the first backup (W5a D-3)."""
    name = f"slateops-backup-{secrets.token_hex(16)}"
    argv = [
        "docker", "run", "--rm", "--pull=never", "--name", name,
        "--network", f"{instance}_provider", "--env-file", str(ctx.paths.etc / "app.env"),
        "--user", "10001:10001", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--no-healthcheck",
        "--interactive", "--env", "SLATEOPS_ENV_SOURCE=process",
        "--entrypoint", "python", image, "operations/backup_state.py",
    ]  # fmt: skip
    payload = {"installation_id": instance, "project": instance, "op": "policy_default"}
    result = ctx.runner.run(step, argv, timeout=120, input=json.dumps(payload).encode())
    try:
        answer = json.loads(result.text()) if result.ok else {}
    except ValueError:
        answer = {}
    if not isinstance(answer, dict) or "code" in answer or "policy" not in answer:
        ctx.runner.run(step, ["docker", "rm", "--force", name], timeout=60)
        raise failed("policy_default_failed")
    ctx.log.line(step, "INFO", f"default policy {'written' if answer.get('written') else 'kept'}")


def _first_backup(
    ctx: Context, step: str, image: str, project: str, restart: Callable[[], None]
) -> None:
    """Stop the stack, run the backup tool (Restic backup and ``restic check --read-data``) in
    the tick container, then restart in order with ``caddy`` last (10.3 F5)."""
    paths = ctx.paths
    tool = str(paths.bundle_root / "packaging" / "backup" / "backup_installation.py")
    argv = container_argv(ctx, image, [tool, "--config", str(config_path(paths))])
    if not ctx.runner.run(step, compose.argv(paths, project, "stop"), timeout=300).ok:
        restart()
        raise failed("first_backup_failed")
    try:
        try:
            result = ctx.runner.run(step, argv, timeout=RUNNER_SECONDS)
        finally:
            remove_container(ctx, step)
    finally:
        restart()
    if not result.ok:
        raise failed("first_backup_failed")
    ctx.log.line(step, "INFO", "first backup and restic check passed")


def _install_units(ctx: Context, step: str) -> None:
    paths = ctx.paths
    paths.systemd.mkdir(mode=0o755, parents=True, exist_ok=True)
    for name in UNITS:
        data = (paths.engine_home / "units" / name).read_bytes()
        target = paths.systemd / name
        if target.is_file() and not target.is_symlink() and target.read_bytes() == data:
            continue
        temporary = target.with_name(f".{name}.{os.getpid()}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    for argv in (
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "slateops-runner.timer"],
    ):
        if not ctx.runner.run(step, argv, timeout=120).ok:
            raise failed("timer_failed")


def setup(
    ctx: Context,
    step: str,
    state: dict[str, Any],
    given: dict[str, Any],
    restart: Callable[[], None],
) -> None:
    """Install step 12 in the TASK-0092 order; each part is safe to repeat after a kill."""
    paths = ctx.paths
    project = str(state["project"])
    target = drive.load_target(paths) or given["backup_target"]
    if not drive.valid_target(target):
        raise failed("backup_target_invalid")
    image = server_image(paths, str(state["version"]))
    _folders(ctx)  # 12.1
    drive.store_target(paths, target)
    if not drive.mount(ctx, step, target):  # 12.2
        raise failed("backup_target_missing")
    drive.open_or_init(ctx, step)
    write_config(ctx, step, project)  # 12.3
    # B-1: a kill during 12.5 leaves the stack stopped and a rerun starts here; the bridge
    # needs the database. On a first run the providers already run, and this changes nothing.
    compose.up(ctx, step, project, compose.PROVIDER_SERVICES, deps=True)
    compose.wait_healthy(ctx, step, project, compose.PROVIDER_SERVICES)
    _policy_default(ctx, step, project, image)  # 12.4
    _first_backup(ctx, step, image, project, restart)  # 12.5
    ctx.outputs["recovery_key"] = drive.new_recovery_key(ctx, step)  # 12.6
    _install_units(ctx, step)  # 12.7, without the unmount: the drive stays mounted
    state["backup_setup"] = "ready"


# Jobs --------------------------------------------------------------------------------------------


def _instance(ctx: Context) -> str:
    instance = installed_instance(ctx.paths)
    if instance is None:
        raise refused("not_installed")
    return instance


def _stopped_at_backup(paths: Paths) -> str | None:
    """The project of an install that stopped in step 12 (TASK-0094 F5: "Choose another drive"
    after a failed first backup; the rerun of step 12 takes the stored target)."""
    state = journal.load(paths)
    project = (state or {}).get("project")
    if state is None or not journal.done(state, 11) or journal.done(state, 12):
        return None
    return project if isinstance(project, str) else None


def set_target(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    """``set-backup-target``: mount the new folder, open or create its repository, keep it.
    A refusal unmounts the new folder and keeps the old target stored; the next tick mounts
    it again."""
    paths, step = ctx.paths, ctx.step(1, "target")
    instance = installed_instance(paths) or _stopped_at_backup(paths)
    if instance is None:
        raise refused("not_installed")
    target = request["backup_target"]
    with runner_idle(ctx, step, instance):
        progress.report(ctx, "unmount")
        if not drive.unmount(ctx, step):
            raise failed("backup_target_busy")
        try:
            progress.report(ctx, "mount")
            if not drive.mount(ctx, step, target):
                raise refused("backup_target_missing")
            progress.report(ctx, "repository")
            repository = drive.open_or_init(ctx, step)
        except Exception:
            drive.unmount(ctx, step)
            raise
        drive.store_target(paths, target)
    return {"code": "backup_target_set", "repository": repository}


def new_key(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    """``new-recovery-key``: a new recovery key; the old one stops working (8.3, W10b-3)."""
    paths, step = ctx.paths, ctx.step(1, "key")
    instance = _instance(ctx)
    with runner_idle(ctx, step, instance):
        progress.report(ctx, "mount")
        target = drive.load_target(paths)
        if target is None or not drive.mount(ctx, step, target):
            raise refused("backup_target_missing")
        progress.report(ctx, "key")
        key = drive.new_recovery_key(ctx, step)
    return {"code": "recovery_key_created", "recovery_key": key}
