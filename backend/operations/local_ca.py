"""Create, renew and check the installation's local CA and server certificate.

``init`` makes a root, signs one name-constrained intermediate with it and discards the root
key in memory, then issues the server certificate. ``renew`` issues a new server certificate
30 days before expiry. ``check`` verifies the chain. Output is one line of safe JSON; the
exit code is 0 (done), 2 (refused input or state) or 3 (I/O or crypto failure). No network.

``--ca-dir`` holds ``current/`` (root.crt, intermediate.crt, intermediate.key) and an
uncommitted ``.staging/``; ``--tls-dir`` holds server.crt (leaf + intermediate) and
server.key. A CA is never overwritten or repaired; a missing or mismatched leaf is reissued.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import verification
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_DAYS = 7305  # 20 years (P-5): no root key remains to sign a new intermediate.
LEAF_DAYS = 397
RENEW_DAYS = 30
BACKDATE = timedelta(minutes=5)
CA_FILES = ("intermediate.crt", "intermediate.key", "root.crt")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class LocalCAError(Exception):
    """A safe result code; the message never holds key material."""

    def __init__(self, code: str, exit_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise LocalCAError("invalid_arguments", 2)


def _validate_host(host: str) -> str:
    labels = host.split(".")
    if (
        len(host) > 253
        or len(labels) < 2
        or labels[-1] != "local"
        or not all(_LABEL.match(label) for label in labels)
    ):
        raise LocalCAError("invalid_host", 2)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise LocalCAError("invalid_host", 2)


def _fingerprint(certificate: x509.Certificate) -> str:
    return hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()


def _key_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _builder(
    subject: x509.Name, issuer: x509.Name, key: ec.EllipticCurvePrivateKey, start: datetime,
    end: datetime, issuer_key: ec.EllipticCurvePrivateKey | None,
) -> x509.CertificateBuilder:
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
    )
    if issuer_key is not None:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), False
        )
    return builder


def _ca_usage(path_length: int) -> list[tuple[x509.ExtensionType, bool]]:
    return [
        (x509.BasicConstraints(ca=True, path_length=path_length), True),
        (
            x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            True,
        ),
    ]


def _name_constraints(host: str) -> x509.NameConstraints:
    return x509.NameConstraints(
        permitted_subtrees=[x509.DNSName(host)],
        excluded_subtrees=[
            x509.IPAddress(ipaddress.ip_network("0.0.0.0/0")),
            x509.IPAddress(ipaddress.ip_network("::/0")),
        ],
    )


def _new_ca(host: str, now: datetime) -> tuple[x509.Certificate, x509.Certificate, bytes]:
    """Return the root, the intermediate and the intermediate key; the root key is dropped."""
    start, organization = now - BACKDATE, x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                                                             "Slate Operations")
    end = start + timedelta(days=CA_DAYS)
    root_name = x509.Name([organization, x509.NameAttribute(
        NameOID.COMMON_NAME, f"Slate Operations local root ({host})")])
    issuing_name = x509.Name([organization, x509.NameAttribute(
        NameOID.COMMON_NAME, f"Slate Operations local issuer ({host})")])
    root_key = ec.generate_private_key(ec.SECP256R1())
    intermediate_key = ec.generate_private_key(ec.SECP256R1())
    root_builder = _builder(root_name, root_name, root_key, start, end, None)
    for extension, critical in _ca_usage(1):
        root_builder = root_builder.add_extension(extension, critical)
    root = root_builder.sign(root_key, hashes.SHA256())
    builder = _builder(issuing_name, root_name, intermediate_key, start, end, root_key)
    for extension, critical in _ca_usage(0):
        builder = builder.add_extension(extension, critical)
    # The intermediate may issue server certificates only (W81-1; not critical, as public CAs).
    builder = builder.add_extension(_name_constraints(host), True).add_extension(
        x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False
    )
    intermediate = builder.sign(root_key, hashes.SHA256())
    del root_key  # Never serialized: "removed after signing" with no file to delete.
    return root, intermediate, _key_pem(intermediate_key)


def _new_leaf(
    host: str, intermediate: x509.Certificate, issuer_key: ec.EllipticCurvePrivateKey,
    now: datetime, leaf_days: int,
) -> tuple[x509.Certificate, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    start = now - BACKDATE
    end = min(start + timedelta(days=leaf_days), intermediate.not_valid_after_utc)
    leaf = (
        _builder(x509.Name([]), intermediate.subject, key, start, end, issuer_key)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), True)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(issuer_key, hashes.SHA256())
    )
    return leaf, _key_pem(key)


def _verify(
    root: x509.Certificate, intermediate: x509.Certificate, leaf: x509.Certificate, host: str,
    now: datetime,
) -> bool:
    verifier = (
        verification.PolicyBuilder()
        .store(verification.Store([root]))
        .time(now)
        .build_server_verifier(x509.DNSName(host))
    )
    try:
        verifier.verify(leaf, [intermediate])
    except verification.VerificationError:
        return False
    return True


def _outsider(host: str) -> str:
    """A name outside the constraint for the throwaway self-check leaf."""
    return "other.local" if host != "other.local" else "another.local"


def _self_check(
    root: x509.Certificate, intermediate: x509.Certificate, issuer_key: ec.EllipticCurvePrivateKey,
    leaf: x509.Certificate, host: str, now: datetime,
) -> None:
    """F6: the real leaf must pass and a throwaway other.local leaf must fail."""
    if not _verify(root, intermediate, leaf, host, now) or _outsider_passes(
        root, intermediate, issuer_key, host, now
    ):
        raise LocalCAError("self_check_failed", 3)


def _outsider_passes(
    root: x509.Certificate, intermediate: x509.Certificate, issuer_key: ec.EllipticCurvePrivateKey,
    host: str, now: datetime,
) -> bool:
    name = _outsider(host)
    other, _key = _new_leaf(name, intermediate, issuer_key, now, 1)
    return _verify(root, intermediate, other, name, now)


def _same_key(certificate: x509.Certificate, key: ec.EllipticCurvePrivateKey) -> bool:
    form = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return certificate.public_key().public_bytes(*form) == key.public_key().public_bytes(*form)


def _load_key(path: Path) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("not an EC key")
    return key


def _load_ca(
    current: Path, host: str, now: datetime,
) -> tuple[x509.Certificate, x509.Certificate, ec.EllipticCurvePrivateKey]:
    try:
        if sorted(path.name for path in current.iterdir()) != list(CA_FILES):
            raise ValueError("incomplete")
        root = x509.load_pem_x509_certificate((current / "root.crt").read_bytes())
        intermediate = x509.load_pem_x509_certificate((current / "intermediate.crt").read_bytes())
        key = _load_key(current / "intermediate.key")
        root.verify_directly_issued_by(root)
        intermediate.verify_directly_issued_by(root)
        constraints = intermediate.extensions.get_extension_for_class(x509.NameConstraints)
        if (
            not _same_key(intermediate, key)
            or not constraints.critical
            or constraints.value != _name_constraints(host)
            or not intermediate.not_valid_before_utc <= now < intermediate.not_valid_after_utc
        ):
            raise ValueError("foreign")
    except (OSError, ValueError, TypeError, InvalidSignature, x509.ExtensionNotFound):
        raise LocalCAError("ca_state_invalid", 2) from None
    return root, intermediate, key


def _load_leaf(
    tls_dir: Path, root: x509.Certificate, intermediate: x509.Certificate, host: str,
    now: datetime,
) -> x509.Certificate | None:
    """Return the valid installed leaf, or None when it is missing, damaged or mismatched."""
    try:
        chain = x509.load_pem_x509_certificates((tls_dir / "server.crt").read_bytes())
        key = _load_key(tls_dir / "server.key")
    except (OSError, ValueError, TypeError):
        return None
    if len(chain) != 2 or chain[1] != intermediate or not _same_key(chain[0], key):
        return None
    return chain[0] if _verify(root, intermediate, chain[0], host, now) else None


def _write_new(path: Path, data: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install_leaf(
    tls_dir: Path, leaf: x509.Certificate, key_pem: bytes, intermediate: x509.Certificate,
) -> None:
    chain = b"".join(c.public_bytes(serialization.Encoding.PEM) for c in (leaf, intermediate))
    staged = ((".server.key.new", "server.key", key_pem, 0o600),
              (".server.crt.new", "server.crt", chain, 0o644))
    for temporary, _name, _data, _mode in staged:
        (tls_dir / temporary).unlink(missing_ok=True)
    for temporary, _name, data, mode in staged:
        _write_new(tls_dir / temporary, data, mode)
    for temporary, name, _data, _mode in staged:
        (tls_dir / temporary).replace(tls_dir / name)
    _sync_directory(tls_dir)


def _create_ca(ca_dir: Path, host: str, now: datetime, leaf_days: int) -> tuple[
    x509.Certificate, x509.Certificate, ec.EllipticCurvePrivateKey, x509.Certificate, bytes
]:
    root, intermediate, key_pem = _new_ca(host, now)
    key = serialization.load_pem_private_key(key_pem, password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    leaf, leaf_key = _new_leaf(host, intermediate, key, now, leaf_days)
    _self_check(root, intermediate, key, leaf, host, now)
    staging = ca_dir / ".staging"
    staging.mkdir(mode=0o700)
    try:
        _write_new(staging / "root.crt", root.public_bytes(serialization.Encoding.PEM), 0o644)
        _write_new(
            staging / "intermediate.crt",
            intermediate.public_bytes(serialization.Encoding.PEM), 0o644,
        )
        _write_new(staging / "intermediate.key", key_pem, 0o600)
        _sync_directory(staging)
        staging.rename(ca_dir / "current")
        _sync_directory(ca_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return root, intermediate, key, leaf, leaf_key


def _result(result: str, root: x509.Certificate, leaf: x509.Certificate) -> dict[str, str]:
    return {
        "result": result,
        "root_sha256": _fingerprint(root),
        "leaf_not_after": leaf.not_valid_after_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def run(
    command: str, *, host: str, ca_dir: Path, tls_dir: Path, now: datetime,
    renew_days: int = RENEW_DAYS, leaf_days: int = LEAF_DAYS,
) -> dict[str, str]:
    """Run one command and return its safe result; raise ``LocalCAError`` to refuse."""
    host = _validate_host(host)
    if not 1 <= renew_days < leaf_days <= LEAF_DAYS:
        raise LocalCAError("invalid_arguments", 2)
    if not ca_dir.is_dir() or not tls_dir.is_dir():
        raise LocalCAError("directory_missing", 2)
    current, staging = ca_dir / "current", ca_dir / ".staging"
    if command == "init" and not current.exists():
        if any(
            (tls_dir / name).exists() or (tls_dir / name).is_symlink()
            for name in ("server.crt", "server.key")
        ):
            raise LocalCAError("ca_state_invalid", 2)  # The CA is lost; never start over.
        if staging.is_symlink() or staging.is_file():
            staging.unlink()
        elif staging.exists():
            shutil.rmtree(staging)  # Never committed, never trusted.
        root, intermediate, _key, leaf, leaf_key = _create_ca(ca_dir, host, now, leaf_days)
        _install_leaf(tls_dir, leaf, leaf_key, intermediate)
        return _result("created", root, leaf)
    root, intermediate, key = _load_ca(current, host, now)
    installed = _load_leaf(tls_dir, root, intermediate, host, now)
    if command == "check":
        if installed is None:
            raise LocalCAError("leaf_invalid", 2)
        if _outsider_passes(root, intermediate, key, host, now):
            raise LocalCAError("self_check_failed", 3)
        return _result("valid", root, installed)
    if installed is not None and (
        command == "init"
        or installed.not_valid_after_utc - now > timedelta(days=renew_days)
    ):
        return _result("exists" if command == "init" else "not_due", root, installed)
    leaf, leaf_key = _new_leaf(host, intermediate, key, now, leaf_days)
    _self_check(root, intermediate, key, leaf, host, now)
    _install_leaf(tls_dir, leaf, leaf_key, intermediate)
    return _result("created" if command == "init" else "renewed", root, leaf)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Local CA and server certificate for one installation.")
    parser.add_argument("command", choices=("init", "renew", "check"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--ca-dir", type=Path, required=True)
    parser.add_argument("--tls-dir", type=Path, required=True)
    parser.add_argument("--renew-days", type=int, default=RENEW_DAYS)
    parser.add_argument("--leaf-days", type=int, default=LEAF_DAYS)
    try:
        options = parser.parse_args(argv)
        output = run(
            options.command, host=options.host, ca_dir=options.ca_dir, tls_dir=options.tls_dir,
            now=datetime.now(UTC), renew_days=options.renew_days, leaf_days=options.leaf_days,
        )
        code = 0
    except LocalCAError as error:
        output, code = {"code": error.code}, error.exit_code
    except OSError:
        output, code = {"code": "io_failed"}, 3
    except Exception:  # Process boundary: report a safe code, never the exception text.
        output, code = {"code": "ca_failed"}, 3
    print(json.dumps(output, separators=(",", ":")))
    return code


if __name__ == "__main__":
    sys.exit(main())
