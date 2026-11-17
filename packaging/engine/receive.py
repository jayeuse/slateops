"""``receive``: take the setup payload as a tar stream and keep only what the signed
manifest proves (plan 3.2 rule 1, 5.2, W5b-8; W4 carries).

Wire contract (W7): standard input is one tar stream. Its first member is ``request.json``
(``run_id``, ``setup_version``; at most 4 KiB). The other members are exactly the signed
manifest, its sigstore bundle, the engine bundle and our two image archives of that
version, each a regular file within its limit; the stream has a total limit.

Order: read the request; check the free space; clear old staging; stage each part into a
new root-only folder with ``O_EXCL | O_NOFOLLOW`` while hashing it; verify the manifest
signature with cosign (exact identity, exact issuer, no skip option) before any manifest
field is read; check the schema and the version; compare each SHA-256; ``docker load``
each archive and check the loaded image by its manifest digest (containerd store); keep
the manifest, its signature and the engine bundle; delete the staging on every path.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import IO, Any, BinaryIO

from engine import release
from engine.context import Context
from engine.core import RUN_ID, Paths, failed, is_run_id, is_version, private_dir, refused

REQUEST = "request.json"
REQUEST_LIMIT = 4 * 1024
GIB = 1024**3
MIB = 1024**2
IMAGE_LIMIT = 2 * GIB  # a release asset is below 2 GiB (plan 5.2)
TOTAL_LIMIT = 2 * IMAGE_LIMIT + 66 * MIB + REQUEST_LIMIT
STREAM_LIMIT = TOTAL_LIMIT + 16 * MIB  # tar headers, padding and end blocks
# Planning value: the staged parts plus the unpacked images of one load, with room left.
MIN_FREE_BYTES = 12 * GIB
RESERVE_BYTES = 1 * GIB
CHUNK = 1024 * 1024
ISSUER = "https://token.actions.githubusercontent.com"
IDENTITY = (
    "https://github.com/" + release.REPOSITORY + "/.github/workflows/release.yml@refs/tags/v{}"
)
ROLES = (("server", "slateops-server"), ("caddy", "slateops-caddy"))
# cosign texts that mean "could not reach Sigstore", not "bad signature".
_UNREACHABLE = ("no such host", "dial tcp", "i/o timeout", "connection refused", "tls handshake")


def expected_parts(version: str) -> dict[str, int]:
    return {
        release.MANIFEST: MIB,
        release.SIGNATURE: MIB,
        release.bundle_name(version): 64 * MIB,
        **{release.archive_name(name, version): IMAGE_LIMIT for _, name in ROLES},
    }


class LimitedReader:
    """Refuse the stream once it passes ``limit`` bytes."""

    def __init__(self, stream: BinaryIO, limit: int) -> None:
        self.stream, self.limit, self.count = stream, limit, 0

    def read(self, size: int = -1) -> bytes:
        allowed = self.limit - self.count + 1
        data = self.stream.read(allowed if size < 0 else min(size, allowed))
        self.count += len(data)
        if self.count > self.limit:
            raise refused("payload_too_large")
        return data


def read_request(stream: BinaryIO) -> dict[str, Any]:
    """Open the tar stream and read its first member, ``request.json``."""
    reader = LimitedReader(stream, STREAM_LIMIT)
    try:
        tar = tarfile.open(fileobj=reader, mode="r|")  # type: ignore[call-overload]
        member = tar.next()
        if member is None or member.name != REQUEST or not member.isreg():
            raise refused("invalid_input")
        if member.size > REQUEST_LIMIT:
            raise refused("invalid_input")
        file = tar.extractfile(member)
        request = json.loads(file.read(REQUEST_LIMIT + 1)) if file else None
    except (tarfile.TarError, ValueError, UnicodeDecodeError) as error:
        raise refused("invalid_input") from error
    if (
        not isinstance(request, dict)
        or set(request) != {"run_id", "setup_version"}
        or not is_run_id(request["run_id"])
        or not is_version(request["setup_version"])
    ):
        raise refused("invalid_input")
    return {**request, "_tar": tar}


def _clear_old_staging(paths: Paths) -> None:
    for entry in private_dir(paths.staging).iterdir():
        if RUN_ID.match(entry.name) and entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)


def discard_staging(paths: Paths, ctx: Context | None) -> None:
    if ctx is None:
        return
    folder = paths.staging / ctx.run_id
    if folder.is_dir() and not folder.is_symlink():
        shutil.rmtree(folder)


def _store(source: IO[bytes], target: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        while chunk := source.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
            file.write(chunk)
        file.flush()
        os.fsync(file.fileno())
    return digest.hexdigest(), size


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths, version = ctx.paths, request["setup_version"]
    tar: tarfile.TarFile = request["_tar"]
    free = ctx.deps.disk_free(private_dir(paths.state))
    ctx.log.line(ctx.step(1, "space"), "INFO", f"free {free} bytes, need {MIN_FREE_BYTES}")
    if free < MIN_FREE_BYTES:
        raise failed("insufficient_space")
    _clear_old_staging(paths)
    staging = paths.staging / ctx.run_id
    staging.mkdir(mode=0o700)
    received = _stage(ctx, tar, staging, expected_parts(version))
    _verify_signature(ctx, staging, version)
    manifest = _manifest(staging / release.MANIFEST, version)
    _compare(manifest, received, version)
    for role, name in ROLES:
        entry = manifest["images"][role]
        _load(ctx, staging / release.archive_name(name, version), entry["ref"], role)
    keep = private_dir(release.release_folder(paths, version))
    for name in (release.MANIFEST, release.SIGNATURE, release.bundle_name(version)):
        os.replace(staging / name, keep / name)
    ctx.log.line(ctx.step(6, "keep"), "INFO", f"kept the verified release {version}")
    return {"code": "received", "version": version}


def _stage(
    ctx: Context, tar: tarfile.TarFile, staging: Path, expected: dict[str, int]
) -> dict[str, tuple[str, int]]:
    step = ctx.step(2, "stage")
    received: dict[str, tuple[str, int]] = {}
    total = 0
    try:
        while (member := tar.next()) is not None:
            name = member.name
            if name not in expected or name in received or not member.isreg():
                ctx.log.line(step, "WARN", f"unexpected part {name!r}")
                raise refused("payload_unexpected_part")
            total += member.size
            if member.size > expected[name] or total > TOTAL_LIMIT:
                raise refused("payload_too_large")
            if ctx.deps.disk_free(staging) < member.size + RESERVE_BYTES:
                raise failed("insufficient_space")
            source = tar.extractfile(member)
            if source is None:
                raise refused("payload_unexpected_part")
            received[name] = _store(source, staging / name)
            ctx.log.line(step, "INFO", f"part {name}: {received[name][1]} bytes")
    except tarfile.TarError as error:
        raise refused("payload_invalid") from error
    if set(received) != set(expected):
        raise refused("payload_incomplete")
    return received


def _verify_signature(ctx: Context, staging: Path, version: str) -> None:
    argv = [
        "cosign",
        "verify-blob",
        "--bundle",
        str(staging / release.SIGNATURE),
        "--certificate-identity",
        IDENTITY.format(version),
        "--certificate-oidc-issuer",
        ISSUER,
        str(staging / release.MANIFEST),
    ]
    result = ctx.runner.run(ctx.step(3, "signature"), argv, timeout=300)
    if result.ok:
        return
    text = result.stderr.decode("utf-8", errors="replace").lower()
    if result.returncode is None or any(marker in text for marker in _UNREACHABLE):
        raise failed("manifest_check_unreachable")
    raise refused("manifest_signature_invalid")


def _manifest(path: Path, version: str) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise refused("manifest_invalid") from error
    if not isinstance(manifest, dict):
        raise refused("manifest_invalid")
    schema = manifest.get("schema_version")
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise refused("manifest_invalid")
    if schema != release.SCHEMA_VERSION:
        raise refused("manifest_unsupported")
    if manifest.get("version") != version:
        raise refused("version_mismatch")
    return manifest


def _compare(manifest: dict[str, Any], received: dict[str, tuple[str, int]], version: str) -> None:
    images = manifest.get("images")
    bundle = manifest.get("engine_bundle")
    if not isinstance(images, dict) or not isinstance(bundle, dict):
        raise refused("manifest_invalid")
    entries: list[tuple[str, Any, str]] = [
        (role, images.get(role), release.archive_name(name, version)) for role, name in ROLES
    ]
    entries.append(("engine_bundle", bundle, release.bundle_name(version)))
    for part, entry, archive in entries:
        if not isinstance(entry, dict) or entry.get("archive") != archive:
            raise refused("manifest_invalid", part=part)
        sha256, size = received[archive]
        if entry.get("sha256") != sha256 or entry.get("size") != size:
            raise refused("payload_mismatch", part=part)
    for role, name in ROLES:
        match = release.REFERENCE.match(str(images[role].get("ref", "")))
        if (
            match is None
            or match.group("tag") != version
            or not match.group("name").endswith(f"/{name}")
        ):
            raise refused("manifest_invalid", part=role)


def _load(ctx: Context, archive: Path, reference: str, role: str) -> None:
    step = ctx.step(5, "load")
    match = release.REFERENCE.match(reference)
    if match is None:
        raise refused("manifest_invalid", part=role)
    tagged, digest = f"{match.group('name')}:{match.group('tag')}", match.group("digest")
    loaded = ctx.runner.run(
        step, ["docker", "load", "--quiet", "--input", str(archive)], timeout=1800
    )
    if not loaded.ok:
        raise failed("image_load_failed", part=role)
    archive.unlink()
    inspect = ctx.runner.run(
        step,
        [
            "docker",
            "image",
            "inspect",
            "--platform",
            "linux/amd64",
            "--format",
            "{{.Id}} {{json .RepoDigests}}",
            tagged,
        ],
        timeout=60,
    )
    if not inspect.ok:
        raise failed("image_check_failed", part=role)
    found = inspect.text().split(" ", 1)[0].strip()
    if found != digest:
        ctx.log.line(step, "ERROR", f"{role}: loaded {found}, manifest {digest}")
        ctx.runner.run(step, ["docker", "image", "rm", tagged], timeout=120)
        raise refused("image_digest_mismatch", part=role)
    ctx.log.line(step, "INFO", f"{role}: {tagged} is {digest}")
