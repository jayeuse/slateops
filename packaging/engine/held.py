"""The values that the engine holds and must never write (plan 10.6 item 3).

Secrets: every secret-named value in the env files of ``/etc/slateops/`` and
``/etc/slateops/new/``, the password in every connection string, and the content of a
one-value secret file (for example the Restic password). Personal data: the SMTP user and
sender address, and the administrator email and user name of the stored answers. The
redactor masks each of them in every form (``redaction.forms``).
"""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path

from engine.core import Paths
from engine.env_templates import TemplateError
from engine.redaction import SECRET_NAME, url_passwords
from engine.smtp_env import unquote

PERSONAL_NAMES = frozenset({"SMTP_USER", "SMTP_ADMIN_EMAIL", "ADMIN_EMAIL", "ADMIN_USERNAME"})
_SECRET_FILE = re.compile(r"pass|secret|key|token", re.I)
_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)\Z")
FILE_LIMIT = 1024 * 1024


def _regular_files(folder: Path) -> list[Path]:
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    return [path for path in entries if stat.S_ISREG(path.lstat().st_mode)]


def _value(raw: str) -> str:
    if raw.startswith('"'):
        try:
            return unquote(raw)
        except TemplateError:
            return raw
    return raw


def load_held(paths: Paths) -> tuple[list[str], list[str], list[str]]:
    """(secrets, personal values, words): ``words`` holds the SMTP password, which can be
    shorter than the redactor's minimum and is masked as a whole word (S85-3)."""
    secrets: list[str] = []
    personal: list[str] = []
    words: list[str] = []
    for path in (*_regular_files(paths.etc), *_regular_files(paths.etc / "new")):
        if path.stat().st_size > FILE_LIMIT:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        bindings = [match for line in text.splitlines() if (match := _LINE.match(line))]
        if not bindings and _SECRET_FILE.search(path.name) and text.strip():
            secrets.append(text.strip())
        for binding in bindings:
            name, value = binding.group(1), _value(binding.group(2))
            if name == "SMTP_PASS":
                words.append(value)
            if name in PERSONAL_NAMES:
                personal.append(value)
            elif SECRET_NAME.search(name):
                secrets.append(value)
            secrets.extend(url_passwords(value))
    try:
        answers = json.loads(paths.answers.read_text())
    except (OSError, ValueError):
        answers = {}
    if isinstance(answers, dict):
        for key in ("admin_email", "admin_username"):
            found = answers.get(key)
            if isinstance(found, str):
                personal.append(found)
    return secrets, personal, words
