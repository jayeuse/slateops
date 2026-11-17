"""Redact text before the engine writes it or returns it (plan 10.1 item 3, 10.6 items 3-4).

The engine cannot import ``backend/``, so the W5a rules of
``backend/operations/install/redaction.py`` are copied here unchanged (the ``W5A_*`` names);
``tests/test_redaction.py`` fails when they drift. The engine applies the copy, except two
W5a rules that scan again from every position on a long token (``W5A_WHOLE_MATCHES[2]``,
``W5A_VALUE_MATCHES[2]``): it runs bounded forms of them (``_JWT``,
``_SECRET_ASSIGNMENT``) until the W5a module bounds its own (S85-1). The engine adds:

- every line longer than ``LINE_LIMIT`` is replaced by a mask before any rule runs;
- held values in more forms: URL-encoded, and JSON-escaped the way Go writes it; the SMTP
  password (``words``) is held at any length and masked as a whole word;
- personal values (email, user name) held by the engine, masked as whole words;
- header values of ``Authorization``, ``Cookie``, ``Set-Cookie`` and ``X-Forwarded-For``;
- secret-like query parameters, JWK private members, and long mixed-case base64 runs (a key
  body without its BEGIN and END lines);
- email addresses (also ``%40``), Windows profile folder names, client addresses in
  access-log fields, and BitLocker recovery passwords (eight groups of six digits).

Every rule has a left boundary or bounded lengths, so each scan is linear in the text
(``tests/test_redaction.py`` times every rule on long lines). Masks name the kind only.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus, unquote, urlsplit

# --- Copied from backend/operations/install/redaction.py (W5a). Keep byte for byte. ---
MASK = "[REDACTED]"
MIN_SECRET_LENGTH = 8
SECRET_NAME = re.compile(r"PASS|SECRET|TOKEN|KEY|JWKS|CREDENTIAL|DATABASE_URL|DSN", re.I)
_KEY_END = r"-----END [A-Z0-9 ]*PRIVATE KEY-----"
W5A_WHOLE_MATCHES = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:" + _KEY_END + r"|\Z)", re.S),
    re.compile(r"\A(?:(?!-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----).)*?" + _KEY_END, re.S),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),
    re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_-]+"),
    re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._~+/=-]+"),
)
W5A_VALUE_MATCHES = (
    # A connection-string password up to the last "@" in reach (it can hold "@" and "#").
    # The left boundary and the bounded lengths keep the scan linear on a long token.
    re.compile(
        r"(?<![a-zA-Z0-9+.-])([a-zA-Z][a-zA-Z0-9+.-]{0,31}://[^\s/:@]{0,256}:)\S{1,256}(?=@)"
    ),
    re.compile(r"(\b[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*=\s*)('[^']*'|\S+)"),
    re.compile(r"(\b[A-Z0-9_]*(?:PASS|SECRET|TOKEN|KEY)[A-Z0-9_]*=)\S+"),
    re.compile(
        r"""((?:"|'|\b)[A-Za-z0-9_.-]{0,64}(?:pass(?:word|wd)?|secret|token|key)s?(?:"|')?"""
        r"""\s*:\s*)("(?:[^"\\]|\\.)*"|'[^']*'|[^\s,}\]]+)""",
        re.I,
    ),
)
W5A_MASK = MASK
# --- End of the W5a copy. ---

PERSONAL_MASK = "[PERSONAL]"
EMAIL_MASK = "[EMAIL]"
USER_MASK = "[USER]"
CLIENT_MASK = "[CLIENT-IP]"

# Whole values that end at a line end or a quote: header values and secret-like query values.
_HEADER = re.compile(
    r"""(\b(?:authorization|proxy-authorization|cookie|set-cookie)\\?["']?\s*[:=]\s*"""
    r"""(?:\[\s*)?\\?["']?)[^"'\r\n\\]+""",
    re.I,
)
_QUERY = re.compile(
    r"([?&;](?:[A-Za-z0-9_.-]{0,64}(?:token|key|secret|signature|sig|password|passwd|code|jwt|auth)"
    r"[A-Za-z0-9_.-]{0,64})=)[^&#\s\"'\\]+",
    re.I,
)
# JWK private members (RFC 7518: d, p, q, dp, dq, qi; oct key k), also inside escaped JSON.
_JWK = re.compile(r"""(\\?"(?:d|p|q|dp|dq|qi|k)\\?"\s*:\s*\\?")[^"\\]+""")
# A key body line, or any long base64 run with upper case, lower case and a digit.
_BASE64_RUN = re.compile(
    r"(?<![A-Za-z0-9+/=])(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])"
    r"[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])"
)
# The left boundaries keep each scan linear: without them a long token is scanned again
# from every position (minutes for a 1 MiB line). systemd unit instances
# (serial-getty@hvc0.service) are not addresses.
_UNIT_SUFFIX = r"(?:service|socket|timer|mount|target|slice|scope|path|device|swap)\b"
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}(?:@|%40)[A-Za-z0-9.-]{1,253}\.(?!"
    + _UNIT_SUFFIX
    + r")[A-Za-z]{2,63}"
)
# Bounded forms of W5A_WHOLE_MATCHES[2] and W5A_VALUE_MATCHES[2] (S85-1): a left boundary
# instead of \b, and bounded lengths. A token directly after "-" or "_" is not taken as a
# JWT start; the base64 rule still covers long segments.
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{1,8192}\.[A-Za-z0-9_-]{1,8192}\.[A-Za-z0-9_-]{0,8192}"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?<![A-Za-z0-9_])([A-Z0-9_]{0,64}(?:PASS|SECRET|TOKEN|KEY)[A-Z0-9_]{0,64}=)\S+"
)
_WINDOWS_PROFILE = re.compile(
    r"((?:[A-Za-z]:|\\\\[^\\/\s]{1,64})?[\\/]{1,4}Users[\\/]{1,4})[^\\/\s\"']{1,256}", re.I
)
# Plan 10.6 item 3: the BitLocker recovery-password format.
_BITLOCKER = re.compile(r"(?<!\d)\d{6}(?:-\d{6}){7}(?!\d)")
LINE_LIMIT = 16_384  # characters; a longer line is masked whole before any rule runs
_CLIENT_FIELD = re.compile(
    r"""((?:\\?["'])?(?:remote_ip|client_ip|remote_addr|x_forwarded_for|x-forwarded-for|"""
    r"""x-real-ip)(?:\\?["'])?\s*[:=]\s*(?:\[\s*)?\\?["']?)[0-9A-Fa-f.:]+""",
    re.I,
)

_WHOLE_MATCHES = (
    W5A_WHOLE_MATCHES[0],
    W5A_WHOLE_MATCHES[1],
    _JWT,
    W5A_WHOLE_MATCHES[3],
    W5A_WHOLE_MATCHES[4],
    _BASE64_RUN,
    _BITLOCKER,
)
_VALUE_MATCHES = (
    _HEADER,
    _QUERY,
    _JWK,
    W5A_VALUE_MATCHES[0],
    W5A_VALUE_MATCHES[1],
    _SECRET_ASSIGNMENT,
    W5A_VALUE_MATCHES[3],
)
# Every rule the redactor applies, by name (the timing test runs each one).
RULES = {
    **{f"whole{index}": rule for index, rule in enumerate(_WHOLE_MATCHES)},
    **{f"value{index}": rule for index, rule in enumerate(_VALUE_MATCHES)},
    "email": _EMAIL,
    "windows_profile": _WINDOWS_PROFILE,
    "client_field": _CLIENT_FIELD,
}


def _word(form: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(form) + r"(?![A-Za-z0-9])")


def mask_long_lines(text: str) -> str:
    return "\n".join(
        f"[LONG LINE {len(line)} characters]" if len(line) > LINE_LIMIT else line
        for line in text.split("\n")
    )


def forms(value: str) -> set[str]:
    """``value`` as written, base64 (standard and URL-safe, with and without padding),
    JSON-escaped (Python and Go), and URL-encoded."""
    raw = value.encode()
    encoded = {base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()}
    escaped = json.dumps(value)[1:-1]
    go_escaped = escaped.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return (
        {value, escaped, go_escaped, quote(value, safe=""), quote_plus(value)}
        | encoded
        | {item.rstrip("=") for item in encoded}
    )


def url_passwords(value: str) -> set[str]:
    """The password inside a connection string, as written and decoded (W5a rule).

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


class Redactor:
    """Mask held secrets, held personal values and the 10.6 patterns."""

    def __init__(
        self,
        secrets: Iterable[str] = (),
        personal: Iterable[str] = (),
        words: Iterable[str] = (),
    ) -> None:
        """``words``: held secrets that can be short (the SMTP password), masked at any
        length as whole words; other secrets count from ``MIN_SECRET_LENGTH`` (W5a rule)."""
        self._inputs = (list(secrets), list(personal), list(words))
        values = {item for value in self._inputs[0] for item in (value, *url_passwords(value))}
        held = {
            form
            for value in values
            if len(value) >= MIN_SECRET_LENGTH
            for form in forms(value)
            if len(form) >= MIN_SECRET_LENGTH
        }
        self._secrets = sorted(held, key=len, reverse=True)
        # S85-3: the SMTP password is held at any length, as a whole word.
        short = {form for value in self._inputs[2] if value for form in forms(value)}
        self._short = [_word(form) for form in sorted(short - held, key=len, reverse=True)]
        people = {form for value in self._inputs[1] if len(value) >= 3 for form in forms(value)}
        self._personal = [_word(form) for form in sorted(people, key=len, reverse=True)]

    def with_values(
        self, secrets: Iterable[str], personal: Iterable[str], words: Iterable[str] = ()
    ) -> Redactor:
        """A redactor that also holds these values (for example a request's)."""
        return Redactor(
            [*self._inputs[0], *secrets],
            [*self._inputs[1], *personal],
            [*self._inputs[2], *words],
        )

    def __call__(self, text: str) -> str:
        text = mask_long_lines(text)
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        for pattern in self._short:
            text = pattern.sub(MASK, text)
        for pattern in self._personal:
            text = pattern.sub(PERSONAL_MASK, text)
        for whole in _WHOLE_MATCHES:
            text = whole.sub(MASK, text)
        for value in _VALUE_MATCHES:
            text = value.sub(lambda match: match.group(1) + MASK, text)
        text = _EMAIL.sub(EMAIL_MASK, text)
        text = _WINDOWS_PROFILE.sub(lambda match: match.group(1) + USER_MASK, text)
        return _CLIENT_FIELD.sub(lambda match: match.group(1) + CLIENT_MASK, text)

    def leaks(self, text: str) -> bool:
        """True when a held secret or personal value is still in ``text``."""
        return any(secret in text for secret in self._secrets) or any(
            pattern.search(text) for pattern in (*self._short, *self._personal)
        )
