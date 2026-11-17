"""Run the installation provisioning job (plan 6.2 step 8) and print one line of safe JSON.

``python -m operations.install.provisioning --confirm [--step-timeout SECONDS]`` runs, in
plan order and with the provisioning env: role provisioning, ``alembic upgrade head``,
``alembic check`` and Storage provisioning (``infra/supabase/README.md``, Lifecycle). The
first failed step stops the job. Each step runs as its own process with a time limit. Its
standard output and error go to this job's standard error after the step's log line,
redacted and capped at 1 MiB per stream (plan 10.1 item 3); standard output holds only the
JSON line. Exit codes follow the backup runner: 0 provisioned, 2 refused before any step,
3 a step failed or timed out.
"""

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from operations.install.joblog import RefusalParser, format_line, log_line
from operations.install.redaction import redactor

BACKEND = Path(__file__).resolve().parents[2]
STREAM_CAP_BYTES = 1024 * 1024
DEFAULT_STEP_SECONDS = 900.0  # planning value: 15 minutes per step

STEPS: tuple[tuple[str, Sequence[str]], ...] = (
    ("roles", (sys.executable, str(BACKEND / "operations/provision_database_role.py"),
               "--confirm")),
    ("migrate", (sys.executable, "-m", "alembic", "upgrade", "head")),
    ("check", (sys.executable, "-m", "alembic", "check")),
    ("storage", (sys.executable, str(BACKEND / "operations/provision_storage.py"),
                 "--confirm")),
)
FAILURE_CODES = {
    "roles": "roles_failed",
    "migrate": "migration_failed",
    "check": "schema_check_failed",
    "storage": "storage_failed",
}


@dataclass(frozen=True, slots=True)
class ChildResult:
    """Exit status (``None`` after the time limit) and the last bytes of each stream."""

    status: int | None
    stdout: bytes
    stderr: bytes
    stdout_bytes: int
    stderr_bytes: int


ChildRunner = Callable[[Sequence[str], Path, float], ChildResult]


def _drain(stream: IO[bytes], window: bytearray, total: list[int]) -> None:
    """Read a pipe to its end and keep only its last ``STREAM_CAP_BYTES`` bytes."""
    while chunk := stream.read(65536):
        total[0] += len(chunk)
        window += chunk
        if len(window) > STREAM_CAP_BYTES:
            del window[: len(window) - STREAM_CAP_BYTES]


def run_child(command: Sequence[str], cwd: Path, limit: float) -> ChildResult:
    """Run one step with no input; kill it at the time limit."""
    try:
        process = subprocess.Popen(
            list(command), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return ChildResult(127, b"", b"", 0, 0)
    windows, totals = (bytearray(), bytearray()), ([0], [0])
    assert process.stdout is not None and process.stderr is not None
    readers = [
        threading.Thread(target=_drain, args=(stream, window, total), daemon=True)
        for stream, window, total in zip(
            (process.stdout, process.stderr), windows, totals, strict=True
        )
    ]
    for reader in readers:
        reader.start()
    status: int | None
    try:
        status = process.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        status = None
    for reader in readers:
        reader.join(timeout=10)
    return ChildResult(status, bytes(windows[0]), bytes(windows[1]), totals[0][0], totals[1][0])


def _log_stream(
    step: str, name: str, data: bytes, total: int, redact: Callable[[str], str]
) -> None:
    """Log the stream's last lines, at most ``STREAM_CAP_BYTES`` as written to the log."""
    if total == 0:
        return
    text = data.decode("utf-8", "replace")
    if total > len(data):
        # The window starts inside a line; that fragment could hold part of a secret.
        text = text.partition("\n")[2]
    unfinished = 0
    if text and not text.endswith("\n"):
        # A stream cut by the time limit or a crash can end inside a secret; never log it.
        text, _, tail = text.rpartition("\n")
        unfinished = len(tail.encode())
    kept, written = 0, []
    for line in reversed(redact(text).splitlines()):
        formatted = format_line(f"provision.{step}", name, line)
        size = len(formatted.encode()) + 1
        if kept + size > STREAM_CAP_BYTES:
            break
        kept += size
        written.append(formatted)
    log_line(
        f"provision.{step}", "info",
        f"{name}_bytes={total} kept_bytes={kept} unfinished_bytes_dropped={unfinished}",
    )
    for formatted in reversed(written):
        print(formatted, file=sys.stderr, flush=True)


def _emit(value: dict[str, str]) -> None:
    print(json.dumps(value, separators=(",", ":")), flush=True)


def main(argv: Sequence[str] | None = None, *, run_child: ChildRunner = run_child) -> int:
    parser = RefusalParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="confirm provisioning of this installation's database and Storage")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_SECONDS,
                        help="time limit of each step in seconds (default: 900)")
    try:
        args = parser.parse_args(argv)
        if not args.confirm or not 0 < args.step_timeout < float("inf"):
            raise ValueError
    except ValueError:
        log_line("provision", "error", "invalid_input")
        _emit({"code": "invalid_input"})
        return 2
    redact = redactor(os.environ)
    for step, command in STEPS:
        log_line(f"provision.{step}", "info", "start " + redact(" ".join(command)))
        started = time.monotonic()
        result = run_child(command, BACKEND, args.step_timeout)
        seconds = f"seconds={time.monotonic() - started:.3f}"
        code = None
        if result.status is None:
            code = "step_timeout"
            log_line(f"provision.{step}", "error", f"{code} {seconds}")
        elif result.status != 0:
            code = FAILURE_CODES[step]
            log_line(f"provision.{step}", "error", f"{code} exit={result.status} {seconds}")
        else:
            log_line(f"provision.{step}", "info", f"ok exit=0 {seconds}")
        _log_stream(step, "stdout", result.stdout, result.stdout_bytes, redact)
        _log_stream(step, "stderr", result.stderr, result.stderr_bytes, redact)
        if code is not None:
            _emit({"step": step, "code": code})
            return 3
    _emit({"result": "provisioned"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
