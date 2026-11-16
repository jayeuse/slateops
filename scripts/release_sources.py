"""Source packages that the release attaches (docs/plans/windows-installer.md W4-7, H4).

`.github/workflows/release.yml` (job `source-packages`) runs `fetch` once. It reads the
package databases that the notices job copied out of the Linux image, the server image
and the Caddy image, then:

1. Debian: for each source package and version of the Linux image and the server image
   (Docker's packages excluded: their source is upstream, SOURCE-OFFER.txt), it asks
   snapshot.debian.org for the source files, downloads each one, checks it against its
   SHA-1 (snapshot's file name) and against the SHA-256 in the package's .dsc.
2. Alpine: for each origin of the Caddy image, it downloads the aports folder at the
   commit that built the package (the apk database's `c:` field), and each upstream file
   that the APKBUILD names from Alpine's distfiles, checked against the APKBUILD SHA-512.
3. It packs whole packages into `slateops-sources-<version>-<n>.tar` assets, each below
   ASSET_LIMIT (GitHub refuses a release asset of 2 GiB or more).

A source that is not published, or a file that differs from its hash, stops the run.
Every download is logged (plan section 10). Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import logging
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Collection, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

# Run as a file, the script directory is first on sys.path; the repository root lets both
# ways (file and `scripts.release_sources`) share the package models.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release_artifacts import (  # noqa: E402
    DOCKER_SOURCES,
    AlpinePackage,
    alpine_packages,
    debian_packages,
)

LOG = logging.getLogger("release_sources")
SNAPSHOT = "https://snapshot.debian.org"
APORTS_ARCHIVE = "https://gitlab.alpinelinux.org/alpine/aports/-/archive"
DISTFILES = "https://distfiles.alpinelinux.org/distfiles"
# GitHub refuses a release asset of 2 GiB or more; keep a margin below it.
ASSET_LIMIT = 1900 * 1024**2
USER_AGENT = "slateops-release-sources"
_SAFE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+~@=,-]*")
_CHECKSUMS = re.compile(r"""sha512sums=(["'])(.*?)\1""", re.DOTALL)

# Answers that a later try can change (run 43925764551: a GitLab answer that was not a
# 404 became "no folder"). 403 is here as an assumption: services answer abuse limits on
# shared runner addresses with it, and a lasting 403 still fails, with its status.
TRANSIENT_STATUS = frozenset({403, 408, 429})
TRIES = 6
MAX_WAIT = 120.0

Check = Callable[[bytes], object]


class Fetch(Protocol):
    def __call__(self, url: str, check: Check | None = None) -> bytes: ...


class SourceError(Exception):
    """A source package that the workflow cannot attach as published."""


class NotFoundError(SourceError):
    """The server answered 404: the file does not exist there."""


def _retry_after(error: urllib.error.HTTPError) -> float:
    value = error.headers.get("Retry-After", "") if error.headers else ""
    return float(value) if value.strip().isdigit() else 0.0


def download(
    url: str, check: Check | None = None, *, tries: int = TRIES, timeout: float = 300
) -> bytes:
    """GET a URL, with bounded tries and growing waits for answers that can change.

    Rate limits, server errors, time-outs, broken or truncated transfers, and a body that
    `check` refuses (it raises ValueError) are tried again; the waits double from 2 s,
    or follow Retry-After, up to MAX_WAIT. A lasting failure names its cause. A 404 raises
    NotFoundError at once; any other answer raises SourceError at once.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, tries + 1):
        wait = float(2**attempt)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                content: bytes = response.read()
            if check is not None:
                check(content)
            return content
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise NotFoundError(f"HTTP 404 {url}") from None
            if error.code not in TRANSIENT_STATUS and error.code < 500:
                raise SourceError(f"HTTP {error.code} {url}") from None
            reason = f"HTTP {error.code}"
            wait = max(wait, _retry_after(error))
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            reason = f"{type(error).__name__}: {error}"
        except ValueError as error:
            reason = f"unusable answer: {error}"
        if attempt == tries:
            raise SourceError(f"{url}: {reason} after {tries} tries")
        LOG.warning("try %d of %d failed for %s: %s", attempt, tries, url, reason)
        time.sleep(min(wait, MAX_WAIT))
    raise SourceError(url)  # pragma: no cover - the loop returns or raises


def _json(content: bytes) -> object:
    return json.loads(content)


def _gzip_tar(content: bytes) -> object:
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            return tar.getmembers()
    except (tarfile.TarError, EOFError, OSError) as error:
        raise ValueError(f"not a gzip tar archive ({error})") from None


def _safe(name: str) -> str:
    if not _SAFE_NAME.fullmatch(name):
        raise SourceError(f"unsafe file name {name!r}")
    return name


def debian_sources(statuses: Iterable[str], exclude: Collection[str]) -> list[tuple[str, str]]:
    """Each Debian source package and version once, without the excluded binary packages."""
    sources = {
        (package.source, package.source_version)
        for status in statuses
        for package in debian_packages(status)
        if package.name not in exclude
    }
    return sorted(sources)


def debian_folder(source: str, version: str) -> str:
    """The folder of a source package, named like its Debian files (no epoch)."""
    return _safe(f"{source}_{version.split(':', 1)[-1]}")


def _dsc_checksums(text: str) -> dict[str, str]:
    block = text.split("\nChecksums-Sha256:\n", 1)
    if len(block) != 2:
        raise SourceError("the dsc has no Checksums-Sha256 field")
    checksums: dict[str, str] = {}
    for line in block[1].splitlines():
        if not line.startswith(" "):
            break
        digest, _, name = line.split()
        checksums[name] = digest
    return checksums


def fetch_debian(source: str, version: str, folder: Path, fetch: Fetch) -> int:
    """Download one Debian source package into folder; return its size in bytes."""
    package = f"{quote(source, safe='')}/{quote(version, safe='')}"
    url = f"{SNAPSHOT}/mr/package/{package}/srcfiles?fileinfo=1"
    answer = json.loads(fetch(url, _json))
    files: dict[str, str] = {}
    for item in answer["result"]:
        digest = str(item["hash"])
        for info in answer["fileinfo"][digest]:
            files[_safe(str(info["name"]))] = digest
    dscs = [name for name in files if name.endswith(".dsc")]
    if len(dscs) != 1:
        raise SourceError(f"{source} {version}: {len(dscs)} dsc files at snapshot.debian.org")
    folder.mkdir(parents=True, exist_ok=True)
    contents: dict[str, bytes] = {}
    for name, digest in sorted(files.items()):
        content = fetch(f"{SNAPSHOT}/file/{digest}")
        if hashlib.sha1(content, usedforsecurity=False).hexdigest() != digest:
            raise SourceError(f"{source} {version}: {name} does not match its SHA-1")
        contents[name] = content
    for name, digest in _dsc_checksums(contents[dscs[0]].decode(errors="replace")).items():
        if name not in contents or hashlib.sha256(contents[name]).hexdigest() != digest:
            raise SourceError(f"{source} {version}: {name} does not match the dsc")
    for name, content in contents.items():
        (folder / name).write_bytes(content)
    return sum(len(content) for content in contents.values())


def apkbuild_checksums(text: str) -> list[tuple[str, str]]:
    """The (SHA-512, file name) pairs of an APKBUILD's sha512sums block."""
    found = _CHECKSUMS.search(text)
    if found is None:
        return []
    pairs: list[tuple[str, str]] = []
    for line in found[2].splitlines():
        if line.strip():
            digest, name = line.split()
            pairs.append((digest, _safe(name)))
    return pairs


def alpine_branch(release: str) -> str:
    major, minor, *_ = release.strip().split(".")
    return f"v{major}.{minor}"


def _aports_folder(package: AlpinePackage, fetch: Fetch) -> dict[str, bytes]:
    for repository in ("main", "community"):
        url = (
            f"{APORTS_ARCHIVE}/{package.commit}/aports-{package.commit}.tar.gz"
            f"?path={repository}/{package.origin}"
        )
        try:
            archive = fetch(url, _gzip_tar)
        except NotFoundError:
            continue  # Only a 404 means "not in this repository"; other failures stop.
        files: dict[str, bytes] = {}
        suffix = f"/{repository}/{package.origin}/"
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                if not member.isfile() or suffix not in member.name:
                    continue
                relative = member.name.split(suffix, 1)[1]
                if "/" in relative:
                    continue
                file = tar.extractfile(member)
                if file is not None:
                    files[_safe(relative)] = file.read()
        if "APKBUILD" in files:
            return files
    raise SourceError(f"aports has no folder for {package.origin} at {package.commit}")


def fetch_alpine(package: AlpinePackage, branch: str, folder: Path, fetch: Fetch) -> int:
    """Download one Alpine origin's aports folder and distfiles; return its size in bytes."""
    files = _aports_folder(package, fetch)
    for digest, name in apkbuild_checksums(files["APKBUILD"].decode(errors="replace")):
        if name not in files:
            files[name] = fetch(f"{DISTFILES}/{branch}/{quote(name)}")
        if hashlib.sha512(files[name]).hexdigest() != digest:
            raise SourceError(f"{package.origin}: {name} does not match its SHA-512")
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (folder / name).write_bytes(content)
    return sum(len(content) for content in files.values())


def _tar_size(folder: Path) -> int:
    size = 512  # the folder's own header
    for path in folder.rglob("*"):
        size += 512 + (-(-path.stat().st_size // 512) * 512 if path.is_file() else 0)
    return size


def pack(staging: Path, output: Path, version: str, limit: int = ASSET_LIMIT) -> list[Path]:
    """Pack each package folder whole into tar assets below limit; return their paths."""
    reserve = 1024 + tarfile.RECORDSIZE  # end blocks and the final record padding
    folders = sorted(path for kind in ("alpine", "debian") for path in (staging / kind).glob("*"))
    groups: list[list[Path]] = []
    used = limit
    for folder in folders:
        size = _tar_size(folder)
        if size + reserve > limit:
            raise SourceError(f"{folder.relative_to(staging)} is larger than {limit} bytes")
        if used + size + reserve > limit:
            groups.append([])
            used = 0
        groups[-1].append(folder)
        used += size
    output.mkdir(parents=True, exist_ok=True)
    archives: list[Path] = []
    for number, group in enumerate(groups, 1):
        archive = output / f"slateops-sources-{version}-{number}.tar"
        with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tar:
            for folder in group:
                for path in [folder, *sorted(folder.rglob("*"))]:
                    info = tar.gettarinfo(path, path.relative_to(staging).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    info.mode = 0o755 if path.is_dir() else 0o644
                    if path.is_file():
                        with path.open("rb") as file:
                            tar.addfile(info, file)
                    else:
                        tar.addfile(info)
        if archive.stat().st_size >= limit:
            raise SourceError(f"{archive.name} is {archive.stat().st_size} bytes, over {limit}")
        archives.append(archive)
    return archives


def _fetch_all(args: argparse.Namespace, staging: Path) -> None:
    statuses = [path.read_text() for path in args.debian_status]
    debian = debian_sources(statuses, exclude=set(DOCKER_SOURCES))
    alpine = alpine_packages(args.apk_installed.read_text())
    branch = alpine_branch(args.alpine_release.read_text())
    LOG.info("sources: %d Debian, %d Alpine (%s)", len(debian), len(alpine), branch)

    def logged(url: str, check: Check | None = None) -> bytes:
        content = download(url, check)
        LOG.info("fetched %s (%d bytes)", url, len(content))
        return content

    def one_debian(item: tuple[str, str]) -> int:
        source, version = item
        folder = staging / "debian" / debian_folder(source, version)
        return fetch_debian(source, version, folder, logged)

    def one_alpine(package: AlpinePackage) -> int:
        folder = staging / "alpine" / _safe(f"{package.origin}-{package.version}")
        return fetch_alpine(package, branch, folder, logged)

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        sizes = [*pool.map(one_debian, debian), *pool.map(one_alpine, alpine)]
    LOG.info("downloaded %d source packages, %d bytes", len(sizes), sum(sizes))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="download, check and pack the source packages")
    fetch.add_argument("--version", required=True)
    fetch.add_argument("--debian-status", type=Path, action="append", required=True)
    fetch.add_argument("--apk-installed", type=Path, required=True)
    fetch.add_argument("--alpine-release", type=Path, required=True)
    fetch.add_argument("--staging", type=Path, required=True)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--jobs", type=int, default=4)
    fetch.add_argument("--summary", type=Path, help="append the asset sizes (workflow summary)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _fetch_all(args, args.staging)
        archives = pack(args.staging, args.output, args.version)
    except SourceError as error:
        LOG.error("%s", error)
        return 1
    lines = [f"- `{path.name}`: {path.stat().st_size / 2**20:.1f} MiB\n" for path in archives]
    if args.summary is not None:
        with args.summary.open("a") as summary:
            summary.write("### Source package assets (H4)\n" + "".join(lines))
    for line in lines:
        LOG.info("%s", line.strip())
    return 0


class _ActionsFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        prefix = {"ERROR": "::error::", "WARNING": "::warning::"}.get(record.levelname, "")
        return prefix + record.getMessage()


if __name__ == "__main__":
    handler = logging.StreamHandler()
    handler.setFormatter(_ActionsFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    sys.exit(main())
