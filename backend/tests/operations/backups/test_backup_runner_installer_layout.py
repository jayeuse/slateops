"""The runner on the installer layout (plan W10b-4; TASK-0083 carries D-1 and D-2)."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from operations import backup_runner
from operations.backups.host import Host, RunnerError, physical_archive
from tests.operations.backups.backup_runner_fixtures import (
    NOW,
    SyntheticCommands,
    execute,
    private_file,
    runner_config,
    successful_archive,
)
from tests.repository import REPOSITORY_ROOT

INSTALLER_SERVICES = {
    "db",
    "auth",
    "storage",
    "realtime",
    "api-gw",
    "provider-volume-init",
    "api",
    "caddy",
}
INSTALLER_FILES = ("compose.yaml", "compose.production.yaml", "compose.installer.yaml")


def _installer(tmp_path: Path, *, services: set[str]) -> tuple[Path, Path, SyntheticCommands]:
    config, state = runner_config(tmp_path)
    raw = json.loads(config.read_text())
    raw["compose_layout"] = "installer"
    private_file(config, json.dumps(raw))
    commands = SyntheticCommands(config)
    commands.containers = [commands.container(name) for name in sorted(services)]
    commands.original_running = services - {"provider-volume-init", "studio"}
    return config, state, commands


def _refuses_before_claim(config: Path, state: Path, commands: SyntheticCommands) -> None:
    archived: list[dict[str, Any]] = []

    def refuse_archive(host: Host, journal: dict[str, Any]) -> None:
        archived.append(journal)
        raise AssertionError("an inadmissible source must be refused before the archive")

    with pytest.raises(RunnerError, match="admission_failed"):
        backup_runner.run_once(
            config, state, command_runner=commands, archive_runner=refuse_archive, now=lambda: NOW
        )
    assert not commands.operations
    assert not any("stop" in args for args, _ in commands.calls)
    assert not archived


def test_an_installer_backup_admits_its_eight_services_and_uses_three_compose_files(
    tmp_path: Path,
) -> None:
    config, state, commands = _installer(tmp_path, services=INSTALLER_SERVICES)

    result = execute(config, state, commands, archive_runner=successful_archive)

    assert result["state"] == "succeeded"
    running = {
        item["Config"]["Labels"]["com.docker.compose.service"]
        for item in commands.containers
        if item["State"]["Status"] == "running"
    }
    assert running == commands.original_running
    compose = [args for args, _ in commands.calls if args[:2] == ["docker", "compose"]]
    expected = [str(REPOSITORY_ROOT / "infra" / "supabase" / name) for name in INSTALLER_FILES]
    assert compose
    assert all(
        [args[index + 1] for index, value in enumerate(args) if value == "-f"] == expected
        for args in compose
    )


def test_an_installer_project_with_a_studio_container_is_refused(tmp_path: Path) -> None:
    config, state, commands = _installer(tmp_path, services=INSTALLER_SERVICES | {"studio"})

    _refuses_before_claim(config, state, commands)


@pytest.mark.parametrize(
    ("owned", "admitted"),
    [(("caddy_config_file",), True), (("caddy_config_file", "app_env_file"), False)],
)
def test_the_runner_admits_the_caddyfile_owned_by_the_caddy_user_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owned: tuple[str, ...], admitted: bool
) -> None:
    config, state = runner_config(tmp_path)
    raw = json.loads(config.read_text())
    commands = SyntheticCommands(config)
    uid = 1000 if os.geteuid() not in {0, 1000} else 4242
    monkeypatch.setattr(physical_archive(), "_CADDY_UID", uid, raising=False)
    paths = {raw[key] for key in owned}
    real_stat = os.stat

    def fake_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(path, *args, **kwargs)
        if isinstance(path, (str, os.PathLike)) and os.fspath(path) in paths:
            fields = list(result[:10])
            fields[4] = uid
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "stat", fake_stat)

    if admitted:
        assert execute(config, state, commands)["state"] == "succeeded"
    else:
        _refuses_before_claim(config, state, commands)
