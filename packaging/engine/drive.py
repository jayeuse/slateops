"""The backup drive (plan 8.2, 8.3; TASK-0093 AC-2, AC-4, AC-5).

The Restic repository is the drvfs mount point ``/var/lib/slateops/backup/repository``. When
nothing is mounted there it is an empty, local, root-only folder, so the runner's admission
passes without the drive (TASK-0092, O-2). The drive stays mounted: install step 12 mounts it,
and a tick mounts it again when ``/proc/self/mountinfo`` shows no mount at that path. Reading
``mountinfo`` touches no drive. The mount test matches the mount point only: WSL2 lists a drvfs
mount with its own file system type (``9p`` or ``virtiofs``; W14 confirms which).

Rules:

- The target is ``[A-Z]:\\`` plus at most 8 folder names (``valid_target``). ``mount_argv`` is
  the one builder of the mount arguments, from fixed parts and the stored target only.
- ``restic init`` runs only on an empty folder that ``mountinfo`` shows mounted, owned by the
  engine's user and private; a non-empty folder must open with the installation's password.
- The recovery key is a second Restic key. It is held in memory, masked in every log line, and
  written only to a root-only temporary file under ``/run/slateops`` for ``restic key add``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

from engine.context import Context
from engine.core import Paths, failed, private_dir, refused, write_private

OPTIONS = "uid=0,gid=0,umask=077,nosuid,nodev,noexec"
MOUNT = "/usr/bin/mount"
TARGET_LIMIT = 200
FOLDER_LIMIT = 8
_TARGET = re.compile(r"([A-Z]):\\(.*)\Z", re.S)
_NAME = re.compile(r"[A-Za-z0-9 ._-]{1,200}\Z")
_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"{kind}{n}" for kind in ("COM", "LPT") for n in range(10))}
)
_KEY_ID = re.compile(r"[0-9a-f]{8,64}\Z")
RESTIC_SECONDS = 600


def valid_target(value: Any) -> bool:
    """AC-4: a drive letter and 1 to 8 plain folder names, 200 characters at most. A drive
    root is refused: it holds ``System Volume Information``, so it is never empty."""
    if not isinstance(value, str) or len(value) > TARGET_LIMIT:
        return False
    match = _TARGET.match(value)
    if match is None:
        return False
    names = match.group(2).split("\\")
    return len(names) <= FOLDER_LIMIT and all(
        _NAME.match(name)
        and name not in (".", "..")
        and not name.endswith((".", " "))
        and name.split(".")[0].rstrip(" ").upper() not in _DEVICES
        for name in names
    )


def backup_root(paths: Paths) -> Path:
    return paths.state / "backup"


def mount_point(paths: Paths) -> Path:
    return backup_root(paths) / "repository"


def _target_file(paths: Paths) -> Path:
    return paths.state / "backup-target.json"


def load_target(paths: Paths) -> str | None:
    try:
        value = json.loads(_target_file(paths).read_text()).get("target")
    except (OSError, ValueError, AttributeError):
        return None
    return value if valid_target(value) else None


def store_target(paths: Paths, target: str) -> None:
    if not valid_target(target):
        raise refused("invalid_input")
    write_private(_target_file(paths), (json.dumps({"target": target}) + "\n").encode())


def _unescape(field: str) -> str:
    """``mountinfo`` writes a space, tab, newline and backslash as octal escapes."""
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), field)


def mounted(paths: Paths) -> bool:
    """A mount at the fixed path in ``/proc/self/mountinfo`` (no drive access)."""
    try:
        lines = (paths.proc / "self" / "mountinfo").read_text().splitlines()
    except OSError:
        return False
    wanted = str(mount_point(paths))
    return any(
        len(fields) > 4 and _unescape(fields[4]) == wanted
        for fields in (line.split(" ") for line in lines)
    )


def mount_argv(paths: Paths, target: str) -> list[str]:
    """The one mount argument list (AC-2). ``systemd-run`` runs it as a transient service, so
    install step 12 mounts in the same context as the timer's tick (TASK-0092)."""
    if not valid_target(target):
        raise refused("invalid_input")
    return [
        "systemd-run", "--wait", "--collect", "--quiet", "--",
        MOUNT, "-t", "drvfs", target, str(mount_point(paths)), "-o", OPTIONS,
    ]  # fmt: skip


def mount(ctx: Context, step: str, target: str) -> bool:
    """Mount ``target`` unless a mount is there; True when ``mountinfo`` then shows one."""
    paths = ctx.paths
    if mounted(paths):
        return True
    ctx.runner.run(step, mount_argv(paths, target), timeout=120)
    found = mounted(paths)
    ctx.log.line(step, "INFO" if found else "WARN",
                 "backup target mounted" if found else "backup target not mounted")  # fmt: skip
    return found


def unmount(ctx: Context, step: str) -> bool:
    """A plain ``umount`` (no lazy, no force); True when nothing is mounted afterwards."""
    paths = ctx.paths
    if not mounted(paths):
        return True
    ctx.runner.run(step, ["umount", str(mount_point(paths))], timeout=120)
    return not mounted(paths)


# Restic -------------------------------------------------------------------------------------------


def restic(paths: Paths, *tail: str, password_file: Path | None = None) -> list[str]:
    password = password_file or paths.etc / "restic-password"
    return [
        "restic", "--no-cache", "--repo", str(mount_point(paths)),
        "--password-file", str(password), *tail,
    ]  # fmt: skip


def open_or_init(ctx: Context, step: str) -> str:
    """``created`` for a new repository on an empty mounted folder, ``opened`` for one that
    opens with the installation's password; refuse anything else (AC-4). Callers run it only
    after ``mount`` returned True, that is, after ``mountinfo`` showed the mount."""
    paths = ctx.paths
    point = mount_point(paths)
    details = os.lstat(point)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.geteuid()
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        ctx.log.line(step, "ERROR", f"mounted folder owner {details.st_uid} mode "
                     f"{stat.S_IMODE(details.st_mode):o}")  # fmt: skip
        raise refused("backup_target_refused")
    with os.scandir(point) as entries:
        empty = next(entries, None) is None
    if empty:
        if not ctx.runner.run(step, restic(paths, "init"), timeout=RESTIC_SECONDS).ok:
            raise failed("restic_init_failed")
        return "created"
    if not ctx.runner.run(step, restic(paths, "cat", "config"), timeout=RESTIC_SECONDS).ok:
        raise refused("backup_target_refused")
    return "opened"


def _keys(ctx: Context, step: str) -> list[dict[str, Any]]:
    result = ctx.runner.run(step, restic(ctx.paths, "key", "list", "--json"), timeout=120)
    try:
        rows = json.loads(result.text()) if result.ok else None
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(
        isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and _KEY_ID.match(row["id"])
        and isinstance(row.get("current"), bool)
        for row in rows
    ):
        raise failed("recovery_key_failed")
    return rows


def _readable(raw: bytes) -> str:
    """160 random bits as 32 base32 letters and digits, in groups of four for printing."""
    text = base64.b32encode(raw).decode("ascii")
    return "-".join(text[i : i + 4] for i in range(0, len(text), 4))


def new_recovery_key(ctx: Context, step: str) -> str:
    """Add a new recovery key, check that it opens the repository, then remove every key
    except the working key and the new one (AC-5). Safe to repeat after a kill."""
    paths = ctx.paths
    key = _readable(secrets.token_bytes(20))
    ctx.redactor = ctx.redactor.with_values([key], [])
    ctx.log.redact = ctx.redactor
    before = _keys(ctx, step)
    current = [row["id"] for row in before if row["current"]]
    if len(current) != 1:
        raise failed("recovery_key_failed")
    folder = private_dir(paths.run)
    staged = folder / f".recovery-{secrets.token_hex(4)}"
    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w") as file:
            file.write(key)
        argv = restic(paths, "key", "add", "--new-password-file", str(staged))
        if not ctx.runner.run(step, argv, timeout=RESTIC_SECONDS).ok:
            raise failed("recovery_key_failed")
        added = {row["id"] for row in _keys(ctx, step)} - {row["id"] for row in before}
        check = restic(paths, "cat", "config", password_file=staged)
        if len(added) != 1 or not ctx.runner.run(step, check, timeout=RESTIC_SECONDS).ok:
            raise failed("recovery_key_failed")
    finally:
        staged.unlink(missing_ok=True)
    keep = {*current, *added}
    for row in _keys(ctx, step):
        if row["id"] not in keep:
            remove = restic(paths, "key", "remove", row["id"])
            if not ctx.runner.run(step, remove, timeout=RESTIC_SECONDS).ok:
                raise failed("recovery_key_failed")
    ctx.log.line(step, "INFO", "recovery key added; older recovery keys removed")
    return key
