"""Run the Excel import parser in its child process, bounded (spec D9.3, D14 E1-E4).

The parent sends the exact checked bytes on stdin, reads at most ``OUTPUT_LIMIT`` bytes,
kills the child on overflow or after 60 s, and always reaps it. Each exit code of the child
names one refusal; any other exit, a signal included, is ``unreadable``.

The answer counts against the request's file memory budget as it is read (``reserve_download``,
held until the response is sent): ``ANSWER_MEMORY_FACTOR`` bytes for each byte read, for the
raw bytes, the decoded rows and the validated response. A full budget stops the child and
refuses the file as ``busy`` (503 ``files_busy`` with its ``Retry-After``).
"""

import json
import os
import subprocess
import sys
import threading
from typing import Any

from fastapi import HTTPException

from app.systems.platform.files.providers import reserve_download

CHILD = ["-m", "app.systems.openview.worksheets.import_child"]
OUTPUT_LIMIT = 16 * 1024 * 1024 + 64 * 1024  # the child's cap and its JSON frame
TIMEOUT_SECONDS = 60
# Measured: 10,001 rows of 100 two-character texts (6.0 MB) peak at 61.7 MB in the parent
# through json, the response model and its rendering, plus the raw bytes (about 11.3 x).
ANSWER_MEMORY_FACTOR = 12
_LIMITS = {
    13: ("rows", 10_000, "A sheet holds at most 10,000 rows"),
    14: ("columns", 100, "A sheet holds at most 100 columns"),
    15: ("cell", 4_000, "A text cell holds at most 4,000 characters"),
}
_REASONS = {10: "archive_bounds", 11: "macro", 12: "unreadable", 16: "limit", 17: "tab"}


class ImportRefused(Exception):
    """A refused file: the event ``reason`` and the HTTP answer."""

    def __init__(self, reason: str, status_code: int, detail: Any,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(reason)
        self.reason, self.status_code, self.detail = reason, status_code, detail
        self.headers = headers


def _refusal(code: int) -> ImportRefused:
    if code in _LIMITS:
        limit, maximum, message = _LIMITS[code]
        return ImportRefused("limit", 422, {"code": "worksheet_limit", "message": message,
                                            "limit": limit, "maximum": maximum})
    if code == 17:
        return ImportRefused("tab", 422, {"code": "import_tab_invalid",
                                          "message": "The file has no such tab"})
    reason = _REASONS.get(code, "unreadable")
    return ImportRefused(reason, 422, {"code": "import_file_invalid", "reason": reason,
                                       "message": "This file cannot be imported"})


def parse_import(content: bytes, tab: int) -> dict[str, Any]:
    """The parsed tab, or :class:`ImportRefused`."""

    # A fixed module, no shell and a minimal environment: no settings reach the child.
    child = subprocess.Popen(
        [sys.executable, *CHILD, str(tab)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath, "PYTHONNOUSERSITE": "1"},
    )
    timed_out = threading.Event()

    def stop() -> None:
        timed_out.set()
        child.kill()

    def feed() -> None:
        try:
            assert child.stdin is not None
            child.stdin.write(content)
        except (BrokenPipeError, OSError):
            pass  # the child stopped reading; its exit code says why
        finally:
            if child.stdin is not None:
                try:
                    child.stdin.close()
                except OSError:
                    pass

    timer = threading.Timer(TIMEOUT_SECONDS, stop)
    writer = threading.Thread(target=feed, daemon=True)
    timer.start()
    writer.start()
    output = bytearray()
    overflow = finished = False
    busy: HTTPException | None = None
    try:
        assert child.stdout is not None
        while chunk := child.stdout.read(64 * 1024):
            try:
                reserve_download(len(chunk) * ANSWER_MEMORY_FACTOR)
            except HTTPException as full:
                busy = full
                break
            output += chunk
            if len(output) > OUTPUT_LIMIT:
                overflow = True
                child.kill()
                break
        finished = busy is None
    finally:
        if overflow or timed_out.is_set() or not finished:
            child.kill()
        code = child.wait()
        timer.cancel()
        writer.join(timeout=5)
        if child.stdout is not None:
            child.stdout.close()
    if busy is not None:
        raise ImportRefused("busy", 503, busy.detail, dict(busy.headers or {}))
    if timed_out.is_set():
        raise ImportRefused("timeout", 503, {"code": "import_unavailable",
                                             "message": "The file could not be read in time"})
    if overflow:
        raise _refusal(16)
    if code != 0:
        raise _refusal(code)
    try:
        parsed: dict[str, Any] = json.loads(bytes(output))
    except ValueError as error:
        raise _refusal(12) from error
    return parsed
