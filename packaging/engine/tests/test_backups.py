"""Install step 12, ``set-backup-target`` and ``new-recovery-key`` (TASK-0093 AC-2, AC-4 to
AC-6, AC-8; plan 6.2 step 12, 8.2, 8.3, 10.3 F5)."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine.core import Paths
from engine.runner import Result

from .backup_host import CHUNKER_SECRET
from .helpers import RUN_ID, log_text, progress_lines
from .test_install import ANSWERS, World, _commands, _mode, _setup, run

TARGET = ANSWERS["backup_target"]
MAINTENANCE = "maintenance-20261117T120000Z-ab12cd"
OPTIONS = "uid=0,gid=0,umask=077,nosuid,nodev,noexec"


@pytest.fixture
def world(tmp_path: Path) -> tuple[Paths, World]:
    return _setup(tmp_path)


@pytest.fixture
def installed(tmp_path: Path) -> tuple[Paths, World, dict[str, Any]]:
    paths, fake = _setup(tmp_path)
    code, result = run(paths, fake)
    assert code == 0, result
    return paths, fake, result


def _job(paths: Paths, fake: World, job: str, **values: Any) -> tuple[int, dict[str, Any]]:
    return run(paths, fake, {"run_id": MAINTENANCE, **values}, job=job)


def _texts(fake: World) -> list[str]:
    return [" ".join(argv) for argv in fake.calls]


def _inits(fake: World) -> int:
    return len([argv for argv in fake.calls if argv[0] == "restic" and argv[-1] == "init"])


# AC-6: step 12 in the TASK-0092 order ----------------------------------------------------------


def test_ac6_step_12_sets_up_the_backup_in_order_and_keeps_the_drive_mounted(
    installed: tuple[Paths, World, dict[str, Any]],
) -> None:
    paths, fake, _ = installed
    texts = _texts(fake)
    start = next(i for i, text in enumerate(texts) if "bootstrap_admin.py" in text)
    order = [
        "/usr/bin/mount -t drvfs",
        "--password-file",  # restic init
        "operations/backup_state.py",  # policy_default
        " stop",  # the stack stops for the first backup
        "backup_installation.py --config",
        "key add --new-password-file",
        "systemctl daemon-reload",
        "systemctl enable --now slateops-runner.timer",
    ]
    positions = [next(i for i, t in enumerate(texts[start:]) if m in t) for m in order]
    config = json.loads((paths.etc / "backup.json").read_text())
    backup = paths.state / "backup"

    assert positions == sorted(positions), positions
    assert texts[start + positions[1]].endswith(" init")
    assert fake.host.policy_inputs == [
        {"installation_id": config["installation_id"], "project": config["project_name"],
         "op": "policy_default"}
    ]  # fmt: skip
    assert config == {
        "version": 3, "installation_id": config["project_name"],
        "project_name": config["project_name"], "deployment": "production",
        "compose_layout": "installer", "compose_root": str(paths.bundle_root / "infra/supabase"),
        "provider_env_file": str(paths.etc / "provider.env"),
        "app_env_file": str(paths.etc / "app.env"),
        "caddy_config_file": str(paths.etc / "Caddyfile"),
        "tls_directory": str(paths.etc / "tls"),
        "restic_repository": str(backup / "repository"),
        "restic_password_file": str(paths.etc / "restic-password"),
        "staging_directory": str(backup / "staging"),
        "completion_marker": str(backup / "markers" / "backup-complete.json"),
    }  # fmt: skip
    assert _mode(paths.etc / "backup.json") == 0o600
    assert fake.host.snapshots == 1 and {"caddy", "api", "db"} <= fake.started
    assert (
        "ExecStart=/usr/local/bin/slateops-engine --timer tick"
        in (paths.systemd / "slateops-runner.service").read_text()
    )
    assert "OnCalendar=*-*-* *:*:00" in (paths.systemd / "slateops-runner.timer").read_text()
    assert fake.host.mounted == TARGET
    assert not [argv for argv in fake.calls if argv[0] == "umount"]  # 12.7 does not unmount


def test_ac6_f5_a_failed_first_backup_stops_the_install_and_restarts_the_services(
    world: tuple[Paths, World],
) -> None:
    paths, fake = world
    fake.host.first_backup_fails = True

    code, result = run(paths, fake)

    assert (code, result) == (
        3,
        {"code": "first_backup_failed", "message_key": "install.first_backup_failed"},
    )
    assert {"caddy", "api", "db"} <= fake.started
    assert fake.host.container is None
    assert "12" not in json.loads(paths.journal.read_text())["steps"]
    assert not _commands(fake, "enable --now")


# AC-2, AC-4: the target, the mount and the repository ------------------------------------------


def test_ac2_one_argument_list_from_fixed_parts_and_the_target(
    installed: tuple[Paths, World, dict[str, Any]],
) -> None:
    paths, fake, _ = installed

    [mount] = _commands(fake, "drvfs")

    assert mount == [
        "systemd-run", "--wait", "--collect", "--quiet", "--", "/usr/bin/mount", "-t", "drvfs",
        TARGET, str(paths.state / "backup" / "repository"), "-o", OPTIONS,
    ]  # fmt: skip


@pytest.mark.parametrize(
    "target",
    [
        "e:\\Backups", "E:", "E:\\Back\\", "E:\\.", "E:\\..\\Windows", "E:\\Backups.",
        "E:\\Backups ", "E:\\CON", "E:\\nul.txt", "E:\\Com1", "E:\\Back$ups", "E:\\Back/ups",
        "E:/Backups", "\\\\server\\share", "E:\\" + "\\".join("abcdefghi"), "E:\\" + "a" * 198,
        "E:\\Back\x00ups", "E:\\",
    ],
)  # fmt: skip
def test_ac4_set_backup_target_refuses_a_target_outside_the_rule(
    installed: tuple[Paths, World, dict[str, Any]], target: str
) -> None:
    paths, fake, _ = installed
    calls = len(fake.calls)

    code, result = _job(paths, fake, "set-backup-target", backup_target=target)

    assert (code, result["code"]) == (2, "invalid_input")
    assert len(fake.calls) == calls


@pytest.mark.parametrize(
    "target", ["F:\\SlateOps-backups", "F:\\" + "\\".join("abcdefgh"), "F:\\" + "a" * 197,
               "F:\\My Backups-2.v1"]
)  # fmt: skip
def test_ac4_set_backup_target_accepts_the_rule_and_stores_it_root_only(
    installed: tuple[Paths, World, dict[str, Any]], tmp_path: Path, target: str
) -> None:
    paths, fake, _ = installed
    fake.host.add_drive(target, tmp_path / "drive-f")

    code, result = _job(paths, fake, "set-backup-target", backup_target=target)

    assert (code, result) == (0, {"code": "backup_target_set", "repository": "created"})
    stored = paths.state / "backup-target.json"
    assert json.loads(stored.read_text()) == {"target": target}
    assert _mode(stored) == 0o600
    assert fake.host.mounted == target


@pytest.mark.parametrize("content", ["foreign", "other-repository", "this-repository"])
def test_ac4_a_non_empty_folder_must_open_with_the_installation_password(
    installed: tuple[Paths, World, dict[str, Any]], tmp_path: Path, content: str
) -> None:
    paths, fake, _ = installed
    drive = fake.host.add_drive("G:\\Old", tmp_path / "drive-g")
    if content == "foreign":
        (drive / "holiday.jpg").write_text("photo")
    elif content == "other-repository":
        (drive / "config").write_text("restic repository")
        (drive / "keys.json").write_text(json.dumps({"ffffffff": "another password"}))
    else:
        (drive / "config").write_text("restic repository")
        password = (paths.etc / "restic-password").read_text()
        (drive / "keys.json").write_text(json.dumps({"ffffffff": password}))
    before = sorted(path.name for path in drive.iterdir())

    code, result = _job(paths, fake, "set-backup-target", backup_target="G:\\Old")

    assert _inits(fake) == 1  # only step 12's, on its empty folder
    if content == "this-repository":
        assert (code, result) == (0, {"code": "backup_target_set", "repository": "opened"})
        return
    assert (code, result["code"]) == (2, "backup_target_refused")
    assert fake.host.mounted is None and sorted(p.name for p in drive.iterdir()) == before
    assert json.loads((paths.state / "backup-target.json").read_text()) == {"target": TARGET}


def test_ac4_init_runs_only_after_mountinfo_shows_the_mount(
    installed: tuple[Paths, World, dict[str, Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The mount command answers 0 but nothing is mounted: the empty local mount point must
    # never become a repository.
    paths, fake, _ = installed
    fake.host.add_drive("H:\\Backups", tmp_path / "drive-h")
    monkeypatch.setattr(fake.host, "_mount", lambda argv: Result(0, b"", b""))

    code, result = _job(paths, fake, "set-backup-target", backup_target="H:\\Backups")

    assert (code, result["code"]) == (2, "backup_target_missing")
    assert _inits(fake) == 1


@pytest.mark.parametrize("target", ["e:\\Backups", "E:\\", "E:\\CON", "E:\\" + "a" * 198])
def test_ac4_the_install_answers_use_the_same_target_rule(
    world: tuple[Paths, World], target: str
) -> None:
    paths, fake = world
    answers = {**ANSWERS, "backup_target": target}

    code, result = run(paths, fake, {"run_id": RUN_ID, "version": "0.1.0-rc.9", "answers": answers})

    assert (code, result["code"]) == (2, "invalid_input")
    assert fake.calls == []


# AC-5: the recovery key -------------------------------------------------------------------------


def test_ac5_the_recovery_key_opens_the_repository_and_reaches_no_file_or_log(
    installed: tuple[Paths, World, dict[str, Any]],
) -> None:
    paths, fake, result = installed
    key = result["recovery_key"]
    keys = fake.host.keys()

    assert len(keys) == 2 and key in keys.values()
    assert key not in log_text(paths)
    assert CHUNKER_SECRET not in log_text(paths)
    for path in (*paths.state.rglob("*"), *paths.etc.rglob("*"), *paths.run.rglob("*")):
        if path.is_file() and path.parent != fake.host.mount_point:
            assert key.encode() not in path.read_bytes(), path


def test_ac5_new_recovery_key_adds_a_key_and_removes_the_old_one(
    installed: tuple[Paths, World, dict[str, Any]],
) -> None:
    paths, fake, first = installed
    working = (paths.etc / "restic-password").read_text()

    code, result = _job(paths, fake, "new-recovery-key")

    assert (code, result["code"]) == (0, "recovery_key_created")
    assert sorted(fake.host.keys().values()) == sorted([working, result["recovery_key"]])
    assert result["recovery_key"] != first["recovery_key"]
    assert result["recovery_key"] not in log_text(paths)
    assert CHUNKER_SECRET not in log_text(paths)


# AC-8: no change while the runner runs ----------------------------------------------------------


@pytest.fixture
def runner_lock(installed: tuple[Paths, World, dict[str, Any]]) -> Iterator[None]:
    paths, fake, _ = installed
    project = fake.host.policy_inputs[0]["project"]
    lock = paths.state / "runner" / project / "lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    status = lock.stat()
    (paths.proc / "locks").write_text(
        f"1: FLOCK  ADVISORY  WRITE 99 {os.major(status.st_dev):02x}:"
        f"{os.minor(status.st_dev):02x}:{status.st_ino} 0 EOF\n"
    )
    yield
    os.close(descriptor)


@pytest.mark.parametrize(
    ("job", "values"),
    [
        ("set-backup-target", {"backup_target": "F:\\Backups"}),
        ("new-recovery-key", {}),
        ("renew-certificate", {}),
    ],
)
@pytest.mark.parametrize("busy", ["lock", "container"])
def test_ac8_target_key_and_renewal_jobs_refuse_while_the_runner_runs(
    installed: tuple[Paths, World, dict[str, Any]],
    request: pytest.FixtureRequest,
    tmp_path: Path,
    job: str,
    values: dict[str, Any],
    busy: str,
) -> None:
    paths, fake, _ = installed
    fake.host.add_drive("F:\\Backups", tmp_path / "drive-f")
    if busy == "lock":
        request.getfixturevalue("runner_lock")
    else:
        fake.host.container = fake.host.now
    keys, target = fake.host.keys(), (paths.state / "backup-target.json").read_bytes()
    mounts = (fake.host.mounts, fake.host.unmounts)

    code, result = _job(paths, fake, job, **values)

    assert (code, result["code"]) == (2, "runner_busy")
    assert fake.host.keys() == keys
    assert (paths.state / "backup-target.json").read_bytes() == target
    assert (fake.host.mounts, fake.host.unmounts) == mounts
    assert not _commands(fake, "local_ca.py renew")


def test_w14_d5_target_and_key_jobs_report_their_steps(
    installed: tuple[Paths, World, dict[str, Any]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, fake, _ = installed
    other = "F:\\SlateOps-backups"
    fake.host.add_drive(other, tmp_path / "drives/F")
    capsys.readouterr()

    assert _job(paths, fake, "set-backup-target", backup_target=other)[0] == 0
    assert _job(paths, fake, "new-recovery-key")[0] == 0

    assert progress_lines(capsys.readouterr().err) == [
        "progress set-backup-target 1/3 unmount start",
        "progress set-backup-target 2/3 mount start",
        "progress set-backup-target 3/3 repository start",
        "progress new-recovery-key 1/2 mount start",
        "progress new-recovery-key 2/2 key start",
    ]
