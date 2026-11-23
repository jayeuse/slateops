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
    # A token starts only where no token character precedes it, and each part is bounded,
    # so the scan stays linear on a long run ("eyJ-eyJ-..." started a scan at every "e").
    re.compile(
        r"(?<![\w-])eyJ[A-Za-z0-9_-]{1,16384}\.[A-Za-z0-9_-]{1,16384}\.[A-Za-z0-9_-]{0,16384}"
    ),
    re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_-]+"),
    re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._~+/=-]+"),
)
VALUE_MATCHES = (
    # A connection-string password up to the last "@" in reach (it can hold "@" and "#").
    # The left boundary and the bounded lengths keep the scan linear on a long token.
    re.compile(
        r"(?<![a-zA-Z0-9+.-])([a-zA-Z][a-zA-Z0-9+.-]{0,31}://[^\s/:@]{0,256}:)\S{1,256}(?=@)"
    ),
    re.compile(r"(\b[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*=\s*)('[^']*'|\S+)"),
    # (?<!\w) is the word start of the former \b; bounded name parts keep one long word
    # with many secret words and no "=" from being scanned again from every split.
    re.compile(r"((?<!\w)[A-Z0-9_]{0,64}(?:PASS|SECRET|TOKEN|KEY)[A-Z0-9_]{0,64}=)\S+"),
    # JSON ("password": "...") and YAML (api_key: ...): a field name that ends in a secret
    # word. "KeyError: ..." ends in another word and stays readable.
    re.compile(
        r"""((?:"|'|\b)[A-Za-z0-9_.-]{0,64}(?:pass(?:word|wd)?|secret|token|key)s?(?:"|')?"""
        r"""\s*:\s*)("(?:[^"\\]|\\.)*"|'[^']*'|[^\s,}\]]+)""",
        re.I,
    ),
)


def _forms(secret: str) -> set[str]:
    """The value as written, in base64, and inside a JSON string."""
    raw = secret.encode()
    encoded = {base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()}
    return {secret, json.dumps(secret)[1:-1]} | encoded | {value.rstrip("=") for value in encoded}


def url_passwords(value: str) -> set[str]:
    """The password inside a connection string, as written and decoded.

    ``urlsplit`` stops at an unencoded ``#``, ``/`` or ``@`` in the password, so the
    user-info up to the last ``@`` is also taken."""
    if "://" not in value:
        return set()
    found: set[str] = set()
    try:
        parsed = urlsplit(value).password
    except ValueError:
        parsed = None
    if parsed:
        found.add(parsed)
    userinfo = value.split("://", 1)[1].rpartition("@")[0]
    if ":" in userinfo:
        found.add(userinfo.split(":", 1)[1])
    return found | {unquote(item) for item in found}


def held_secrets(environ: Mapping[str, str]) -> list[str]:
    """Exact values to mask, longest first so a longer value is never partly masked."""
    values: set[str] = set()
    for name, value in environ.items():
        if SECRET_NAME.search(name):
            values.add(value)
        values.update(url_passwords(value))
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
