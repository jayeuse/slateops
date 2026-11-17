"""``update`` and the package night (TASK-0095; plan 7.3 to 7.5, section 12; W13b-1 to W13b-4,
W13b-6 to W13b-10).

The fake world extends the install world: Compose keeps containers per project (image,
working folder label, running), networks with the app subnet (Docker refuses an overlapping
one) and volumes with their data; the step-5 backup writes its completion marker and keeps a
snapshot of the data and the env files; the host restore tool restores a snapshot into a new
project and finalizes it.
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import io
import json
import shutil
import stat
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from engine import cli, update
from engine.core import Paths, private_dir
from engine.runner import Result

from .helpers import VERSION, Clock, deps
from .test_install import PROVIDERS, ROOT, Killed, World, _setup, run

TARGET = "0.1.0-rc.10"
UPDATE = "update-20261117T120000Z-ab12cd"
TICK = "backup-20261117T121000Z-ab12cd"
SUPPORT = "maintenance-20261117T121000Z-ab12cd"
TARGET_DIGEST = {"server": "sha256:" + "e" * 64, "caddy": "sha256:" + "f" * 64}
GIB = 1024**3


def _ok(text: str = "") -> Result:
    return Result(0, text.encode(), b"")


def _label_project(argv: list[str]) -> str:
    return next(a for a in argv if "com.docker.compose.project=" in a).split("project=")[1]


class UpdateWorld(World):
    def __init__(self, paths: Paths) -> None:
        super().__init__(paths)
        self.containers: dict[str, dict[str, dict[str, Any]]] = {}
        self.networks: dict[str, str] = {}  # network name -> subnet
        self.data: dict[str, str] = {}  # volume name -> its content
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.migration_fails = False
        self.down_leaves_db = False
        self.apt_fails = False
        self.api_reports: str | None = None  # an image whose SLATEOPS_VERSION is another
        # Containers outside every Compose project: id -> the volume it mounts. The backup
        # tool's volume export (`docker run --rm ... tar`) stays "created" when the tool dies
        # between create and start (test build rc.17, `keen_kilby`).
        self.loose: dict[str, str] = {}
        self.tool_dies_in_export = False
        self.drive_gone_at_migration = False  # the rollback finds no backup drive
        self.apt: list[list[str]] = []
        self.sources_seen: dict[str, str] = {}

    def _env(self) -> dict[str, str]:
        text = (self.paths.etc / "provider.env").read_text()
        return dict(line.split("=", 1) for line in text.splitlines() if line[:1].isupper())

    def _sync(self) -> None:
        self.started = {
            service
            for box in self.containers.values()
            for service, container in box.items()
            if container["running"]
        }

    def _do(self, argv: list[str], env: dict[str, str], stdin: bytes | None) -> Result:
        text = " ".join(argv)
        if argv[:2] == ["docker", "run"] and "backup_runner.py" in text and self.loose:
            # The runner's admission (`check_readers`): a reader of a project volume that is
            # neither exited nor part of the project.
            return Result(3, b'{"code": "child_unresolved"}\n', b"")
        if argv[:3] == ["docker", "volume", "ls"]:
            project = _label_project(argv)
            return _ok("".join(f"{v}\n" for v in self.data if v.startswith(f"{project}_")))
        if argv[:2] == ["docker", "ps"] and any(a.startswith("volume=") for a in argv):
            volume = next(a for a in argv if a.startswith("volume=")).split("=", 1)[1]
            project = volume.split("_", 1)[0]
            rows = [f"{k}\t\n" for k, v in self.loose.items() if v == volume]
            if volume.endswith("_supabase-db-data") and "db" in self.containers.get(project, {}):
                rows.append(f"{project}-db-1\t{project}\n")
            return _ok("".join(rows))
        if argv[:3] == ["docker", "rm", "--force"] and argv[3] in self.loose:
            del self.loose[argv[3]]
            return _ok(argv[3] + "\n")
        if argv[0] == "python3":
            return self._restore_tool(argv)
        if argv[0] == "apt-get":
            return self._apt(argv)
        if argv[:2] == ["docker", "run"] and "backup_installation.py" in text:
            return self._backup(argv, stdin)
        if argv[:2] == ["docker", "ps"] and any("com.docker.compose.project=" in a for a in argv):
            project = _label_project(argv)
            box = self.containers.get(project, {})
            if "--all" in argv:  # the working-folder labels of every container
                return _ok("".join(f"{c['dir']}\n" for c in box.values()))
            return _ok("".join(f"{project}-{s}-1\n" for s, c in box.items() if c["running"]))
        if argv[:3] == ["docker", "network", "ls"]:
            project = _label_project(argv)
            return _ok("".join(f"{n}\n" for n in self.networks if n.startswith(f"{project}_")))
        if argv[:3] == ["docker", "image", "inspect"] and TARGET in argv[-1]:
            role = "server" if "slateops-server" in argv[-1] else "caddy"
            return _ok(TARGET_DIGEST[role] + "\n")
        if "operations.install.provisioning" in argv and any(TARGET in a for a in argv):
            project = argv[argv.index("--network") + 1].removesuffix("_provider")
            if self.migration_fails:
                self.data[f"{project}_supabase-db-data"] = "half-migrated"
                if self.drive_gone_at_migration:
                    self.host.pull_drive()
                    self.host._umount(["umount", str(self.host.mount_point)])
                return Result(3, b'{"step":"migrate","code":"migration_failed"}\n', b"")
        return super()._do(argv, env, stdin)

    # Compose per project ------------------------------------------------------------------

    def _compose(self, argv: list[str]) -> Result:
        project = argv[argv.index("--project-name") + 1]
        folder = str(Path(argv[argv.index("-f") + 1]).parent)
        tail = argv[argv.index("-f", argv.index("-f") + 3) + 2 :]
        box = self.containers.setdefault(project, {})
        if tail[0] == "up":
            services = [item for item in tail[1:] if not item.startswith("--") and item != "never"]
            env = self._env()
            if not any(name.startswith(f"{project}_") for name in self.networks):
                subnet = env["SLATEOPS_APP_PRIVATE_SUBNET"]
                if subnet in self.networks.values():
                    return Result(1, b"", b"invalid pool request: Pool overlaps with other one\n")
                self.networks[f"{project}_app"] = subnet
            for service in services:
                image = {"api": env["SLATEOPS_SERVER_IMAGE"],
                         "caddy": env["SLATEOPS_CADDY_IMAGE"]}.get(service, "provider")  # fmt: skip
                old = box.get(service)
                if old and old["image"] == image and "--force-recreate" not in tail:
                    old["running"] = True
                else:
                    box[service] = {"image": image, "dir": folder, "running": True,
                                    "instance": env["SLATEOPS_INSTANCE_ID"]}  # fmt: skip
                if service == "db":
                    for volume in ("supabase-db-data", "supabase-storage-data"):
                        name = f"{project}_{volume}"
                        if name not in self.data:
                            self.data[name] = "install-data"
                            self.volumes.add(name)
                            self.volume_creations.append(name)
            init = box.get("provider-volume-init")
            if (
                "storage" in services
                and "--no-deps" not in tail
                and (init is None or "--always-recreate-deps" in tail)
            ):  # started only as a dependency of storage; recreated only with this flag
                box["provider-volume-init"] = {"image": "provider", "dir": folder,
                                               "running": False, "instance": ""}  # fmt: skip
            if "caddy" in services:
                self.served = self.file_leaf()
            self._sync()
            return _ok()
        if tail[0] == "stop":
            for container in box.values():
                container["running"] = False
            self.stops += 1
            self._sync()
            return _ok()
        if tail[0] == "down":
            assert "-v" not in tail and "--volumes" not in tail, tail
            if self.down_leaves_db and "db" in box:
                self.containers[project] = {"db": box["db"]}
            else:
                self.containers.pop(project, None)
                for name in [n for n in self.networks if n.startswith(f"{project}_")]:
                    del self.networks[name]
            self._sync()
            return _ok()
        if tail[0] == "ps":
            rows = [
                {"Service": s, "State": "running" if c["running"] else "exited",
                 "Health": "healthy", "ExitCode": 0}
                for s, c in sorted(box.items())
            ]  # fmt: skip
            return _ok("\n".join(json.dumps(row) for row in rows))
        if tail[:4] == ["exec", "-T", "caddy", "caddy"]:
            self.reloads += 1
            self.served = self.file_leaf()
            return _ok()
        if tail[0] == "exec":
            api = box.get("api")
            if not api or not api["running"]:
                return Result(1, b"", b"service api is not running")
            if "SLATEOPS_VERSION" in " ".join(tail):
                return _ok((self.api_reports or api["image"].rsplit(":", 1)[1]) + "\n")
            return Result(0, b'200 {"status":"ready"}', b"")
        return _ok()

    # The backup tool, the host restore tool and apt ----------------------------------------

    def _backup(self, argv: list[str], stdin: bytes | None) -> Result:
        config = json.loads(Path(argv[argv.index("--config") + 1]).read_text())
        marker, project = Path(config["completion_marker"]), config["project_name"]
        if marker.exists():
            return Result(1, b"", b"Backup failed: completion marker already exists\n")
        if any(c["running"] for c in self.containers.get(project, {}).values()):
            return Result(1, b"", b"Backup failed: the project is running\n")
        if self.tool_dies_in_export:  # the export container is created, then the engine dies
            self.loose["keen_kilby"] = f"{project}_supabase-db-data"
            raise Killed
        found = self.host.answer(argv, stdin)
        assert found is not None
        if found.ok:
            number = len(self.snapshots) + 1
            snapshot, digest = f"{number:064x}", f"{number:064x}".replace("0", "9")
            self.snapshots[snapshot] = {
                "data": {k: v for k, v in self.data.items() if k.startswith(f"{project}_")},
                "env": {n: (self.paths.etc / n).read_text() for n in ("provider.env", "app.env")},
                "manifest_sha256": digest,
                "source": config["installation_id"],
            }
            marker.write_text(json.dumps({"format_version": 3, "snapshot_id": snapshot,
                                          "manifest_sha256": digest, "source_project": project,
                                          "source_installation_id": project}))  # fmt: skip
        return found

    def _restore_tool(self, argv: list[str]) -> Result:
        start = argv.index("-c") + 2
        packaging, mode, config, snapshot, project, directory = argv[start : start + 6]
        assert Path(packaging) == self.paths.bundle_root / "packaging"
        target = Path(directory)
        found = self.snapshots[snapshot]
        if json.loads(Path(config).read_text())["installation_id"] != found["source"]:
            return Result(1, b"", b"Restore failed: snapshot source does not match the config\n")
        if mode == "restore":
            binding = Path(argv[start + 6])
            assert stat.S_IMODE(binding.stat().st_mode) == 0o600
            assert json.loads(binding.read_text()) == {
                "format_version": 1, "snapshot_id": snapshot,
                "target_project": project, "target_directory": directory,
            }  # fmt: skip
            if target.exists() or any(name.startswith(f"{project}_") for name in self.data):
                return Result(1, b"", b"Restore failed: target already owns Docker resources\n")
            for volume, content in found["data"].items():
                self.data[f"{project}_{volume.split('_', 1)[1]}"] = content
            private = target / "restored-source-private"
            private.mkdir(parents=True)
            for name, content in found["env"].items():
                (private / name).write_text(content)
            pending = {"snapshot_id": snapshot, "manifest_sha256": found["manifest_sha256"]}
            (target / "restore-pending.json").write_text(json.dumps(pending))
            return _ok("Restore staged offline; application sessions still require finalization.\n")
        box = self.containers.get(project, {})
        running = sorted(s for s, c in box.items() if c["running"])
        if running != ["db"] or box["db"]["instance"] != project:
            return Result(1, b"", b"Restore failed: start only the isolated target PostgreSQL\n")
        (target / "restore-finalized.json").write_text(json.dumps({"target_project": project}))
        return _ok("Restore finalization complete.\n")

    def _apt(self, argv: list[str]) -> Result:
        self.apt.append(argv)
        folder = Path(next(a for a in argv if a.startswith("Dir::Etc::SourceParts=")).split("=")[1])
        self.sources_seen = {path.name: path.read_text() for path in sorted(folder.iterdir())}
        if self.apt_fails and "upgrade" in argv:
            return Result(100, b"", b"E: Sub-process /usr/bin/dpkg returned an error code (1)\n")
        return _ok()


class Installed:
    """An installed machine, a staged target release, and one clock."""

    def __init__(self, root: Path) -> None:
        self.paths, _ = _setup(root)
        self.fake = UpdateWorld(self.paths)
        code, result = run(self.paths, self.fake)
        assert code == 0, result
        self.project = json.loads(self.paths.installation.read_text())["project"]
        self.subnet = json.loads(self.paths.journal.read_text())["subnet"]
        self.clock = Clock()
        sources = ROOT / "packaging/linux-image/rootfs/etc/apt/sources.list.d"
        shutil.copytree(sources, self.paths.apt_sources)
        self.origin: dict[str, dict[str, str]] = {}
        self.fake.calls.clear()

    def stage(self, version: str = TARGET, *, tamper: bool = False, app_line: str = "") -> None:
        """What ``receive`` keeps for ``version``: the manifest and the engine bundle; with
        ``app_line``, the bundle's ``app.env`` template has one more line."""
        files = io.BytesIO()
        template = "engine/templates/app.env"
        app = (self.paths.engine_home / "templates/app.env").read_text() + app_line + "\n"
        with tarfile.open(fileobj=files, mode="w") as tar:
            for path in sorted(self.paths.bundle_root.rglob("*")):
                name = path.relative_to(self.paths.bundle_root).as_posix()
                if path.is_file() and name not in ("engine/VERSION", template):
                    tar.add(path, name)
            for name, content in (("engine/VERSION", f"{version}\n"), ("slateops-engine", "#\n"),
                                  (template, app)):  # fmt: skip
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(content), 0o755
                tar.addfile(info, io.BytesIO(content.encode()))
        bundle = gzip.compress(files.getvalue())
        kept = private_dir(self.paths.releases / version)
        name = f"slateops-engine-{version}.tar.gz"
        (kept / name).write_bytes(bundle + (b"x" if tamper else b""))
        refs = {role: f"ghcr.io/jayeuse/slateops-{role}:{version}@{TARGET_DIGEST[role]}"
                for role in TARGET_DIGEST}  # fmt: skip
        manifest = {
            "schema_version": 1,
            "version": version,
            "images": {"server": {"ref": refs["server"]}, "caddy": {"ref": refs["caddy"]},
                       "providers": PROVIDERS},
            "engine_bundle": {"archive": name, "sha256": hashlib.sha256(bundle).hexdigest(),
                              "size": len(bundle)},
        }  # fmt: skip
        (kept / "release-manifest.json").write_text(json.dumps(manifest))

    def job(self, job: str, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        out = io.StringIO()
        dependencies = deps(
            self.paths,
            make_runner=self.fake.runner,
            docker_api=self.fake.docker_api,
            https_get=self.fake.https_get,
            chown=self.fake.chown,
            served_certificate=self.fake.served_certificate,
            clock=self.clock,
        )
        data = io.BytesIO(json.dumps(request).encode())
        code = cli.main([job], stdin=data, stdout=out, deps=dependencies)
        lines = out.getvalue().splitlines()
        assert len(lines) == 1, out.getvalue()
        return code, json.loads(lines[0])

    def update(self, version: str = TARGET) -> tuple[int, dict[str, Any]]:
        return self.job("update", {"run_id": UPDATE, "version": version})

    def tick(self) -> tuple[int, dict[str, Any]]:
        return self.job("tick", {"run_id": TICK})

    def journal(self) -> dict[str, Any]:
        found: dict[str, Any] = json.loads(
            (self.paths.state / "update" / f"{UPDATE}.json").read_text()
        )
        return found

    def installation(self) -> dict[str, Any]:
        found: dict[str, Any] = json.loads(self.paths.installation.read_text())
        return found

    def env(self, name: str) -> dict[str, str]:
        text = (self.paths.etc / name).read_text()
        return dict(line.split("=", 1) for line in text.splitlines() if line[:1].isupper())

    def running(self, project: str) -> dict[str, str]:
        box = self.fake.containers.get(project, {})
        return {s: c["image"].rsplit(":", 1)[-1] for s, c in box.items() if c["running"]}

    def index(self, marker: str) -> int:
        return next(i for i, argv in enumerate(self.fake.calls) if marker in " ".join(argv))


@pytest.fixture
def machine(tmp_path: Path) -> Installed:
    return Installed(tmp_path)


SERVICES = {"db", "auth", "storage", "realtime", "api-gw", "api", "caddy"}


def _on(version: str) -> dict[str, str]:
    return {s: version if s in ("api", "caddy") else "provider" for s in SERVICES}


# W13b-1 --------------------------------------------------------------------------------------


def test_w13b_1_an_update_runs_the_target_release_and_keeps_the_data(machine: Installed) -> None:
    paths, fake = machine.paths, machine.fake
    machine.stage(app_line="SLATEOPS_UPDATE_PROBE=https://{{PUBLIC_HOST}}/probe")
    secrets_before = {k: v for k, v in machine.env("provider.env").items() if "IMAGE" not in k}

    code, result = machine.update()

    assert (code, result) == (0, {"code": "updated", "from_version": VERSION, "version": TARGET})
    assert machine.running(machine.project) == _on(TARGET)
    root = paths.bundle_root.parent / TARGET
    assert {c["dir"] for c in fake.containers[machine.project].values()} == {
        str(root / "infra/supabase")
    }
    assert fake.data[f"{machine.project}_supabase-db-data"] == "install-data"
    assert not [argv for argv in fake.calls if argv[0] == "python3"]
    assert {k: v for k, v in machine.env("provider.env").items() if "IMAGE" not in k} == (
        secrets_before
    )
    assert machine.installation()["version"] == TARGET
    config = json.loads((paths.etc / "backup.json").read_text())
    assert config["compose_root"] == str(root / "infra/supabase")
    assert paths.engine_command.resolve() == (root / "slateops-engine").resolve()
    assert machine.journal()["state"] == "succeeded"
    # 7.3 step 6: a new template key is added from values that the files already hold.
    assert machine.env("app.env")["SLATEOPS_UPDATE_PROBE"] == "https://frontdesk-pc.local/probe"
    # Renewal and resend-invitation read the server image from the install journal.
    assert json.loads(paths.journal.read_text())["server_image"].endswith(f":{TARGET}")
    # 7.3: the backup runs with the services stopped, before the first target container.
    assert machine.index("backup_installation.py") < machine.index("--force-recreate")


def test_w13b_1_an_api_that_reports_another_version_is_rolled_back(machine: Installed) -> None:
    machine.stage()
    machine.fake.api_reports = VERSION

    code, result = machine.update()

    assert (code, result["code"], result["update"]) == (3, "api_version_mismatch", "rolled_back")
    assert machine.installation()["version"] == VERSION


# W13b-2 and W13b-9 ---------------------------------------------------------------------------


@pytest.fixture
def rolled_back(machine: Installed) -> Installed:
    machine.stage()
    machine.fake.migration_fails = True
    machine.origin = {name: machine.env(name) for name in ("provider.env", "app.env")}
    code, result = machine.update()
    assert (code, result["code"], result["update"]) == (3, "provisioning_failed", "rolled_back")
    return machine


def test_w13b_2_a_failed_migration_rolls_back_with_the_data_the_origin_and_the_name(
    rolled_back: Installed,
) -> None:
    machine, paths, fake = rolled_back, rolled_back.paths, rolled_back.fake
    restored = f"{machine.project}-r1"

    assert machine.journal()["state"] == "rolled_back"
    assert machine.installation() == {
        "instance_id": restored,
        "project": restored,
        "public_host": "frontdesk-pc.local",
        "version": VERSION,
    }
    assert machine.running(restored) == _on(VERSION)
    assert fake.data[f"{restored}_supabase-db-data"] == "install-data"
    for name in ("provider.env", "app.env"):
        changed = {k for k, v in machine.env(name).items() if machine.origin[name].get(k) != v}
        assert changed == {"SLATEOPS_INSTANCE_ID"}, name
    assert machine.env("provision.env")["SLATEOPS_INSTANCE_ID"] == restored
    # 7.5 step 6: the policy is adopted with the fixed marker; the config names the new project.
    assert json.loads((paths.etc / "backup.json").read_text())["installation_id"] == restored
    adopt = [a for a in fake.calls if "--restore-finalized" in a]
    assert [a[a.index("--restore-finalized") + 1] for a in adopt] == [
        str(paths.state / "runner/restore-finalized.json")
    ]
    # C-1, C-6: the snapshot of this update's own backup marker; no binding is left.
    [restore] = [a for a in fake.calls if a[0] == "python3" and "restore" in a]
    assert restore[restore.index("-c") + 5] == machine.journal()["snapshot_id"]
    assert not list((paths.state / "update").glob("*.restore-binding.json"))
    # The journal is closed: later ticks never resume the update.
    fake.calls.clear()
    code, result = machine.tick()
    assert (code, result["code"]) == (0, "ran")
    assert machine.journal()["state"] == "rolled_back"
    assert not [a for a in fake.calls if a[0] == "python3" or "--force-recreate" in a]


def test_w13b_9_the_rollback_removes_the_failed_networks_keeps_its_volumes_then_restores(
    rolled_back: Installed,
) -> None:
    machine, fake = rolled_back, rolled_back.fake
    failed, restored = machine.project, f"{machine.project}-r1"

    assert fake.containers.get(failed, {}) == {}
    assert not [name for name in fake.networks if name.startswith(f"{failed}_")]
    assert fake.data[f"{failed}_supabase-db-data"] == "half-migrated"  # kept for support
    assert fake.networks == {f"{restored}_app": machine.subnet}  # same subnet, no overlap
    assert machine.index(" down ") < machine.index("python3")


def test_the_rollback_is_refused_while_a_container_of_the_failed_project_runs(
    machine: Installed,
) -> None:
    machine.stage()
    machine.fake.migration_fails = True
    machine.fake.down_leaves_db = True

    code, result = machine.update()

    assert (code, result["code"], result["update"]) == (3, "provisioning_failed", "needs_support")
    assert machine.journal()["rollback_code"] == "rollback_refused"
    assert not [a for a in machine.fake.calls if a[0] == "python3"]


# W13b-3 and W13b-4 ---------------------------------------------------------------------------


def test_w13b_3_a_failure_before_step_7_recovers_on_the_old_images_with_no_restore(
    machine: Installed,
) -> None:
    machine.stage()
    machine.fake.host.first_backup_fails = True

    code, result = machine.update()

    assert (code, result["code"], result["update"]) == (3, "backup_failed", "failed")
    assert machine.running(machine.project) == _on(VERSION)
    assert machine.env("provider.env")["SLATEOPS_SERVER_IMAGE"].endswith(f":{VERSION}")
    assert not [a for a in machine.fake.calls if a[0] == "python3" or "--force-recreate" in a]
    assert machine.installation()["version"] == VERSION
    assert machine.journal()["state"] == "failed"


def test_w13b_3_a_new_secret_in_the_target_fails_step_6_and_recover_writes_the_old_images(
    machine: Installed,
) -> None:
    machine.stage(app_line="SLATEOPS_NEW_SECRET={{SLATEOPS_NEW_SECRET}}")

    code, result = machine.update()

    assert (code, result["code"], result["update"]) == (3, "env_render_failed", "failed")
    assert machine.env("provider.env")["SLATEOPS_SERVER_IMAGE"].endswith(f":{VERSION}")
    assert "SLATEOPS_NEW_SECRET" not in machine.env("app.env")
    assert machine.running(machine.project) == _on(VERSION)
    assert not [a for a in machine.fake.calls if a[0] == "python3" or "--force-recreate" in a]


def test_w13b_4_low_space_gives_insufficient_space_with_no_outage(machine: Installed) -> None:
    machine.stage()
    volume = machine.paths.docker_volumes / f"{machine.project}_supabase-db-data/_data"
    volume.mkdir(parents=True)
    (volume / "base").write_bytes(b"\0" * 300_000)
    used = sum(p.lstat().st_blocks * 512 for p in volume.parent.rglob("*"))
    needed = 2 * used + 2 * GIB
    stops = machine.fake.stops  # the install's first backup stopped the services once
    out = io.StringIO()
    dependencies = deps(machine.paths, make_runner=machine.fake.runner, clock=machine.clock,
                        disk_free=lambda path: needed - 1)  # fmt: skip
    data = io.BytesIO(json.dumps({"run_id": UPDATE, "version": TARGET}).encode())

    code = cli.main(["update"], stdin=data, stdout=out, deps=dependencies)

    assert (code, json.loads(out.getvalue())) == (3, {
        "code": "insufficient_space", "message_key": "update.insufficient_space",
        "needs_gb": 3, "update": "failed",
    })  # fmt: skip
    assert machine.fake.stops == stops and machine.running(machine.project) == _on(VERSION)
    changes = ("stop", "up", "down", "run")
    assert not [a for a in machine.fake.calls if a[:2] == ["docker", "compose"] and
                set(a) & set(changes) or a[:2] == ["docker", "run"]]  # fmt: skip
    assert machine.journal()["state"] == "failed"


# W13b-6 and W13b-10 --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("staged", "expected"),
    [(False, "manifest_missing"), (True, "payload_mismatch")],
    ids=["receive-kept-nothing", "bundle-changed-after-receive"],
)
def test_w13b_6_a_release_that_receive_did_not_verify_is_refused_before_anything_stops(
    machine: Installed, staged: bool, expected: str
) -> None:
    if staged:
        machine.stage(tamper=True)

    code, result = machine.update()

    assert (code, result["code"]) == (2, expected)
    assert not [
        a for a in machine.fake.calls if a[:2] in (["docker", "compose"], ["docker", "run"])
    ]
    assert machine.running(machine.project) == _on(VERSION)


def test_w13b_10_versions_order_by_semver_precedence() -> None:
    ordered = ["0.1.0-rc.2", "0.1.0-rc.9", "0.1.0-rc.10", "0.1.0", "0.1.1-rc.1", "0.1.1",
               "0.2.0", "0.10.0", "1.0.0-rc.1"]  # fmt: skip

    assert sorted(reversed(ordered), key=update.precedence) == ordered


@pytest.mark.parametrize("version", [VERSION, "0.1.0-rc.8", "0.0.9"])
def test_w13b_10_the_engine_refuses_a_target_that_is_not_newer(
    machine: Installed, version: str
) -> None:
    machine.stage(version)

    code, result = machine.update(version)

    assert (code, result["code"]) == (2, "version_not_newer")
    assert machine.fake.calls == []


# W13b-7 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kill_at", "fails", "state", "version", "project"),
    [
        ("backup_installation.py", False, "failed", VERSION, ""),
        ("--always-recreate-deps db", False, "rolled_back", VERSION, "-r1"),
        ("operations.install.provisioning", False, "rolled_back", VERSION, "-r1"),
        ("python3", True, "rolled_back", VERSION, "-r2"),
        ("--restore-finalized", True, "rolled_back", VERSION, "-r2"),
        ("com.docker.compose.project.working_dir", False, "succeeded", TARGET, ""),
    ],
    ids=[
        "during-the-backup",
        "first-target-container",
        "migration",
        "rollback-restore",
        "rollback-adopt",
        "step-12-label-check",
    ],  # fmt: skip
)
def test_w13b_7_a_restart_during_an_update_resumes_by_the_section_12_rule(
    machine: Installed,
    monkeypatch: pytest.MonkeyPatch,
    kill_at: str,
    fails: bool,
    state: str,
    version: str,
    project: str,
) -> None:
    machine.stage()
    fake = machine.fake
    fake.migration_fails = fails
    counted: list[str] = []
    original = fake.answer

    def answer(argv: list[str], env: dict[str, str], stdin: bytes | None = None) -> Result:
        if kill_at in " ".join(argv) and not counted:
            counted.append(kill_at)
            raise Killed
        return original(argv, env, stdin)

    monkeypatch.setattr(fake, "answer", answer)
    with pytest.raises(Killed):
        machine.update()
    monkeypatch.undo()
    status = {"run_id": SUPPORT, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}
    assert machine.job("status", status)[1]["engine_idle"] is False

    code, result = machine.tick()

    assert (code, result["code"], result["update"]) == (0, "update_closed", state)
    assert machine.journal()["state"] == state
    assert machine.running(machine.project + project) == _on(version)
    assert not list((machine.paths.state / "update").glob("*.restore-binding.json"))
    assert machine.job("status", status)[1]["engine_idle"] is True
    if state == "succeeded":  # the switched command runs the target bundle with its image
        target = machine.paths.bundle_root.parent / TARGET / "engine"
        machine.paths = dataclasses.replace(machine.paths, engine_home=target)
        fake.host.image_id, fake.host.image_label = TARGET_DIGEST["server"], TARGET
    code, result = machine.tick()
    assert (code, result["code"], machine.journal()["state"]) == (0, "ran", state)


def test_w13b_7_closing_an_update_cut_in_its_backup_leaves_the_runner_able_to_back_up(
    machine: Installed,
) -> None:
    machine.stage()
    machine.fake.tool_dies_in_export = True
    with pytest.raises(Killed):
        machine.update()
    machine.fake.tool_dies_in_export = False

    code, result = machine.tick()

    assert (code, result["code"], result["update"]) == (0, "update_closed", "failed")
    assert machine.fake.loose == {}
    code, result = machine.tick()
    assert (code, result["code"], result["runner"]) == (0, "ran", "idle")


# W13b-8 --------------------------------------------------------------------------------------

SUNDAY_NIGHT = datetime(2026, 11, 21, 19, 30, tzinfo=UTC)  # Sunday 03:30 in Asia/Manila


@pytest.mark.parametrize("update_tonight", [False, True], ids=["no-update", "update-tonight"])
def test_w13b_8_the_package_night_runs_on_a_night_with_no_update_and_leaves_the_services_ready(
    machine: Installed, update_tonight: bool
) -> None:
    fake = machine.fake
    if update_tonight:
        folder = private_dir(machine.paths.state / "update")
        (folder / f"{UPDATE}.json").write_text(
            json.dumps(
                {"run_id": UPDATE, "state": "succeeded", "started_at": "2026-11-21T19:00:00+00:00"}
            )
        )
    machine.clock = Clock(SUNDAY_NIGHT)

    code, result = machine.tick()

    assert code == 0
    if update_tonight:
        assert (result["package_night"], fake.apt) == ("not_due", [])
        return
    assert result["package_night"] == "ok"
    assert [argv[-1] for argv in fake.apt] == ["update", "upgrade"]
    assert "Dpkg::Options::=--force-confold" in fake.apt[1]
    assert list(fake.sources_seen) == ["docker.sources", "security.sources"]
    assert "Suites: trixie-security\n" in fake.sources_seen["security.sources"]
    assert "trixie-updates" not in fake.sources_seen["security.sources"]
    ups = [a for a in fake.calls[fake.calls.index(fake.apt[1]) :] if " up " in " ".join(a)]
    assert [a[-1] for a in ups] == ["api-gw", "api", "caddy"]
    assert machine.running(machine.project) == _on(VERSION)
    code, again = machine.tick()
    assert again["package_night"] == "not_due"


def test_a_failed_package_night_shows_needs_support(machine: Installed) -> None:
    machine.fake.apt_fails = True
    machine.clock = Clock(SUNDAY_NIGHT)

    code, result = machine.tick()

    assert (code, result["package_night"]) == (0, "needs_support")
    status = {"run_id": SUPPORT, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}
    assert machine.job("status", status)[1]["state"] == "needs_support"
    assert machine.running(machine.project) == _on(VERSION)


def test_s95_1_after_a_rollback_that_needs_support_nothing_starts_the_failed_project(
    machine: Installed,
) -> None:
    machine.stage()
    machine.fake.migration_fails = True
    machine.fake.drive_gone_at_migration = True
    code, result = machine.update()
    assert (code, result["update"]) == (3, "needs_support")
    assert machine.journal()["rollback_code"] == "backup_target_missing"
    machine.clock = Clock(SUNDAY_NIGHT)  # a due package night, more than 24 h later
    machine.fake.calls.clear()

    code, result = machine.tick()

    assert (code, result["package_night"]) == (0, "not_due")
    assert not [a for a in machine.fake.calls if a[:2] == ["docker", "compose"] and "up" in a]
    code, result = machine.job("update", {"run_id": UPDATE.replace("ab12cd", "cd34ef"),
                                          "version": TARGET})  # fmt: skip
    assert (code, result["code"]) == (2, "update_needs_support")
    status = {"run_id": SUPPORT, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}
    assert machine.job("status", status)[1]["state"] == "needs_support"
