"""``update``: update the installation to a newer release that ``receive`` kept (plan 7.3 to
7.5, section 12; W13b, TASK-0095).

Input (the setup-program path, plan 7.4): ``run_id`` and the target ``version``. The installed
engine runs every step. Steps 6 to 11 read the target bundle's templates and Compose files
through paths that point at that bundle (TASK-0095 decision D-1: the plan's "run the new
engine" is not built as a hand-over). Steps (``update.NN.<name>``), each recorded in the
journal ``/var/lib/slateops/update/<run ID>.json`` before the next starts:

1. ``lock``: the runner's host lock for the whole update, so no tick, backup or export
   starts; refuse while a runner journal is active (``recovery_required``).
2. ``release``: the target manifest that ``receive`` verified (signature, SHA-256); the
   engine bundle checked by its SHA-256 again and unpacked beside the old one.
3. ``space``: room for one restored copy of the volumes (7.5); else ``insufficient_space``,
   and nothing stops.
4. ``images``: our two images by manifest digest; the provider images by digest.
5. ``backup``: stop the services; the offline backup with this run's own completion marker;
   its snapshot ID and manifest SHA-256 go into the journal (TASK-0083 C-1).
6. ``env``: the two image names change and new template keys are added; every other value,
   every secret included, stays.
7. ``providers``: the rollback boundary, journaled before the first container starts; then the
   provider services on the target images, every container recreated (TASK-0092 C-2).
8. ``health``; 9. ``provision`` (roles, ``alembic upgrade head``, Storage); 10. ``api``
   (ready, and the running container reports the target version); 11. ``caddy`` (HTTPS
   through loopback).
12. ``switch``: every container carries the target bundle's Compose folder; then the backup
    config's ``compose_root``, the command link and the ``installation.json`` version, in
    that order (C-2).

A failure before step 7 runs ``recover``: the env files get the old image names again and the
services start on the old images, ``caddy`` last after readiness; the journal closes
``failed``. A failure in or after step 7 rolls back by restore (7.5) into ``<base>-r<n>``; the
journal closes ``rolled_back``. A rollback or recover that cannot finish closes
``needs_support``. A closed journal is never resumed. Section 12: the next engine job that
holds the engine lock (the tick or another update) closes an interrupted update by the same
rule, except that an update whose step 11 is done finishes step 12.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

from engine import answers, backups, compose, drive, install, journal, progress, release, tick
from engine.context import Context
from engine.core import (
    FAILED,
    INSTANCE_ID,
    JobError,
    Paths,
    engine_version,
    failed,
    is_run_id,
    is_version,
    private_dir,
    refused,
    write_private,
)
from engine.env_templates import TemplateError, render
from engine.runner import Result

KEYS = {"run_id": is_run_id, "version": is_version}
REQUIRED = frozenset(KEYS)
OPEN = ("running", "rolling_back")
IMAGE_KEYS = {"server": "SLATEOPS_SERVER_IMAGE", "caddy": "SLATEOPS_CADDY_IMAGE"}
RESTORE_SECONDS = 4 * 3600  # planning value: the Restic restore and the volume import
_ROLLBACK = re.compile(r"(?P<base>.+)-r(?P<n>[1-9][0-9]{0,3})\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_LINE = re.compile(r"([A-Z_][A-Z0-9_]*)=(.*)\Z")
_VERSION_READ = "import os; print(os.environ.get('SLATEOPS_VERSION', ''))"
_FOLDER_LABEL = '{{.Label "com.docker.compose.project.working_dir"}}'
# The host restore (TASK-0083 C-3): a subprocess of the old bundle's restore tool with
# ``--engine-binding``; the confirmation comes from ``confirmation_text()``.
_RESTORE = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from backup import restore_installation as tool\n"
    "mode, config, snapshot, project, directory = sys.argv[2:7]\n"
    "head = ['--config', config, '--snapshot', snapshot, '--target-project', project,\n"
    "        '--target-instance-id', project, '--target-directory', directory]\n"
    "if mode == 'finalize':\n"
    "    raise SystemExit(tool.main([*head, '--finalize']))\n"
    "text = tool.confirmation_text(Path(config), snapshot, project, Path(directory), project)\n"
    "raise SystemExit(tool.main([*head, '--execute', '--confirm', text,\n"
    "                            '--engine-binding', sys.argv[7]]))\n"
)


def precedence(version: str) -> tuple[int, int, int, int, int]:
    """SemVer precedence of ``X.Y.Z`` and ``X.Y.Z-rc.N`` (W13b-10): a release candidate comes
    before its release, and ``N`` compares as a number."""
    core, _, candidate = version.partition("-rc.")
    major, minor, patch = (int(part) for part in core.split("."))
    return (major, minor, patch, 0, int(candidate)) if candidate else (major, minor, patch, 1, 0)


# The journal -------------------------------------------------------------------------------


def folder(paths: Paths) -> Path:
    return paths.state / "update"


def journal_path(paths: Paths, run_id: str) -> Path:
    return folder(paths) / f"{run_id}.json"


def binding_path(paths: Paths, run_id: str) -> Path:
    return folder(paths) / f"{run_id}.restore-binding.json"


def bundle_root(paths: Paths, version: str) -> Path:
    """Each version's bundle folder, beside the others (``/opt/slateops/engine/<version>``)."""
    return paths.bundle_root.parent / version


def journals(paths: Paths) -> list[dict[str, Any]]:
    found = []
    for path in sorted(folder(paths).glob("*.json")):
        if path.name.endswith(".restore-binding.json"):
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and is_run_id(data.get("run_id")):
            found.append(data)
    return found


def is_open(paths: Paths) -> bool:
    """An update runs or was interrupted: ``engine_idle`` stays false (plan 7.4)."""
    return any(record.get("state") in OPEN for record in journals(paths))


def needs_support(paths: Paths) -> bool:
    """An update closed ``needs_support`` (a rollback or recover that did not finish): the
    install journal can still name the failed project, so nothing may start it again. No
    self-service retry in v1; the person sends Save report to support (TASK-0095 S95-1)."""
    return any(record.get("state") == "needs_support" for record in journals(paths))


def started_since(paths: Paths, moment: datetime) -> bool:
    for record in journals(paths):
        try:
            if datetime.fromisoformat(str(record.get("started_at"))) >= moment:
                return True
        except ValueError:
            continue
    return False


def _at(ctx: Context) -> str:
    return ctx.deps.clock().isoformat()


def _save(paths: Paths, record: dict[str, Any]) -> None:
    private_dir(folder(paths))
    data = json.dumps(record, indent=2, sort_keys=True) + "\n"
    write_private(journal_path(paths, record["run_id"]), data.encode())


def _mark(ctx: Context, record: dict[str, Any], number: int) -> None:
    record["steps"][f"{number:02d}"] = _at(ctx)
    _save(ctx.paths, record)


def _done(record: dict[str, Any], number: int) -> bool:
    steps = record.get("steps")
    return isinstance(steps, dict) and f"{number:02d}" in steps


# Shared parts ------------------------------------------------------------------------------


def _with_bundle(ctx: Context, root: Path) -> Context:
    """The same run, with the templates and Compose files of the bundle at ``root``."""
    paths = dataclasses.replace(ctx.paths, engine_home=root / "engine")
    return dataclasses.replace(ctx, deps=dataclasses.replace(ctx.deps, paths=paths))


def _images(manifest: dict[str, Any], version: str) -> dict[str, str]:
    images = manifest.get("images")
    names: dict[str, str] = {}
    for role in IMAGE_KEYS:
        entry = images.get(role) if isinstance(images, dict) else None
        reference = str(entry.get("ref", "")) if isinstance(entry, dict) else ""
        match = release.REFERENCE.match(reference)
        if match is None or match.group("tag") != version:
            raise refused("manifest_invalid", part=role)
        names[role] = f"{match.group('name')}:{match.group('tag')}"
    return names


def _host(paths: Paths) -> str:
    given = answers.load(paths)
    if given is None:
        raise failed("install_state_mismatch", part="answers")
    return str(given["public_host"])


def _installed(paths: Paths) -> dict[str, Any]:
    try:
        found = json.loads(paths.installation.read_text())
    except (OSError, ValueError) as error:
        raise refused("not_installed") from error
    if not isinstance(found, dict) or not is_version(found.get("version")):
        raise refused("not_installed")
    return found


def _write_json(path: Path, value: dict[str, Any]) -> None:
    write_private(path, (json.dumps(value, sort_keys=True) + "\n").encode())


def write_env(ctx: Context, step: str, images: dict[str, str]) -> None:
    """Step 6 (and ``recover``): set the two image names, add the template keys that the
    files do not have yet, keep every other line. A new key that needs a value no file
    holds (a new secret) fails before step 7 (decision D-3)."""
    paths = ctx.paths
    texts = {name: (paths.etc / name).read_text(encoding="utf-8") for name in install.ENV_FILES}
    values: dict[str, str] = {}
    for text in texts.values():
        for line in text.splitlines():
            if match := _LINE.match(line):
                values.setdefault(match.group(1), match.group(2))
    values["PUBLIC_HOST"] = _host(paths)
    values.update({IMAGE_KEYS[role]: name for role, name in images.items()})
    for name, text in texts.items():
        lines, keys = [], set()
        for line in text.splitlines():
            match = _LINE.match(line)
            if match:
                keys.add(match.group(1))
                if match.group(1) in IMAGE_KEYS.values():
                    line = f"{match.group(1)}={values[match.group(1)]}"
            lines.append(line)
        template = (paths.engine_home / "templates" / name).read_text(encoding="utf-8")
        added = []
        try:
            for line in template.splitlines():
                match = _LINE.match(line)
                if match and match.group(1) not in keys:
                    added.append(render(line, values).rstrip("\n"))
        except TemplateError as error:
            raise failed("env_render_failed", part=name) from error
        data = "\n".join([*lines, *added]) + "\n"
        if data != text:
            write_private(paths.etc / name, data.encode())
        ctx.log.line(step, "INFO", f"{name}: image names set, {len(added)} new keys")


def start_all(ctx: Context, step: str, project: str) -> None:
    """Providers, then ``api`` until ready, then ``caddy`` last with HTTPS through loopback."""
    compose.up(ctx, step, project, compose.PROVIDER_SERVICES, deps=True)
    compose.wait_healthy(ctx, step, project, compose.PROVIDER_SERVICES)
    compose.up(ctx, step, project, ("api",), deps=False)
    compose.wait_healthy(ctx, step, project, ("api",))
    compose.wait_api_ready(ctx, step, project)
    compose.up(ctx, step, project, ("caddy",), deps=False)
    install.wait_https(ctx, step, _host(ctx.paths))


def _link(paths: Paths, root: Path) -> None:
    """Point ``/usr/local/bin/slateops-engine`` at the launcher of the bundle at ``root``."""
    command = paths.engine_command
    command.parent.mkdir(parents=True, exist_ok=True)
    temporary = command.with_name(f".{command.name}.new")
    temporary.unlink(missing_ok=True)
    os.symlink(root / "slateops-engine", temporary)
    os.replace(temporary, command)


# Steps 2 to 12 -----------------------------------------------------------------------------


def _bundle(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> Path:
    paths, name = ctx.paths, release.bundle_name(version)
    entry = manifest.get("engine_bundle")
    if not isinstance(entry, dict) or entry.get("archive") != name:
        raise refused("manifest_invalid", part="engine_bundle")
    archive = release.release_folder(paths, version) / name
    digest = hashlib.sha256()
    try:
        with archive.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise refused("manifest_missing") from error
    if digest.hexdigest() != entry.get("sha256"):
        raise refused("payload_mismatch", part="engine_bundle")
    root = bundle_root(paths, version)
    if root.is_symlink():
        raise failed("unsafe_path", part="engine_bundle")
    if not root.is_dir():
        temporary = root.with_name(f".{version}.{ctx.run_id}")
        shutil.rmtree(temporary, ignore_errors=True)
        temporary.mkdir(mode=0o755)
        try:
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(temporary, filter="data")
            os.rename(temporary, root)
        except (OSError, tarfile.TarError) as error:
            shutil.rmtree(temporary, ignore_errors=True)
            raise failed("bundle_incomplete") from error
    unpacked = dataclasses.replace(paths, engine_home=root / "engine")
    if engine_version(unpacked) != version or not all(
        path.is_file() for path in compose.files(unpacked)
    ):
        raise failed("bundle_incomplete")
    ctx.log.line(step, "INFO", f"engine bundle {version} unpacked beside {engine_version(paths)}")
    return root


def volume_bytes(paths: Paths, project: str) -> int:
    """The space that the project's Docker volumes take (allocated blocks)."""
    total = 0
    for volume in sorted(paths.docker_volumes.glob(f"{project}_*")):
        for top, folders, files in os.walk(volume):
            for name in (*folders, *files):
                try:
                    total += os.lstat(os.path.join(top, name)).st_blocks * 512
                except OSError:
                    continue
    return total


def _space(ctx: Context, step: str, project: str) -> None:
    """Room for one restored copy (7.5): the Restic restore unpacks the volume archives into
    staging, then imports them into new volumes; plus the install reserve (planning value)."""
    used = volume_bytes(ctx.paths, project)
    need = 2 * used + install.SPACE_BYTES
    free = ctx.deps.disk_free(ctx.paths.state)
    ctx.log.line(step, "INFO" if free >= need else "ERROR",
                 f"volumes {used} bytes; free {free}, need {need}")  # fmt: skip
    if free < need:
        raise failed("insufficient_space", needs_gb=math.ceil(need / 10**9))


def _backup(ctx: Context, step: str, record: dict[str, Any]) -> None:
    """Step 5: stop, then the backup tool in the runner container with this run's own config
    and marker (the tool refuses a marker that exists, and install's first one does)."""
    paths, project = ctx.paths, record["project"]
    image = backups.server_image(paths, record["from_version"])
    target = drive.load_target(paths)
    if target is None or not drive.mount(ctx, step, target):
        raise failed("backup_target_missing")
    run = private_dir(backup_config(paths, record).parent)
    config = json.loads(backups.config_path(paths).read_text())
    config["completion_marker"] = str(run / "backup-complete.json")
    _write_json(run / "backup.json", config)
    record["stopped"] = True
    _save(paths, record)
    if not ctx.runner.run(step, compose.argv(paths, project, "stop"), timeout=300).ok:
        raise failed("services_not_stopped")
    tool = str(paths.bundle_root / "packaging" / "backup" / "backup_installation.py")
    argv = backups.container_argv(ctx, image, [tool, "--config", str(run / "backup.json")])
    try:
        result = ctx.runner.run(step, argv, timeout=backups.RUNNER_SECONDS)
    finally:
        backups.remove_container(ctx, step)
    if not result.ok:
        raise failed("backup_failed")
    try:
        marker = json.loads((run / "backup-complete.json").read_text())
    except (OSError, ValueError) as error:
        raise failed("backup_failed") from error
    if not (
        isinstance(marker, dict)
        and _HEX.match(str(marker.get("snapshot_id", "")))
        and _HEX.match(str(marker.get("manifest_sha256", "")))
        and marker.get("source_project") == project
    ):
        raise failed("backup_failed")
    record["snapshot_id"] = marker["snapshot_id"]
    record["manifest_sha256"] = marker["manifest_sha256"]
    ctx.log.line(step, "INFO", f"pre-update snapshot {marker['snapshot_id']}")


def _check_version(ctx: Context, step: str, project: str, version: str) -> None:
    """Step 10: the running ``api`` container reports the target ``SLATEOPS_VERSION`` (W1)."""
    argv = compose.argv(ctx.paths, project, "exec", "-T", "api", "python", "-c", _VERSION_READ)
    result = ctx.runner.run(step, argv, timeout=30)
    found = result.text().strip()
    ctx.log.line(step, "INFO", f"api reports version {found or '?'}")
    if not result.ok or found != version:
        raise failed("api_version_mismatch")


def _switch(ctx: Context, record: dict[str, Any]) -> None:
    """Step 12 in the C-2 order; the labels are checked before anything changes."""
    paths, version, project = ctx.paths, record["target_version"], record["project"]
    step, root = ctx.step(12, "switch"), bundle_root(paths, record["target_version"])
    progress.report(ctx, "switch", job="update")
    wanted = str(root / "infra" / "supabase")
    label = f"label=com.docker.compose.project={project}"
    listing = ctx.runner.run(step, ["docker", "ps", "--all", "--filter", label,
                                    "--format", _FOLDER_LABEL], timeout=60)  # fmt: skip
    folders = set(listing.text().splitlines())
    if not listing.ok or folders != {wanted}:
        ctx.log.line(step, "ERROR", f"Compose folders of the containers: {sorted(folders)}")
        raise failed("recreate_incomplete")
    images = _images(release.require(paths, version), version)
    write_private(backups.config_path(paths), backups.config_bytes(paths, project, root))
    _link(paths, root)
    _write_json(paths.installation, {**_installed(paths), "version": version})
    state = journal.load(paths)  # renewal reads the server image here
    if not isinstance(state, dict) or state.get("schema") != journal.SCHEMA:
        raise failed("install_state_mismatch", part="journal")
    state.update(version=version, server_image=images["server"], caddy_image=images["caddy"])
    journal.save(paths, state)
    record["state"], record["finished_at"] = "succeeded", _at(ctx)
    _mark(ctx, record, 12)
    ctx.log.line(step, "INFO", f"updated to {version}")


def _forward(ctx: Context, record: dict[str, Any], manifest: dict[str, Any]) -> None:
    paths, version, project = ctx.paths, record["target_version"], record["project"]
    images = _images(manifest, version)
    progress.report(ctx, "release")
    new = _with_bundle(ctx, _bundle(ctx, ctx.step(2, "release"), manifest, version))
    _mark(ctx, record, 2)
    progress.report(ctx, "space")
    _space(ctx, ctx.step(3, "space"), project)
    _mark(ctx, record, 3)
    progress.report(ctx, "images")
    install.step_images(new, ctx.step(4, "images"), {"version": version}, {}, manifest)
    _mark(ctx, record, 4)
    progress.report(ctx, "backup")
    _backup(ctx, ctx.step(5, "backup"), record)
    _mark(ctx, record, 5)
    progress.report(ctx, "env")
    write_env(new, ctx.step(6, "env"), images)
    _mark(ctx, record, 6)
    step = ctx.step(7, "providers")
    progress.report(ctx, "providers")
    record["boundary"] = True  # 7.3 step 7: recorded before the first target container starts
    _save(paths, record)
    compose.check_config(new, step, project)
    compose.up(new, step, project, compose.PROVIDER_SERVICES, deps=True, recreate=True)
    _mark(ctx, record, 7)
    progress.report(ctx, "health")
    compose.wait_healthy(new, ctx.step(8, "health"), project, compose.PROVIDER_SERVICES)
    _mark(ctx, record, 8)
    progress.report(ctx, "provision")
    state = {"project": project, "server_image": images["server"]}
    install.step_provision(new, ctx.step(9, "provision"), state, {}, manifest)
    _mark(ctx, record, 9)
    step = ctx.step(10, "api")
    progress.report(ctx, "api")
    compose.up(new, step, project, ("api",), deps=False, recreate=True)
    compose.wait_healthy(new, step, project, ("api",))
    compose.wait_api_ready(new, step, project)
    _check_version(new, step, project, version)
    _mark(ctx, record, 10)
    step = ctx.step(11, "caddy")
    progress.report(ctx, "caddy")
    compose.up(new, step, project, ("caddy",), deps=False, recreate=True)
    install.wait_https(new, step, _host(paths))
    _mark(ctx, record, 11)
    _switch(ctx, record)


# Recover and rollback ----------------------------------------------------------------------


def _remove_tool_children(ctx: Context, step: str, project: str) -> None:
    """A step-5 backup cut by a restart or its time limit: the backup tool's volume export
    (``docker run --rm ... tar``) outlives the tool, created or running, outside the Compose
    project (test build rc.17: a "created" container). The runner admits no backup while a
    container outside the project holds a project volume (``check_readers``,
    ``child_unresolved``). Under the engine lock and the runner's lock no runner, export or
    other job runs, so each such container is the update's own: remove it, then confirm."""
    label = f"label=com.docker.compose.project={project}"
    listing = ctx.runner.run(step, ["docker", "volume", "ls", "--quiet", "--filter", label],
                             timeout=60)  # fmt: skip
    if not listing.ok:
        raise failed("docker_unavailable")
    for attempt in (1, 2):
        loose: set[str] = set()
        for volume in listing.text().split():
            found = ctx.runner.run(step, ["docker", "ps", "--all", "--no-trunc", "--filter",
                                          f"volume={volume}", "--format",
                                          '{{.ID}}\t{{.Label "com.docker.compose.project"}}'],
                                   timeout=60)  # fmt: skip
            if not found.ok:
                raise failed("docker_unavailable")
            for row in found.text().splitlines():
                identity, _, owner = row.partition("\t")
                if identity and not owner:
                    loose.add(identity)
        if not loose:
            return
        if attempt == 2:
            raise failed("backup_child_unresolved")
        ctx.log.line(step, "WARN", f"removing {len(loose)} export container(s) of the cut backup")
        for identity in sorted(loose):
            ctx.runner.run(step, ["docker", "rm", "--force", identity], timeout=60)


def _recover(ctx: Context, record: dict[str, Any]) -> None:
    """Before step 7: the old image names again, then the services on the old images."""
    step = ctx.step(20, "recover")
    if not record.get("stopped"):
        ctx.log.line(step, "INFO", "nothing was stopped; nothing to recover")
        return
    progress.report(ctx, "recover", job="recover")
    if not _done(record, 5):  # the backup did not finish: its children may remain
        _remove_tool_children(ctx, step, record["project"])
    old = _images(release.require(ctx.paths, record["from_version"]), record["from_version"])
    write_env(ctx, step, old)
    start_all(ctx, step, record["project"])


def _down(ctx: Context, step: str, project: str) -> None:
    """7.5 step 1: containers and networks go, volumes stay; refuse while one still runs."""
    ctx.runner.run(step, compose.argv(ctx.paths, project, "down", "--remove-orphans"),
                   timeout=600)  # fmt: skip
    label = f"label=com.docker.compose.project={project}"
    running = ctx.runner.run(step, ["docker", "ps", "--filter", label,
                                    "--format", "{{.Names}}"], timeout=60)  # fmt: skip
    if not running.ok or running.text().strip():
        raise failed("rollback_refused")
    networks = ctx.runner.run(step, ["docker", "network", "ls", "--filter", label,
                                     "--format", "{{.Name}}"], timeout=60)  # fmt: skip
    if not networks.ok or networks.text().strip():
        raise failed("rollback_networks_remain")


def backup_config(paths: Paths, record: dict[str, Any]) -> Path:
    """Step 5's own config: the source installation and Compose root of the snapshot. The
    rollback passes it to the restore tool, because ``backup.json`` can already name the
    restored project (a restart during adopt) or the target bundle (a step-12 failure)."""
    run = backups.runner_state(paths) / str(record["project"]) / "update" / str(record["run_id"])
    return run / "backup.json"


def _tool(
    ctx: Context,
    step: str,
    mode: str,
    record: dict[str, Any],
    project: str,
    directory: Path,
    binding: Path | None = None,
) -> Result:
    paths = ctx.paths
    argv = [
        "python3", "-I", "-c", _RESTORE, str(paths.bundle_root / "packaging"), mode,
        str(backup_config(paths, record)), record["snapshot_id"], project, str(directory),
        *([] if binding is None else [str(binding)]),
    ]  # fmt: skip
    return ctx.runner.run(step, argv, timeout=RESTORE_SECONDS,
                          extra_env={"SLATEOPS_RUN_ID": ctx.run_id})  # fmt: skip


def _rebind(text: str, instance: str) -> bytes:
    """7.5 step 3: only the instance ID changes; the origin, URLs and host name stay (the
    same-origin exception of 7.5)."""
    lines = text.splitlines()
    found = [i for i, line in enumerate(lines) if line.startswith("SLATEOPS_INSTANCE_ID=")]
    if len(found) != 1:
        raise failed("rebind_failed")
    lines[found[0]] = f"SLATEOPS_INSTANCE_ID={instance}"
    return ("\n".join(lines) + "\n").encode()


def _rename(paths: Paths, project: str) -> None:
    """Every reader of the project follows the restored one: the install journal (tick,
    status, snapshot) and ``installation.json``."""
    state = journal.load(paths)
    if not isinstance(state, dict) or state.get("schema") != journal.SCHEMA:
        raise failed("install_state_mismatch", part="journal")
    state["project"] = project
    journal.save(paths, state)
    renamed = {**_installed(paths), "instance_id": project, "project": project}
    _write_json(paths.installation, renamed)


def _rollback(ctx: Context, record: dict[str, Any], job: str = "rollback") -> None:
    """7.5: restore ``record["snapshot_id"]`` into ``<base>-r<n>``. The support restore
    (``restore``, plan 8.4) runs the same steps with its own progress job."""
    paths, failed_project = ctx.paths, record["project"]
    match = _ROLLBACK.match(failed_project)
    base, first = (match.group("base"), int(match.group("n")) + 1) if match else (failed_project, 1)
    earlier = [failed_project, *record.setdefault("rollbacks", [])]
    project = f"{base}-r{first + len(record['rollbacks'])}"
    if not INSTANCE_ID.match(project):
        raise failed("rollback_name_invalid")
    record["rollbacks"].append(project)  # a later attempt takes the next number
    record["state"] = "rolling_back"
    _save(paths, record)
    step = ctx.step(21, "down")
    progress.report(ctx, "down", job=job)
    for name in earlier:
        _down(ctx, step, name)
    step = ctx.step(22, "restore")
    progress.report(ctx, "restore", job=job)
    if not _HEX.match(str(record.get("snapshot_id", ""))):
        raise failed("snapshot_missing")
    directory = private_dir(paths.state / "restore") / project
    target = drive.load_target(paths)
    if target is None or not drive.mount(ctx, step, target):
        raise failed("backup_target_missing")
    binding = binding_path(paths, record["run_id"])
    try:  # C-5, C-6: one private file per attempt, deleted on every path
        bound = {"format_version": 1, "snapshot_id": record["snapshot_id"],
                 "target_project": project, "target_directory": str(directory)}  # fmt: skip
        _write_json(binding, bound)
        restored = _tool(ctx, step, "restore", record, project, directory, binding)
    finally:
        binding.unlink(missing_ok=True)
    if not restored.ok:
        raise failed("restore_failed")
    try:
        pending = json.loads((directory / "restore-pending.json").read_text())
    except (OSError, ValueError) as error:
        raise failed("restore_failed") from error
    expected = record.get("manifest_sha256")  # the support restore knows only the snapshot
    if (
        not isinstance(pending, dict)
        or pending.get("snapshot_id") != record["snapshot_id"]
        or (expected is not None and pending.get("manifest_sha256") != expected)
    ):
        raise failed("restore_mismatch")
    step = ctx.step(23, "rebind")
    progress.report(ctx, "rebind", job=job)
    private = directory / "restored-source-private"
    for name in ("provider.env", "app.env"):
        write_private(paths.etc / name, _rebind((private / name).read_text(), project))
    write_private(paths.etc / "provision.env",
                  _rebind((paths.etc / "provision.env").read_text(), project))  # fmt: skip
    step = ctx.step(24, "finalize")
    progress.report(ctx, "finalize", job=job)
    compose.up(ctx, step, project, ("db",), deps=False)
    compose.wait_healthy(ctx, step, project, ("db",))
    finalized = _tool(ctx, step, "finalize", record, project, directory)
    if not finalized.ok or not (directory / "restore-finalized.json").is_file():
        raise failed("finalize_failed")
    progress.report(ctx, "start", job=job)
    start_all(ctx, ctx.step(25, "start"), project)
    step = ctx.step(26, "adopt")
    progress.report(ctx, "adopt", job=job)
    _rename(paths, project)
    _link(paths, paths.bundle_root)  # the old engine stays the command
    backups.write_config(ctx, step, project)
    write_private(tick.marker(paths), (directory / "restore-finalized.json").read_bytes())
    tick.adopt(ctx, {"run_id": ctx.run_id})
    record["restored_project"] = project


def close(ctx: Context, record: dict[str, Any], code: str) -> str:
    record.setdefault("failure_code", code)
    boundary = bool(record.get("boundary"))
    try:
        if boundary:
            _rollback(ctx, record, str(record.get("kind", "rollback")))
        else:
            _recover(ctx, record)
        restored = "restored" if record.get("kind") == "restore" else "rolled_back"
        state = restored if boundary else "failed"
    except Exception as error:  # the services stay as they are; support takes over
        found = error.code if isinstance(error, JobError) else "engine_failed"
        record["rollback_code" if boundary else "recover_code"] = found
        ctx.log.line(ctx.step(27, "close"), "ERROR", f"{'rollback' if boundary else 'recover'}"
                     f" did not finish: {found}")  # fmt: skip
        state = "needs_support"
    record["state"], record["finished_at"] = state, _at(ctx)
    _save(ctx.paths, record)
    ctx.log.line(ctx.step(27, "close"), "INFO", f"update closed: {state}")
    return state


def resume(ctx: Context) -> str | None:
    """Section 12: close each interrupted update; return the last outcome, or None."""
    outcome = None
    for record in journals(ctx.paths):
        if record.get("state") not in OPEN:
            continue
        step = ctx.step(20, "resume")
        ctx.log.line(step, "WARN", f"closing the interrupted update {record['run_id']}")
        binding_path(ctx.paths, record["run_id"]).unlink(missing_ok=True)  # C-6
        if backups.container_created(ctx, step) is not None:
            backups.remove_container(ctx, step)  # the killed update's backup or adopt
        with backups.runner_idle(ctx, step, record["project"]):
            code = "interrupted"
            if record["state"] == "running" and _done(record, 11):
                try:
                    _switch(ctx, record)
                    outcome = "succeeded"
                    continue
                except JobError as error:
                    code = error.code
            outcome = close(ctx, record, code)
    return outcome


# The job -----------------------------------------------------------------------------------


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths, version = ctx.paths, request["version"]
    resume(ctx)
    if needs_support(paths):
        raise refused("update_needs_support")
    instance = backups.installed_instance(paths)
    if instance is None:
        raise refused("not_installed")
    if (paths.run / "stopped").exists():  # power.stopped; power imports this module
        raise refused("stopped")
    installed = str(_installed(paths)["version"])
    if precedence(version) <= precedence(installed):
        raise refused("version_not_newer")
    manifest = release.require(paths, version)  # receive keeps only a verified release
    record: dict[str, Any] = {
        "schema": 1, "run_id": ctx.run_id, "from_version": installed, "target_version": version,
        "project": instance, "state": "running", "started_at": _at(ctx), "steps": {},
        "boundary": False, "stopped": False,
    }  # fmt: skip
    step = ctx.step(1, "lock")
    progress.report(ctx, "lock")
    with backups.runner_idle(ctx, step, instance):
        if backups.active_journal(paths, instance).exists():
            raise refused("recovery_required")
        _save(paths, record)
        ctx.log.line(step, "INFO", f"update {installed} to {version}, project {instance}")
        try:
            _forward(ctx, record, manifest)
        except Exception as error:
            known = error if isinstance(error, JobError) else JobError("engine_failed", FAILED)
            ctx.log.line(ctx.step(20, "failed"), "ERROR", f"update failed: {known.code}")
            state = close(ctx, record, known.code)
            raise JobError(known.code, known.exit_code, **known.fields, update=state) from error
    return {"code": "updated", "from_version": installed, "version": version}
