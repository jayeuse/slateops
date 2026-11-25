"""``stop`` and ``start``: the owner's Stop and Start in the settings program (owner request
2026-11-25). The fake world is the update world."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import power

from .test_update import TARGET, Installed

RUN = "maintenance-20261125T120000Z-ab12cd"


@pytest.fixture
def machine(tmp_path: Path) -> Installed:
    return Installed(tmp_path)


def _systemctl(machine: Installed) -> list[list[str]]:
    return [argv for argv in machine.fake.calls if argv[:1] == ["systemctl"]]


def test_stop_stops_the_backup_timer_then_docker_and_says_so_in_status(
    machine: Installed,
) -> None:
    code, result = machine.job("stop", {"run_id": RUN})

    assert (code, result) == (0, {"code": "stopped"})
    calls = _systemctl(machine)
    assert ["systemctl", "stop", "slateops-runner.timer"] in calls
    assert ["systemctl", "stop", "docker.socket", "docker.service"] in calls
    assert calls.index(["systemctl", "stop", "slateops-runner.timer"]) < calls.index(
        ["systemctl", "stop", "docker.socket", "docker.service"]
    )
    # No container is stopped one by one: Docker starts them again at the next Linux start.
    compose_stops = [
        argv for argv in machine.fake.calls if "compose" in argv[:2] and "stop" in argv
    ]
    assert not compose_stops
    assert power.stopped(machine.paths)


def test_a_stopped_installation_refuses_restore_and_update(machine: Installed) -> None:
    machine.job("stop", {"run_id": RUN})
    machine.stage()

    restore = machine.job("restore", {"run_id": "maintenance-20261125T120100Z-ab12cd"})
    updated = machine.update(TARGET)

    assert (restore[0], restore[1]["code"]) == (2, "stopped")
    assert (updated[0], updated[1]["code"]) == (2, "stopped")


def test_start_starts_docker_and_the_timer_then_waits_for_the_services(
    machine: Installed,
) -> None:
    machine.job("stop", {"run_id": RUN})
    machine.fake.calls.clear()

    code, result = machine.job("start", {"run_id": "maintenance-20261125T120200Z-ab12cd"})

    assert (code, result) == (0, {"code": "started"})
    calls = _systemctl(machine)
    assert calls[:2] == [
        ["systemctl", "start", "docker.socket", "docker.service"],
        ["systemctl", "start", "slateops-runner.timer"],
    ]
    assert not power.stopped(machine.paths)
    assert machine.index("caddy") > machine.index(" api")  # caddy last, after the api
