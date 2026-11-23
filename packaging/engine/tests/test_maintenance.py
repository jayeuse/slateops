"""``prepare-uninstall``, ``set-email``, the ``status`` instance ID and ``set-backup-target``
after a failed first backup (TASK-0096 E-1 to E-4; plan 9.1, 9.2, 9.3; TASK-0094 F5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine import smtp_env
from engine.core import Paths, private_dir

from .helpers import log_text, progress_lines
from .test_install import ANSWERS, World, _setup, run

MAINTENANCE = "maintenance-20261117T120000Z-ab12cd"
UNINSTALL = "uninstall-20261117T120000Z-ab12cd"
STATUS = {"run_id": MAINTENANCE, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}
NEW_PASSWORD = "new " + 'app-pa$$ "w" #9'


@pytest.fixture
def installed(tmp_path: Path) -> tuple[Paths, World]:
    paths, fake = _setup(tmp_path)
    code, result = run(paths, fake)
    assert code == 0, result
    fake.calls.clear()
    return paths, fake


def _job(paths: Paths, fake: World, job: str, run_id: str = MAINTENANCE) -> dict[str, Any]:
    code, result = run(paths, fake, {"run_id": run_id}, job=job)
    return {"exit": code, **result}


# E-1 -----------------------------------------------------------------------------------------


def test_e1_prepare_uninstall_gives_the_kept_values_then_stops_docker_not_the_containers(
    installed: tuple[Paths, World],
) -> None:
    paths, fake = installed
    installation = json.loads(paths.installation.read_text())

    result = _job(paths, fake, "prepare-uninstall", UNINSTALL)

    assert result == {
        "exit": 0,
        "code": "ready_for_uninstall",
        "version": installation["version"],
        "instance_id": installation["instance_id"],
        "business_name": ANSWERS["business_name"],
        "public_host": ANSWERS["public_host"],
    }
    stops = [argv for argv in fake.calls if argv[:2] == ["systemctl", "stop"]]
    assert stops == [
        ["systemctl", "stop", "slateops-runner.timer"],
        ["systemctl", "stop", "docker.socket", "docker.service"],
    ]
    assert not [argv for argv in fake.calls if argv[:2] == ["docker", "compose"] and "stop" in argv]


# E-2 -----------------------------------------------------------------------------------------


def test_e2_status_reports_the_instance_id_of_the_installation(
    installed: tuple[Paths, World],
) -> None:
    paths, fake = installed

    code, result = run(paths, fake, STATUS, job="status")

    assert (code, result["instance_id"]) == (
        0,
        json.loads(paths.installation.read_text())["instance_id"],
    )


# E-3 -----------------------------------------------------------------------------------------


def _stage_new_email(paths: Paths) -> dict[str, str]:
    values = {
        "SMTP_HOST": "smtp.office365.test",
        "SMTP_PORT": "587",
        "SMTP_ADMIN_EMAIL": "frontdesk" + "@office365.test",
        "SMTP_USER": "frontdesk" + "@office365.test",
        "SMTP_PASS": NEW_PASSWORD,
        "SMTP_SENDER_NAME": "Front Desk Dental",
    }
    private_dir(paths.staged_smtp.parent)
    paths.staged_smtp.write_text(smtp_env.render(values))
    return values


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def test_ac_b4_set_email_adds_the_staged_values_and_recreates_auth_then_api(
    installed: tuple[Paths, World],
) -> None:
    # DEC-0041: the install wrote no SMTP line; set-email adds the six and both Auth and the
    # API (which reads SMTP_* from Compose at creation) start again with them.
    paths, fake = installed
    before = _lines(paths.etc / "provider.env")
    assert [line for line in before if line.startswith("SMTP_")] == []
    values = _stage_new_email(paths)

    result = _job(paths, fake, "set-email")

    assert result == {"exit": 0, "code": "email_set"}
    after = _lines(paths.etc / "provider.env")
    expected = smtp_env.parse(smtp_env.render(values))
    written = [line for line in after if line.startswith("SMTP_")]
    assert smtp_env.parse("\n".join(written) + "\n") == expected
    assert [line for line in after if not line.startswith("SMTP_")] == before
    assert not paths.staged_smtp.exists()
    ups = [argv for argv in fake.calls if argv[:2] == ["docker", "compose"] and "up" in argv]
    assert [up[up.index("up") :] for up in ups] == [
        ["up", "--detach", "--pull", "never", "--no-deps", "--force-recreate", "auth"],
        ["up", "--detach", "--pull", "never", "--no-deps", "--force-recreate", "api"],
    ]
    assert NEW_PASSWORD not in log_text(paths)


def test_ac_b4_set_email_again_replaces_the_email_settings_in_place(
    installed: tuple[Paths, World],
) -> None:
    paths, fake = installed
    _stage_new_email(paths)
    assert _job(paths, fake, "set-email")["exit"] == 0
    first = _lines(paths.etc / "provider.env")
    values = {**_stage_new_email(paths), "SMTP_HOST": "smtp.gmail.test"}
    private_dir(paths.staged_smtp.parent)
    paths.staged_smtp.write_text(smtp_env.render(values))

    assert _job(paths, fake, "set-email")["exit"] == 0

    after = _lines(paths.etc / "provider.env")
    assert len(after) == len(first)
    assert "SMTP_HOST=smtp.gmail.test" in after
    assert [line.split("=", 1)[0] for line in after] == [line.split("=", 1)[0] for line in first]


def test_e3_set_email_without_staged_values_changes_nothing(
    installed: tuple[Paths, World],
) -> None:
    paths, fake = installed
    before = (paths.etc / "provider.env").read_bytes()

    result = _job(paths, fake, "set-email")

    assert (result["exit"], result["code"]) == (2, "smtp_not_staged")
    assert (paths.etc / "provider.env").read_bytes() == before
    assert not [argv for argv in fake.calls if argv[:2] == ["docker", "compose"]]


# E-4 -----------------------------------------------------------------------------------------


def test_e4_after_a_failed_first_backup_another_drive_is_set_and_the_install_completes_on_it(
    tmp_path: Path,
) -> None:
    paths, fake = _setup(tmp_path)
    fake.host.first_backup_fails = True
    assert run(paths, fake)[1]["code"] == "first_backup_failed"
    fake.host.first_backup_fails = False
    other = "F:\\SlateOps-backups"
    fake.host.add_drive(other, tmp_path / "drives/F")

    code, result = run(paths, fake, {"run_id": MAINTENANCE, "backup_target": other},
                       job="set-backup-target")  # fmt: skip

    assert (code, result["code"]) == (0, "backup_target_set")
    version = json.loads(paths.journal.read_text())["version"]
    code, result = run(
        paths, fake, {"run_id": "install-20261117T121500Z-ab12cd", "version": version}
    )
    assert (code, result["code"], result["backup_setup"]) == (0, "installed", "ready")
    assert fake.host.mounted == other and fake.host.snapshots == 1


def test_w14_d5_set_email_and_prepare_uninstall_report_their_steps(
    installed: tuple[Paths, World], capsys: pytest.CaptureFixture[str]
) -> None:
    paths, fake = installed
    _stage_new_email(paths)
    capsys.readouterr()

    assert _job(paths, fake, "set-email")["exit"] == 0
    assert _job(paths, fake, "prepare-uninstall", UNINSTALL)["exit"] == 0

    assert progress_lines(capsys.readouterr().err) == [
        "progress set-email 1/2 write start",
        "progress set-email 2/2 auth start",
        "progress prepare-uninstall 1/2 stop_timer start",
        "progress prepare-uninstall 2/2 stop_docker start",
    ]
