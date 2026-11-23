"""Run logs (plan 10.1): one folder per run, line format, capped step output, rotation.

A line is ``<UTC time> <run ID> <step ID> <level> <text>`` (the W5a format in
``backend/operations/install/joblog.py``): the text is redacted, then every control
character is written as a visible escape. Step output is captured in memory, cut to the
last 1 MiB, cut after its last complete line, redacted as one text, and only then written.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from engine.core import Paths, private_dir, run_kind
from engine.redaction import Redactor

STREAM_CAP_BYTES = 1024 * 1024  # planning value, plan 10.1 item 3
KEEP_RUNS = 20  # planning value, plan 10.1 item 5
KIND_CAP_BYTES = 50 * 1000 * 1000  # planning value, plan 10.1 item 5
KEEP_MARK = ".keep"
_RUN_TIME = re.compile(r"[0-9]{8}T[0-9]{6}Z")
# The first run of these kinds is never rotated out (plan 10.1 item 5).
KEEP_FIRST = ("install", "update")

# C0 (except tab), DEL, C1 and the Unicode line and paragraph separators (W5a joblog).
_ESCAPED_CODES = [*range(0x00, 0x09), *range(0x0A, 0x20), *range(0x7F, 0xA0), 0x2028, 0x2029]
_ESCAPES = {code: f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}" for code in _ESCAPED_CODES}


def escape_controls(text: str) -> str:
    return text.translate(_ESCAPES)


def utc_now() -> datetime:
    return datetime.now(UTC)


def cap(data: bytes, limit: int = STREAM_CAP_BYTES) -> bytes:
    """The last ``limit`` bytes, without the partial first line the cut leaves (S85-2: a cut
    can fall inside a secret, and a fragment no rule recognizes would stay)."""
    if len(data) <= limit:
        return data
    kept = data[-limit:]
    newline = kept.find(b"\n")
    return kept[newline + 1 :] if newline >= 0 else b""


def drop_unfinished(data: bytes) -> bytes:
    """Leave out a last line that has no newline (W84-1): a child stopped by the time limit
    or a signal can end in the middle of a secret, and half a secret matches no held value
    and no pattern. A note with the byte count takes its place."""
    if not data or data.endswith(b"\n"):
        return data
    kept = data[: data.rfind(b"\n") + 1]
    left_out = len(data) - len(kept)
    return kept + f"[unfinished last line left out: {left_out} bytes]\n".encode()


def _size(folder: Path) -> int:
    return sum(path.lstat().st_size for path in folder.rglob("*") if path.is_file())


def _run_time(path: Path) -> tuple[str, str]:
    """Order runs by the UTC time in the run ID: receive/ holds runs of several kinds."""
    found = _RUN_TIME.search(path.name)
    return (found.group(0) if found else "", path.name)


def rotate(kind_folder: Path, current: Path) -> None:
    """Keep the newest ``KEEP_RUNS`` runs and at most ``KIND_CAP_BYTES``, removing the oldest
    first; never the current run or a kept run."""
    runs = sorted(
        (path for path in kind_folder.iterdir() if path.is_dir() and not path.is_symlink()),
        key=_run_time,
        reverse=True,
    )
    newest = set(runs[:KEEP_RUNS])
    total = sum(_size(path) for path in runs)
    for path in reversed(runs):
        if path == current or (path / KEEP_MARK).exists():
            continue
        if path not in newest or total > KIND_CAP_BYTES:
            total -= _size(path)
            shutil.rmtree(path)


class RunLog:
    """The log folder of one run: ``/var/log/slateops/<kind>/<run ID>/``."""

    def __init__(
        self,
        paths: Paths,
        run_id: str,
        job: str,
        redact: Redactor,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        kind = "receive" if job == "receive" else run_kind(run_id)
        self.run_id = run_id
        self.redact = redact
        self.clock = clock
        kind_folder = private_dir(paths.logs / kind)
        self.folder = kind_folder / run_id
        first = (
            kind in KEEP_FIRST
            and not self.folder.exists()
            and not any((path / KEEP_MARK).exists() for path in kind_folder.iterdir())
        )
        private_dir(self.folder)
        if first:
            self._write(self.folder / KEEP_MARK, b"")
        rotate(kind_folder, self.folder)
        self._counter = len(list(self.folder.glob("[0-9][0-9][0-9]-*")))

    def _write(self, path: Path, data: bytes, *, append: bool = False) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if append else os.O_TRUNC)
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "ab" if append else "wb") as file:
            file.write(data)

    def format_line(self, step: str, level: str, text: str) -> str:
        moment = self.clock().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        return f"{moment} {self.run_id} {step} {level} {escape_controls(self.redact(text))}"

    def line(self, step: str, level: str, text: str) -> None:
        self._write(
            self.folder / "engine.log",
            (self.format_line(step, level, text) + "\n").encode(),
            append=True,
        )

    def output(self, step: str, stream: str, data: bytes) -> str:
        """Write one capped, redacted command stream; return the file name."""
        self._counter += 1
        name = f"{self._counter:03d}-{step}.{stream}.log"
        text = self.redact(drop_unfinished(cap(data)).decode("utf-8", errors="replace"))
        self._write(self.folder / name, text.encode())
        return name

    def text(self, name: str, text: str) -> None:
        """Write a redacted text file (facts, snapshot parts) into the run folder."""
        target = self.folder / name
        private_dir(target.parent)
        self._write(target, self.redact(text).encode())


class NullLog(RunLog):
    """For jobs that keep no run log (``status``, which the setup program polls)."""

    def __init__(self, redact: Redactor) -> None:
        self.run_id = "-"
        self.redact = redact
        self.clock = utc_now
        self.folder = Path("/nonexistent")
        self._counter = 0

    def line(self, step: str, level: str, text: str) -> None:
        return None

    def output(self, step: str, stream: str, data: bytes) -> str:
        return ""

    def text(self, name: str, text: str) -> None:
        return None
