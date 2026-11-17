"""The staged email settings ``/etc/slateops/new/smtp.env`` (plan 3.2 rule 3).

``SMTP_HOST`` and ``SMTP_PORT`` are literal values; the customer text (sender address,
user, password, sender name) is in Compose double quotes through
``env_templates.compose_quoted``, the same form as ``provider.env``. ``parse`` returns the
exact values, so ``install`` can render ``provider.env`` from them without quoting twice.
"""

from __future__ import annotations

from collections.abc import Mapping

from engine.env_templates import TemplateError, compose_quoted, is_literal

FIELDS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_ADMIN_EMAIL",
    "SMTP_USER",
    "SMTP_PASS",
    "SMTP_SENDER_NAME",
)
LITERAL = frozenset({"SMTP_HOST", "SMTP_PORT"})


def render(values: Mapping[str, str]) -> str:
    if set(values) != set(FIELDS):
        raise TemplateError("the staged email settings need exactly the six SMTP values")
    lines = ["# Staged by slateops-engine smtp-test after a passing test (plan 3.2)."]
    for name in FIELDS:
        value = values[name]
        if name in LITERAL:
            if not is_literal(value):
                raise TemplateError(f"{name} is not a literal env value")
            lines.append(f"{name}={value}")
        else:
            lines.append(f"{name}={compose_quoted(value)}")
    return "\n".join(lines) + "\n"


def unquote(value: str) -> str:
    """Reverse ``compose_quoted``: ``\\\\`` -> ``\\``, ``\\"`` -> ``"``, ``$$`` -> ``$``."""
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        raise TemplateError("a quoted value must start and end with a double quote")
    body, out, index = value[1:-1], [], 0
    while index < len(body):
        character = body[index]
        pair = body[index : index + 2]
        if pair in ("\\\\", '\\"', "$$"):
            out.append(pair[1])
            index += 2
        elif character in '\\"$':
            raise TemplateError("a quoted value has an unescaped character")
        else:
            out.append(character)
            index += 1
    return "".join(out)


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in FIELDS or name in values:
            raise TemplateError("the staged email settings have an unexpected line")
        values[name] = value if name in LITERAL else unquote(value)
    if set(values) != set(FIELDS):
        raise TemplateError("the staged email settings are incomplete")
    return values
