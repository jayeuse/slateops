"""The public trust files that Caddy serves (plan 6.3, W6a; TASK-0089 R3, R6, R7, R9).

``/etc/slateops/trust/`` (root, 0755) holds exactly three regular files (0644), all made from
the root certificate ``/etc/slateops/ca/current/root.crt``:

- ``slateops-ca.sha256``: the security code, the SHA-256 of the root's DER as 32 uppercase
  hexadecimal pairs joined by ``:`` (95 characters), one line. The trust page shows it
  (``readFile``), and W8 shows the same value from the install result (R7: one formatter).
- ``slateops-ca.crt``: the root in DER (``application/x-x509-ca-cert``).
- ``slateops.mobileconfig``: an unsigned Apple configuration profile with one
  ``com.apple.security.root`` payload. Its identifiers and UUIDs come from the fingerprint, so
  the same root always gives the same bytes.

The folder is a sibling of ``tls/`` and ``ca/`` and is mounted read-only into Caddy as the
template root. Any other entry in it (a file, a link or a folder) stops the job: the engine
never repairs it (plan 6.1). Each file is written to a new temporary file and renamed, so
Caddy never reads half a file.
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import ssl
import stat
import uuid
from pathlib import Path

from engine.context import Context
from engine.core import Paths, private_dir, refused

CODE = "slateops-ca.sha256"
CERTIFICATE = "slateops-ca.crt"
PROFILE = "slateops.mobileconfig"
NAMES = frozenset({CODE, CERTIFICATE, PROFILE})
IDENTIFIER = "local.slateops.trust"  # Proposed; Apple does not check the domain


def format_fingerprint(hex_digest: str) -> str:
    """``local_ca``'s lowercase SHA-256 as uppercase pairs joined by ``:`` (R7)."""
    upper = hex_digest.upper()
    return ":".join(upper[index : index + 2] for index in range(0, len(upper), 2))


def root_der(paths: Paths) -> bytes:
    pem = (paths.etc / "ca" / "current" / "root.crt").read_text(encoding="ascii")
    return ssl.PEM_cert_to_DER_cert(pem)


def security_code(paths: Paths) -> str:
    return format_fingerprint(hashlib.sha256(root_der(paths)).hexdigest())


def profile(der: bytes) -> bytes:
    fingerprint = hashlib.sha256(der).hexdigest()

    def unique(kind: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{IDENTIFIER}:{kind}:{fingerprint}")).upper()

    content = {
        "PayloadContent": [
            {
                "PayloadCertificateFileName": CERTIFICATE,
                "PayloadContent": der,
                "PayloadDescription": "Adds the Slate Operations root certificate.",
                "PayloadDisplayName": "Slate Operations local root",
                "PayloadIdentifier": f"{IDENTIFIER}.root.{fingerprint[:16]}",
                "PayloadType": "com.apple.security.root",
                "PayloadUUID": unique("root"),
                "PayloadVersion": 1,
            }
        ],
        "PayloadDescription": "Lets this device open Slate Operations on the local network.",
        "PayloadDisplayName": "Slate Operations",
        "PayloadIdentifier": f"{IDENTIFIER}.{fingerprint[:16]}",
        "PayloadRemovalDisallowed": False,
        "PayloadType": "Configuration",
        "PayloadUUID": unique("profile"),
        "PayloadVersion": 1,
    }
    return plistlib.dumps(content, fmt=plistlib.FMT_XML, sort_keys=True)


def contents(paths: Paths) -> dict[str, bytes]:
    der = root_der(paths)
    code = format_fingerprint(hashlib.sha256(der).hexdigest())
    return {CODE: (code + "\n").encode("ascii"), CERTIFICATE: der, PROFILE: profile(der)}


def _check_folder(paths: Paths) -> None:
    """R3: the folder is a real folder beside ``tls/`` and ``ca/`` and holds no other entry."""
    folder = paths.trust
    for private in (paths.etc / "tls", paths.etc / "ca"):
        if folder == private or folder in private.parents or private in folder.parents:
            raise refused("trust_folder_unexpected")
    if folder.is_symlink():
        raise refused("trust_folder_unexpected")
    private_dir(paths.etc)
    folder.mkdir(mode=0o755, exist_ok=True)
    if not stat.S_ISDIR(folder.lstat().st_mode):
        raise refused("trust_folder_unexpected")
    os.chmod(folder, 0o755)
    for entry in folder.iterdir():
        if entry.name.startswith(".") and entry.name.endswith(".new") and entry.is_file():
            entry.unlink()  # a temporary file of an interrupted write of this module
            continue
        if entry.name not in NAMES or entry.is_symlink() or not entry.is_file():
            raise refused("trust_folder_unexpected", part=entry.name[:60])


def _publish(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.new")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def write(ctx: Context, step: str) -> str:
    """Write the three files (R6); return the security code."""
    paths = ctx.paths
    files = contents(paths)
    _check_folder(paths)
    for name, data in sorted(files.items()):
        _publish(paths.trust / name, data)
    directory = os.open(paths.trust, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    code = files[CODE].decode("ascii").strip()
    ctx.log.line(step, "INFO", f"trust files written; security code {code}")
    return code
