"""The one command runner of the engine (plan 10.1 item 3, 3.2 rule 2, W2 carry).

Every command goes through ``Runner.run``:

- only an allow-listed Linux program, named without a path (never a Windows program:
  interop is off, and no value from Windows becomes a program or an argument here);
- a fixed minimal environment, so no inherited variable overrides a Compose ``--env-file``
  value or points Docker somewhere else; a call may add only the named ``EXTRA_NAMES``
  (personal values that ``docker run -e NAME`` takes from the caller, so they never become
  an argument); their names are logged, never their values;
- its arguments, exit code and duration on the run log; its output captured in memory,
  cut to 1 MiB per stream, redacted, then written.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from engine.logs import RunLog

PROGRAMS = frozenset(
    {
        "chronyc",
        "cosign",
        "docker",
        "ip",
        "journalctl",
        "ss",
        "systemctl",
        "systemd-run",
        "timedatectl",
        "wslinfo",
    }
)
ENVIRONMENT = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C.UTF-8",
}
# Values a child may take from the engine's environment (TASK-0081 A-3: step 11 passes the
# administrator email and user name to ``docker run -e NAME``).
EXTRA_NAMES = frozenset({"ADMIN_EMAIL", "ADMIN_USERNAME"})
MISSING = 127


@dataclass(frozen=True)
class Result:
    """``returncode`` is None after the time limit and 127 when the program is missing."""

    returncode: int | None
    stdout: bytes
    stderr: bytes

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")


class Runner:
    def __init__(
        self,
        log: RunLog,
        *,
        programs: frozenset[str] = PROGRAMS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.log = log
        self.programs = programs
        self.clock = clock

    def run(
        self,
        step: str,
        argv: Sequence[str],
        *,
        timeout: float,
        log_output: bool = True,
        extra_env: Mapping[str, str] | None = None,
    ) -> Result:
        program = argv[0] if argv else ""
        if program not in self.programs:
            raise ValueError(f"program {program!r} is not allowed")
        extras = dict(extra_env or {})
        if not extras.keys() <= EXTRA_NAMES:
            raise ValueError(f"environment {sorted(extras)!r} is not allowed")
        added = f" (child environment adds {', '.join(sorted(extras))})" if extras else ""
        self.log.line(step, "INFO", f"run: {shlex.join(argv)}{added}")
        started = self.clock()
        try:
            result = self._execute(list(argv), timeout, {**ENVIRONMENT, **extras})
        except subprocess.TimeoutExpired as expired:
            result = Result(None, _bytes(expired.stdout), _bytes(expired.stderr))
        except FileNotFoundError:
            result = Result(MISSING, b"", b"")
        seconds = self.clock() - started
        status = "time limit" if result.returncode is None else f"exit {result.returncode}"
        level = "INFO" if result.ok else "WARN"
        self.log.line(step, level, f"{status} after {seconds:.1f} s ({program})")
        if log_output:
            for stream, data in (("stdout", result.stdout), ("stderr", result.stderr)):
                if data:
                    self.log.line(step, "INFO", f"{stream}: {self.log.output(step, stream, data)}")
        return result

    def _execute(self, argv: list[str], timeout: float, env: dict[str, str]) -> Result:
        completed = subprocess.run(
            argv,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return Result(completed.returncode, completed.stdout, completed.stderr)


def _bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    return value.encode() if isinstance(value, str) else value
