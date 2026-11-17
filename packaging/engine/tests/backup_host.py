"""A fake backup host for the engine tests (TASK-0093): the drvfs mount, Restic, the
``slateops-runner`` container, the bridge and systemd.

A "drive" is a folder that stands for a Windows target. A mount moves its entries into the
mount point and writes a ``/proc/self/mountinfo`` line; an unmount moves them back, so the
local mount point is empty whenever nothing is mounted, as on the real host. A repository is
a ``config`` file plus a ``keys.json`` map of key ID to password.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine.core import Paths
from engine.runner import Result

RUNNER = "slateops-runner"


def _ok(text: str = "") -> Result:
    return Result(0, text.encode(), b"")


class BackupHost:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.drives: dict[str, Path] = {}
        self.mounted: str | None = None
        self.mounts = 0
        self.unmounts = 0
        self.container: datetime | None = None  # the creation time of slateops-runner
        self.container_sticky = False  # docker rm --force does not remove it
        self.runner_result: Result | Callable[[list[str]], Result] = _ok('{"state": "idle"}\n')
        self.first_backup_fails = False
        self.snapshots = 0
        self.policy_inputs: list[dict[str, Any]] = []
        self.image_label = "0.1.0-rc.9"
        self.image_id = "sha256:" + "a" * 64
        self.enabled: list[str] = []
        self.next_key = 0
        self.now = datetime(2026, 11, 17, 10, 15, tzinfo=UTC)

    # Drives and the mount -------------------------------------------------------------------

    @property
    def mount_point(self) -> Path:
        return self.paths.state / "backup" / "repository"

    def add_drive(self, target: str, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        self.drives[target] = folder
        return folder

    def _mountinfo(self) -> Path:
        return self.paths.proc / "self" / "mountinfo"

    def _write_mountinfo(self) -> None:
        self._mountinfo().parent.mkdir(parents=True, exist_ok=True)
        lines = ["22 1 0:21 / /proc rw,nosuid - proc proc rw"]
        if self.mounted is not None:
            lines.append(f"101 22 0:52 / {self.mount_point} rw,nosuid,nodev,noexec - 9p E: rw")
        self._mountinfo().write_text("\n".join(lines) + "\n")

    def _mount(self, argv: list[str]) -> Result:
        target, point = argv[argv.index("drvfs") + 1], argv[argv.index("drvfs") + 2]
        drive = self.drives.get(target)
        if self.mounted is not None or drive is None or not drive.is_dir():
            return Result(32, b"", b"mount: wrong fs type or bad option\n")
        assert point == str(self.mount_point)
        for entry in drive.iterdir():
            shutil.move(str(entry), str(self.mount_point / entry.name))
        self.mount_point.chmod(0o700)
        self.mounted, self.mounts = target, self.mounts + 1
        self._write_mountinfo()
        return _ok()

    def _umount(self, argv: list[str]) -> Result:
        assert argv == ["umount", str(self.mount_point)], argv  # plain: no -l, no -f
        if self.mounted is None:
            return Result(32, b"", b"umount: not mounted\n")
        drive = self.drives[self.mounted]
        if drive.is_dir():  # a pulled drive has nothing to take back
            for entry in self.mount_point.iterdir():
                shutil.move(str(entry), str(drive / entry.name))
        self.mounted, self.unmounts = None, self.unmounts + 1
        self._write_mountinfo()
        return _ok()

    def pull_drive(self) -> None:
        """The USB drive is removed while mounted: the mount stays, its content is gone."""
        assert self.mounted is not None
        drive = self.drives.pop(self.mounted)
        for entry in self.mount_point.iterdir():
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
        shutil.rmtree(drive)
        self.drives[self.mounted] = drive  # a later mount of this target fails (missing)

    # Restic ----------------------------------------------------------------------------------

    def keys(self) -> dict[str, str]:
        path = self.mount_point / "keys.json"
        return json.loads(path.read_text()) if path.is_file() else {}

    def _save_keys(self, keys: dict[str, str]) -> None:
        (self.mount_point / "keys.json").write_text(json.dumps(keys))

    def _restic(self, argv: list[str]) -> Result:
        assert argv[:3] == ["restic", "--no-cache", "--repo"], argv
        assert argv[3] == str(self.mount_point)
        password = Path(argv[argv.index("--password-file") + 1]).read_text()
        tail = argv[argv.index("--password-file") + 2 :]
        exists = (self.mount_point / "config").is_file()
        if tail == ["init"]:
            if any(self.mount_point.iterdir()):
                return Result(1, b"", b"Fatal: config file already exists\n")
            (self.mount_point / "config").write_text("restic repository")
            self._save_keys({self._new_id(): password})
            return _ok("created restic repository\n")
        keys = self.keys()
        if not exists or password not in keys.values():
            return Result(1, b"", b"Fatal: wrong password or no key found\n")
        if tail == ["cat", "config"]:
            return _ok('{"version":2}\n')
        if tail == ["key", "list", "--json"]:
            rows = [{"id": key, "current": value == password} for key, value in keys.items()]
            return _ok(json.dumps(rows))
        if tail[:3] == ["key", "add", "--new-password-file"]:
            keys[self._new_id()] = Path(tail[3]).read_text()
            self._save_keys(keys)
            return _ok("saved new key\n")
        if tail[:2] == ["key", "remove"]:
            if keys.get(tail[2]) == password:
                return Result(1, b"", b"refusing to remove the current key\n")
            keys.pop(tail[2])
            self._save_keys(keys)
            return _ok("removed key\n")
        raise AssertionError(f"unexpected restic call {argv}")

    def _new_id(self) -> str:
        self.next_key += 1
        return f"{self.next_key:08x}"

    # Docker ----------------------------------------------------------------------------------

    def _run_container(self, argv: list[str]) -> Result:
        assert argv[argv.index("--name") + 1] == RUNNER
        self.container = self.now
        if any(item.endswith("backup_installation.py") for item in argv):
            ok = (
                not self.first_backup_fails
                and self.mounted is not None
                and (self.mount_point / "config").is_file()
            )
            if ok:
                self.snapshots += 1
            result = _ok("Backup complete\n") if ok else Result(1, b"", b"Backup failed\n")
        else:
            found = self.runner_result
            result = found(argv) if callable(found) else found
        if result.returncode is not None and "--rm" in argv:
            self.container = None
        return result

    def answer(self, argv: list[str], stdin: bytes | None) -> Result | None:
        """The answer for a backup-host command, or None for any other command."""
        if argv[:1] == ["systemd-run"] and "drvfs" in argv:
            return self._mount(argv)
        if argv[:1] == ["umount"]:
            return self._umount(argv)
        if argv[:1] == ["restic"]:
            return self._restic(argv)
        if argv[:1] == ["systemctl"] and argv[1:2] in (["daemon-reload"], ["enable"]):
            self.enabled.append(" ".join(argv[1:]))
            return _ok()
        if argv[:2] == ["docker", "run"] and "operations/backup_state.py" in argv:
            self.policy_inputs.append(json.loads(stdin or b"{}"))
            return _ok('{"written":true,"policy":{"schedule":"daily","adopted":true}}\n')
        if argv[:2] == ["docker", "run"] and RUNNER in argv:
            return self._run_container(argv)
        if argv[:3] == ["docker", "ps", "--all"] and f"name={RUNNER}" in argv:
            return _ok(f"{RUNNER}\n" if self.container is not None else "")
        if argv[:3] == ["docker", "container", "inspect"] and argv[-1] == RUNNER:
            if self.container is None:
                return Result(1, b"", b"Error: No such container: slateops-runner\n")
            return _ok(self.container.strftime("%Y-%m-%dT%H:%M:%S.123456789Z") + "\n")
        if argv[:4] == ["docker", "rm", "--force", RUNNER]:
            if self.container is None:
                return Result(1, b"", b"Error: No such container\n")
            if not self.container_sticky:
                self.container = None
            return _ok(RUNNER + "\n")
        if argv[:3] == ["docker", "image", "inspect"] and "org.opencontainers" in " ".join(argv):
            return _ok(f"{self.image_id} {self.image_label}\n")
        return None

    def age_container(self, seconds: float) -> None:
        assert self.container is not None
        self.container -= timedelta(seconds=seconds)
