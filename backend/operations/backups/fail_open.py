"""Bounded automatic recovery of a failed or interrupted backup on later runner ticks.

The tick after a failure calls the unchanged ``recover_claim`` with fresh admission. The try
count lives in the journal and is saved before each try, so a crash during a try counts.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.observability import log_event
from operations.backups.host import Host, Json, RunnerError, read_private_json

Clock = Callable[[], datetime]
Recover = Callable[[Host, Json, Clock], dict[str, object]]

TRIES = 3
# Below one minute, so each per-minute tick can try despite scheduler jitter.
SPACING = timedelta(seconds=50)
# These states need a person: the try is not counted and the automatic path ends.
REFUSALS = frozenset(
    {"journal_invalid", "child_unresolved", "result_unconfirmed", "verification_failed"}
)


def _run_id(journal: Json) -> str:
    claim = journal.get("claim")
    return str(claim["run"]["id"]) if isinstance(claim, dict) else str(journal["claim_id"])


def _log(journal: Json, tries: int, *, cause: str | None = None) -> None:
    log_event(
        "operational_attention",
        reason_code="backup_auto_recovery_ended" if cause else "backup_auto_recovery_started",
        upstream="backup-runner",
        operation_id=_run_id(journal),
        count=tries,
        cause=cause,
    )


def fail_open(host: Host, journal: Json, now: Clock, recover: Recover) -> dict[str, object]:
    """Start one counted recovery try, or refuse with ``recovery_required``."""
    state = journal.get("auto_recovery", {"tries": 0, "last_started_at": None, "ended": None})
    try:
        if (
            not isinstance(state, dict)
            or type(state.get("tries")) is not int
            or not 0 <= state["tries"] <= TRIES
            or not isinstance(state.get("ended"), str | None)
        ):
            raise ValueError
        raw = state.get("last_started_at")
        started = None if raw is None else datetime.fromisoformat(raw)
        if started is not None and started.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise RunnerError("journal_invalid") from error
    if (
        state["ended"] is not None
        or state["tries"] >= TRIES
        or started is not None
        and now() - started < SPACING
    ):
        raise RunnerError("recovery_required")
    tries = state["tries"] + 1
    journal["auto_recovery"] = {"tries": tries, "last_started_at": now().isoformat(), "ended": None}
    host.save(journal)
    _log(journal, tries)
    try:
        result = recover(host, journal, now)
    except RunnerError as error:
        if error.code in REFUSALS:
            # A refusal is not counted and ends the automatic path. Change only the counter:
            # the refused try's in-memory edits stay unsaved.
            saved = read_private_json(host.run_directory(journal) / "journal.json")
            saved["auto_recovery"] = {
                **journal["auto_recovery"],
                "tries": tries - 1,
                "ended": error.code,
            }
            host.save(saved)
        _log(journal, tries, cause=error.code)
        raise
    except Exception:
        _log(journal, tries, cause="operator_failed")
        raise
    _log(journal, tries, cause=str(result["state"]))
    return result
