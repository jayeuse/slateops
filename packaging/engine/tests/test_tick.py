"""``tick``, ``runner-recover``, ``runner-adopt``, the daily renewal in the tick and the Linux
start record (TASK-0093 AC-1 to AC-3, AC-7 to AC-11; plan 8.1, 8.2, 6.3, 10.2)."""

from __future__ import annotations

import io
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from engine import cli
from engine.runner import Result

from .helpers import Clock, deps, make_paths
from .test_install import _commands, _setup, run

TICK = "backup-20261117T110000Z-ab12cd"
SUPPORT = "maintenance-20261117T110000Z-ab12cd"
STATUS = {"run_id": SUPPORT, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}


def _tick_id(minute: int) -> dict[str, str]:
    return {"run_id": f"backup-20261117T11{minute:02d}00Z-ab12cd"}


class Machine:
    """An installed machine with one clock that the test can move."""

    def __init__(self, root: Path) -> None:
        self.paths, self.fake = _setup(root)
        code, result = run(self.paths, self.fake)
        assert code == 0, result
        self.clock = Clock()
        self.fake.calls.clear()

    def job(self, job: str, request: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        request = {"run_id": TICK if job == "tick" else SUPPORT} if request is None else request
        return self.argv([job], json.dumps(request).encode())

    def argv(self, argv: list[str], data: bytes = b"") -> tuple[int, dict[str, Any]]:
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
        code = cli.main(argv, stdin=io.BytesIO(data), stdout=out, deps=dependencies)
        lines = out.getvalue().splitlines()
        assert len(lines) == 1, out.getvalue()
        return code, json.loads(lines[0])

    @property
    def project(self) -> str:
        return str(json.loads(self.paths.installation.read_text())["project"])

    def runs(self) -> list[list[str]]:
        return [argv for argv in self.fake.calls if "backup_runner.py" in " ".join(argv)]

    def removals(self) -> list[int]:
        rm = ["docker", "rm", "--force", "slateops-runner"]
        return [i for i, argv in enumerate(self.fake.calls) if argv == rm]

    def hold(self, path: Path) -> None:
        """Show ``path`` as flock-held in the fake ``/proc/locks``."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        status = path.stat()
        (self.paths.proc / "locks").write_text(
            f"1: FLOCK  ADVISORY  WRITE 99 {os.major(status.st_dev):02x}:"
            f"{os.minor(status.st_dev):02x}:{status.st_ino} 0 EOF\n"
        )


@pytest.fixture
def machine(tmp_path: Path) -> Machine:
    return Machine(tmp_path)


# AC-1, AC-10: the unchanged runner in the container -----------------------------------------------


def test_ac1_a_tick_before_step_12_does_nothing(tmp_path: Path) -> None:
    paths, fake = _setup(tmp_path)
    out = io.StringIO()

    code = cli.main(["tick"], stdin=io.BytesIO(json.dumps({"run_id": TICK}).encode()),
                    stdout=out, deps=deps(paths, make_runner=fake.runner))  # fmt: skip

    assert (code, json.loads(out.getvalue())) == (0, {"code": "not_set_up"})
    assert fake.calls == []


def test_ac1_ac10_the_timer_tick_runs_the_unchanged_runner_in_the_documented_container(
    machine: Machine,
) -> None:
    paths = machine.paths

    code, result = machine.argv(["--timer", "tick"])

    assert (code, result["code"], result["runner"]) == (0, "ran", "idle")
    [folder] = (paths.logs / "backup").iterdir()
    assert folder.name.startswith("backup-") and len(folder.name) == len(TICK)
    [argv] = machine.runs()
    bundle, state = paths.bundle_root, paths.state
    assert argv[: argv.index("--mount")] == [
        "docker", "run", "--rm", "--init", "--name", "slateops-runner", "--pull=never",
        "--user", "0:0", "--read-only", "--tmpfs", "/tmp",
        "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE",
        "--security-opt", "no-new-privileges", "--no-healthcheck",
    ]  # fmt: skip
    assert [argv[i + 1] for i, item in enumerate(argv) if item == "--mount"] == [
        f"type=bind,source={paths.docker_socket},target=/var/run/docker.sock",
        "type=bind,source=/usr/bin/docker,target=/usr/local/bin/docker,readonly",
        "type=bind,source=/usr/bin/restic,target=/usr/local/bin/restic,readonly",
        "type=bind,source=/usr/libexec/docker/cli-plugins,"
        "target=/usr/libexec/docker/cli-plugins,readonly",
        f"type=bind,source={bundle},target={bundle},readonly",
        f"type=bind,source={paths.etc},target={paths.etc},readonly",
        f"type=bind,source={paths.logs / 'app'},target={paths.logs / 'app'},readonly",
        f"type=bind,source={state / 'backup'},target={state / 'backup'}",
        f"type=bind,source={state / 'runner'},target={state / 'runner'}",
    ]
    assert [argv[i + 1] for i, item in enumerate(argv) if item == "--tmpfs"][1:] == [
        f"{paths.etc / 'ca'}:ro,noexec,nosuid,nodev,size=4k,mode=0000",
        f"{paths.etc / 'new'}:ro,noexec,nosuid,nodev,size=4k,mode=0000",
    ]
    assert argv[argv.index("--entrypoint") + 1 :] == [
        "python", machine.fake.host.image_id,
        str(bundle / "backend/operations/backup_runner.py"), "run",
        "--backup-config", str(paths.etc / "backup.json"),
        "--state-directory", str(state / "runner"),
    ]  # fmt: skip


@pytest.mark.parametrize("part", ["engine", "installation", "label", "image", "compose_root"])
def test_ac1_a_version_or_layout_mismatch_gives_runner_layout_stale_and_no_container(
    machine: Machine, part: str
) -> None:
    paths, host = machine.paths, machine.fake.host
    if part == "engine":
        (paths.engine_home / "VERSION").write_text("0.1.0-rc.8\n")
    elif part == "installation":
        record = json.loads(paths.installation.read_text())
        paths.installation.write_text(json.dumps({**record, "version": "0.1.0-rc.8"}))
    elif part == "label":
        host.image_label = "0.1.0-rc.8"
    elif part == "image":
        host.image_id = "sha256:" + "9" * 64
    else:
        config = json.loads((paths.etc / "backup.json").read_text())
        config["compose_root"] = "/opt/slateops/engine/0.1.0-rc.8/infra/supabase"
        (paths.etc / "backup.json").write_text(json.dumps(config))

    code, result = machine.job("tick")

    assert (code, result["code"]) == (2, "runner_layout_stale")
    assert machine.runs() == []
    assert machine.job("status", STATUS)[1]["backup"] == "runner_layout_stale"


@pytest.mark.parametrize("job", ["tick", "runner-recover", "runner-adopt", "renew-certificate"])
def test_ac10_the_runner_jobs_accept_only_a_run_id(machine: Machine, job: str) -> None:
    code, result = machine.job(job, {"run_id": SUPPORT, "action": "run"})

    assert (code, result["code"]) == (2, "invalid_input")
    assert machine.fake.calls == []


def test_ac10_recover_and_adopt_run_the_runner_recovery_actions(machine: Machine) -> None:
    marker = machine.paths.state / "runner" / "restore-finalized.json"

    assert machine.job("runner-recover")[0] == 0
    assert machine.job("runner-adopt")[0] == 0

    commands = [argv[argv.index("--entrypoint") + 3 :] for argv in machine.runs()]
    assert commands[0][:2] == [
        str(machine.paths.bundle_root / "backend/operations/backup_runner.py"),
        "recover",
    ]
    assert commands[1][1:] == [
        "recover", "--backup-config", str(machine.paths.etc / "backup.json"),
        "--state-directory", str(machine.paths.state / "runner"),
        "--restore-finalized", str(marker),
    ]  # fmt: skip


def test_a_tick_that_does_nothing_keeps_no_log_folder(machine: Machine) -> None:
    # Parent correction A: 20 runs are kept per kind (plan 10.1 item 5), so idle ticks
    # must not rotate the night's backup log out before the morning.
    logs = machine.paths.logs / "backup"
    machine.job("tick")  # the first tick runs the daily renewal: kept

    for minute in range(1, 26):
        machine.job("tick", _tick_id(minute))  # no claim, no mount, no renewal, no refusal

    assert [path.name for path in logs.iterdir()] == [TICK]
    machine.fake.host.runner_result = Result(0, b'{"state": "succeeded"}\n', b"")
    machine.job("tick", _tick_id(30))
    assert len(list(logs.iterdir())) == 2


# AC-2, AC-3: the kept mount -----------------------------------------------------------------------


def test_ac2_a_mounted_target_is_not_touched_and_an_unmounted_one_is_mounted_first(
    machine: Machine,
) -> None:
    host = machine.fake.host
    machine.job("tick")
    assert _commands(machine.fake, "drvfs") == []

    host._umount(["umount", str(host.mount_point)])
    machine.job("tick", _tick_id(1))

    [mount] = _commands(machine.fake, "drvfs")
    assert machine.fake.calls.index(mount) < machine.fake.calls.index(machine.runs()[-1])
    assert host.mounted is not None


@pytest.mark.parametrize(
    "runner",
    [
        Result(3, b'{"code": "backup_failed"}\n', b""),
        Result(3, b'{"state": "failed", "export_id": "x"}\n', b""),
        Result(2, b'{"code": "admission_failed"}\n', b""),
        Result(None, b"", b""),
    ],
    ids=["backup-failed", "export-failed", "admission-failed", "time-limit"],
)
def test_ac2_ac3_a_pulled_drive_recovers_with_no_person(machine: Machine, runner: Result) -> None:
    host = machine.fake.host
    host.pull_drive()
    host.runner_result = runner

    first = machine.job("tick")
    unmounts = [argv for argv in machine.fake.calls if argv[0] == "umount"]
    host.runner_result = Result(0, b'{"state": "idle"}\n', b"")
    second = machine.job("tick", _tick_id(1))

    assert unmounts == [["umount", str(host.mount_point)]]  # plain: no -l, no -f
    assert first[0] == 0 and second[1]["backup"] == "backup_target_missing"
    assert len(machine.runs()) == 2  # the runner still runs: fail-open restarts the services
    assert machine.job("status", STATUS)[1]["backup"] == "backup_target_missing"
    host.drives[next(iter(host.drives))].mkdir(parents=True)  # the drive is back
    machine.job("tick", _tick_id(2))
    assert host.mounted is not None
    assert machine.job("status", STATUS)[1]["backup"] == "ok"


# AC-7: the container is gone before the lock is released ------------------------------------------


def _raise(argv: list[str]) -> Result:
    raise RuntimeError("the docker client broke")


@pytest.mark.parametrize(
    "runner",
    [Result(0, b'{"state": "idle"}\n', b""), Result(None, b"", b""), _raise],
    ids=["normal-end", "time-limit", "exception"],
)
def test_ac7_the_engine_removes_and_confirms_the_container_on_every_path(
    machine: Machine, runner: Any
) -> None:
    host = machine.fake.host
    host.runner_result = runner

    code, _ = machine.job("tick")

    [removal] = machine.removals()
    assert removal > machine.fake.calls.index(machine.runs()[0])
    assert machine.fake.calls[removal + 1][:3] == ["docker", "ps", "--all"]  # confirmed gone
    assert host.container is None
    assert code == (3 if runner is _raise else 0)
    renewals = [i for i, argv in enumerate(machine.fake.calls) if "local_ca.py" in " ".join(argv)]
    assert all(i > removal for i in renewals)


def test_ac7_a_container_that_stays_fails_the_tick_and_runs_no_renewal(machine: Machine) -> None:
    host = machine.fake.host
    host.container_sticky = True
    host.runner_result = Result(None, b"", b"")

    code, result = machine.job("tick")

    assert (code, result["code"]) == (3, "runner_not_removed")
    assert not _commands(machine.fake, "local_ca.py")


@pytest.mark.parametrize("age", [7200 + 3600, 60], ids=["older-than-limit", "young"])
def test_ac7_an_orphan_container_starts_no_runner(machine: Machine, age: int) -> None:
    host = machine.fake.host
    host.container = host.now
    host.age_container(age)

    code, result = machine.job("tick")

    assert machine.runs() == []
    if age > 7200:
        assert (code, result["code"]) == (0, "orphan_removed")
        assert host.container is None
    else:
        assert (code, result["code"], machine.removals()) == (2, "runner_busy", [])


# AC-8, AC-9: renewal in the tick ------------------------------------------------------------------


def _renewals(machine: Machine) -> int:
    return len(_commands(machine.fake, "local_ca.py renew"))


def test_ac9_the_tick_renews_once_a_day_and_an_hour_after_a_failure(machine: Machine) -> None:
    machine.job("tick")
    machine.job("tick", _tick_id(1))
    assert _renewals(machine) == 1
    machine.clock.now += timedelta(hours=23)
    machine.job("tick", _tick_id(2))
    assert _renewals(machine) == 1
    machine.clock.now += timedelta(hours=1, minutes=1)
    machine.fake.check_fails = True
    machine.job("tick", _tick_id(3))
    assert _renewals(machine) == 2
    machine.fake.check_fails = False
    machine.clock.now += timedelta(minutes=59)
    machine.job("tick", _tick_id(4))
    assert _renewals(machine) == 2
    machine.clock.now += timedelta(minutes=2)
    machine.job("tick", _tick_id(5))
    assert _renewals(machine) == 3


def test_ac9_stale_staged_leaf_files_are_removed_before_the_renewal(machine: Machine) -> None:
    tls = machine.paths.etc / "tls"
    for name in (".server.crt.new", ".server.key.new"):
        (tls / name).write_text("left by a killed renewal")

    code, _ = machine.job("renew-certificate")

    assert code == 0
    assert not (tls / ".server.crt.new").exists() and not (tls / ".server.key.new").exists()


def test_ac8_renewal_skips_while_a_runner_journal_is_active(machine: Machine) -> None:
    active = machine.paths.state / "runner" / machine.project / "active.json"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text('{"claim_id": "x"}')

    code, result = machine.job("tick")

    assert (code, result["renewal"]) == (0, "skipped")
    assert _renewals(machine) == 0
    assert machine.job("renew-certificate")[1]["code"] == "runner_busy"


def test_ac8_engine_idle_is_false_while_the_runner_holds_its_lock(machine: Machine) -> None:
    assert machine.job("status", STATUS)[1]["engine_idle"] is True

    machine.hold(machine.paths.state / "runner" / machine.project / "lock")

    assert machine.job("status", STATUS)[1]["engine_idle"] is False


# AC-11: each Linux start and its ready time -----------------------------------------------------


def _boot(machine: Machine, boot_id: str, ticks: int) -> None:
    proc = machine.paths.proc
    (proc / "sys/kernel/random").mkdir(parents=True, exist_ok=True)
    (proc / "sys/kernel/random/boot_id").write_text(boot_id + "\n")
    (proc / "stat").write_text("cpu  1 2 3\nbtime 1795428000\nprocesses 9\n")
    (proc / "1").mkdir(exist_ok=True)
    fields = ["S", *["0"] * 18, str(ticks), "0"]
    (proc / "1/stat").write_text(f"1 (systemd) {' '.join(fields)}\n")


def test_ac11_each_linux_start_and_its_ready_time_are_recorded(
    machine: Machine, tmp_path: Path
) -> None:
    _boot(machine, "0f2c6a1e-5d7b-4c11-9b0e-2d4f6a8c1e3b", 500)
    machine.fake.started.discard("caddy")  # not ready yet

    machine.job("tick")
    first = machine.job("status", STATUS)[1]["linux_start"]
    machine.fake.started.add("caddy")
    machine.job("tick", _tick_id(1))
    ready = machine.job("status", STATUS)[1]["linux_start"]
    _boot(machine, "7a1d3c5e-2b4f-4a6c-8e0d-1f3b5d7a9c2e", 300)
    machine.job("tick", _tick_id(2))

    starts = json.loads(machine.paths.report.read_text())["starts"]
    assert first == {"started_at": "2026-11-23T10:00:05+00:00", "ready_at": None}
    assert ready["ready_at"] is not None and ready["started_at"] == first["started_at"]
    assert [start["started_at"] for start in starts] == [
        "2026-11-23T10:00:05+00:00",
        "2026-11-23T10:00:03+00:00",
    ]
    out = io.StringIO()
    cli.main(["status"], stdin=io.BytesIO(json.dumps(STATUS).encode()), stdout=out,
             deps=deps(make_paths(tmp_path / "fresh")))  # fmt: skip
    assert json.loads(out.getvalue())["linux_start"] is None  # no start recorded yet
