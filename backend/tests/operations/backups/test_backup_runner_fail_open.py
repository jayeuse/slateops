"""A failed or interrupted backup recovers on the next ticks: bounded, counted and logged."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from operations import backup_runner
from operations.backups import fail_open
from operations.backups.host import RunnerError
from tests.operations.backups.backup_runner_fixtures import (
    NOW,
    SERVICES,
    SyntheticCommands,
    active_journal,
    execute,
    runner_config,
)


def fail_archive(host: Any, journal: dict[str, Any]) -> None:
    raise RunnerError("backup_failed")


def tick(minutes: float, seconds: int = 0) -> Callable[[], datetime]:
    moment = NOW + timedelta(minutes=minutes, seconds=seconds)
    return lambda: moment


def status(commands: SyntheticCommands, name: str) -> str:
    return str(
        next(
            item
            for item in commands.containers
            if item["Config"]["Labels"]["com.docker.compose.service"] == name
        )["State"]["Status"]
    )


def failed_backup(tmp_path: Path) -> tuple[Path, Path, SyntheticCommands]:
    config, state = runner_config(tmp_path)
    commands = SyntheticCommands(config)
    with pytest.raises(RunnerError, match="backup_failed"):
        execute(config, state, commands, archive_runner=fail_archive)
    return config, state, commands


def test_failed_backup_resumes_the_services_that_ran_before_on_the_next_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, commands = failed_backup(tmp_path)
    logger = Mock()
    monkeypatch.setattr(fail_open, "log_event", logger)
    before = len(commands.calls)

    result = execute(config, state, commands, now=tick(1))

    assert commands.claim is not None
    run_id = commands.claim["run"]["id"]
    assert result == {"state": "failed", "run_id": run_id}
    assert commands.claim["run"]["failure_code"] == "backup_failed"
    assert commands.claim["run"]["reconciled_at"] is not None
    assert {name for name in SERVICES if status(commands, name) == "running"} == {
        "db", "auth", "storage", "imgproxy", "realtime", "meta", "api-gw", "api", "caddy"
    }
    calls = [args for args, _ in commands.calls[before:]]
    caddy = next(
        item["Id"]
        for item in commands.containers
        if item["Config"]["Labels"]["com.docker.compose.service"] == "caddy"
    )
    readiness = next(index for index, args in enumerate(calls) if args[:2] == ["docker", "exec"])
    opened = next(
        index
        for index, args in enumerate(calls)
        if args[:2] == ["docker", "start"] and caddy in args
    )
    assert readiness < opened
    assert [(call.args, call.kwargs) for call in logger.call_args_list] == [
        (
            ("operational_attention",),
            {
                "reason_code": "backup_auto_recovery_started",
                "upstream": "backup-runner",
                "operation_id": run_id,
                "count": 1,
                "cause": None,
            },
        ),
        (
            ("operational_attention",),
            {
                "reason_code": "backup_auto_recovery_ended",
                "upstream": "backup-runner",
                "operation_id": run_id,
                "count": 1,
                "cause": "failed",
            },
        ),
    ]


def test_unready_api_keeps_ingress_closed_for_three_tries_then_requires_recovery(
    tmp_path: Path,
) -> None:
    config, state, commands = failed_backup(tmp_path)
    commands.readiness = False
    with pytest.raises(RunnerError, match="readiness_failed"):
        execute(config, state, commands, now=tick(1))
    bridged = len(commands.operations)
    # A tick 49 s after the previous try start consumes no try; 50 s later it tries.
    with pytest.raises(RunnerError, match="recovery_required"):
        execute(config, state, commands, now=tick(1, 49))
    assert len(commands.operations) == bridged
    for moment in (tick(1, 50), tick(2, 40)):
        with pytest.raises(RunnerError, match="readiness_failed"):
            execute(config, state, commands, now=moment)
    assert status(commands, "caddy") == "exited"
    bridged = len(commands.operations)

    with pytest.raises(RunnerError, match="recovery_required"):
        execute(config, state, commands, now=tick(10))

    assert len(commands.operations) == bridged
    assert status(commands, "caddy") == "exited"
    assert commands.claim is not None
    assert commands.claim["run"]["reconciled_at"] is None
    commands.readiness = True
    assert execute(config, state, commands, recover=True)["state"] == "failed"
    assert commands.claim["run"]["reconciled_at"] is not None


@pytest.mark.parametrize(
    ("raised", "logged", "counted", "ended", "tries"),
    [
        (RunnerError("journal_invalid"), "journal_invalid", 0, "journal_invalid", 1),
        (RunnerError("child_unresolved"), "child_unresolved", 0, "child_unresolved", 1),
        (RunnerError("result_unconfirmed"), "result_unconfirmed", 0, "result_unconfirmed", 1),
        (RunnerError("verification_failed"), "verification_failed", 0, "verification_failed", 1),
        (RunnerError("restart_failed"), "restart_failed", 1, None, 3),
        (RunnerError("admission_failed"), "admission_failed", 1, None, 3),
        (OSError("power lost"), "operator_failed", 1, None, 3),
    ],
    ids=[
        "journal_invalid-refusal",
        "child_unresolved-refusal",
        "result_unconfirmed-refusal",
        "verification_failed-refusal",
        "restart_failed-counted",
        "admission_failed-counted",
        "crash-counted",
    ],
)
def test_a_refusal_ends_automatic_recovery_and_any_other_failed_try_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
    logged: str,
    counted: int,
    ended: str | None,
    tries: int,
) -> None:
    config, state, commands = failed_backup(tmp_path)
    logger = Mock()
    monkeypatch.setattr(fail_open, "log_event", logger)
    _, saved = active_journal(state)
    real = backup_runner.recover_claim
    calls: list[str] = []

    def failing_try(host: Any, journal: dict[str, Any], now: Any) -> dict[str, object]:
        calls.append(journal["claim_id"])
        journal["phase"] = "changed only in memory"
        raise raised

    monkeypatch.setattr(backup_runner, "recover_claim", failing_try)
    with pytest.raises(type(raised), match=str(raised)):
        execute(config, state, commands, now=tick(1))
    after = active_journal(state)[1]
    assert after["phase"] == saved["phase"]
    assert after["auto_recovery"] == {
        "tries": counted,
        "last_started_at": "2026-10-03T12:01:00+00:00",
        "ended": ended,
    }
    assert logger.call_args_list[-1].kwargs["cause"] == logged
    for minute in (2, 3):
        with pytest.raises((RunnerError, OSError)):
            execute(config, state, commands, now=tick(minute))

    with pytest.raises(RunnerError, match="recovery_required"):
        execute(config, state, commands, now=tick(4))

    assert len(calls) == tries
    monkeypatch.setattr(backup_runner, "recover_claim", real)
    assert execute(config, state, commands, recover=True)["state"] == "failed"


@pytest.mark.parametrize(
    "damaged",
    [
        3,
        {"tries": "1", "last_started_at": None, "ended": None},
        {"tries": 1, "last_started_at": 5, "ended": None},
        {"tries": 1, "last_started_at": None, "ended": 5},
        {"tries": 1, "last_started_at": "yesterday", "ended": None},
        {"tries": 1, "last_started_at": "2026-10-03T12:00:00", "ended": None},
        {"tries": -1, "last_started_at": None, "ended": None},
        {"tries": 4, "last_started_at": None, "ended": None},
    ],
    ids=[
        "not-an-object",
        "tries-not-int",
        "started-not-text",
        "ended-not-text",
        "started-not-iso",
        "started-without-timezone",
        "tries-negative",
        "tries-above-limit",
    ],
)
def test_a_damaged_counter_refuses_without_a_try(tmp_path: Path, damaged: object) -> None:
    config, state, commands = failed_backup(tmp_path)
    path, saved = active_journal(state)
    saved["auto_recovery"] = damaged
    path.write_text(json.dumps(saved))
    bridged = len(commands.operations)

    with pytest.raises(RunnerError, match="journal_invalid"):
        execute(config, state, commands, now=tick(1))

    assert len(commands.operations) == bridged
    assert status(commands, "caddy") == "exited"


def test_a_volume_reader_found_by_recover_claim_ends_automatic_recovery(tmp_path: Path) -> None:
    config, state, commands = failed_backup(tmp_path)
    listings: list[list[str]] = []

    def reader_after_admission(args: list[str], **kwargs: Any) -> Any:
        # The second container listing of the tick is the disposition check in recover_claim.
        if args[:2] == ["docker", "ps"]:
            listings.append(args)
            commands.orphan = len(listings) > 1
        return commands(args, **kwargs)

    before = len(commands.calls)
    with pytest.raises(RunnerError, match="child_unresolved"):
        execute(config, state, reader_after_admission, now=tick(1))

    assert len(listings) == 2
    assert not any(args[:2] == ["docker", "start"] for args, _ in commands.calls[before:])
    assert active_journal(state)[1]["auto_recovery"] == {
        "tries": 0,
        "last_started_at": "2026-10-03T12:01:00+00:00",
        "ended": "child_unresolved",
    }
    commands.orphan = False
    with pytest.raises(RunnerError, match="recovery_required"):
        execute(config, state, commands, now=tick(2))
    assert execute(config, state, commands, recover=True)["state"] == "failed"


@pytest.mark.parametrize(
    "interruption",
    [RunnerError("backup_interrupted"), OSError("power lost")],
    ids=["interrupted", "crash-without-outcome"],
)
def test_an_interrupted_run_takes_the_same_path_on_the_next_tick(
    tmp_path: Path, interruption: Exception
) -> None:
    config, state = runner_config(tmp_path)
    commands = SyntheticCommands(config)

    def interrupt(host: Any, journal: dict[str, Any]) -> None:
        raise interruption

    with pytest.raises(type(interruption), match=str(interruption)):
        execute(config, state, commands, archive_runner=interrupt)

    result = execute(config, state, commands, now=tick(1))

    assert result["state"] == "interrupted"
    assert commands.claim is not None
    assert commands.claim["run"]["failure_code"] == "backup_interrupted"
    assert status(commands, "caddy") == "running"
