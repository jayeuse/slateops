"""``install``: the first install of one installation (plan 6.1, 6.2; TASK-0086).

Input (W7 wire contract): ``run_id``, ``version`` and, on the first run, ``answers`` (plan 6.1
plus ``time_zone``). A rerun resumes from the journal; it may leave ``answers`` out
(TASK-0080 N-3), and answers that it does give must equal the stored ones. ``admin_password``
(DEC-0041) is required until step 11 is done; it is held in memory only: never stored, never
an argument or an environment value, and masked in every log line from the job's start.

Steps (step IDs ``install.NN.<name>``; each is journaled before the next starts):

1. ``release``: the verified release that ``receive`` kept; the app subnet (W5b-7).
2. ``folders``: owners and modes of every folder the installation uses.
3. ``images``: our two images by manifest digest; the provider images by digest.
4. ``secrets``: ``/etc/slateops/new`` is emptied (N-6), and the W2 generator runs in a
   one-shot container with no network. The install needs no email settings (DEC-0041):
   ``provider.env`` gets none, and ``set-email`` adds them later.
5. ``env``: ``provider.env``, ``app.env`` and ``provision.env`` from the W2 templates (0600).
6. ``tls``: the local CA and server certificate (W2 ``local_ca.py init``, no network) and
   the Caddyfile (W5b-6). W6a adds port 80, the trust files and the renewal.
7. ``providers``: ``db auth storage realtime api-gw``, then a wait for health.
8. ``provision``: the W5a provisioning job on the provider network.
9. ``api``: start ``api``; wait for the internal ``/api/ready``.
10. ``caddy``: start ``caddy``; ``https://<public_host>/api/ready`` through loopback.
11. ``admin``: the first administrator with the typed password, no invitation (DEC-0041).
12. ``backup``: the backup drive, the repository, the config, the default policy, the first
    backup, the recovery key and the runner timer (W10b, ``engine.backups``).
13. ``finish``: ``installation.json`` and the safe result.

Rules (plan 6.1): a step never overwrites a secret, the CA, a volume or the Caddyfile: a file
that exists is kept when it equals what the step would write and refused otherwise. When
the state does not match the journal, the job stops with ``install_state_mismatch`` and
repairs nothing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Any

from engine import (
    answers,
    backups,
    compose,
    invitation,
    journal,
    prefetch,
    progress,
    release,
    subnet,
    trust,
)
from engine.context import Context
from engine.core import (
    INSTANCE_ID,
    failed,
    held_lock,
    is_run_id,
    is_version,
    lock_is_held,
    private_dir,
    refused,
)
from engine.env_templates import TemplateError, render
from engine.held import load_held

KEYS = {
    "run_id": is_run_id,
    "version": is_version,
    "answers": lambda value: isinstance(value, dict),
    "admin_password": invitation.valid_password,
}
REQUIRED = frozenset({"run_id", "version"})
STEPS = tuple(enumerate(progress.STEPS["install"], start=1))  # the one list (W14-D5)
ENV_FILES = ("provider.env", "app.env", "provision.env")
GENERATED = "generated.env"
RESTIC = "restic-password"
CADDYFILE = "Caddyfile"
TRUST_MOUNT = "/srv/slateops-trust"  # the Caddy template root (generate_config --trust-root)
API_UID = 10001  # the server image's appuser (infra/docker/backend.Dockerfile)
CADDY_UID = 1000  # the Caddy image's user (infra/docker/caddy.Dockerfile)
EXPORT_ROOT = "backup/backup-exports"  # next to the Restic repository (TASK-0081 O-2, W10b)
SPACE_BYTES = 2 * 1024**3  # planning value: free space before each writing step (10.7)
PREFETCH_WAIT_SECONDS = 3600
PROVISION_SECONDS = 4 * 900 + 120  # the W5a job's four step limits, plus start-up
_SAFE = re.compile(r"[a-z_]{1,40}\Z")
_LINE = re.compile(r"([A-Z_][A-Z0-9_]*)=(.*)\Z")
# S86-3: the secret generator (step 4) and the CA jobs (step 6, renewal) run as root (UID 0)
# in their containers, an exception to the Compose baseline's non-root rule. The need: their
# output must be owned by root inside root-only 0700 folders (`/etc/slateops/new`, `ca/`),
# which a non-root user could not write and which the backup admission requires (owner
# root). The other controls hold: no network, a read-only root file system, every capability
# dropped (the CA jobs add one, below), no-new-privileges, `--pull never` on the verified
# server image, and only the one or two folders that the job writes mounted.
#
# N-1: the CA jobs add CAP_DAC_READ_SEARCH because the server key belongs to Caddy (UID 1000)
# and, without it, `local_ca.py` cannot read the key and issues a new certificate on every
# run (TASK-0089). What the capability allows, in full (capabilities(7)):
# - read any file and search any folder that the container sees, whatever its permissions:
#   the image, `ca/` and `tls/` (it gives no write right and no owner change);
# - open_by_handle_at(2), which Docker's default seccomp profile allows once this
#   capability is added: a process in the container that can guess file handles could open
#   files elsewhere on the host file system that holds the bind-mounted folders (`/etc` of
#   the distribution), outside the mounts;
# - linkat(2) with AT_EMPTY_PATH (a link to an open file; the mounts it could write to are
#   `ca/` and `tls/`).
# W89-1: the job runs as UID 0, so code inside it could also open by handle any root-owned
# file with the owner-write bit set and write it through the read-write `ca/` and `tls/`
# mounts. The job's inputs come only from root-only `/etc/slateops` and the release's own
# server image (verified by `receive`); `local_ca.py` runs there with fixed arguments, no
# network and nothing from outside, so using the capability beyond reading the key needs
# code execution inside that job.
ONE_SHOT_ROOT = [
    "--user",
    "0:0",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,nodev,size=16m",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--no-healthcheck",
]

Step = Callable[[Context, str, dict[str, Any], dict[str, Any], dict[str, Any]], None]


def _safe(value: Any) -> str:
    return value if isinstance(value, str) and _SAFE.match(value) else "unknown"


def _at(ctx: Context) -> str:
    return ctx.deps.clock().isoformat()


def _json_tail(text: str) -> dict[str, Any]:
    try:
        found = json.loads(text.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def literal_lines(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := _LINE.match(line):
            values[match.group(1)] = match.group(2)
    return values


def commit_new(
    ctx: Context,
    path: Path,
    data: bytes,
    *,
    mode: int = 0o600,
    owner: tuple[int, int] | None = None,
) -> bool:
    """Write ``path`` once: keep an equal file, refuse a different one (plan 6.1)."""
    if path.is_symlink():
        raise refused("install_state_mismatch", part=path.name)
    if path.exists():
        if path.read_bytes() != data:
            raise refused("install_state_mismatch", part=path.name)
        return False
    temporary = path.with_name(f".{path.name}.new")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temporary, mode)
    if owner is not None:
        ctx.deps.chown(temporary, *owner)
    os.link(temporary, path)  # never replaces an existing file
    temporary.unlink()
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return True


def _folder(ctx: Context, path: Path, mode: int, owner: tuple[int, int] = (0, 0)) -> None:
    if path.is_symlink():
        raise failed("unsafe_path", part=path.name)
    path.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path, mode)
    ctx.deps.chown(path, *owner)


def hold_new_values(ctx: Context) -> None:
    """Mask the values this run has just created (F2, S86-1). The job loads the held values
    once at its start, before the answers are stored (step 0) and before steps 4 and 5
    create the secrets; from here on every log line and step output masks them too."""
    ctx.redactor = ctx.redactor.with_values(*load_held(ctx.paths))
    ctx.log.redact = ctx.redactor


def _server_image(state: dict[str, Any]) -> str:
    return str(state["server_image"])


def _project(state: dict[str, Any]) -> str:
    return str(state["project"])


# Step 1 ------------------------------------------------------------------------------------


def step_release(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    images = manifest.get("images")
    names: dict[str, str] = {}
    for role in ("server", "caddy"):
        entry = images.get(role) if isinstance(images, dict) else None
        match = release.REFERENCE.match(str((entry or {}).get("ref", "")))
        if match is None or match.group("tag") != state["version"]:
            raise refused("manifest_invalid", part=role)
        names[role] = f"{match.group('name')}:{match.group('tag')}"
    release.providers(manifest)
    state["server_image"], state["caddy_image"] = names["server"], names["caddy"]
    ctx.log.line(step, "INFO", f"release {state['version']}: {names['server']}, {names['caddy']}")
    state["subnet"] = subnet.choose(ctx, step)


# Step 2 ------------------------------------------------------------------------------------


def step_folders(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    paths = ctx.paths
    private_dir(paths.etc)
    _folder(ctx, paths.etc, 0o700)
    _folder(ctx, paths.new, 0o700)
    _folder(ctx, paths.etc / "ca", 0o700)  # never mounted except into the CA job
    _folder(ctx, paths.etc / "tls", 0o755)  # Caddy's only TLS mount (read only)
    _folder(ctx, paths.trust, 0o755)  # the public trust files, Caddy's template root (R3)
    private_dir(paths.logs)
    _folder(ctx, paths.logs / "app", 0o700, (API_UID, API_UID))  # SLATEOPS_LOG_ROOT
    private_dir(paths.state)
    backups.make_export_root(ctx)  # README export root rule; 0750, group API_UID
    ctx.log.line(step, "INFO", "folders ready")


# Step 3 ------------------------------------------------------------------------------------


def step_images(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    for role in ("server", "caddy"):
        match = release.REFERENCE.match(str(manifest["images"][role]["ref"]))
        assert match is not None  # step 1 checked it
        tagged, digest = f"{match.group('name')}:{match.group('tag')}", match.group("digest")
        argv = [
            "docker",
            "image",
            "inspect",
            "--platform",
            "linux/amd64",
            "--format",
            "{{.Id}}",
            tagged,
        ]
        result = ctx.runner.run(step, argv, timeout=60)
        if not result.ok or result.text().strip() != digest:
            raise failed("image_missing", part=role)
    paths = ctx.paths
    started = ctx.deps.clock()
    while lock_is_held(paths.prefetch_lock, paths.proc):
        if (ctx.deps.clock() - started).total_seconds() > PREFETCH_WAIT_SECONDS:
            raise failed("pull_timeout")
        ctx.log.line(step, "INFO", "waiting for the running prefetch")
        ctx.deps.sleep(5.0)
    references = release.providers(manifest)
    api = ctx.deps.docker_api(paths.docker_socket)
    if all(api.image_exists(reference) for reference in references):
        ctx.log.line(step, "INFO", f"{len(references)} provider images present by digest")
        return
    with held_lock(paths.prefetch_lock, "prefetch_running"):
        code = prefetch.pull_all(ctx.deps, ctx.log, step, ctx.run_id, state["version"])
    if code != "prefetch_done":
        raise failed(code)


# Step 4 ------------------------------------------------------------------------------------


def _empty(folder: Path) -> None:
    for entry in folder.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def step_secrets(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    paths = ctx.paths
    _empty(paths.new)  # N-6: a repeated step starts from an empty folder
    argv = [
        "docker", "run", "--rm", "--pull", "never", "--network", "none", *ONE_SHOT_ROOT,
        "--mount", f"type=bind,source={paths.new},target=/new",
        "--env", f"SLATEOPS_RUN_ID={ctx.run_id}",
        "--entrypoint", "python", _server_image(state),
        "operations/supabase_keys.py", "--format", "docker",
        "--output", f"/new/{GENERATED}", "--restic-password-file", f"/new/{RESTIC}",
    ]  # fmt: skip
    if not ctx.runner.run(step, argv, timeout=120).ok:
        raise failed("secrets_failed")
    generated = paths.new / GENERATED
    if not (generated.is_file() and (paths.new / RESTIC).is_file()):
        raise failed("secrets_failed")
    instance = literal_lines(generated).get("SLATEOPS_INSTANCE_ID", "")
    if not INSTANCE_ID.match(instance):
        raise failed("secrets_failed")
    state["project"] = instance
    ctx.log.line(step, "INFO", f"secrets generated; instance {instance}")


# Step 5 ------------------------------------------------------------------------------------


def step_env(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    paths = ctx.paths
    try:
        values = {
            **literal_lines(paths.new / GENERATED),
            "PUBLIC_HOST": given["public_host"],
            "SLATEOPS_SERVER_IMAGE": state["server_image"],
            "SLATEOPS_CADDY_IMAGE": state["caddy_image"],
            "SLATEOPS_APP_PRIVATE_SUBNET": state["subnet"],
            "SLATEOPS_BACKUP_EXPORT_ROOT": str(paths.state / EXPORT_ROOT),
        }
        for name in ENV_FILES:
            template = (paths.engine_home / "templates" / name).read_text(encoding="utf-8")
            written = commit_new(ctx, paths.etc / name, render(template, values).encode())
            ctx.log.line(step, "INFO", f"{name}: {'written' if written else 'kept (equal)'}")
    except TemplateError as error:
        raise failed("env_render_failed") from error
    source, target = paths.new / RESTIC, paths.etc / RESTIC
    if source.is_file():
        commit_new(ctx, target, source.read_bytes())
    elif not target.is_file():
        raise refused("install_state_mismatch", part=RESTIC)


def cleanup_generator_output(ctx: Context) -> None:
    """After step 5 is journaled: the generator output is now in the env files (TASK-0081 A-3
    item 4)."""
    paths = ctx.paths
    for path in (paths.new / GENERATED, paths.new / RESTIC):
        if path.exists() or path.is_symlink():
            path.unlink()


# Step 6 ------------------------------------------------------------------------------------


def _render_caddyfile(ctx: Context, host: str) -> str:
    path = ctx.paths.bundle_root / "infra" / "caddy" / "generate_config.py"
    spec = importlib.util.spec_from_file_location("slateops_caddy_config", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise failed("bundle_incomplete")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text: str = module.render_config(
        public_host=host,
        listen_address="0.0.0.0",
        https_port=443,
        health_port=3449,
        backend_port=8000,
        tls_mode="custom",
        upstream_host="api",
        cert_file=Path("/run/caddy-tls/server.crt"),
        key_file=Path("/run/caddy-tls/server.key"),
        trust_root=Path(TRUST_MOUNT),
    )
    return text


def ca_argv(ctx: Context, server_image: str, command: str, host: str, name: str) -> list[str]:
    """``local_ca.py <command>`` in a one-shot container: no network, only ``ca/`` and
    ``tls/`` mounted, UID 0 with only DAC_READ_SEARCH: every file read, open_by_handle_at
    (as UID 0, also a write to a root-owned, owner-writable file through the read-write
    mounts) and an AT_EMPTY_PATH link; inputs only from root-only ``/etc/slateops`` and the
    release's server image (see S86-3, N-1 and W89-1 above)."""
    ca, tls = ctx.paths.etc / "ca", ctx.paths.etc / "tls"
    return [
        "docker", "run", "--rm", "--name", name, "--pull", "never", "--network", "none",
        *ONE_SHOT_ROOT, "--cap-add", "DAC_READ_SEARCH",
        "--mount", f"type=bind,source={ca},target=/ca",
        "--mount", f"type=bind,source={tls},target=/tls",
        "--env", f"SLATEOPS_RUN_ID={ctx.run_id}",
        "--entrypoint", "python", server_image,
        "operations/local_ca.py", command, "--host", host,
        "--ca-dir", "/ca", "--tls-dir", "/tls",
    ]  # fmt: skip


def run_ca(ctx: Context, step: str, server_image: str, command: str, host: str) -> str:
    """Run one ``local_ca.py`` command; return its ``result`` or raise its safe code."""
    # W89-2: a fixed, unique name, so the engine can remove the container: the time limit
    # stops only the docker client, and the container would keep running.
    name = f"slateops-ca-{command}-{ctx.run_id}-{secrets.token_hex(3)}"
    result = ctx.runner.run(step, ca_argv(ctx, server_image, command, host, name), timeout=120)
    output = _json_tail(result.text())
    wanted = {
        "init": ("created", "exists"),
        "renew": ("renewed", "not_due"),
        "check": ("valid",),
    }[command]
    if not result.ok or output.get("result") not in wanted:
        ctx.runner.run(step, ["docker", "rm", "--force", name], timeout=60)
        code = "ca_check_failed" if command == "check" else "ca_failed"
        raise failed(code, cause=_safe(output.get("code")))
    ctx.log.line(step, "INFO", f"local CA {command}: {output['result']}")
    return str(output["result"])


def give_key_to_caddy(ctx: Context) -> None:
    """Caddy (UID 1000) reads the key through its read-only mount; every CA run keeps this
    owner and mode (TASK-0083 carry to W6a)."""
    key = ctx.paths.etc / "tls" / "server.key"
    if key.is_symlink() or not key.is_file():
        raise failed("ca_failed", cause="leaf_missing")
    ctx.deps.chown(key, CADDY_UID, CADDY_UID)
    os.chmod(key, 0o600)


def step_tls(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    paths = ctx.paths
    host = given["public_host"]
    # W6a-5: init runs the F6 self-check before it writes any CA file (W2); check proves the
    # chain again, and the real certificate passes, before the engine writes its own files.
    run_ca(ctx, step, _server_image(state), "init", host)
    run_ca(ctx, step, _server_image(state), "check", host)
    give_key_to_caddy(ctx)
    trust.write(ctx, step)
    text = _render_caddyfile(ctx, host)
    # W5b-6: Caddy reads the Caddyfile as its owner; no group or other access, so the
    # backup admission's mode rule holds (its owner rule is W10b-4, TASK-0086 D-1).
    commit_new(ctx, paths.etc / CADDYFILE, text.encode(), owner=(CADDY_UID, CADDY_UID))


# Steps 7 to 10 -----------------------------------------------------------------------------


def step_providers(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    project = _project(state)
    compose.check_config(ctx, step, project)
    compose.up(ctx, step, project, compose.PROVIDER_SERVICES, deps=True)
    compose.wait_healthy(ctx, step, project, compose.PROVIDER_SERVICES)


def step_provision(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    argv = [
        "docker", "run", "--rm", "--pull", "never", "--network", f"{_project(state)}_provider",
        "--env-file", str(ctx.paths.etc / "provision.env"),
        "--env", f"SLATEOPS_RUN_ID={ctx.run_id}",
        *invitation.ONE_SHOT,
        "--entrypoint", "python", _server_image(state),
        "-m", "operations.install.provisioning", "--confirm",
    ]  # fmt: skip
    # The job's stderr is its log (W5a C-2); the runner redacts it again before writing.
    result = ctx.runner.run(step, argv, timeout=PROVISION_SECONDS)
    output = _json_tail(result.text())
    if result.ok and output.get("result") == "provisioned":
        ctx.log.line(step, "INFO", "provisioned")
        return
    raise failed(
        "provisioning_failed", part=_safe(output.get("step")), cause=_safe(output.get("code"))
    )


def step_api(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    project = _project(state)
    compose.up(ctx, step, project, ("api",), deps=False)
    compose.wait_healthy(ctx, step, project, ("api",))
    compose.wait_api_ready(ctx, step, project)


def step_caddy(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    compose.up(ctx, step, _project(state), ("caddy",), deps=False)
    wait_https(ctx, step, given["public_host"])


def wait_https(ctx: Context, step: str, host: str) -> None:
    """``https://<host>/api/ready`` through loopback answers 200, trusting only the CA."""
    root = ctx.paths.etc / "ca" / "current" / "root.crt"
    started = ctx.deps.clock()
    seen = "no answer"
    while (ctx.deps.clock() - started).total_seconds() <= compose.HEALTH_SECONDS:
        try:
            code, _ = ctx.deps.https_get(host, "/api/ready", root, 10.0)
        except (OSError, ssl.SSLError) as error:
            seen = f"{type(error).__name__}: {error}"
        else:
            if code == 200:
                ctx.log.line(step, "INFO", f"https://{host}/api/ready through loopback: 200")
                return
            seen = f"HTTP {code}"
        ctx.deps.sleep(compose.POLL_SECONDS)
    ctx.log.line(step, "ERROR", f"https://{host}/api/ready through loopback: {seen}")
    raise failed("https_not_ready")


# Steps 11 to 13 ----------------------------------------------------------------------------


def step_admin(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], password: str
) -> None:
    """The only step that takes the password, so it is not in ``RUNNERS`` (DEC-0041)."""
    state["admin"] = invitation.create_admin(
        ctx, step, _project(state), _server_image(state), given, password
    )


def step_backup(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    def restart() -> None:  # after the first backup: providers, then api, then caddy last
        project = _project(state)
        compose.up(ctx, step, project, compose.PROVIDER_SERVICES, deps=True)
        compose.wait_healthy(ctx, step, project, compose.PROVIDER_SERVICES)
        step_api(ctx, step, state, given, manifest)
        step_caddy(ctx, step, state, given, manifest)

    backups.setup(ctx, step, state, given, restart)


def _root_certificate(ctx: Context) -> tuple[str, str]:
    pem = (ctx.paths.etc / "ca" / "current" / "root.crt").read_text(encoding="ascii")
    return pem, hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def step_finish(
    ctx: Context, step: str, state: dict[str, Any], given: dict[str, Any], manifest: dict[str, Any]
) -> None:
    record = {
        "instance_id": _project(state),
        "project": _project(state),
        "public_host": given["public_host"],
        "version": state["version"],
    }
    commit_new(ctx, ctx.paths.installation, (json.dumps(record, sort_keys=True) + "\n").encode())
    ctx.log.line(step, "INFO", f"installed {state['version']}")


RUNNERS: dict[int, Step] = {
    1: step_release,
    2: step_folders,
    3: step_images,
    4: step_secrets,
    5: step_env,
    6: step_tls,
    7: step_providers,
    8: step_provision,
    9: step_api,
    10: step_caddy,
    12: step_backup,
    13: step_finish,
}


# The journal against the state -------------------------------------------------------------


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def check_state(ctx: Context, state: dict[str, Any] | None) -> None:
    """Refuse when the files on disk do not match the journal (plan 6.1)."""
    paths = ctx.paths
    etc = paths.etc
    later = [
        *(etc / name for name in (*ENV_FILES, RESTIC, CADDYFILE)),
        etc / "ca" / "current",
        paths.installation,
    ]
    steps = state or {"steps": {}}
    if not journal.done(steps, 4) and any(_exists(path) for path in later):
        raise refused("install_state_mismatch", part="secrets")
    required = {
        2: [etc, paths.new, etc / "ca", etc / "tls", paths.trust, paths.logs / "app",
            paths.state / EXPORT_ROOT],
        5: [etc / name for name in (*ENV_FILES, RESTIC)],
        6: [etc / "ca" / "current" / "root.crt", etc / "tls" / "server.crt",
            etc / "tls" / "server.key", etc / CADDYFILE],
        12: [backups.config_path(paths)],
        13: [paths.installation],
    }  # fmt: skip
    if journal.done(steps, 4) and not journal.done(steps, 5):
        required[4] = [paths.new / GENERATED, paths.new / RESTIC]
    for number, files in sorted(required.items()):
        if journal.done(steps, number) and not all(_exists(path) for path in files):
            raise refused("install_state_mismatch", part=dict(STEPS)[number])


def _start(ctx: Context, request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The journal and the answers of this run (first run or resume)."""
    paths, version = ctx.paths, request["version"]
    state = journal.load(paths)
    given = request.get("answers")
    if state is None:
        if given is None:
            raise refused("invalid_input")
        parsed = answers.parse(given)
        if parsed is None:
            raise refused("invalid_input")
        if "admin_password" not in request:
            raise refused("invalid_input")
        check_state(ctx, None)
        release.require(paths, version)
        answers.store(paths, parsed)
        hold_new_values(ctx)
        state = journal.new(version, ctx.run_id, _at(ctx))
        journal.save(paths, state)
        return state, parsed
    if state.get("schema") != journal.SCHEMA:
        raise refused("install_state_mismatch", part="journal")
    if state.get("version") != version:
        raise refused("version_mismatch")
    stored = answers.load(paths)
    if stored is None:
        raise refused("install_state_mismatch", part="answers")
    if given is not None:
        parsed = answers.parse(given)
        if parsed is None:
            raise refused("invalid_input")
        if parsed != stored:
            raise refused("answers_changed")
    check_state(ctx, state)
    if journal.done(state, 13):
        return state, stored  # complete: a rerun changes no state file (only its own log)
    if not journal.done(state, 11) and "admin_password" not in request:
        raise refused("invalid_input")
    state.setdefault("runs", []).append(ctx.run_id)
    journal.save(paths, state)
    return state, stored


def _result(ctx: Context, state: dict[str, Any]) -> dict[str, Any]:
    pem, fingerprint = _root_certificate(ctx)
    # 8.3: the recovery key only from the run that made it (never stored, shown once); W8
    # bridges this output to the secret pipe. A later run's result has no key.
    shown = {"recovery_key": ctx.outputs["recovery_key"]} if "recovery_key" in ctx.outputs else {}
    return {
        **shown,
        "code": "installed",
        "version": state["version"],
        "admin": state.get("admin", "unknown"),
        "backup_setup": state.get("backup_setup", "not_built"),
        "ca_root_sha256": fingerprint,
        "ca_certificate_pem": pem,
        # R7: the one formatted value that the trust page and W8 show.
        "ca_security_code": trust.format_fingerprint(fingerprint),
    }


def _space(ctx: Context, step: str) -> None:
    free = ctx.deps.disk_free(ctx.paths.state)
    if free < SPACE_BYTES:
        ctx.log.line(step, "ERROR", f"free {free} bytes, need {SPACE_BYTES}")
        raise failed("insufficient_space")


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    password = request.get("admin_password")
    if isinstance(password, str):  # masked from the first log line of this job on
        ctx.redactor = ctx.redactor.with_values([password], [], words=[password])
        ctx.log.redact = ctx.redactor
    state, given = _start(ctx, request)
    manifest = release.require(ctx.paths, state["version"])
    if journal.done(state, 5):
        cleanup_generator_output(ctx)
    skipped = 0
    for number, name in STEPS:
        step = ctx.step(number, name)
        if journal.done(state, number):
            progress.report(ctx, name, state="done")
            skipped += 1
            continue
        progress.report(ctx, name)
        if number > 1:
            _space(ctx, step)
        ctx.log.line(step, "INFO", f"start {name}")
        if number == 11:
            assert isinstance(password, str)  # _start refuses a missing one before step 11
            step_admin(ctx, step, state, given, password)
        else:
            RUNNERS[number](ctx, step, state, given, manifest)
        if number in (4, 5):
            hold_new_values(ctx)
        journal.mark(ctx.paths, state, number, name, _at(ctx))
        if number == 5:
            cleanup_generator_output(ctx)
    if skipped:
        ctx.log.line(ctx.step(0, "resume"), "INFO", f"{skipped} completed steps skipped")
    return _result(ctx, state)


# Read by snapshot and status: the project of an installation with a journal.
def project_of(ctx: Context) -> str | None:
    state = journal.load(ctx.paths)
    project = (state or {}).get("project")
    return project if isinstance(project, str) and INSTANCE_ID.match(project) else None
