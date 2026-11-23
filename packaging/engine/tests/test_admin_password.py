"""``admin-password``: the first administrator's password from the settings program (TASK-0097
AC-B8, DEC-0042: a person can sign in again without email)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.core import Paths
from engine.runner import ENVIRONMENT

from .helpers import log_text, progress_lines
from .test_install import ANSWERS, EMAIL, USERNAME, World, _commands, _setup, run

RUN = "maintenance-20261123T110000Z-ap11cd"
NEW_PASSWORD = "New front " + 'pa$$ "q" #9'


@pytest.fixture
def installed(tmp_path: Path) -> tuple[Paths, World]:
    paths, fake = _setup(tmp_path)
    code, result = run(paths, fake)
    assert code == 0, result
    fake.calls.clear()
    fake.environments.clear()
    return paths, fake


def _reset(paths: Paths, fake: World, password: Any = NEW_PASSWORD) -> tuple[int, dict[str, Any]]:
    request: dict[str, Any] = {"run_id": RUN}
    if password is not None:
        request["admin_password"] = password
    return run(paths, fake, request, job="admin-password")


def test_ac_b8_the_password_reaches_the_operation_only_on_its_standard_input(
    installed: tuple[Paths, World],
) -> None:
    paths, fake = installed

    code, result = _reset(paths, fake)

    assert (code, result) == (0, {"code": "reset"})
    [(argv, env)] = [(a, e) for a, e in zip(fake.calls, fake.environments, strict=True)
                     if "operations/reset_admin_password.py" in a]  # fmt: skip
    project = json.loads(paths.installation.read_text())["project"]
    assert argv[:4] == ["docker", "run", "--rm", "--interactive"]
    assert argv[argv.index("--network") + 1] == f"{project}_provider"
    assert argv[argv.index("--env-file") + 1] == str(paths.etc / "app.env")
    assert argv[argv.index("operations/reset_admin_password.py") :] == [
        "operations/reset_admin_password.py", "--confirm", "--json", "--password-stdin",
    ]  # fmt: skip
    assert env == {**ENVIRONMENT, "ADMIN_EMAIL": EMAIL, "ADMIN_USERNAME": USERNAME}
    assert fake.reset_stdin == [NEW_PASSWORD.encode() + b"\n"]
    assert NEW_PASSWORD not in json.dumps(fake.calls) + json.dumps(fake.environments)
    root = paths.etc.parent.parent
    for path in root.rglob("*"):
        if path.is_file():
            assert NEW_PASSWORD.encode() not in path.read_bytes(), path


@pytest.mark.parametrize(
    "password",
    [
        pytest.param(None, id="missing"),
        pytest.param("eleven-char", id="shorter-than-12"),
        pytest.param("é" * 37, id="more-than-72-bytes"),
        pytest.param("first line\nsecond line", id="line-break"),
        pytest.param("tab\tinside-password", id="control-character"),
        pytest.param(123456789012, id="not-text"),
    ],
)
def test_ac_b8_a_password_outside_the_rule_is_refused_before_any_command(
    installed: tuple[Paths, World], password: Any
) -> None:
    paths, fake = installed

    code, result = _reset(paths, fake, password)

    assert (code, result["code"]) == (2, "invalid_input")
    assert fake.calls == []


def test_ac_b8_before_the_install_nothing_runs(tmp_path: Path) -> None:
    paths, fake = _setup(tmp_path)

    code, result = _reset(paths, fake)

    assert (code, result["code"]) == (2, "not_installed")
    assert fake.calls == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ((2, '{"code":"admin_missing"}'), (2, "admin_missing")),
        ((3, '{"code":"reset_failed"}'), (3, "reset_failed")),
        ((2, "not json"), (3, "reset_failed")),
        ((0, '{"result":"sent"}'), (3, "reset_failed")),
    ],
    ids=["admin-missing", "failed", "no-json", "other-result"],
)
def test_ac_b8_the_operation_result_passes_through(
    installed: tuple[Paths, World], answer: tuple[int, str], expected: tuple[int, str]
) -> None:
    paths, fake = installed
    fake.reset_answer = answer

    code, result = _reset(paths, fake)

    assert (code, result["code"]) == expected


def test_ac_b8_a_password_that_the_operation_prints_never_reaches_the_log(
    installed: tuple[Paths, World],
) -> None:
    paths, fake = installed
    fake.reset_answer = (3, f"failed for {NEW_PASSWORD} and {EMAIL}")

    code, _ = _reset(paths, fake)

    assert code == 3
    logs = log_text(paths)
    assert "failed for" in logs
    for value in (NEW_PASSWORD, EMAIL, ANSWERS["admin_username"]):
        assert value not in logs, value


def test_ac_b8_admin_password_reports_its_step(
    installed: tuple[Paths, World], capsys: pytest.CaptureFixture[str]
) -> None:
    paths, fake = installed
    capsys.readouterr()

    assert _reset(paths, fake)[0] == 0

    assert progress_lines(capsys.readouterr().err) == ["progress admin-password 1/1 reset start"]
    assert _commands(fake, "reset_admin_password.py")
