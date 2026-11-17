"""``smtp-test`` against a local SMTP server (plan 4.1 page 6, 3.2 rule 3; AC-M1 to AC-M6)."""

from __future__ import annotations

import os
import ssl
import stat
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import smtp, smtp_env
from engine.core import Paths

from .helpers import RUN_ID, call, deps, log_text, make_paths
from .smtp_server import Behavior, SmtpServer, closed_port, make_certificates

USER = "office" + "@frontdesk.test"
PASSWORD = "app pass $HOME #1 \"q\" \\ 'x' "
ADMIN = "owner" + "@frontdesk.test"


@pytest.fixture(scope="module")
def certificates(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return make_certificates(tmp_path_factory.mktemp("certificates"))


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return make_paths(tmp_path)


def _request(server_port: int, /, **changes: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "run_id": RUN_ID,
        "host": "localhost",
        "port": server_port,
        "user": USER,
        "password": PASSWORD,
        "sender_email": USER,
        "sender_name": " Front Desk $1 ",
        "admin_email": ADMIN,
    }
    request.update(changes)
    return request


def _tls(certificates: dict[str, Path]) -> Callable[[], ssl.SSLContext]:
    def context() -> ssl.SSLContext:
        made = ssl.create_default_context(cafile=str(certificates["ca"]))
        # Python 3.13 and later set this by default; the image runs 3.13, CI 3.14.
        made.verify_flags |= ssl.VERIFY_X509_STRICT
        return made

    return context


@pytest.fixture
def serve(certificates: dict[str, Path]) -> Iterator[Callable[..., SmtpServer]]:
    servers: list[SmtpServer] = []

    def start(**options: Any) -> SmtpServer:
        options.setdefault("certificate", certificates["localhost"])
        behavior = Behavior(user=USER, password=PASSWORD, **options)
        server = SmtpServer(behavior).__enter__()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.__exit__()


def _run(
    paths: Paths, certificates: dict[str, Path], request: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    code, payload, _ = call(["smtp-test"], request, deps(paths, tls_context=_tls(certificates)))
    return code, payload


def test_ac_m2_starttls_pass_sends_one_message_and_stages_the_values(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    server = serve()

    code, payload = _run(paths, certificates, _request(server.port))

    assert (code, payload) == (0, {"code": "smtp_passed"})
    commands = server.behavior.commands
    assert ("AUTH", True) in commands
    assert ("AUTH", False) not in commands
    assert len(server.behavior.messages) == 1
    message = server.behavior.messages[0]
    assert message["tls"] is True
    assert [line.lower() for line in message["to"]] == [f"rcpt to:<{ADMIN}>"]
    assert message["from"].lower().startswith(f"mail from:<{USER}>")
    staged = paths.staged_smtp
    assert stat.S_IMODE(os.stat(staged).st_mode) == 0o600
    assert smtp_env.parse(staged.read_text()) == {
        "SMTP_HOST": "localhost",
        "SMTP_PORT": str(server.port),
        "SMTP_ADMIN_EMAIL": USER,
        "SMTP_USER": USER,
        "SMTP_PASS": PASSWORD,
        "SMTP_SENDER_NAME": " Front Desk $1 ",
    }


def test_ac_m2_implicit_tls_on_the_implicit_port(
    paths: Paths,
    certificates: dict[str, Path],
    serve: Callable[..., SmtpServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = serve(implicit_tls=True, starttls=False)
    monkeypatch.setattr(smtp, "IMPLICIT_TLS_PORT", server.port)

    code, payload = _run(paths, certificates, _request(server.port))

    assert (code, payload["code"]) == (0, "smtp_passed")
    assert server.behavior.commands[0] == ("EHLO", True)


def test_ac_m2_no_authentication_without_tls(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    server = serve(starttls=False)

    code, payload = _run(paths, certificates, _request(server.port))

    assert (code, payload) == (3, {"code": "smtp_no_tls", "message_key": "smtp-test.smtp_no_tls"})
    verbs = [verb for verb, _ in server.behavior.commands]
    assert "AUTH" not in verbs
    assert "MAIL" not in verbs
    assert not paths.staged_smtp.exists()


@pytest.mark.parametrize("leaf", ["other.test", "untrusted"])
def test_ac_m2_the_certificate_and_host_name_are_checked(
    paths: Paths,
    certificates: dict[str, Path],
    serve: Callable[..., SmtpServer],
    tmp_path: Path,
    leaf: str,
) -> None:
    trust = certificates
    if leaf == "untrusted":
        (tmp_path / "other-ca").mkdir()
        trust = make_certificates(tmp_path / "other-ca")
        server = serve()
    else:
        server = serve(certificate=certificates["other.test"])

    code, payload = _run(paths, trust, _request(server.port))

    assert (code, payload["code"]) == (3, "smtp_tls_certificate")
    assert ("AUTH", True) not in server.behavior.commands
    assert not paths.staged_smtp.exists()


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"auth_reply": "535 5.7.8 Username and Password not accepted"}, "smtp_auth_refused"),
        (
            {
                "auth_reply": "535 5.7.139 Authentication unsuccessful, "
                "SmtpClientAuthentication is disabled"
            },
            "smtp_m365_auth_disabled",
        ),
        (
            {"sender_reply": "550 5.7.60 SMTP; Client does not have permissions"},
            "smtp_sender_refused",
        ),
        (
            {"recipient_reply": "550 5.1.1 The email account does not exist"},
            "smtp_recipient_refused",
        ),
    ],
    ids=["password", "m365-auth-off", "sender", "recipient"],
)
def test_ac_m3_error_classes_and_the_log_keeps_no_reply_text(
    paths: Paths,
    certificates: dict[str, Path],
    serve: Callable[..., SmtpServer],
    options: dict[str, str],
    expected: str,
) -> None:
    server = serve(**options)

    code, payload = _run(paths, certificates, _request(server.port))

    assert (code, payload["code"]) == (3, expected)
    logs = log_text(paths)
    assert f"{expected} reply 5" in logs
    assert "SmtpClientAuthentication" not in logs
    assert "does not exist" not in logs
    assert not paths.staged_smtp.exists()


def test_ac_m3_unreachable_and_implicit_tls_to_a_plain_server(
    paths: Paths,
    certificates: dict[str, Path],
    serve: Callable[..., SmtpServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreachable = _run(paths, certificates, _request(closed_port()))
    plain = serve()
    monkeypatch.setattr(smtp, "IMPLICIT_TLS_PORT", plain.port)
    no_tls = _run(paths, certificates, _request(plain.port))

    assert (unreachable[0], unreachable[1]["code"]) == (3, "smtp_unreachable")
    assert (no_tls[0], no_tls[1]["code"]) == (3, "smtp_no_tls")


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "pass\rword"},
        {"password": "pass\nword"},
        {"user": "office\x00@frontdesk.test"},
        {"sender_name": "Front Desk"},
        {"sender_name": "Front\x85Desk"},
        {"sender_name": "Front\x1bDesk"},
        {"host": "smtp.example.test;rm"},
        {"host": "smtp.example.test\r\n"},
        {"port": 0},
        {"port": "587"},
        {"port": True},
        {"admin_email": "not-an-address"},
        {"password": ""},
        {"mode": "send"},
    ],
    ids=[
        "cr",
        "lf",
        "nul",
        "line-separator",
        "nel",
        "escape",
        "host-shell",
        "host-crlf",
        "port-zero",
        "port-text",
        "port-bool",
        "admin-email",
        "user-without-password",
        "mode",
    ],
)
def test_ac_m1_bad_values_are_refused_before_any_connection(
    paths: Paths,
    certificates: dict[str, Path],
    serve: Callable[..., SmtpServer],
    changes: dict[str, Any],
) -> None:
    server = serve()

    code, payload = _run(paths, certificates, _request(server.port, **changes))

    assert (code, payload["code"]) == (2, "invalid_input")
    assert server.behavior.commands == []
    assert not paths.staged_smtp.exists()


def test_ac_m5_no_password_address_or_trace_reaches_any_log(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    server = serve()

    _run(paths, certificates, _request(server.port))

    logs = log_text(paths)
    for value in (PASSWORD.strip(), "app pass", USER, ADMIN, "frontdesk.test", "AUTH PLAIN"):
        assert value not in logs
    assert f"connect localhost:{server.port} starttls" in logs
    assert "sent over starttls" in logs


def test_ac_m4_a_failed_test_keeps_the_earlier_staged_values(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    good = serve()
    _run(paths, certificates, _request(good.port))
    before = paths.staged_smtp.read_bytes()
    bad = serve(auth_reply="535 5.7.8 nope")

    code, _ = _run(paths, certificates, _request(bad.port, sender_name="Changed"))

    assert code == 3
    assert paths.staged_smtp.read_bytes() == before


def test_ac_m6_discard_deletes_the_staged_values_and_needs_only_the_run_id(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    server = serve()
    _run(paths, certificates, _request(server.port))

    first = _run(paths, certificates, {"run_id": RUN_ID, "mode": "discard"})
    again = _run(paths, certificates, {"run_id": RUN_ID, "mode": "discard"})
    extra = _run(paths, certificates, {"run_id": RUN_ID, "mode": "discard", "password": "x" * 9})

    assert first == (0, {"code": "smtp_discarded"})
    assert again == (0, {"code": "smtp_discarded"})
    assert extra == (2, {"code": "invalid_input", "message_key": "smtp-test.invalid_input"})
    assert not paths.staged_smtp.exists()


@pytest.mark.parametrize("value", ["plain", "$HOME and $$", '"quoted" \\ back', " edge ", "a#b c"])
def test_ac_m4_staged_values_round_trip(value: str) -> None:
    values = {name: value for name in smtp_env.FIELDS}
    values["SMTP_HOST"], values["SMTP_PORT"] = "smtp.example.test", "587"

    assert smtp_env.parse(smtp_env.render(values)) == values


def test_ac_m3_a_server_with_no_usable_auth_method_refuses_the_sign_in(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    server = serve(auth_mechanisms="XOAUTH2")

    code, payload = _run(paths, certificates, _request(server.port))

    assert (code, payload["code"]) == (3, "smtp_auth_refused")
    assert not paths.staged_smtp.exists()


def test_ac_m1_a_password_that_smtp_cannot_send_is_refused_before_connecting(
    paths: Paths, certificates: dict[str, Path], serve: Callable[..., SmtpServer]
) -> None:
    server = serve()

    code, payload = _run(paths, certificates, _request(server.port, password="pässwörd-1234"))

    assert (code, payload["code"]) == (2, "invalid_input")
    assert server.behavior.commands == []
