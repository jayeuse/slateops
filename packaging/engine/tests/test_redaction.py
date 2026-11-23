"""Engine redaction (plan 10.1 item 3, 10.6 items 3 and 4; AC-L7, AC-L8).

Seeded values are built at run time, so the repository secret scan sees no literal key.
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest

from engine import redaction
from engine.held import load_held
from engine.redaction import Redactor
from operations.install import redaction as w5a

from .helpers import make_paths

# A generated-looking secret (32 characters) and a password with URL and JSON specials.
SECRET = "Qm9" + "xT7vLp2RkW8sNc4YhJ6dFa1ZuE5gBi3"
PASSWORD = "p@ss" + '/w&rd <x> "q" 1234'
EMAIL = "maria.santos" + "@example.test"
USERNAME = "msantos" + "77"
PEM_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
PEM_END = "-----END " + "PRIVATE KEY-----"
# A key body line, built from short pieces so the secret scan sees no literal.
BODY_LINE = "".join(
    [
        "MIIEvQIB",
        "ADANBgkq",
        "hkiG9w0B",
        "AQEFAASC",
        "BKcwggSj",
        "AgEAAoIB",
        "AQC7Vx2K",
        "s9WqLm",
    ]
)


def _redactor() -> Redactor:
    return Redactor(secrets=[SECRET, PASSWORD], personal=[EMAIL, USERNAME])


@pytest.mark.parametrize(
    "form",
    [
        SECRET,
        base64.b64encode(SECRET.encode()).decode(),
        base64.urlsafe_b64encode(SECRET.encode()).decode().rstrip("="),
        json.dumps(PASSWORD)[1:-1],
        json.dumps(PASSWORD)[1:-1]
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e"),
        quote(PASSWORD, safe=""),
        quote_plus(PASSWORD),
    ],
    ids=["raw", "base64", "base64url-unpadded", "json", "go-json", "url", "url-plus"],
)
def test_ac_l7_every_form_of_a_held_secret_is_masked(form: str) -> None:
    text = f'level=info msg="value {form} end"'

    out = _redactor()(text)

    assert form not in out
    assert "[REDACTED]" in out


@pytest.mark.parametrize(
    ("text", "kept", "gone"),
    [
        (
            "GET /auth/v1/verify?type=invite&token=a1b2c3d4e5f6a7b8&redirect_to=x HTTP/1.1",
            "type=invite",
            "a1b2c3d4e5f6a7b8",
        ),
        ("/realtime/v1/websocket?apikey=zz11yy22xx33&vsn=1.0.0", "vsn=1.0.0", "zz11yy22xx33"),
        ("Authorization: Basic dXNlcjpodW50ZXIy", "Authorization:", "dXNlcjpodW50ZXIy"),
        ('"authorization":"Bearer abc.def.ghi"', "authorization", "abc.def.ghi"),
        ("Cookie: sb-access=abc123; csrf=def456", "Cookie:", "abc123"),
        ('{"set-cookie":["session=qwe789; HttpOnly"]}', "set-cookie", "qwe789"),
        ('{"kty":"EC","crv":"P-256","d":"u1v2w3x4y5z6a7b8"}', '"kty":"EC"', "u1v2w3x4y5z6a7b8"),
        ('{\\"kty\\":\\"oct\\",\\"k\\":\\"m9n8b7v6c5x4\\"}', "kty", "m9n8b7v6c5x4"),
        ("postgres://supabase_admin:hunter22hunter@db:5432/postgres", "@db:5432", "hunter22"),
        ("from 10.1.2.3 user maria.santos@example.test signed in", "signed in", "maria.santos"),
        ("invite sent to maria.santos%40example.test", "invite sent", "maria.santos"),
        (r"open C:\Users\JDelacruz\AppData\Local\Temp\x.log", "AppData", "JDelacruz"),
        ("open C:/Users/JDelacruz/Desktop", "Desktop", "JDelacruz"),
        ('{"remote_ip":"192.168.1.44","status":200}', '"status":200', "192.168.1.44"),
        ('{"client_ip":"fe80::1","uri":"/api"}', '"uri":"/api"', "fe80::1"),
        ("X-Forwarded-For: 192.168.1.50", "X-Forwarded-For:", "192.168.1.50"),
        (
            "recovery key 123456-234567-345678-456789-567890-678901-789012-890123 shown",
            "shown",
            "456789-567890",
        ),
    ],
    ids=[
        "query-token",
        "query-apikey",
        "basic-auth",
        "bearer-json",
        "cookie",
        "set-cookie-json",
        "jwk-d",
        "jwk-k-escaped",
        "url-password",
        "email",
        "email-url-encoded",
        "windows-profile-path",
        "windows-profile-slash",
        "caddy-remote-ip",
        "caddy-client-ip",
        "forwarded-for",
        "bitlocker-recovery-password",
    ],
)
def test_ac_l7_patterns_mask_values_and_keep_the_line_readable(
    text: str, kept: str, gone: str
) -> None:
    out = Redactor()(text)

    assert gone not in out
    assert kept in out


def test_ac_l7_a_key_cut_by_the_cap_and_a_body_without_begin_are_masked() -> None:
    cut = f"line before\n{PEM_BEGIN}\n{BODY_LINE}\n{BODY_LINE}"
    body_only = f"{BODY_LINE}\n{BODY_LINE}\n{PEM_END}\nline after"
    loose_body = f"started\n{BODY_LINE}\nstopped"

    outs = [Redactor()(text) for text in (cut, body_only, loose_body)]

    assert all(BODY_LINE not in out for out in outs)
    assert "line before" in outs[0]
    assert "line after" in outs[1]
    assert "started" in outs[2]
    assert "stopped" in outs[2]


@pytest.mark.parametrize(
    "text",
    [
        "image sha256:" + "a1" * 32,
        "container 3f4e5d6c7b8a9f0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b2a3f4e",
        "run install-20261117T101500Z-ab12cd step prepare.04.time",
        "KeyError: 'missing'",
        "ghcr.io/jayeuse/slateops-server:0.1.0-rc.8",
        "chrony offset +0.000123 seconds",
        "uuid 2b9c1d4e-7f3a-4c5b-9e8d-1a2b3c4d5e6f",
        "serial-getty@hvc0.service loaded failed failed",
        "pid 123456 exited after 234567 ms",
    ],
)
def test_ac_l7_diagnostic_values_stay_readable(text: str) -> None:
    assert Redactor()(text) == text


def test_ac_l7_a_personal_value_is_masked_only_as_a_whole_word() -> None:
    out = _redactor()(f"user {USERNAME} and {USERNAME}x")

    assert out == f"user [PERSONAL] and {USERNAME}x"


def test_ac_l7_leaks_finds_a_held_form_that_survived() -> None:
    held = _redactor()

    assert held.leaks(f"x {base64.b64encode(SECRET.encode()).decode()} y")
    assert not held.leaks("nothing held here")


# The reviewer's shapes (S85-1) and the earlier ones, 64 KiB each. Measured before the fix,
# the quadratic rules took 3 to 36 s on one of these lines; the slowest linear rule (the
# bounded W5a field rule on "a.a.") takes about 0.3 s. The limit is 1 s per rule.
SHAPES = {
    "slashes": "/" * 65_536,
    "backslashes": "\\" * 65_536,
    "key-runs": "KEY" * 21_845,
    "query-key-runs": "?key" * 16_384,
    "jwt-starts": "eyJ-" * 16_384,
    "letters": "a" * 65_536,
    "dots": "a." * 32_768,
    "url-runs": "x://" * 16_384,
    "open-quotes": '"key": "' * 8_192,
    "password-quotes": "password='" * 6_553,
    "at-runs": "a@b." * 16_384,
    "user-paths": "/Users" * 10_922,
    "equals": "a=" * 32_768,
    "hex": "0f" * 32_768,
    "digits-dashes": "123456-" * 9_362,
}


def test_s85_1_every_rule_scans_a_long_line_in_linear_time() -> None:
    slow: list[tuple[str, str, float]] = []
    for name, rule in redaction.RULES.items():
        for shape, line in SHAPES.items():
            started = time.perf_counter()
            rule.sub("", line)
            seconds = time.perf_counter() - started
            if seconds > 1.0:
                slow.append((name, shape, round(seconds, 2)))

    assert slow == []


def test_s85_1_a_line_above_the_limit_is_masked_whole_before_the_rules() -> None:
    long_line = "/" * (redaction.LINE_LIMIT + 1)

    out = Redactor()(f"before\n{long_line}\nafter {SECRET}")

    assert out == f"before\n[LONG LINE {redaction.LINE_LIMIT + 1} characters]\nafter {SECRET}"


def test_s85_3_a_short_smtp_password_is_masked_as_a_whole_word() -> None:
    short = "pw7" + "!aZ"
    line = json.dumps({"level": "error", "msg": f"535 auth failed for user x pass {short}"})

    out = Redactor(words=[short])(line + f" {short}x")

    assert short + '"' not in out
    assert "pass [REDACTED]" in out
    assert out.endswith(f" {short}x")


def test_s85_3_only_the_smtp_password_is_held_as_a_word(tmp_path: Path) -> None:
    # app.env holds AUTH_REFRESH_TOKEN_DAYS=7: a short value under a secret-like name that
    # must not mask every "7" in the logs.
    short = "pw7" + "!aZ"
    paths = make_paths(tmp_path)
    (paths.etc / "new").mkdir(parents=True)
    (paths.etc / "app.env").write_text("AUTH_REFRESH_TOKEN_DAYS=7\n")
    (paths.etc / "new/smtp.env").write_text(f'SMTP_HOST=h.test\nSMTP_PASS="{short}"\n')

    out = Redactor(*load_held(paths))(f"retry 7 of 9; pass {short}")

    assert out == "retry 7 of 9; pass [REDACTED]"


def test_ac_l8_the_engine_keeps_every_w5a_rule_unchanged() -> None:
    assert redaction.W5A_MASK == w5a.MASK == redaction.MASK
    assert w5a.MIN_SECRET_LENGTH == redaction.MIN_SECRET_LENGTH
    assert (w5a.SECRET_NAME.pattern, w5a.SECRET_NAME.flags) == (
        redaction.SECRET_NAME.pattern,
        redaction.SECRET_NAME.flags,
    )
    for ours, theirs in (
        (redaction.W5A_WHOLE_MATCHES, w5a.WHOLE_MATCHES),
        (redaction.W5A_VALUE_MATCHES, w5a.VALUE_MATCHES),
    ):
        assert [(p.pattern, p.flags) for p in ours] == [(p.pattern, p.flags) for p in theirs]


@pytest.mark.parametrize(
    "text",
    [
        "token eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln and more",
        'Bearer-free "eyJhbGciOi.eyJzdWIi.c2ln"',
        "SERVICE_ROLE_KEY=abc123 DB_PASSWORD=xyz SECRET_TOKEN_X=1",
        "KeyError: 'missing' and KEY=",
    ],
)
def test_s85_1_the_bounded_rules_mask_what_their_w5a_rules_mask(text: str) -> None:
    pairs = (
        (redaction._JWT, w5a.WHOLE_MATCHES[2], False),
        (redaction._SECRET_ASSIGNMENT, w5a.VALUE_MATCHES[2], True),
    )
    for ours, theirs, grouped in pairs:

        def mask(match: re.Match[str], grouped: bool = grouped) -> str:
            return match.group(1) + "[M]" if grouped else "[M]"

        assert ours.sub(mask, text) == theirs.sub(mask, text)
