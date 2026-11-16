"""Redact child output before an installer job logs it (plan 10.1 item 3 and 10.6 item 3).

Two layers: every exact secret value that the job holds in its environment (secret-named
variables, and the password inside any connection string), also in base64 and JSON-escaped
form; then the 10.6 patterns: private keys, tokens, connection-string passwords, and the
values of secret-named fields in ``KEY=value``, JSON and YAML form.
"""

import base64
import json
import re
from collections.abc import Callable, Mapping
from urllib.parse import unquote, urlsplit

MASK = "[REDACTED]"
# Shorter values would mask ordinary words; generated secrets are 32 characters or more.
MIN_SECRET_LENGTH = 8
SECRET_NAME = re.compile(r"PASS|SECRET|TOKEN|KEY|JWKS|CREDENTIAL|DATABASE_URL|DSN", re.I)
_KEY_END = r"-----END [A-Z0-9 ]*PRIVATE KEY-----"
WHOLE_MATCHES = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:" + _KEY_END + r"|\Z)", re.S),
    # The kept window can start inside a key: mask up to an END line with no BEGIN before it.
    re.compile(r"\A(?:(?!-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----).)*?" + _KEY_END, re.S),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),
    re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_-]+"),
    re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._~+/=-]+"),
)
VALUE_MATCHES = (
    re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]*:)[^\s@]+(?=@)"),
    re.compile(r"(\b[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*=\s*)('[^']*'|\S+)"),
    re.compile(r"(\b[A-Z0-9_]*(?:PASS|SECRET|TOKEN|KEY)[A-Z0-9_]*=)\S+"),
    # JSON ("password": "...") and YAML (api_key: ...): a field name that ends in a secret
    # word. "KeyError: ..." ends in another word and stays readable.
    re.compile(
        r"""((?:"|'|\b)[A-Za-z0-9_.-]*(?:pass(?:word|wd)?|secret|token|key)s?(?:"|')?"""
        r"""\s*:\s*)("(?:[^"\\]|\\.)*"|'[^']*'|[^\s,}\]]+)""",
        re.I,
    ),
)


def _forms(secret: str) -> set[str]:
    """The value as written, in base64, and inside a JSON string."""
    raw = secret.encode()
    encoded = {base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()}
    return {secret, json.dumps(secret)[1:-1]} | encoded | {value.rstrip("=") for value in encoded}


def held_secrets(environ: Mapping[str, str]) -> list[str]:
    """Exact values to mask, longest first so a longer value is never partly masked."""
    values: set[str] = set()
    for name, value in environ.items():
        if SECRET_NAME.search(name):
            values.add(value)
        try:
            password = urlsplit(value).password if "://" in value else None
        except ValueError:
            password = None
        if password:
            values.update({password, unquote(password)})
    forms = {form for value in values if len(value) >= MIN_SECRET_LENGTH for form in _forms(value)}
    return sorted((form for form in forms if len(form) >= MIN_SECRET_LENGTH),
                  key=len, reverse=True)


def redactor(environ: Mapping[str, str]) -> Callable[[str], str]:
    secrets = held_secrets(environ)

    def redact(text: str) -> str:
        for secret in secrets:
            text = text.replace(secret, MASK)
        for pattern in WHOLE_MATCHES:
            text = pattern.sub(MASK, text)
        for pattern in VALUE_MATCHES:
            text = pattern.sub(lambda match: match.group(1) + MASK, text)
        return text

    return redact
