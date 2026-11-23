"""A local SMTP server for the ``smtp-test`` tests: STARTTLS or implicit TLS, AUTH PLAIN and
LOGIN, and scripted refusals. Certificates are made at run time."""

from __future__ import annotations

import base64
import datetime as dt
import socket
import socketserver
import ssl
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def _name(text: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])


def make_certificates(folder: Path) -> dict[str, Path]:
    """A test CA, a leaf for ``localhost`` and a leaf for ``other.test``; PEM files."""
    now = dt.datetime.now(dt.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("engine test CA"))
        .issuer_name(_name("engine test CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    files = {"ca": folder / "ca.pem"}
    files["ca"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for host in ("localhost", "other.test"):
        key = ec.generate_private_key(ec.SECP256R1())
        leaf = (
            x509.CertificateBuilder()
            .subject_name(_name(host))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
            )
            .sign(ca_key, hashes.SHA256())
        )
        chain = folder / f"{host}.pem"
        chain.write_bytes(
            leaf.public_bytes(serialization.Encoding.PEM)
            + key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        files[host] = chain
    return files


@dataclass
class Behavior:
    certificate: Path
    implicit_tls: bool = False
    starttls: bool = True
    auth: bool = True
    auth_mechanisms: str = "PLAIN LOGIN"
    user: str = ""
    password: str = ""
    auth_reply: str | None = None
    sender_reply: str | None = None
    recipient_reply: str | None = None
    commands: list[tuple[str, bool]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


class _Handler(socketserver.StreamRequestHandler):
    server: _Server

    def setup(self) -> None:
        behavior = self.server.behavior
        self.tls = behavior.implicit_tls
        if self.tls:
            self.request = self.server.tls.wrap_socket(self.request, server_side=True)
        super().setup()

    def say(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")
        self.wfile.flush()

    def handle(self) -> None:
        behavior = self.server.behavior
        sender, recipients = "", []
        self.say("220 fake ESMTP")
        while line := self.rfile.readline():
            text = line.decode(errors="replace").rstrip("\r\n")
            verb = text.split(" ", 1)[0].upper()
            behavior.commands.append((verb, self.tls))
            if verb in ("EHLO", "HELO"):
                lines = ["fake"]
                if behavior.starttls and not self.tls:
                    lines.append("STARTTLS")
                if behavior.auth:
                    lines.append(f"AUTH {behavior.auth_mechanisms}")
                lines.append("SIZE 1000000")
                for index, item in enumerate(lines):
                    self.say(f"250{'-' if index < len(lines) - 1 else ' '}{item}")
            elif verb == "STARTTLS":
                self.say("220 go ahead")
                self.request = self.server.tls.wrap_socket(self.request, server_side=True)
                self.rfile = self.request.makefile("rb")
                self.wfile = self.request.makefile("wb")
                self.tls = True
            elif verb == "AUTH":
                if behavior.auth_reply:
                    self.say(behavior.auth_reply)
                    continue
                parts = text.split(" ")
                user, password = "", ""
                if len(parts) >= 3 and parts[1].upper() == "PLAIN":
                    _, user, password = base64.b64decode(parts[2]).decode().split("\0")
                good = (user, password) == (behavior.user, behavior.password)
                self.say("235 2.7.0 accepted" if good else "535 5.7.8 bad credentials")
            elif verb == "MAIL":
                sender = text
                self.say(behavior.sender_reply or "250 2.1.0 ok")
            elif verb == "RCPT":
                recipients.append(text)
                self.say(behavior.recipient_reply or "250 2.1.5 ok")
            elif verb == "DATA":
                self.say("354 go ahead")
                body = []
                while (data := self.rfile.readline()) not in (b".\r\n", b""):
                    body.append(data.decode(errors="replace"))
                behavior.messages.append(
                    {"from": sender, "to": recipients, "data": "".join(body), "tls": self.tls}
                )
                self.say("250 2.0.0 queued")
            elif verb == "QUIT":
                self.say("221 bye")
                return
            else:
                self.say("250 ok")


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, behavior: Behavior) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.behavior = behavior
        self.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.tls.load_cert_chain(behavior.certificate)


class SmtpServer:
    def __init__(self, behavior: Behavior) -> None:
        self.behavior = behavior
        self.server = _Server(behavior)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )

    def __enter__(self) -> SmtpServer:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


def closed_port() -> int:
    """A local port with nothing listening."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
