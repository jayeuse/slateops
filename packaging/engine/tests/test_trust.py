"""The public trust files (TASK-0089 AC-E1 to AC-E3; R3, R6, R7, R8; plan 6.3).

A real CA from the W2 tool (``backend/operations/local_ca.py``, imported only here, as the
redaction drift test does) makes the root certificate, so the files are checked against
``local_ca``'s own ``root_sha256``.
"""

from __future__ import annotations

import hashlib
import io
import os
import plistlib
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID

from engine import trust
from engine.context import Context
from engine.core import JobError, Paths, private_dir
from engine.logs import RunLog
from engine.redaction import Redactor
from operations import local_ca

from .helpers import RUN_ID, deps, make_paths

HOST = "frontdesk-pc.local"


@pytest.fixture
def ca(tmp_path: Path) -> tuple[Paths, dict[str, str]]:
    paths = make_paths(tmp_path)
    for folder in (paths.etc / "ca", paths.etc / "tls"):
        private_dir(folder)
    result = local_ca.run(
        "init",
        host=HOST,
        ca_dir=paths.etc / "ca",
        tls_dir=paths.etc / "tls",
        now=datetime(2026, 11, 17, tzinfo=UTC),
    )
    return paths, result


def _context(paths: Paths) -> Context:
    dependencies = deps(paths)
    log = RunLog(paths, RUN_ID, "install", Redactor())
    runner = dependencies.make_runner(log)
    return Context(dependencies, "install", RUN_ID, log, runner, Redactor(), dependencies.clock())


def test_ac_e1_r7_the_security_code_is_local_cas_fingerprint_in_uppercase_pairs(
    ca: tuple[Paths, dict[str, str]],
) -> None:
    paths, result = ca

    trust.write(_context(paths), "install.06.tls")

    code = (paths.trust / "slateops-ca.sha256").read_text()
    expected = ":".join(result["root_sha256"].upper()[i : i + 2] for i in range(0, 64, 2))
    assert code == expected + "\n"
    assert len(code.strip()) == 95
    assert trust.format_fingerprint(result["root_sha256"]) == expected
    assert trust.security_code(paths) == expected


def test_ac_e1_the_certificate_is_the_root_in_der_and_the_profile_installs_it(
    ca: tuple[Paths, dict[str, str]],
) -> None:
    paths, result = ca

    trust.write(_context(paths), "install.06.tls")

    der = (paths.trust / "slateops-ca.crt").read_bytes()
    assert hashlib.sha256(der).hexdigest() == result["root_sha256"]
    profile = plistlib.load(io.BytesIO((paths.trust / "slateops.mobileconfig").read_bytes()))
    [payload] = profile["PayloadContent"]
    assert profile["PayloadType"] == "Configuration"
    assert profile["PayloadDisplayName"] == "Slate Operations"
    assert payload["PayloadType"] == "com.apple.security.root"
    assert payload["PayloadContent"] == der
    assert profile["PayloadUUID"] != payload["PayloadUUID"]


def test_ac_e1_r6_the_files_are_public_regular_files_and_the_same_root_gives_the_same_bytes(
    ca: tuple[Paths, dict[str, str]],
) -> None:
    paths, _ = ca
    trust.write(_context(paths), "install.06.tls")
    first = {path.name: path.read_bytes() for path in paths.trust.iterdir()}

    trust.write(_context(paths), "install.06.tls")

    assert sorted(first) == ["slateops-ca.crt", "slateops-ca.sha256", "slateops.mobileconfig"]
    assert {path.name: path.read_bytes() for path in paths.trust.iterdir()} == first
    assert stat.S_IMODE(paths.trust.stat().st_mode) == 0o755
    for path in paths.trust.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o644, path.name


@pytest.mark.parametrize("kind", ["file", "folder", "link"])
def test_ac_e2_any_other_entry_in_the_trust_folder_stops_the_job_and_stays(
    ca: tuple[Paths, dict[str, str]], kind: str
) -> None:
    paths, _ = ca
    private_dir(paths.trust)
    other = paths.trust / "server.key"
    if kind == "file":
        other.write_text("x")
    elif kind == "folder":
        other.mkdir()
    else:
        other.symlink_to(paths.etc / "tls" / "server.key")

    with pytest.raises(JobError) as refused:
        trust.write(_context(paths), "install.06.tls")

    assert refused.value.code == "trust_folder_unexpected"
    assert other.is_symlink() or other.exists()
    assert not (paths.trust / "slateops-ca.sha256").exists()


def test_ac_e2_a_trust_folder_that_is_a_link_is_refused(
    ca: tuple[Paths, dict[str, str]],
) -> None:
    paths, _ = ca
    os.symlink(paths.etc / "tls", paths.trust)

    with pytest.raises(JobError) as refused:
        trust.write(_context(paths), "install.06.tls")

    assert refused.value.code == "trust_folder_unexpected"
    assert sorted(path.name for path in (paths.etc / "tls").iterdir()) == [
        "server.crt",
        "server.key",
    ]


def test_ac_e3_r8_the_root_common_name_starts_with_slate_operations(
    ca: tuple[Paths, dict[str, str]],
) -> None:
    # The iPhone step says "turn on Slate Operations" (TASK-0088 contract item 6).
    paths, _ = ca
    root = x509.load_pem_x509_certificate((paths.etc / "ca/current/root.crt").read_bytes())

    [name] = root.subject.get_attributes_for_oid(NameOID.COMMON_NAME)

    assert str(name.value).startswith("Slate Operations")
