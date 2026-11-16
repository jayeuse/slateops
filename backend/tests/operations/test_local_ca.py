"""Local CA for the installer (plan W2-4, 6.3, A-4, P-5; TASK-0081)."""

import hashlib
import ipaddress
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import verification
from cryptography.x509.oid import ExtendedKeyUsageOID

from operations import local_ca

HOST = "frontdesk.local"
CA_USAGE = x509.KeyUsage(
    digital_signature=False, content_commitment=False, key_encipherment=False,
    data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
    encipher_only=False, decipher_only=False,
)
LEAF_USAGE = x509.KeyUsage(
    digital_signature=True, content_commitment=False, key_encipherment=False,
    data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
    encipher_only=False, decipher_only=False,
)
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
START = NOW - timedelta(minutes=5)


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    ca_dir.mkdir()
    tls_dir.mkdir()
    return ca_dir, tls_dir


def run(command: str, dirs: tuple[Path, Path], *, now: datetime = NOW, host: str = HOST):
    return local_ca.run(command, host=host, ca_dir=dirs[0], tls_dir=dirs[1], now=now)


def snapshot(*roots: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root.parent)): path.read_bytes()
        for root in roots for path in sorted(root.rglob("*")) if path.is_file()
    }


def certificates(dirs: tuple[Path, Path]) -> tuple[x509.Certificate, x509.Certificate, list]:
    current = dirs[0] / "current"
    root = x509.load_pem_x509_certificate((current / "root.crt").read_bytes())
    intermediate = x509.load_pem_x509_certificate((current / "intermediate.crt").read_bytes())
    chain = x509.load_pem_x509_certificates((dirs[1] / "server.crt").read_bytes())
    return root, intermediate, chain


def verify(root: x509.Certificate, chain: list[x509.Certificate], host: str, now: datetime):
    verifier = (
        verification.PolicyBuilder()
        .store(verification.Store([root]))
        .time(now)
        .build_server_verifier(x509.DNSName(host))
    )
    return verifier.verify(chain[0], chain[1:])


def foreign_leaf(
    dirs: tuple[Path, Path], *names: x509.GeneralName,
    usage: x509.ObjectIdentifier = ExtendedKeyUsageOID.SERVER_AUTH,
) -> x509.Certificate:
    """A leaf that only a holder of the intermediate key could make, for a forbidden name."""
    current = dirs[0] / "current"
    issuer_key = serialization.load_pem_private_key(
        (current / "intermediate.key").read_bytes(), password=None
    )
    assert isinstance(issuer_key, ec.EllipticCurvePrivateKey)
    issuer = x509.load_pem_x509_certificate((current / "intermediate.crt").read_bytes())
    key = ec.generate_private_key(ec.SECP256R1())
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([]))
        .issuer_name(issuer.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(START)
        .not_valid_after(START + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName(list(names)), critical=True)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            critical=False,
        )
        .sign(issuer_key, hashes.SHA256())
    )


def test_w2_4_p_5_init_issues_the_name_constrained_chain(dirs) -> None:
    result = run("init", dirs)
    root, intermediate, chain = certificates(dirs)
    leaf = chain[0]
    assert result == {
        "result": "created",
        "root_sha256": hashlib.sha256(root.public_bytes(serialization.Encoding.DER)).hexdigest(),
        "leaf_not_after": "2027-12-18T11:55:00Z",
    }
    assert sorted(path.name for path in (dirs[0] / "current").iterdir()) == [
        "intermediate.crt", "intermediate.key", "root.crt",
    ]
    assert sorted(path.name for path in dirs[1].iterdir()) == ["server.crt", "server.key"]
    if os.name != "nt":
        assert (dirs[0] / "current" / "intermediate.key").stat().st_mode & 0o777 == 0o600
        assert (dirs[1] / "server.key").stat().st_mode & 0o777 == 0o600
    # P-5: 20 years for the root and the intermediate; no root key remains to renew either.
    assert (root.not_valid_before_utc, root.not_valid_after_utc) == (
        START, START + timedelta(days=7305)
    )
    assert intermediate.not_valid_after_utc == root.not_valid_after_utc
    assert root.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length == 1
    for certificate, usage in ((root, CA_USAGE), (intermediate, CA_USAGE), (leaf, LEAF_USAGE)):
        key_usage = certificate.extensions.get_extension_for_class(x509.KeyUsage)
        assert key_usage.critical and key_usage.value == usage
    assert ExtendedKeyUsageOID.SERVER_AUTH not in [
        oid for extension in root.extensions if isinstance(extension.value, x509.ExtendedKeyUsage)
        for oid in extension.value
    ]
    issuing_usage = intermediate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    assert not issuing_usage.critical
    assert list(issuing_usage.value) == [ExtendedKeyUsageOID.SERVER_AUTH]
    constraints = intermediate.extensions.get_extension_for_class(x509.NameConstraints)
    assert constraints.critical
    assert constraints.value.permitted_subtrees == [x509.DNSName(HOST)]
    assert constraints.value.excluded_subtrees == [
        x509.IPAddress(ipaddress.ip_network("0.0.0.0/0")),
        x509.IPAddress(ipaddress.ip_network("::/0")),
    ]
    assert intermediate.extensions.get_extension_for_class(
        x509.BasicConstraints
    ).value.path_length == 0
    assert chain[1] == intermediate and len(chain) == 2
    assert leaf.subject == x509.Name([])
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.critical and list(san.value) == [x509.DNSName(HOST)]
    assert leaf.not_valid_after_utc - leaf.not_valid_before_utc == timedelta(days=397)
    assert not leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert list(leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [
        ExtendedKeyUsageOID.SERVER_AUTH
    ]


def test_w2_4_chain_verifies_only_for_the_host(dirs) -> None:
    run("init", dirs)
    root, _intermediate, chain = certificates(dirs)
    assert verify(root, chain, HOST, NOW)
    # The IP leaf also names the permitted host: only the excluded IP subtree rejects it.
    for names, host in (
        ((x509.DNSName("other.local"),), "other.local"),
        ((x509.DNSName(HOST), x509.IPAddress(ipaddress.ip_address("192.168.1.5"))), HOST),
    ):
        with pytest.raises(verification.VerificationError):
            verify(root, [foreign_leaf(dirs, *names), chain[1]], host, NOW)


def test_w2_4_root_private_key_never_reaches_disk(dirs) -> None:
    run("init", dirs)
    root, _intermediate, _chain = certificates(dirs)
    root_public = root.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    keys = [
        serialization.load_pem_private_key(path.read_bytes(), password=None)
        for directory in dirs for path in directory.rglob("*")
        if path.is_file() and b"PRIVATE KEY" in path.read_bytes()
    ]
    assert len(keys) == 2
    assert all(
        key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ) != root_public
        for key in keys
    )


def test_w2_4_renew_replaces_the_leaf_only_30_days_before_expiry(dirs) -> None:
    run("init", dirs)
    before = snapshot(*dirs)
    leaf_end = START + timedelta(days=397)
    assert run("renew", dirs, now=leaf_end - timedelta(days=30, seconds=1))["result"] == "not_due"
    assert snapshot(*dirs) == before
    result = run("renew", dirs, now=leaf_end - timedelta(days=30))
    after = snapshot(*dirs)
    assert result["result"] == "renewed"
    assert {name: after[name] for name in after if name.startswith("ca/")} == {
        name: before[name] for name in before if name.startswith("ca/")
    }
    assert after["tls/server.key"] != before["tls/server.key"]
    root, _intermediate, chain = certificates(dirs)
    assert verify(root, chain, HOST, leaf_end)


def test_w2_3_init_keeps_a_complete_installation(dirs) -> None:
    first = run("init", dirs)
    before = snapshot(*dirs)
    assert run("init", dirs)["result"] == "exists"
    assert snapshot(*dirs) == before
    assert run("check", dirs) == {**first, "result": "valid"}


def test_w2_3_init_discards_an_uncommitted_staging_folder(dirs) -> None:
    staging = dirs[0] / ".staging"
    staging.mkdir()
    (staging / "root.crt").write_text("interrupted", encoding="utf-8")
    assert run("init", dirs)["result"] == "created"
    assert sorted(path.name for path in dirs[0].iterdir()) == ["current"]


@pytest.mark.parametrize("damage", ["missing", "other-key"], ids=["leaf-missing", "leaf-mismatch"])
def test_w2_3_init_reissues_a_missing_or_mismatched_leaf_from_the_same_ca(dirs, damage) -> None:
    first = run("init", dirs)
    ca_before = snapshot(dirs[0])
    if damage == "missing":
        shutil.rmtree(dirs[1])
        dirs[1].mkdir()
    else:
        other = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        (dirs[1] / "server.key").write_bytes(other)
    with pytest.raises(local_ca.LocalCAError) as raised:
        run("check", dirs)
    assert (raised.value.code, raised.value.exit_code) == ("leaf_invalid", 2)
    result = run("init", dirs)
    assert (result["result"], result["root_sha256"]) == ("created", first["root_sha256"])
    assert snapshot(dirs[0]) == ca_before
    assert run("check", dirs)["result"] == "valid"


@pytest.mark.parametrize("damage", ["incomplete", "foreign"])
def test_w2_3_init_refuses_an_incomplete_or_foreign_ca(dirs, tmp_path, damage) -> None:
    if damage == "incomplete":
        run("init", dirs)
        (dirs[0] / "current" / "intermediate.key").unlink()
    else:
        other = (tmp_path / "other-ca", tmp_path / "other-tls")
        for path in other:
            path.mkdir()
        run("init", other, host="other.local")
        shutil.copytree(other[0] / "current", dirs[0] / "current")
    before = snapshot(*dirs)
    for command in ("init", "renew", "check"):
        with pytest.raises(local_ca.LocalCAError) as raised:
            run(command, dirs)
        assert (raised.value.code, raised.value.exit_code) == ("ca_state_invalid", 2)
    assert snapshot(*dirs) == before


@pytest.mark.parametrize(
    "host",
    ["FrontDesk.local", "frontdesk.lan", "192.168.1.5", "-bad.local", "a..local", ".local",
     "front_desk.local", "a" * 64 + ".local"],
)
def test_w2_4_refuses_a_host_that_is_not_one_lowercase_local_name(dirs, host) -> None:
    with pytest.raises(local_ca.LocalCAError) as raised:
        run("init", dirs, host=host)
    assert (raised.value.code, raised.value.exit_code) == ("invalid_host", 2)
    assert snapshot(*dirs) == {}


def arguments(dirs: tuple[Path, Path], command: str = "init", host: str = HOST) -> list[str]:
    return [command, "--host", host, "--ca-dir", str(dirs[0]), "--tls-dir", str(dirs[1])]


def test_w2_5_command_prints_one_line_of_safe_json(dirs, capsys) -> None:
    assert local_ca.main(arguments(dirs)) == 0
    output = capsys.readouterr()
    lines = output.out.splitlines()
    assert len(lines) == 1 and output.err == ""
    assert json.loads(lines[0]).keys() == {"result", "root_sha256", "leaf_not_after"}
    secrets_on_disk = [
        path.read_text(encoding="utf-8") for path in (
            dirs[0] / "current" / "intermediate.key", dirs[1] / "server.key",
        )
    ]
    assert all(secret not in output.out for secret in secrets_on_disk)
    assert "PRIVATE" not in output.out and "BEGIN" not in output.out


@pytest.mark.parametrize(
    ("argv", "code", "exit_code"),
    [
        (["init", "--host", "192.168.1.5"], "invalid_host", 2),
        (["init", "--leaf-days", "398"], "invalid_arguments", 2),
        (["init", "--renew-days", "397"], "invalid_arguments", 2),
        (["rotate"], "invalid_arguments", 2),
    ],
    ids=["ip-host", "leaf-too-long", "renew-not-below-leaf", "unknown-command"],
)
def test_w2_5_refusals_print_a_safe_code(dirs, capsys, argv, code, exit_code) -> None:
    command, *rest = argv
    full = [*arguments(dirs, command), *rest] if command != "rotate" else argv
    assert local_ca.main(full) == exit_code
    output = capsys.readouterr()
    assert json.loads(output.out) == {"code": code}
    assert snapshot(*dirs) == {}


def test_w2_5_write_failure_exits_3_and_commits_nothing(dirs, capsys, monkeypatch) -> None:
    def fail(*_arguments: object, **_options: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(local_ca, "_write_new", fail)
    assert local_ca.main(arguments(dirs)) == 3
    assert json.loads(capsys.readouterr().out) == {"code": "io_failed"}
    assert not (dirs[0] / "current").exists()
    assert list(dirs[1].iterdir()) == []


def openssl_verify(dirs: tuple[Path, Path], leaf: x509.Certificate, *purpose: str) -> int:
    folder = dirs[0].parent
    (folder / "leaf.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    current = dirs[0] / "current"
    assert shutil.which("openssl") is not None, "the W81-1 test needs the openssl command"
    return subprocess.run(
        [
            "openssl", "verify", "-attime", str(int(NOW.timestamp())),
            "-CAfile", str(current / "root.crt"), "-untrusted", str(current / "intermediate.crt"),
            *purpose, str(folder / "leaf.pem"),
        ],
        capture_output=True, check=False, timeout=30,
    ).returncode


def test_w2_4_w81_1_intermediate_issues_only_server_certificates(dirs) -> None:
    run("init", dirs)
    _root, _intermediate, chain = certificates(dirs)
    assert openssl_verify(dirs, chain[0], "-purpose", "sslserver", "-verify_hostname", HOST) == 0
    for usage, purpose in (
        (ExtendedKeyUsageOID.CLIENT_AUTH, "sslclient"),
        (ExtendedKeyUsageOID.EMAIL_PROTECTION, "smimesign"),
    ):
        leaf = foreign_leaf(dirs, x509.DNSName(HOST), usage=usage)
        assert openssl_verify(dirs, leaf, "-purpose", purpose) != 0, purpose


def write_ca(dirs: tuple[Path, Path], constraints: x509.NameConstraints, critical: bool) -> None:
    """Commit a CA whose intermediate differs from the profile only in its name constraints."""
    start = START
    end = start + timedelta(days=7305)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "test")])
    root_key = ec.generate_private_key(ec.SECP256R1())
    key = ec.generate_private_key(ec.SECP256R1())
    root_builder = local_ca._builder(name, name, root_key, start, end, None)
    for extension, flag in local_ca._ca_usage(1):
        root_builder = root_builder.add_extension(extension, flag)
    root = root_builder.sign(root_key, hashes.SHA256())
    builder = local_ca._builder(name, name, key, start, end, root_key)
    for extension, flag in local_ca._ca_usage(0):
        builder = builder.add_extension(extension, flag)
    intermediate = builder.add_extension(constraints, critical).sign(root_key, hashes.SHA256())
    current = dirs[0] / "current"
    current.mkdir()
    (current / "root.crt").write_bytes(root.public_bytes(serialization.Encoding.PEM))
    (current / "intermediate.crt").write_bytes(
        intermediate.public_bytes(serialization.Encoding.PEM)
    )
    (current / "intermediate.key").write_bytes(local_ca._key_pem(key))


@pytest.mark.parametrize(
    ("excluded", "critical"),
    [
        (
            [x509.IPAddress(ipaddress.ip_network("0.0.0.0/0")),
             x509.IPAddress(ipaddress.ip_network("::/0"))],
            False,
        ),
        ([x509.IPAddress(ipaddress.ip_network("0.0.0.0/0"))], True),
        (None, True),
    ],
    ids=["not-critical", "ipv6-not-excluded", "no-exclusion"],
)
def test_w2_3_n_2_init_refuses_a_ca_with_other_name_constraints(dirs, excluded, critical) -> None:
    write_ca(dirs, x509.NameConstraints([x509.DNSName(HOST)], excluded), critical)
    before = snapshot(*dirs)
    with pytest.raises(local_ca.LocalCAError) as raised:
        run("init", dirs)
    assert (raised.value.code, raised.value.exit_code) == ("ca_state_invalid", 2)
    assert snapshot(*dirs) == before


@pytest.mark.parametrize("left", ["server.crt", "server.key"])
def test_w2_3_n_3_init_refuses_a_lost_ca_while_a_server_file_remains(dirs, left) -> None:
    run("init", dirs)
    shutil.rmtree(dirs[0] / "current")
    for name in {"server.crt", "server.key"} - {left}:
        (dirs[1] / name).unlink()
    before = snapshot(*dirs)
    with pytest.raises(local_ca.LocalCAError) as raised:
        run("init", dirs)
    assert (raised.value.code, raised.value.exit_code) == ("ca_state_invalid", 2)
    assert snapshot(*dirs) == before
