"""Shared test parts: temporary paths, a scripted runner, a fixed clock, and a job call."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from engine import cli
from engine.context import Dependencies
from engine.core import Paths
from engine.logs import RunLog
from engine.runner import Result, Runner

RUN_ID = "install-20261117T101500Z-ab12cd"
VERSION = "0.1.0-rc.9"


def make_paths(root: Path) -> Paths:
    paths = Paths(
        etc=root / "etc/slateops",
        state=root / "var/lib/slateops",
        logs=root / "var/log/slateops",
        run=root / "run/slateops",
        engine_home=root / "opt/engine",
        engine_command=root / "usr/local/bin/slateops-engine",
        image_record=root / "usr/share/slateops/linux-image.json",
        proc=root / "proc",
        passwd=root / "etc/passwd",
        docker_socket=root / "run/docker.sock",
        systemd=root / "etc/systemd/system",
        docker_volumes=root / "var/lib/docker/volumes",
        apt_sources=root / "etc/apt/sources.list.d",
    )
    (root / "proc").mkdir(parents=True)
    (root / "proc/locks").write_text("")
    return paths


class Clock:
    """A clock that moves one second per read."""

    def __init__(self, start: datetime = datetime(2026, 11, 17, 10, 15, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


Response = Result | Callable[[list[str]], Result]


@dataclass
class Script:
    """Answers by argv prefix (longest first); records every call."""

    answers: dict[tuple[str, ...], Response] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    environments: list[dict[str, str]] = field(default_factory=list)

    def answer(self, argv: list[str], env: dict[str, str] | None = None) -> Result:
        self.calls.append(argv)
        self.environments.append(dict(env or {}))
        for prefix in sorted(self.answers, key=len, reverse=True):
            if tuple(argv[: len(prefix)]) == prefix:
                found = self.answers[prefix]
                return found(argv) if callable(found) else found
        return Result(0, b"", b"")

    def runner(self, log: RunLog) -> Runner:
        script = self

        class ScriptedRunner(Runner):
            def _execute(
                self,
                argv: list[str],
                timeout: float,
                env: dict[str, str],
                stdin: bytes | None = None,
            ) -> Result:
                return script.answer(argv, env)

        return ScriptedRunner(log)


def ok(stdout: str = "", stderr: str = "") -> Result:
    return Result(0, stdout.encode(), stderr.encode())


def fail(code: int = 1, stdout: str = "", stderr: str = "") -> Result:
    return Result(code, stdout.encode(), stderr.encode())


def deps(paths: Paths, script: Script | None = None, **overrides: Any) -> Dependencies:
    values: dict[str, Any] = {
        "paths": paths,
        "make_runner": (script or Script()).runner,
        "clock": Clock(),
        "sleep": lambda seconds: None,
        "disk_free": lambda path: 100 * 1024**3,
    }
    values.update(overrides)
    return Dependencies(**values)


def call(
    job: Sequence[str], request: dict[str, Any] | bytes, dependencies: Dependencies
) -> tuple[int, dict[str, Any], str]:
    """Run ``slateops-engine <job>``; return the exit code, the one JSON object, the raw out."""
    data = request if isinstance(request, bytes) else json.dumps(request).encode()
    out = io.StringIO()
    code = cli.main(list(job), stdin=io.BytesIO(data), stdout=out, deps=dependencies)
    text = out.getvalue()
    lines = text.splitlines()
    assert len(lines) == 1, text
    return code, json.loads(lines[0]), text


def log_text(paths: Paths) -> str:
    """Every file under the log root, joined (to search for a leaked value)."""
    return "\n".join(
        file.read_text(errors="replace") for file in sorted(paths.logs.rglob("*")) if file.is_file()
    )


def progress_lines(err: str) -> list[str]:
    """The progress lines a job wrote to standard error (TASK-0097 W14-D5)."""
    return [line for line in err.splitlines() if line.startswith("progress ")]
