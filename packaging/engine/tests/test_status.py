"""``status`` (plan 3.2 rule 2, 7.4 rule 4, 10.2; AC-S1 to AC-S3)."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from engine import prefetch, report
from engine.core import Paths, private_dir

from .helpers import RUN_ID, VERSION, call, deps, make_paths

REQUEST = {"run_id": RUN_ID, "windows_part_version": "0.1.0", "wsl_version": "2.6.1.0"}


def _engine(paths: Paths, known_bad: list[str] | None = None) -> None:
    paths.engine_home.mkdir(parents=True)
    (paths.engine_home / "VERSION").write_text(VERSION + "\n")
    folder = private_dir(paths.releases / VERSION)
    manifest = {"schema_version": 1, "version": VERSION, "images": {"providers": []}}
    if known_bad is not None:
        manifest["known_bad_wsl_versions"] = known_bad
    (folder / "release-manifest.json").write_text(json.dumps(manifest))


def _lock_line(path: Path) -> str:
    status = path.stat()
    device = f"{os.major(status.st_dev):02x}:{os.minor(status.st_dev):02x}"
    return f"1: FLOCK  ADVISORY  WRITE 4242 {device}:{status.st_ino} 0 EOF\n"


def test_ac_s1_status_returns_only_safe_codes_booleans_and_whole_numbers(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    _engine(paths)
    prefetch.write_state(
        paths,
        {
            "code": "prefetch_running",
            "step": 2,
            "steps_total": 4,
            "bytes_done": 1_200_000_000,
            "bytes_total": 3_400_000_000,
            "retry_in_seconds": 0,
            "path": "/etc/passwd",
        },
    )
    private_dir(paths.run)
    paths.prefetch_lock.write_text("")
    (paths.proc / "locks").write_text(_lock_line(paths.prefetch_lock))

    code, payload, _ = call(["status"], REQUEST, deps(paths))

    assert code == 0
    assert payload == {
        "code": "ok",
        "engine_idle": False,
        "state": "not_installed",
        "prefetch": "prefetch_running",
        "progress": {
            "step": 2,
            "steps_total": 4,
            "bytes_done": 1_200_000_000,
            "bytes_total": 3_400_000_000,
            "retry_in_seconds": 0,
        },
    }
    assert not paths.logs.exists()


def test_ac_s1_engine_idle_is_true_when_no_lock_is_held(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    _engine(paths)
    private_dir(paths.run)
    descriptor = os.open(paths.engine_lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        (paths.proc / "locks").write_text(_lock_line(paths.engine_lock))
        busy = call(["status"], REQUEST, deps(paths))[1]
    finally:
        os.close(descriptor)
    (paths.proc / "locks").write_text("")
    idle = call(["status"], REQUEST, deps(paths))[1]

    assert busy["engine_idle"] is False
    assert idle["engine_idle"] is True
    assert idle["prefetch"] == "prefetch_not_started"


def test_ac_s2_a_known_bad_wsl_version_needs_support(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    _engine(paths, known_bad=["2.6.1.0"])

    bad = call(["status"], REQUEST, deps(paths))[1]
    good = call(["status"], {**REQUEST, "wsl_version": "2.6.2.0"}, deps(paths))[1]

    assert bad["state"] == "needs_support"
    assert good["state"] == "not_installed"


def test_ac_s3_status_records_each_version_change_once(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    _engine(paths)

    call(["status"], REQUEST, deps(paths))
    call(["status"], REQUEST, deps(paths))
    call(["status"], {**REQUEST, "wsl_version": "2.7.0.0"}, deps(paths))

    data = report.load(paths)
    kinds = [(event["kind"], event["from"], event["to"]) for event in data["events"]]
    assert kinds[:2] == [("windows_part_changed", None, "0.1.0"), ("wsl_changed", None, "2.6.1.0")]
    assert kinds[3:] == [("wsl_changed", "2.6.1.0", "2.7.0.0")]
    assert kinds[2][0] == "kernel_changed"
    assert data["versions"]["wsl"] == "2.7.0.0"


def test_architect_2_engine_idle_is_false_when_proc_locks_cannot_be_read(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    _engine(paths)
    private_dir(paths.run)
    paths.engine_lock.write_text("")
    (paths.proc / "locks").unlink()

    payload = call(["status"], REQUEST, deps(paths))[1]

    assert payload["engine_idle"] is False


def test_architect_4_only_four_part_known_bad_wsl_versions_count(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    _engine(paths, known_bad=["2.6", "2.6.1.0; x", "2.6.1.0"])

    bad = call(["status"], {**REQUEST, "wsl_version": "2.6"}, deps(paths))
    known = call(["status"], REQUEST, deps(paths))[1]

    assert (bad[0], bad[1]["code"]) == (2, "invalid_input")
    assert known["state"] == "needs_support"
