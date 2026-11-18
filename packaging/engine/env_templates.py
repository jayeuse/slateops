"""Render the production env templates in templates/. Standard library only.

A template line is blank, a comment that starts in column 0 with ``#`` (copied as it is),
or ``NAME=value``. In a value:

- ``{{NAME}}`` takes a literal value: printable ASCII with no ``$``, ``#``, ``'``, backquote
  or backslash, and no leading double quote. Docker's ``--env-file`` and Compose (``env_file``
  and ``--env-file``, which interpolate) then read the same bytes.
- ``{{NAME|compose}}`` is the whole value and takes customer text for the Compose project
  file only. It is written in Compose double quotes with ``\\``, ``"`` and ``$`` escaped;
  every line boundary of ``str.splitlines()`` and every control character is refused.
  ``docker run --env-file`` would keep the quotes, so a file that ``docker run`` reads must
  not use it.

Errors name the line and the placeholder, never a value.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

_NAME = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}")
_FIELD = re.compile(r"([A-Z_][A-Z0-9_]*)(\|compose)?\Z")
_LITERAL = re.compile(r"[!-~]+\Z")
_LITERAL_UNSAFE = frozenset("$#'`\\")


class TemplateError(ValueError):
    """A template or a value breaks the env format rule; the message holds no value."""


def is_literal(value: str) -> bool:
    """True when every Docker and Compose env reader keeps ``value`` byte for byte unquoted."""
    return (
        _LITERAL.match(value) is not None
        and not value.startswith('"')
        and _LITERAL_UNSAFE.isdisjoint(value)
    )


def compose_quoted(value: str) -> str:
    """Return customer text as one Compose double-quoted value."""
    if "".join(value.splitlines()) != value or any(
        unicodedata.category(character) == "Cc" for character in value
    ):
        raise TemplateError("customer text contains a line break or a control character")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$")
    return f'"{escaped}"'


def render(template: str, values: Mapping[str, str]) -> str:
    """Fill one template; refuse a missing value or a value outside the format rule."""
    lines: list[str] = []
    seen: set[str] = set()
    for number, line in enumerate(template.splitlines(), start=1):
        if not line or line.startswith("#"):
            lines.append(line)
            continue
        name, separator, value = line.partition("=")
        if not separator or _NAME.match(name) is None or name in seen:
            raise TemplateError(f"line {number} is not one new NAME=value binding")
        seen.add(name)
        lines.append(f"{name}={_render_value(name, value, values)}")
    return "\n".join(lines) + "\n"


def _render_value(name: str, value: str, values: Mapping[str, str]) -> str:
    parts = _PLACEHOLDER.split(value)
    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            if "{{" in part or "}}" in part:
                raise TemplateError(f"{name} has an unclosed placeholder")
            rendered.append(part)
            continue
        field = _FIELD.match(part)
        if field is None:
            raise TemplateError(f"{name} has an unsupported placeholder")
        source, compose = field.group(1), field.group(2) is not None
        if source not in values:
            raise TemplateError(f"{name} needs a value for {source}")
        if compose:
            if parts != ["", part, ""]:
                raise TemplateError(f"{name}: a compose placeholder must be the whole value")
            return compose_quoted(values[source])
        if not is_literal(values[source]):
            raise TemplateError(f"{name}: {source} is not a literal env value")
        rendered.append(values[source])
    result = "".join(rendered)
    if not is_literal(result):
        raise TemplateError(f"{name} is not a literal env value")
    return result
