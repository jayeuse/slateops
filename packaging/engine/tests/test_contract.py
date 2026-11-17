"""The job contract and the run log (plan 3.2 rules 1-2, 6.1, 10.1; AC-J1 to AC-J5, AC-L1 to
AC-L3, AC-L5)."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest

from engine import cli
from engine.context import Context
from engine.logs import KEEP_MARK, RunLog, cap
from engine.redaction import Redactor
from engine.runner import ENVIRONMENT, Runner

from .helpers import RUN_ID, Clock, Script, call, deps, fail, log_text, make_paths, ok

STATUS = {"run_id": RUN_ID, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}
LINE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z "
    r"install-20261117T101500Z-ab12cd [a-z-]+\.\d{2}\.[a-z]+ (INFO|WARN|ERROR) "
)


@pytest.mark.parametrize("argv", [["rm"], ["install"], ["status", "extra"], [], ["STATUS"]])
def test_ac_j1_only_allow_listed_jobs_run(tmp_path: Path, argv: list[str]) -> None:
    paths = make_paths(tmp_path)

    code, payload, _ = call(argv, STATUS, deps(paths))

    assert (code, payload) == (2, {"code": "job_unknown", "message_key": "engine.job_unknown"})
    assert not paths.logs.exists()
    assert not paths.state.exists()


@pytest.mark.parametrize(
    "request_data",
    [
        b"{" + b" " * (64 * 1024) + b"}",
        b"not json",
        b"[1, 2]",
        b'{"run_id": "install-20261117T101500Z-ab12cd"}',
        {**STATUS, "extra": "x"},
        {**STATUS, "wsl_version": "2.6.1.0; rm"},
        {**STATUS, "windows_part_version": 1},
    ],
    ids=["too-big", "not-json", "not-object", "missing-key", "unknown-key", "bad-wsl", "bad-type"],
)
def test_ac_j2_input_is_one_bounded_json_object_with_known_keys(
    tmp_path: Path, request_data: bytes | dict[str, object]
) -> None:
    code, payload, _ = call(["status"], request_data, deps(make_paths(tmp_path)))

    assert (code, payload) == (2, {"code": "invalid_input", "message_key": "status.invalid_input"})


@pytest.mark.parametrize(
    "run_id",
    [
        "install-20261117T101500Z-AB12CD",
        "deploy-20261117T101500Z-ab12cd",
        "install-20261117T101500Z-ab12c",
        "install-20261117T101500Z-ab12cd\n",
        "../install-20261117T101500Z-ab12cd",
        "install-2026-11-17T10:15:00Z-ab12cd",
    ],
)
def test_ac_j3_run_id_must_match_the_strict_pattern(tmp_path: Path, run_id: str) -> None:
    paths = make_paths(tmp_path)

    code, payload, _ = call(["status"], {**STATUS, "run_id": run_id}, deps(paths))

    assert (code, payload["code"]) == (2, "invalid_input")
    assert not paths.logs.exists()


def test_ac_j4_an_unexpected_error_is_one_safe_json_and_the_trace_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_paths(tmp_path)
    leaked = "SuperSecretValue" + "123456789"
    (paths.etc).mkdir(parents=True)
    (paths.etc / "app.env").write_text(f"SECURITY_EVENT_SERVER_KEY={leaked}\n")

    def boom(ctx: Context, request: dict[str, object]) -> dict[str, object]:
        raise RuntimeError(f"failed near {leaked}")

    monkeypatch.setitem(
        cli.JOBS, "smtp-test", cli.Job(boom, cli.JOBS["smtp-test"].keys, frozenset())
    )

    code, payload, raw = call(["smtp-test"], {"run_id": RUN_ID, "mode": "discard"}, deps(paths))

    assert (code, payload) == (
        3,
        {"code": "engine_failed", "message_key": "smtp-test.engine_failed"},
    )
    assert "Traceback" not in raw
    logs = log_text(paths)
    assert "RuntimeError: failed near [REDACTED]" in logs
    assert leaked not in logs


@pytest.mark.parametrize(
    "program", ["powershell.exe", "wsl.exe", "/mnt/c/Windows/System32/cmd.exe", "cmd", "bash", ""]
)
def test_ac_j5_the_runner_starts_only_allow_listed_linux_programs(
    tmp_path: Path, program: str
) -> None:
    runner = Runner(RunLog(make_paths(tmp_path), RUN_ID, "prepare", Redactor()))

    with pytest.raises(ValueError, match="is not allowed"):
        runner.run("prepare.01.x", [program, "-c", "x"], timeout=5)


def test_ac_j5_commands_get_only_the_minimal_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://elsewhere:2375")
    monkeypatch.setenv("SMTP_PASS", "from-the-caller")
    runner = Runner(
        RunLog(make_paths(tmp_path), RUN_ID, "prepare", Redactor()), programs=frozenset({"env"})
    )

    result = runner.run("prepare.01.env", ["env"], timeout=10)

    seen = dict(line.split("=", 1) for line in result.text().splitlines() if "=" in line)
    assert {k: v for k, v in seen.items() if not k.startswith("__CF")} == ENVIRONMENT


def test_ac_l1_lines_carry_time_run_id_step_level_and_escape_controls(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    log = RunLog(paths, RUN_ID, "prepare", Redactor(), Clock())

    log.line("prepare.04.time", "INFO", "offset ok\nFAKE 2026 line\x1b[31m")

    lines = (log.folder / "engine.log").read_text().splitlines()
    assert len(lines) == 1
    assert LINE.match(lines[0])
    assert lines[0].endswith("offset ok\\x0aFAKE 2026 line\\x1b[31m")


def test_ac_l2_command_output_is_capped_redacted_and_private(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    secret = "Hx7" + "kPq2Lm9Rt4Wv8Zc1Nb6"
    big = ("x" * 1023 + "\n") * 1100 + f"last line SERVICE_ROLE_KEY={secret}\n"
    script = Script({("docker", "load"): ok(big)})
    log = RunLog(paths, RUN_ID, "receive", Redactor([secret]))
    runner = script.runner(log)

    runner.run("receive.05.load", ["docker", "load", "--quiet"], timeout=5)

    files = sorted(log.folder.glob("*.stdout.log"))
    assert len(files) == 1
    text = files[0].read_text()
    assert len(text.encode()) <= 1024 * 1024
    assert text.endswith("last line SERVICE_ROLE_KEY=[REDACTED]\n")
    assert stat.S_IMODE(os.stat(files[0]).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(log.folder).st_mode) == 0o700
    assert log.folder == paths.logs / "receive" / RUN_ID
    assert "run: docker load --quiet" in (log.folder / "engine.log").read_text()


def test_ac_l3_rotation_keeps_20_runs_the_size_cap_and_the_first_install(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    first = RunLog(paths, "install-20261101T000000Z-aaaaaa", "prepare", Redactor())
    for day in range(2, 27):
        RunLog(paths, f"install-202611{day:02d}T000000Z-aaaaaa", "prepare", Redactor())
    install = paths.logs / "install"
    (install / "install-20261126T000000Z-aaaaaa/engine.log").write_bytes(b"x" * 49_000_000)
    (install / "install-20261125T000000Z-aaaaaa/engine.log").write_bytes(b"x" * 2_000_000)

    RunLog(paths, "install-20261127T000000Z-aaaaaa", "prepare", Redactor())

    assert sorted(p.name for p in install.iterdir()) == [
        "install-20261101T000000Z-aaaaaa",
        "install-20261126T000000Z-aaaaaa",
        "install-20261127T000000Z-aaaaaa",
    ]
    assert (first.folder / KEEP_MARK).exists()


def test_ac_l3_rotation_by_count_removes_the_oldest_runs_only(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    for day in range(1, 23):
        RunLog(paths, f"backup-202611{day:02d}T000000Z-aaaaaa", "prepare", Redactor())

    kept = sorted(p.name for p in (paths.logs / "backup").iterdir())

    assert kept == [f"backup-202611{day:02d}T000000Z-aaaaaa" for day in range(3, 23)]


def test_ac_l5_a_failed_job_saves_a_snapshot_without_inspect_or_config(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    leaked = "Tok" + "en99887766554433xx"
    script = Script(
        {
            ("docker", "ps"): ok("slateops-db-1\trunning\tUp 2 minutes\n"),
            ("docker", "logs"): ok(f"db ready\nPGRST_JWT_SECRET={leaked}\n"),
            ("systemctl", "is-system-running"): fail(1, "offline\n"),
        }
    )
    paths.releases.joinpath("0.1.0-rc.9").mkdir(parents=True)
    paths.releases.joinpath("0.1.0-rc.9/release-manifest.json").write_text("{}")

    code, payload, _ = call(
        ["prepare"], {"run_id": RUN_ID, "version": "0.1.0-rc.9"}, deps(paths, script)
    )

    assert code == 3
    assert payload["code"] == "systemd_not_running"
    folder = paths.logs / "install" / RUN_ID
    snapshots = list(folder.glob("snapshot-*/logs-slateops-db-1.txt"))
    assert len(snapshots) == 1
    assert "PGRST_JWT_SECRET=[REDACTED]" in snapshots[0].read_text()
    assert leaked not in log_text(paths)
    assert all(argv[:2] != ["docker", "inspect"] for argv in script.calls)
    assert all(
        "config" not in argv or "--quiet" in argv for argv in script.calls if argv[0] == "docker"
    )
    assert [
        "docker",
        "logs",
        "--tail",
        "200",
        "--since",
        "2026-11-17T10:15:01Z",
        "slateops-db-1",
    ] in script.calls


def test_s85_2_a_cut_drops_the_partial_first_line(tmp_path: Path) -> None:
    secret = "Hx7" + "kPq2Lm9Rt4Wv8Zc1Nb6Qa5Ys3Ux0Jf"
    # The 1 MiB window starts 22 characters before the end of the secret.
    tail = secret[-22:] + "\nnext line\n" + "y" * (1024 * 1024 - 22 - 11)
    data = ("x" * 5000 + secret[:-22] + tail).encode()
    log = RunLog(make_paths(tmp_path), RUN_ID, "prepare", Redactor())

    name = log.output("prepare.01.cut", "stdout", data)

    text = (log.folder / name).read_text()
    assert secret[-22:] not in text
    assert text.startswith("next line\n")
    assert cap(b"short\nlines\n") == b"short\nlines\n"


def test_architect_8_receive_runs_rotate_by_the_time_in_the_run_id(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    for day in range(1, 21):
        RunLog(paths, f"update-202611{day:02d}T000000Z-aaaaaa", "receive", Redactor())

    RunLog(paths, "install-20261121T000000Z-aaaaaa", "receive", Redactor())

    kept = sorted(p.name for p in (paths.logs / "receive").iterdir())
    assert "update-20261101T000000Z-aaaaaa" not in kept
    assert "install-20261121T000000Z-aaaaaa" in kept
    assert len(kept) == 20
