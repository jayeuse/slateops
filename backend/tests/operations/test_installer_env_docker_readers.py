"""W2-2 (TASK-0081): each real reader of each rendered env file sees the exact bytes.

Readers per file (contract A-2): provider.env through Compose ``--env-file`` interpolation;
app.env through Compose ``env_file:`` and ``docker run --env-file``; the provisioning env
through ``docker run --env-file``. Each reader prints ``/proc/self/environ`` from a container
with no network. Needs Docker; the digest-pinned reader image is pulled when missing.
"""

import importlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# Needs a Docker daemon, so it runs in the integration lanes, not the unit lane (D-2).
pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "packaging" / "engine" / "templates"
KEYS_COMMAND = ROOT / "backend" / "operations" / "supabase_keys.py"
# alpine:latest multi-architecture index on 2026-11-16; about 3 MB.
READER_IMAGE = "alpine@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a"
CUSTOMER_TEXT = {
    "SMTP_PASS": " a$${b} $x #c 'q' \"dq\" \\n back\\ ",
    "SMTP_USER": " spaced user ",
    "SMTP_SENDER_NAME": 'Front "Desk" $HOME',
    "SMTP_ADMIN_EMAIL": "o$f#fice@example.test",
}
ANSWERS = {
    "PUBLIC_HOST": "frontdesk.local",
    "SLATEOPS_SERVER_IMAGE": "ghcr.io/example/slateops-server@sha256:" + "a" * 64,
    "SLATEOPS_CADDY_IMAGE": "ghcr.io/example/slateops-caddy@sha256:" + "b" * 64,
    "SLATEOPS_APP_PRIVATE_SUBNET": "172.31.248.0/28",
    "SLATEOPS_BACKUP_EXPORT_ROOT": "/mnt/slateops-backup/backup-exports",
    "SMTP_HOST": "smtp.example.test",
    "SMTP_PORT": "587",
    **CUSTOMER_TEXT,
}


def docker(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    # Compose lets the calling environment override --env-file values, so the readers run
    # with only what the Docker CLI needs (the engine must do the same).
    environment = {
        name: value for name, value in os.environ.items()
        if name in {"PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT"}
    }
    return subprocess.run(
        ["docker", *arguments], capture_output=True, check=False, timeout=120, cwd=cwd,
        env=environment,
    )


def environ(output: bytes) -> dict[str, str]:
    pairs = (item.decode("utf-8").partition("=") for item in output.split(b"\0") if item)
    return {name: value for name, _separator, value in pairs}


def literal_lines(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _separator, value = line.partition("=")
            values[name] = value
    return values


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    assert shutil.which("docker") is not None, "the W2-2 reader test needs Docker"
    assert docker("info").returncode == 0, "the W2-2 reader test needs a running Docker daemon"
    directory = tmp_path_factory.mktemp("installer-env")
    generated = directory / "generated.env"
    completed = subprocess.run(
        [
            sys.executable, str(KEYS_COMMAND), "--format", "docker", "--output", str(generated),
            "--restic-password-file", str(directory / "restic-password"),
        ],
        capture_output=True, check=False, timeout=60,
    )
    assert completed.returncode == 0
    sys.path.insert(0, str(ROOT / "packaging"))
    render = importlib.import_module("engine.env_templates").render
    values = {**literal_lines(generated), **ANSWERS}
    for name in ("provider.env", "app.env", "provision.env"):
        text = render((TEMPLATES / name).read_text(encoding="utf-8"), values)
        (directory / name).write_text(text, encoding="utf-8")
    return {"directory": directory, "values": values}


def docker_run_reads(path: Path) -> dict[str, str]:
    completed = docker(
        "run", "--rm", "--pull=missing", "--network", "none", "--env-file", str(path),
        READER_IMAGE, "cat", "/proc/self/environ",
    )
    assert completed.returncode == 0, completed.stderr.decode()
    return environ(completed.stdout)


def compose_run_reads(directory: Path, service: dict[str, Any], *options: str) -> dict[str, str]:
    project = f"slateops-w2-reader-{secrets.token_hex(4)}"
    compose_file = directory / f"{project}.yaml"
    service = {
        "image": READER_IMAGE, "pull_policy": "missing", "network_mode": "none",
        "command": ["cat", "/proc/self/environ"], **service,
    }
    compose_file.write_text(json.dumps({"services": {"reader": service}}), encoding="utf-8")
    base = ("compose", "--project-name", project, "-f", str(compose_file), *options)
    try:
        completed = docker(*base, "run", "--rm", "-T", "reader", cwd=directory)
        assert completed.returncode == 0, completed.stderr.decode()
        return environ(completed.stdout)
    finally:
        docker(*base, "down", "--remove-orphans", cwd=directory)
        compose_file.unlink()


def test_w2_2_app_env_reads_the_same_bytes_in_docker_run_and_compose_env_file(files) -> None:
    directory = files["directory"]
    expected = literal_lines(directory / "app.env")
    assert len(expected) == 33
    by_run = docker_run_reads(directory / "app.env")
    by_compose = compose_run_reads(
        directory, {"env_file": [{"path": str(directory / "app.env"), "required": True}]},
    )
    assert {name: by_run.get(name) for name in expected} == expected
    assert {name: by_compose.get(name) for name in expected} == expected
    assert expected["REALTIME_TOKEN_SIGNING_KEY"] == files["values"]["REALTIME_TOKEN_SIGNING_KEY"]


def test_w2_2_provisioning_env_reads_the_same_bytes_in_docker_run(files) -> None:
    directory = files["directory"]
    expected = literal_lines(directory / "provision.env")
    by_run = docker_run_reads(directory / "provision.env")
    assert {name: by_run.get(name) for name in expected} == expected


def test_w2_2_p_2_p_3_provider_env_reads_exact_values_through_compose_interpolation(
    files,
) -> None:
    directory = files["directory"]
    written = literal_lines(directory / "provider.env")
    expected = {
        name: CUSTOMER_TEXT.get(name, value) for name, value in written.items()
    }
    assert {name for name, value in written.items() if value.startswith('"')} == set(
        CUSTOMER_TEXT
    )
    by_compose = compose_run_reads(
        directory,
        {"environment": {name: "${" + name + "}" for name in written}},
        "--env-file", str(directory / "provider.env"),
    )
    assert {name: by_compose.get(name) for name in expected} == expected
    for name in ("JWT_KEYS", "JWT_JWKS"):
        assert by_compose[name] == files["values"][name]


def test_w2_2_generator_output_reads_the_same_bytes_in_both_readers(files) -> None:
    directory = files["directory"]
    expected = literal_lines(directory / "generated.env")
    assert len(expected) == 21
    by_run = docker_run_reads(directory / "generated.env")
    by_compose = compose_run_reads(
        directory,
        {"environment": {name: "${" + name + "}" for name in expected}},
        "--env-file", str(directory / "generated.env"),
    )
    assert {name: by_run.get(name) for name in expected} == expected
    assert {name: by_compose.get(name) for name in expected} == expected
