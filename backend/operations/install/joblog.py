"""Log lines and arguments of installer jobs (plan 10.1): standard error only, safe codes only.

Standard output stays one line of safe JSON for the engine. A line is
``<UTC time> <run ID> <step ID> <level> <text>``; the run ID comes from
``SLATEOPS_RUN_ID`` and is printed only when it matches a strict pattern.
"""

import argparse
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import NoReturn, TextIO

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,95}")
# C0 (except tab), DEL, C1 and the Unicode line and paragraph separators: each could
# forge a line, hide one, or drive a terminal.
CONTROL = re.compile("[\x00-\x08\x0a-\x1f\x7f-\x9f  ]")


def run_id(environ: Mapping[str, str] | None = None) -> str:
    """The engine's run ID, or ``-`` when it is absent or not a safe token."""
    value = (os.environ if environ is None else environ).get("SLATEOPS_RUN_ID", "")
    return value if RUN_ID.fullmatch(value) else "-"


def _escape(match: re.Match[str]) -> str:
    code = ord(match.group())
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def format_line(step: str, level: str, text: str) -> str:
    """The exact line that ``log_line`` writes, without its newline."""
    moment = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return f"{moment} {run_id()} {step} {level} {CONTROL.sub(_escape, text)}"


def log_line(step: str, level: str, text: str, *, stream: TextIO | None = None) -> None:
    """Write one line. Callers pass fixed step IDs and levels; ``text`` is a fixed code or
    child output that the caller has already redacted (``operations.install.redaction``)."""
    print(format_line(step, level, text), file=stream or sys.stderr, flush=True)


class RefusalParser(argparse.ArgumentParser):
    """Raise ``ValueError`` on a bad argument, so the job can print its JSON refusal.

    With ``refuse`` false it keeps argparse's own usage message and exit 2.
    """

    refuse = True

    def error(self, message: str) -> NoReturn:
        if self.refuse:
            raise ValueError(message)
        super().error(message)
