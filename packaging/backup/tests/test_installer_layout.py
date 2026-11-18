"""The installer layout (plan W10b-4; TASK-0083 carries D-1 and D-2).

D-1: Caddy (UID 1000) must read the Caddyfile and ``tls/server.key``, so the installer
makes them owned by UID 1000 with mode 0600. The backup admits that owner for exactly
these two paths. D-2: the installer runs a third Compose file from a versioned bundle root
and starts 8 services; the optional config key ``compose_layout`` names that layout.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backup.backup_installation import BackupError, parse_config, run_backup
from backup.restore_installation import run_restore
from test_supabase_installation import (
    _PRODUCTION_SERVICES,
    _PRODUCTION_VOLUMES,
    BackupCommands,
    _config,
    _mock_volume_exports,
    _private,
)
from test_supabase_restore import SNAPSHOT, TARGET_INSTANCE, RestoreCommands, _digest

REPOSITORY_SUPABASE = Path(__file__).resolve().parents[3] / "infra" / "supabase"
INSTALLER_FILES = ("compose.yaml", "compose.production.yaml", "compose.installer.yaml")
INSTALLER_SERVICES = (
    "db",
    "auth",
    "storage",
    "realtime",
    "api-gw",
    "provider-volume-init",
    "api",
    "caddy",
)


@pytest.fixture
def caddy_owner(monkeypatch: pytest.MonkeyPatch) -> Callable[..., int]:
    """Make ``os.stat`` report chosen paths as owned by the Caddy UID (or another UID).

    The Caddy UID is 1000 unless the test runs as root or as UID 1000; then another UID
    stands for it, so it is never root and never the caller.
    """
    from backup import backup_installation

    uid = 1000 if os.geteuid() not in {0, 1000} else 4242
    monkeypatch.setattr(backup_installation, "_CADDY_UID", uid, raising=False)
    owners: dict[str, int] = {}
    real_stat = os.stat

    def fake_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(path, *args, **kwargs)
        owner = owners.get(os.fspath(path)) if isinstance(path, (str, os.PathLike)) else None
        if owner is None:
            return result
        fields = list(result[:10])
        fields[4] = owner
        return os.stat_result(fields)

    monkeypatch.setattr(os, "stat", fake_stat)

    def own(*paths: Path, owner: int | None = None) -> int:
        for path in paths:
            owners[str(path)] = uid if owner is None else owner
        return uid

    return own


def _another_uid(caddy_uid: int) -> int:
    """An owner that is not root, not the caller and not the Caddy UID (CI runs as 1001)."""
    return max(os.geteuid(), caddy_uid) + 1


def _production(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    config = _config(tmp_path, deployment="production")
    raw = json.loads(config.read_text(encoding="utf-8"))
    _private(Path(raw["tls_directory"]) / "server.key", "tls server key")
    return config, raw


def _rewrite(config: Path, raw: dict[str, Any]) -> None:
    config.write_text(json.dumps(raw), encoding="utf-8")
    config.chmod(0o600)


def _caddy_inputs(raw: dict[str, Any]) -> tuple[Path, Path]:
    return Path(raw["caddy_config_file"]), Path(raw["tls_directory"]) / "server.key"


# D-1 -----------------------------------------------------------------------------------


def test_the_two_caddy_inputs_owned_by_the_caddy_user_are_backed_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caddy_owner: Callable[..., int]
) -> None:
    config, raw = _production(tmp_path)
    caddy_owner(*_caddy_inputs(raw))
    commands = BackupCommands(config)
    _mock_volume_exports(monkeypatch)

    result = run_backup(config, command_runner=commands)

    assert result.snapshot_id == SNAPSHOT
    assert commands.archive_files["private/Caddyfile"] == b"Caddy private config"
    assert commands.archive_files["private/tls/server.key"] == b"tls server key"


@pytest.mark.parametrize(
    "other",
    ["provider_env_file", "app_env_file", "restic_password_file", "config", "tls-certificate"],
)
def test_the_caddy_user_is_refused_as_owner_of_every_other_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caddy_owner: Callable[..., int], other: str
) -> None:
    config, raw = _production(tmp_path)
    target = {
        "config": config,
        "tls-certificate": Path(raw["tls_directory"]) / "certificate.pem",
    }.get(other) or Path(raw[other])
    caddy_owner(*_caddy_inputs(raw), target)
    commands = BackupCommands(config)
    _mock_volume_exports(monkeypatch)

    with pytest.raises(BackupError, match="owner-controlled"):
        run_backup(config, command_runner=commands)

    assert not any(args[0] == "restic" for args, _ in commands.calls)
    assert not Path(raw["completion_marker"]).exists()


@pytest.mark.parametrize(
    ("which", "defect"),
    [
        *(
            (which, defect)
            for which in ("caddyfile", "server-key")
            for defect in ("readable-by-group", "symlink", "another-owner")
        ),
        # The TLS folder itself is checked by the unchanged directory rule, and its copy
        # handles a subfolder as a folder.
        ("caddyfile", "writable-parent"),
        ("caddyfile", "not-a-file"),
    ],
)
def test_a_caddy_input_owned_by_the_caddy_user_must_still_be_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caddy_owner: Callable[..., int],
    which: str,
    defect: str,
) -> None:
    config, raw = _production(tmp_path)
    caddyfile, server_key = _caddy_inputs(raw)
    target = caddyfile if which == "caddyfile" else server_key
    if defect == "writable-parent":
        folder = tmp_path / "caddy"
        folder.mkdir(mode=0o700)
        target = _private(folder / "Caddyfile", "Caddy private config")
        folder.chmod(0o770)
        raw["caddy_config_file"] = str(target)
        _rewrite(config, raw)
    elif defect == "readable-by-group":
        target.chmod(0o640)
    elif defect == "not-a-file":
        target.unlink()
        target.mkdir(mode=0o700)
    elif defect == "symlink":
        real = _private(tmp_path / f"real-{target.name}", "linked content")
        target.unlink()
        target.symlink_to(real)
    uid = caddy_owner(caddyfile if target is server_key else server_key)
    caddy_owner(target, owner=_another_uid(uid) if defect == "another-owner" else None)
    commands = BackupCommands(config)
    _mock_volume_exports(monkeypatch)

    with pytest.raises(BackupError, match="owner-controlled|symlink|filesystem type"):
        run_backup(config, command_runner=commands)

    assert not any(args[0] == "restic" for args, _ in commands.calls)


def _installer_tls(tmp_path: Path) -> tuple[Path, dict[str, Any], Path]:
    """The installer's exact ``tls/`` files: ``server.crt`` written by ``local_ca.py``
    (owner root, mode 0644, a public chain) and ``server.key`` (owned by Caddy, 0600)."""
    config, raw = _production(tmp_path)
    tls = Path(raw["tls_directory"])
    (tls / "certificate.pem").unlink()
    certificate = tls / "server.crt"
    certificate.write_text("public leaf and intermediate", encoding="utf-8")
    certificate.chmod(0o644)
    tls.chmod(0o755)
    return config, raw, certificate


def test_the_installers_exact_tls_files_are_backed_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caddy_owner: Callable[..., int]
) -> None:
    config, raw, _ = _installer_tls(tmp_path)
    caddy_owner(*_caddy_inputs(raw))
    commands = BackupCommands(config)
    _mock_volume_exports(monkeypatch)

    run_backup(config, command_runner=commands)

    assert commands.archive_files["private/tls/server.crt"] == b"public leaf and intermediate"
    assert commands.archive_files["private/tls/server.key"] == b"tls server key"


@pytest.mark.parametrize(
    "defect",
    ["writable-by-group", "writable-by-others", "caddy-owner", "symlink", "other-public-file"],
)
def test_only_a_read_only_server_certificate_may_be_readable_by_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caddy_owner: Callable[..., int], defect: str
) -> None:
    config, raw, certificate = _installer_tls(tmp_path)
    caddy_owner(*_caddy_inputs(raw))
    if defect == "writable-by-group":
        certificate.chmod(0o664)
    elif defect == "writable-by-others":
        certificate.chmod(0o646)
    elif defect == "caddy-owner":
        caddy_owner(certificate)
    elif defect == "symlink":
        real = tmp_path / "real-server.crt"
        real.write_bytes(certificate.read_bytes())
        real.chmod(0o644)
        certificate.unlink()
        certificate.symlink_to(real)
    else:
        other = certificate.with_name("chain.pem")
        other.write_text("another public file", encoding="utf-8")
        other.chmod(0o644)
    commands = BackupCommands(config)
    _mock_volume_exports(monkeypatch)

    with pytest.raises(BackupError, match="owner-controlled|symlink"):
        run_backup(config, command_runner=commands)

    assert not any(args[0] == "restic" for args, _ in commands.calls)


@pytest.mark.parametrize("defect", ["symlink", "not-a-file"])
def test_the_certificate_rule_itself_refuses_a_symlink_or_a_non_file(
    tmp_path: Path, defect: str
) -> None:
    """The admission function keeps its own guards; ``_copy_directory`` also checks both."""
    from backup.backup_installation import _private_input

    certificate = tmp_path / "server.crt"
    if defect == "symlink":
        real = tmp_path / "real.crt"
        real.write_text("public chain", encoding="utf-8")
        real.chmod(0o644)
        certificate.symlink_to(real)
    else:
        certificate.mkdir(mode=0o755)

    with pytest.raises(BackupError, match="symlink|filesystem type"):
        _private_input(certificate, "server.crt", frozenset(), frozenset({certificate}))


def test_a_caller_owned_caddyfile_keeps_the_old_rule_when_caddy_is_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup that runs as the Caddy UID keeps today's rule: no parent-folder check."""
    from backup import backup_installation

    monkeypatch.setattr(backup_installation, "_CADDY_UID", os.geteuid())
    config, raw = _production(tmp_path)
    folder = tmp_path / "caddy"
    folder.mkdir(mode=0o700)
    caddyfile = _private(folder / "Caddyfile", "Caddy private config")
    folder.chmod(0o770)
    raw["caddy_config_file"] = str(caddyfile)
    _rewrite(config, raw)
    commands = BackupCommands(config)
    _mock_volume_exports(monkeypatch)

    run_backup(config, command_runner=commands)

    assert commands.archive_files["private/Caddyfile"] == b"Caddy private config"


# D-2 -----------------------------------------------------------------------------------


def _bundle_root(tmp_path: Path) -> Path:
    """A versioned engine bundle root, as the installer unpacks it (no ``templates/``)."""
    root = tmp_path / "opt" / "slateops" / "engine" / "0.1.0-rc.3" / "infra" / "supabase"
    root.mkdir(parents=True)
    for name in INSTALLER_FILES:
        shutil.copyfile(REPOSITORY_SUPABASE / name, root / name)
    shutil.copytree(REPOSITORY_SUPABASE / "upstream", root / "upstream")
    for path in (root, *root.parents):
        if path == tmp_path:
            break
        path.chmod(0o755)
    return root


def _installer(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    config, raw = _production(tmp_path)
    raw["compose_layout"] = "installer"
    raw["compose_root"] = str(_bundle_root(tmp_path))
    _rewrite(config, raw)
    return config, raw


def _installer_commands(config: Path, services: tuple[str, ...]) -> BackupCommands:
    commands = BackupCommands(config)
    commands.services = services
    commands.images = {
        service: f"example.invalid/{service}@sha256:{service.encode().hex():0<64}"
        for service in services
    }
    return commands


def test_an_installer_config_names_the_installer_compose_layout(tmp_path: Path) -> None:
    config, raw = _installer(tmp_path)

    parsed = parse_config(config)

    root = Path(raw["compose_root"])
    assert parsed.compose_files == tuple(root / name for name in INSTALLER_FILES)


@pytest.mark.parametrize(
    ("deployment", "layout"),
    [
        ("production", "custom"),
        ("production", None),
        ("production", 1),
        ("development", "installer"),
    ],
)
def test_the_compose_layout_takes_only_installer_and_only_for_production(
    tmp_path: Path, deployment: str, layout: object
) -> None:
    config = _config(tmp_path, deployment=deployment)
    raw = json.loads(config.read_text(encoding="utf-8"))
    raw["compose_layout"] = layout
    _rewrite(config, raw)

    with pytest.raises(BackupError, match="compose_layout"):
        parse_config(config)


def test_an_installer_backup_uses_the_three_compose_files_of_its_bundle_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, raw = _installer(tmp_path)
    commands = _installer_commands(config, INSTALLER_SERVICES)
    _mock_volume_exports(monkeypatch)

    run_backup(config, command_runner=commands)

    root = Path(raw["compose_root"])
    compose = next(args for args, _ in commands.calls if args[:2] == ["docker", "compose"])
    files = [compose[index + 1] for index, value in enumerate(compose) if value == "-f"]
    assert files == [str(root / name) for name in INSTALLER_FILES]
    bundled = {name for name in commands.archive_files if name.startswith("compose/")}
    assert {f"compose/{name}" for name in INSTALLER_FILES} <= bundled
    assert any(name.startswith("compose/upstream/") for name in bundled)
    assert not any(name.startswith("compose/templates/") for name in bundled)
    manifest = json.loads(commands.snapshot_manifest or b"{}")
    assert sorted(manifest["images"]) == sorted(INSTALLER_SERVICES)


@pytest.mark.parametrize(
    ("layout", "services"),
    [
        ("installer", (*INSTALLER_SERVICES, "studio")),
        ("current", tuple(name for name in _PRODUCTION_SERVICES if name != "studio")),
    ],
)
def test_each_layout_refuses_the_other_layouts_service_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str, services: tuple[str, ...]
) -> None:
    config = _installer(tmp_path)[0] if layout == "installer" else _production(tmp_path)[0]
    commands = _installer_commands(config, services)
    _mock_volume_exports(monkeypatch)

    with pytest.raises(BackupError, match="source project"):
        run_backup(config, command_runner=commands)

    assert not any(args[0] == "restic" for args, _ in commands.calls)


def _installer_bundle(tmp_path: Path, raw: dict[str, Any], *, without: str | None) -> Path:
    bundle = tmp_path / "snapshot-source" / "slateops-supabase-backup-test" / "bundle"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        member = tarfile.TarInfo("object")
        member.size = 4
        tar.addfile(member, io.BytesIO(b"data"))
    for logical in _PRODUCTION_VOLUMES:
        path = bundle / "volumes" / f"{logical}.tar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(archive.getvalue())
    (bundle / "private").mkdir()
    for name, source in (
        ("provider.env", raw["provider_env_file"]),
        ("app.env", raw["app_env_file"]),
        ("Caddyfile", raw["caddy_config_file"]),
    ):
        (bundle / "private" / name).write_bytes(Path(source).read_bytes())
    root = Path(raw["compose_root"])
    for name in INSTALLER_FILES:
        if name != without:
            (bundle / "compose").mkdir(exist_ok=True)
            shutil.copyfile(root / name, bundle / "compose" / name)
    shutil.copytree(root / "upstream", bundle / "compose" / "upstream")
    files = {
        path.relative_to(bundle).as_posix(): {"sha256": _digest(path), "bytes": path.stat().st_size}
        for path in bundle.rglob("*")
        if path.is_file()
    }
    manifest = {
        "format_version": 3,
        "source_installation_id": raw["installation_id"],
        "source_project": raw["project_name"],
        "deployment": "production",
        "created_at": "2026-11-17T00:00:00+00:00",
        "images": {
            "db": {"ref": "supabase/postgres@sha256:" + "a" * 64, "id": "sha256:" + "b" * 64}
        },
        "volumes": {name: f"{raw['project_name']}_{name}" for name in _PRODUCTION_VOLUMES},
        "files": files,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


@pytest.mark.parametrize("without", [None, "compose.installer.yaml"])
def test_an_installer_restore_expects_the_three_compose_files(
    tmp_path: Path, without: str | None
) -> None:
    config, raw = _installer(tmp_path)
    commands = RestoreCommands(_installer_bundle(tmp_path, raw, without=without))

    def inspect() -> object:
        return run_restore(
            config, SNAPSHOT, "client-b", tmp_path / "target", TARGET_INSTANCE,
            command_runner=commands,
        )

    if without is None:
        assert getattr(inspect(), "executed", None) is False
    else:
        with pytest.raises(BackupError, match="missing or has unlisted files"):
            inspect()
