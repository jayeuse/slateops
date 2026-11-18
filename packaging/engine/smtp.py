"""``smtp-test``: send one test message by GoTrue's rules, then stage the values (plan 4.1
page 6, 3.2 rule 3, 10.7 SMTP row).

Confirmed: the pinned GoTrue (v2.196.0) links ``gopkg.in/gomail.v2`` (``Dialer.Dial``,
``Dialer.tlsConfig`` in its binary). Assumption, from gomail v2's source as known and not
re-read for this version: ``NewDialer`` sets implicit TLS when the port is 465, ``Dial``
uses STARTTLS on other ports when the server offers it, and the TLS configuration checks
the certificate against the host name; Go's PLAIN authentication refuses a password
without TLS. The engine is stricter: on a port other than 465 it requires STARTTLS, so it
never authenticates without TLS, and a pass here means GoTrue connects the same way. With
Python 3.13 and later the default context also applies strict X.509 checks, which can
refuse a nonconforming certificate that Go accepts (a false "certificate" class).

Every value is checked before any network use: CR, LF, NUL, every other line boundary and
control character are refused (W2 rule), host and port must be literal env values. The
password arrives only in the standard input JSON; it is never echoed, logged or traced
(no ``set_debuglevel``). The log keeps the class, the reply code, the host, the port and
the TLS mode. ``mode: discard`` (run ID only) deletes the staged values.

The test email goes to the administrator (DEC-0041: email is set up after the install): the
address in the stored install answers. ``admin_email`` in the request is used only when no
installation's answers exist (the old pre-install page); with neither, the job refuses
``not_installed`` before any connection.
"""

from __future__ import annotations

import re
import smtplib
import socket
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any

from engine import answers, progress, smtp_env
from engine.context import Context
from engine.core import failed, is_run_id, private_dir, refused, write_private
from engine.env_templates import TemplateError, compose_quoted, is_literal

TIMEOUT_SECONDS = 30.0
IMPLICIT_TLS_PORT = 465  # GoTrue (gomail v2): SSL when the port is 465
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST = re.compile(r"(?=.{1,253}\Z)" + _LABEL + r"(?:\." + _LABEL + r")*\Z")
_EMAIL = re.compile(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}\Z")


def _text(limit: int) -> Any:
    def check(value: Any) -> bool:
        if not isinstance(value, str) or len(value) > limit:
            return False
        try:
            compose_quoted(value)
        except TemplateError:
            return False
        return True

    return check


def _email(value: Any) -> bool:
    return _text(320)(value) and _EMAIL.match(value) is not None


KEYS = {
    "run_id": is_run_id,
    "mode": lambda value: value in ("test", "discard"),
    "host": lambda value: isinstance(value, str) and _HOST.match(value) is not None,
    "port": lambda value: (
        isinstance(value, int) and not isinstance(value, bool) and 0 < value < 65536
    ),
    # smtplib sends the user and password as ASCII; other text cannot be sent at all.
    "user": lambda value: _text(320)(value) and value.isascii(),
    "password": lambda value: _text(1024)(value) and value.isascii(),
    "sender_email": _email,
    "sender_name": _text(100),
    "admin_email": _email,
}
TEST_FIELDS = frozenset(KEYS) - {"mode", "admin_email"}
REQUIRED = frozenset({"run_id"})


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    if request.get("mode") == "discard":
        if set(request) - {"run_id", "mode"}:
            raise refused("invalid_input")
        ctx.paths.staged_smtp.unlink(missing_ok=True)
        ctx.log.line(ctx.step(1, "discard"), "INFO", "staged email settings removed")
        return {"code": "smtp_discarded"}
    if not TEST_FIELDS <= request.keys():
        raise refused("invalid_input")
    if bool(request["user"]) != bool(request["password"]):
        raise refused("invalid_input")
    stored = answers.load(ctx.paths)
    if stored is not None:
        request = {**request, "admin_email": stored["admin_email"]}
    elif "admin_email" not in request:
        raise refused("not_installed")
    values = {
        "SMTP_HOST": request["host"],
        "SMTP_PORT": str(request["port"]),
        "SMTP_ADMIN_EMAIL": request["sender_email"],
        "SMTP_USER": request["user"],
        "SMTP_PASS": request["password"],
        "SMTP_SENDER_NAME": request["sender_name"],
    }
    if not is_literal(values["SMTP_HOST"]) or not is_literal(values["SMTP_PORT"]):
        raise refused("invalid_input")
    # From here on, every log line also masks this request's values.
    ctx.redactor = ctx.redactor.with_values(
        [request["password"]],
        [request["user"], request["sender_email"], request["admin_email"]],
        words=[request["password"]],
    )
    ctx.log.redact = ctx.redactor
    progress.report(ctx, "send")
    _send(ctx, request)
    progress.report(ctx, "stage")
    folder = private_dir(ctx.paths.staged_smtp.parent)
    write_private(folder / ctx.paths.staged_smtp.name, smtp_env.render(values).encode())
    ctx.log.line(ctx.step(3, "stage"), "INFO", "staged email settings written")
    # AC-B6: M02 names the address; personal data, on standard output only (never logged).
    return {"code": "smtp_passed", "sent_to": request["admin_email"]}


def _message(request: dict[str, Any]) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((request["sender_name"], request["sender_email"]))
    message["To"] = request["admin_email"]
    message["Subject"] = "Slate Operations test email"
    message["Date"] = format_datetime(datetime.now(UTC))
    message["Message-ID"] = make_msgid(domain=request["sender_email"].rsplit("@", 1)[1])
    message.set_content(
        "This is a test email from Slate Operations setup.\n"
        "The email account works. You can close this message.\n"
    )
    return message


def _send(ctx: Context, request: dict[str, Any]) -> None:
    host, port = request["host"], request["port"]
    mode = "implicit-tls" if port == IMPLICIT_TLS_PORT else "starttls"
    step = ctx.step(2, "send")
    ctx.log.line(step, "INFO", f"connect {host}:{port} {mode}")
    context = ctx.deps.tls_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    client: smtplib.SMTP | None = None
    try:
        if port == IMPLICIT_TLS_PORT:
            client = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)
            client.ehlo()
            if not client.has_extn("starttls"):
                raise _class(ctx, step, "smtp_no_tls", None)
            client.starttls(context=context)
            client.ehlo()
        if request["user"]:
            client.login(request["user"], request["password"])
        client.send_message(_message(request), request["sender_email"], [request["admin_email"]])
        ctx.log.line(step, "INFO", f"sent over {mode}")
    except smtplib.SMTPAuthenticationError as error:
        detail = error.smtp_error if isinstance(error.smtp_error, bytes) else b""
        code = "smtp_m365_auth_disabled" if b"5.7.139" in detail else "smtp_auth_refused"
        raise _class(ctx, step, code, error.smtp_code) from None
    except smtplib.SMTPSenderRefused as error:
        raise _class(ctx, step, "smtp_sender_refused", error.smtp_code) from None
    except smtplib.SMTPRecipientsRefused as error:
        codes = [code for code, _ in error.recipients.values()]
        raise _class(ctx, step, "smtp_recipient_refused", codes[0] if codes else None) from None
    except smtplib.SMTPNotSupportedError:
        raise _class(ctx, step, "smtp_auth_refused", None) from None
    except ssl.SSLCertVerificationError:
        raise _class(ctx, step, "smtp_tls_certificate", None) from None
    except ssl.SSLError:
        raise _class(ctx, step, "smtp_no_tls", None) from None
    except smtplib.SMTPResponseException as error:
        raise _class(ctx, step, "smtp_failed", error.smtp_code) from None
    except smtplib.SMTPServerDisconnected:
        raise _class(ctx, step, "smtp_unreachable", None) from None
    except smtplib.SMTPException:
        # "No suitable authentication method found": the server offers no method we use.
        raise _class(ctx, step, "smtp_auth_refused", None) from None
    except (socket.gaierror, OSError):
        raise _class(ctx, step, "smtp_unreachable", None) from None
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass


def _class(ctx: Context, step: str, code: str, reply: int | None) -> Exception:
    """Log the class and the reply code only (never the reply text); return the error."""
    ctx.log.line(step, "WARN", f"{code} reply {reply if reply is not None else '-'}")
    return failed(code)
