"""``slateops-engine <job>``: the allow-listed jobs (plan 3.2 rule 1, 6.1, section 10).

Input: one JSON object on standard input (at most 64 KiB, known keys only), except
``receive``, which reads a tar stream, and ``--timer tick``, the form that
``slateops-runner.service`` runs: the engine makes the tick's ``backup`` run ID itself (the
Windows ``Exec`` runs exactly one job name, so it cannot reach this form). Output: exactly
one JSON object on standard output with a safe ``code`` (and ``message_key`` on a refusal or
failure). Exit codes: 0 done, 2 refused, 3 failed. A failed job saves the failure snapshot
in its run folder.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any, BinaryIO, TextIO

from engine import (
    backups,
    install,
    invitation,
    log_bundle,
    maintenance,
    packages,
    prefetch,
    prepare,
    receive,
    renewal,
    smtp,
    snapshot,
    status,
    tick,
    update,
)
from engine.context import Context, Dependencies
from engine.core import (
    FAILED,
    INPUT_LIMIT,
    JobError,
    Validator,
    engine_version,
    held_lock,
    read_request,
)
from engine.held import load_held
from engine.logs import NullLog, RunLog
from engine.redaction import Redactor

Handler = Callable[[Context, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Job:
    handler: Handler
    keys: Mapping[str, Validator]
    required: frozenset[str]
    locked: bool = True
    logged: bool = True


JOBS: dict[str, Job] = {
    "receive": Job(receive.handle, {}, frozenset()),
    "prepare": Job(prepare.handle, prepare.KEYS, prepare.REQUIRED),
    "prefetch": Job(prefetch.handle, prefetch.KEYS, prefetch.REQUIRED),
    "status": Job(status.handle, status.KEYS, status.REQUIRED, locked=False, logged=False),
    "smtp-test": Job(smtp.handle, smtp.KEYS, smtp.REQUIRED),
    "log-bundle": Job(log_bundle.handle, log_bundle.KEYS, log_bundle.REQUIRED, locked=False),
    "install": Job(install.handle, install.KEYS, install.REQUIRED),
    "resend-invitation": Job(invitation.handle, invitation.KEYS, invitation.REQUIRED),
    # Run by the tick once a day (plan 6.3) and by support; not a Windows Exec job.
    "renew-certificate": Job(renewal.handle, renewal.KEYS, renewal.REQUIRED),
    # W10b (TASK-0093). On the Windows Exec allow-list: set-backup-target, new-recovery-key.
    # Not on it: tick (the timer), runner-recover and runner-adopt (support, W13b).
    "set-backup-target": Job(backups.set_target, backups.TARGET_KEYS, backups.TARGET_REQUIRED),
    "new-recovery-key": Job(backups.new_key, backups.KEYS, backups.REQUIRED),
    "tick": Job(tick.handle, tick.KEYS, tick.REQUIRED),
    "runner-recover": Job(tick.recover, tick.KEYS, tick.REQUIRED),
    "runner-adopt": Job(tick.adopt, tick.KEYS, tick.REQUIRED),
    # W13b (TASK-0095). On the Windows Exec allow-list: update (from the new setup program).
    # Not on it: package-night (the tick runs it on Sunday; support runs it at once).
    "update": Job(update.handle, update.KEYS, update.REQUIRED),
    "package-night": Job(packages.handle, packages.KEYS, packages.REQUIRED),
    # W9 (TASK-0096), both on the Windows Exec allow-list; set-email reads the secret pipe.
    "prepare-uninstall": Job(
        maintenance.prepare_uninstall, maintenance.KEYS, maintenance.REQUIRED
    ),
    "set-email": Job(maintenance.set_email, maintenance.KEYS, maintenance.REQUIRED),
}


def _emit(stdout: TextIO, payload: dict[str, Any]) -> None:
    stdout.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    stdout.flush()


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    deps: Dependencies | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    source = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout
    deps = deps or Dependencies()
    if len(args) == 3 and args[0] == prefetch.WORKER:
        return prefetch.worker(deps, args[1], args[2])
    if args == [tick.TIMER, "tick"]:
        args, source = ["tick"], io.BytesIO(tick.timer_request(deps.clock()))
    name = args[0] if len(args) == 1 else ""
    job = JOBS.get(name)
    if job is None:
        _emit(out, {"code": "job_unknown", "message_key": "engine.job_unknown"})
        return 2
    ctx: Context | None = None
    try:
        if name == "receive":
            request = receive.read_request(source)
        else:
            request = read_request(source.read(INPUT_LIMIT + 1), job.keys, job.required)
        redactor = Redactor(*load_held(deps.paths))
        run_id = request["run_id"]
        log = (
            RunLog(deps.paths, run_id, name, redactor, deps.clock)
            if job.logged
            else NullLog(redactor)
        )
        ctx = Context(
            deps, name, run_id, log, deps.make_runner(log), redactor, deps.clock(), source,
            progress=stderr if stderr is not None else sys.stderr,
        )  # fmt: skip
        log.line(ctx.step(0, "start"), "INFO", f"engine {engine_version(deps.paths)} job {name}")
        lock: AbstractContextManager[None] = (
            held_lock(deps.paths.engine_lock, "engine_busy") if job.locked else nullcontext()
        )
        with lock:
            try:
                result = job.handler(ctx, request)
            finally:
                # Under the lock: a refused second receive never touches the staging.
                if name == "receive":
                    receive.discard_staging(deps.paths, ctx)
        log.line(ctx.step(0, "result"), "INFO", f"result {result['code']}")
        if not ctx.keep_log:  # an idle tick: 20 runs are kept, the night's log must stay
            shutil.rmtree(log.folder, ignore_errors=True)
        _emit(out, result)
        return 0
    except JobError as error:
        if ctx is not None:
            ctx.log.line(ctx.step(0, "result"), "ERROR", f"result {error.code}")
            if error.exit_code == FAILED:
                _snapshot(ctx)
        _emit(out, {"code": error.code, "message_key": f"{name}.{error.code}", **error.fields})
        return error.exit_code
    except Exception:
        if ctx is not None:
            ctx.log.line(ctx.step(0, "result"), "ERROR", traceback.format_exc())
            _snapshot(ctx)
        _emit(out, {"code": "engine_failed", "message_key": f"{name}.engine_failed"})
        return FAILED


def _snapshot(ctx: Context) -> None:
    try:
        snapshot.take(ctx, ctx.started)
    except Exception:
        ctx.log.line(ctx.step(99, "snapshot"), "WARN", "snapshot incomplete")


if __name__ == "__main__":
    raise SystemExit(main())
