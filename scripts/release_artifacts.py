"""Helpers for the release workflow (docs/plans/windows-installer.md 5.2 and 5.3, slice W3).

`.github/workflows/release.yml` calls each subcommand once:

- `tag` checks the tag with `check_release_version.py` (one tag rule, one validated
  version for the build argument). A stable tag needs LICENSE_WORK_MERGED (DEC-0029
  item 13, plan 5.3) and a commit on origin/main; an rc tag needs a commit on a pushed
  branch (plan 5.1 rule 1). Then it writes the step outputs.
- `image-info` checks an image archive against the pushed digest and records its size,
  SHA-256 and config digest.
- `manifest` writes `release-manifest.json` (decision H11) with the fields P2 has.
- `notices` writes `THIRD-PARTY-NOTICES.txt` from the installed packages and from the
  package databases copied out of the two images, and `SOURCE-OFFER.txt` for the Debian
  packages of the server image (decision H4).
- `notes` writes the release notes with the verification commands.

Standard library only: the workflow runs it with a plain Python, before any install.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

# Run as a file, the script directory is first on sys.path; the repository root lets
# both ways (file and `scripts.release_artifacts`) share one tag rule module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_release_version import (  # noqa: E402
    ReleaseVersionError,
    manifest_versions,
    release_version,
)

# DEC-0029 item 13 and plan 5.3: no stable release before the license work. The license
# work's pull request sets this to True; until then every stable tag is refused.
LICENSE_WORK_MERGED = False

TEST_BUILD_TITLE = "Test build, not for customers"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
MANIFEST_BUNDLE = "release-manifest.json.sigstore.json"
SNAPSHOT_SOURCE = "https://snapshot.debian.org/package"

_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
_PINNED = re.compile(r"[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9_.-]+)?@sha256:[0-9a-f]{64}")
_SERVICE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_IMAGE = re.compile(r"^    image:\s*(.+?)\s*$")
_LICENSE_FILE = re.compile(r"^(?:LICEN[CS]E|COPYING|NOTICE)", re.IGNORECASE)
_DPKG_SOURCE = re.compile(r"(?P<name>\S+)(?: \((?P<version>\S+)\))?")


class ReleaseError(Exception):
    """A release input that the workflow must refuse."""


@dataclass(frozen=True)
class ReleaseTag:
    version: str
    prerelease: bool
    title: str
    image_prefix: str


@dataclass(frozen=True)
class Notice:
    name: str
    version: str
    license: str
    texts: tuple[str, ...]
    source: str = ""


@dataclass(frozen=True)
class DebianPackage:
    name: str
    version: str
    source: str
    source_version: str

    @property
    def source_url(self) -> str:
        source, version = quote(self.source, safe=""), quote(self.source_version, safe="~+")
        return f"{SNAPSHOT_SOURCE}/{source}/{version}/"


def classify_tag(
    tag: str,
    owner: str,
    versions: Mapping[str, object],
    license_work_merged: bool | None = None,
) -> ReleaseTag:
    try:
        version = release_version(tag, versions)
    except ReleaseVersionError as error:
        raise ReleaseError(str(error)) from None
    prerelease = "-rc." in version
    merged = LICENSE_WORK_MERGED if license_work_merged is None else license_work_merged
    if not prerelease and not merged:
        raise ReleaseError(
            f"{tag} is a stable tag. Stable tags wait for the license work "
            "(DEC-0029 item 13): LICENSE_WORK_MERGED in scripts/release_artifacts.py is False."
        )
    title = f"{TEST_BUILD_TITLE} ({tag})" if prerelease else f"Slate Operations {tag}"
    return ReleaseTag(
        version=version,
        prerelease=prerelease,
        title=title,
        image_prefix=f"ghcr.io/{owner.lower()}",
    )


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )


def check_stable_commit(commit: str, main_ref: str, root: Path) -> None:
    """Refuse a stable tag whose commit is not on main (plan 5.1 rule 1)."""
    result = _git(root, "merge-base", "--is-ancestor", commit, main_ref)
    if result.returncode == 1:
        raise ReleaseError(f"stable tag commit {commit} is not on {main_ref.split('/')[-1]}")
    if result.returncode != 0:
        raise ReleaseError(f"cannot check that {commit} is on {main_ref}: {result.stderr.strip()}")


def check_branch_commit(commit: str, root: Path) -> None:
    """Refuse an rc tag whose commit is on no pushed branch (plan 5.1 rule 1)."""
    result = _git(root, "branch", "-r", "--contains", commit)
    if result.returncode != 0:
        raise ReleaseError(f"cannot list the branches with {commit}: {result.stderr.strip()}")
    if not result.stdout.strip():
        raise ReleaseError(f"rc tag commit {commit} is on no pushed branch")


def provider_images(compose_text: str) -> list[str]:
    """Return the unique image references of the Compose services, as written."""
    images: set[str] = set()
    in_services = False
    service = ""
    for line in compose_text.splitlines():
        if line and not line.startswith((" ", "#")):
            in_services = line.rstrip() == "services:"
            continue
        if not in_services:
            continue
        if found := _SERVICE.match(line):
            service = found[1]
        elif found := _IMAGE.match(line):
            image = found[1].strip("\"'")
            if not _PINNED.fullmatch(image):
                raise ReleaseError(
                    f"service {service}: image {image!r} is not pinned by a sha256 digest"
                )
            images.add(image)
    return sorted(images)


def _own_image(role: str, reference: str, name: str, version: str) -> str:
    _, separator, rest = reference.rpartition(f"/{name}:{version}@")
    if not separator or not _DIGEST.fullmatch("@" + rest):
        raise ReleaseError(f"{role} image {reference!r} is not {name}:{version}@sha256:<digest>")
    return reference


def archive_name(name: str, version: str) -> str:
    return f"{name}-{version}-amd64.oci.tar"


def _hash_stream(stream: Iterable[bytes]) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    for chunk in stream:
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _chunks(file: BinaryIO) -> Iterable[bytes]:
    while chunk := file.read(1 << 20):
        yield chunk


def _blob(tar: tarfile.TarFile, members: Mapping[str, tarfile.TarInfo], digest: str) -> bytes:
    """Read a blob of an OCI layout and check that its content has its digest."""
    algorithm, _, hexdigest = digest.partition(":")
    member = members.get(f"blobs/sha256/{hexdigest}")
    file = tar.extractfile(member) if member is not None and algorithm == "sha256" else None
    if file is None:
        raise ReleaseError(f"blob {digest} is missing from the archive")
    content = file.read()
    if hashlib.sha256(content).hexdigest() != hexdigest:
        raise ReleaseError(f"blob {digest} does not match its digest")
    return content


def image_info(reference: str, archive: Path) -> dict[str, object]:
    """Check an OCI archive against the pushed digest; return the manifest image entry.

    The archive must hold exactly one image manifest, with the pushed digest, and every
    blob it names must match its digest. So the archive is that digest's content.
    """
    digest = reference.rpartition("@")[2]
    with tarfile.open(archive) as tar:
        members = {member.name.removeprefix("./"): member for member in tar.getmembers()}
        index_file = tar.extractfile(members["index.json"]) if "index.json" in members else None
        if index_file is None:
            raise ReleaseError(f"{archive.name} has no index.json")
        manifests = json.loads(index_file.read()).get("manifests", [])
        if len(manifests) != 1 or manifests[0].get("mediaType") != OCI_MANIFEST:
            raise ReleaseError(f"{archive.name} must hold exactly one OCI image manifest")
        if manifests[0].get("digest") != digest:
            raise ReleaseError(f"{archive.name} holds {manifests[0].get('digest')}, not {digest}")
        manifest = json.loads(_blob(tar, members, digest))
        config_digest = str(manifest["config"]["digest"])
        _blob(tar, members, config_digest)
        for layer in manifest["layers"]:
            _blob(tar, members, str(layer["digest"]))
    with archive.open("rb") as file:
        sha256, size = _hash_stream(_chunks(file))
    return {
        "ref": reference,
        "archive": archive.name,
        "sha256": sha256,
        "size": size,
        "config_digest": config_digest,
    }


# release-manifest.json format (decision H11; parent decision D2 on TASK-0079):
# 1. "schema_version" is 1. Fields added later keep version 1. A rename, a removal, or a
#    change of a field's type or meaning raises the version.
# 2. A reader ignores keys that it does not know.
# 3. A missing optional field means "not provided" (for example the Linux image before W4,
#    the engine bundle before W5b).
# 4. A reader refuses a manifest whose "schema_version" is higher than the one it knows.
# 5. images.server and images.caddy are objects with "ref" (by digest), "archive" (the
#    release asset file name), "sha256" and "size" (of the archive) and "config_digest";
#    images.providers is the sorted list of Compose references by digest.
SCHEMA_VERSION = 1
IMAGE_FIELDS = frozenset({"ref", "archive", "sha256", "size", "config_digest"})


def _image_entry(
    role: str, info: Mapping[str, object], name: str, version: str
) -> dict[str, object]:
    if set(info) != IMAGE_FIELDS:
        raise ReleaseError(f"{role} image fields {sorted(info)} are not {sorted(IMAGE_FIELDS)}")
    reference, archive, sha256 = info["ref"], info["archive"], info["sha256"]
    size, config_digest = info["size"], info["config_digest"]
    if not isinstance(reference, str):
        raise ReleaseError(f"{role} image ref is not a string")
    _own_image(role, reference, name, version)
    if archive != archive_name(name, version):
        raise ReleaseError(f"{role} image archive {archive!r} is not {archive_name(name, version)}")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise ReleaseError(f"{role} image sha256 {sha256!r} is not 64 hex digits")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ReleaseError(f"{role} image size {size!r} is not a positive integer")
    if not isinstance(config_digest, str) or not _DIGEST.fullmatch("@" + config_digest):
        raise ReleaseError(f"{role} image config_digest {config_digest!r} is not sha256:<hex>")
    return {field: info[field] for field in ("ref", "archive", "sha256", "size", "config_digest")}


def build_manifest(
    version: str,
    server: Mapping[str, object],
    caddy: Mapping[str, object],
    providers: list[str],
) -> dict[str, object]:
    """Build the P2 manifest (format rules above).

    Fields that later slices produce (Linux image, engine bundle, minimum Windows-part
    version, known-bad WSL versions, migration notes) are omitted until their slice adds
    them (rule 3).
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "images": {
            "server": _image_entry("server", server, "slateops-server", version),
            "caddy": _image_entry("caddy", caddy, "slateops-caddy", version),
            "providers": providers,
        },
    }


def _license_name(meta: metadata.PackageMetadata) -> str:
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    declared = meta.get("License")
    if declared and declared.strip() and "\n" not in declared.strip():
        return str(declared).strip()
    classifiers = [
        str(value).removeprefix("License :: ")
        for value in meta.get_all("Classifier") or []
        if str(value).startswith("License :: ")
    ]
    return "; ".join(classifiers) or "UNKNOWN"


def python_notices(site_packages: Path) -> list[Notice]:
    """Read the installed distributions in one site-packages folder."""
    notices: dict[str, Notice] = {}
    for distribution in metadata.distributions(path=[str(site_packages)]):
        meta = distribution.metadata
        texts: list[str] = []
        for file in sorted(distribution.files or [], key=str):
            parts = file.parts
            if not parts or not parts[0].endswith(".dist-info"):
                continue
            if "licenses" in parts[1:-1] or _LICENSE_FILE.match(file.name):
                texts.append(Path(str(distribution.locate_file(file))).read_text(errors="replace"))
        name = str(meta["Name"])
        notices[name.lower()] = Notice(
            name, str(meta["Version"]), _license_name(meta), tuple(texts)
        )
    return [notices[key] for key in sorted(notices)]


def npm_notices(npm_root: Path) -> list[Notice]:
    """Read the production packages of a package-lock.json and their installed licenses."""
    lock = json.loads((npm_root / "package-lock.json").read_text())
    notices: dict[tuple[str, str], Notice] = {}
    for key, entry in lock["packages"].items():
        # devOptional: a development package that is also an optional peer (for example
        # Playwright for Next); the static export does not contain it.
        if not key or entry.get("dev") or entry.get("devOptional") or entry.get("link"):
            continue
        folder = npm_root / key
        if not folder.is_dir():
            if entry.get("optional"):
                continue  # A platform binary for another system; not installed, not shipped.
            raise ReleaseError(f"{key} is a production package but is not installed")
        name = entry.get("name") or key.rsplit("node_modules/", 1)[1]
        version = str(entry.get("version", "UNKNOWN"))
        texts = tuple(
            path.read_text(errors="replace")
            for path in sorted(folder.iterdir(), key=lambda path: path.name)
            if path.is_file() and _LICENSE_FILE.match(path.name)
        )
        notices.setdefault(
            (name, version), Notice(name, version, entry.get("license", "UNKNOWN"), texts)
        )
    return [notices[key] for key in sorted(notices)]


def _stanzas(text: str) -> list[list[str]]:
    return [block.splitlines() for block in re.split(r"\n\s*\n", text) if block.strip()]


def debian_packages(status_text: str) -> list[DebianPackage]:
    """Read the installed packages of a dpkg status file."""
    packages: dict[str, DebianPackage] = {}
    for stanza in _stanzas(status_text):
        fields = dict(
            line.split(": ", 1) for line in stanza if not line.startswith(" ") and ": " in line
        )
        if not fields.get("Status", "").endswith(" installed"):
            continue
        source = _DPKG_SOURCE.fullmatch(fields.get("Source", fields["Package"]))
        if source is None:
            raise ReleaseError(f"package {fields['Package']}: unreadable Source field")
        packages[fields["Package"]] = DebianPackage(
            name=fields["Package"],
            version=fields["Version"],
            source=source["name"],
            source_version=source["version"] or fields["Version"],
        )
    return [packages[name] for name in sorted(packages)]


def debian_notices(files: Path) -> list[Notice]:
    """Notices for the Debian packages in an image, from its copied dpkg files."""
    notices: list[Notice] = []
    for package in debian_packages((files / "var/lib/dpkg/status").read_text()):
        copyright_path = f"/usr/share/doc/{package.name}/copyright"
        try:
            texts: tuple[str, ...] = (
                (files / copyright_path.lstrip("/")).read_text(errors="replace"),
            )
        except OSError:
            texts = ()
        notices.append(
            Notice(
                package.name,
                package.version,
                copyright_path if texts else "UNKNOWN",
                texts,
                package.source_url,
            )
        )
    return notices


def alpine_notices(files: Path) -> list[Notice]:
    """Notices for the Alpine packages in an image, from its copied apk database."""
    notices: dict[str, Notice] = {}
    for stanza in _stanzas((files / "lib/apk/db/installed").read_text()):
        fields = {line[0]: line[2:] for line in stanza if len(line) > 1 and line[1] == ":"}
        name, version = fields["P"], fields["V"]
        origin = fields.get("o", name)
        notices[name] = Notice(
            name,
            version,
            fields.get("L", "UNKNOWN"),
            (),
            f"Alpine source package {origin} {version}",
        )
    return [notices[name] for name in sorted(notices)]


def source_offer(version: str, packages: list[DebianPackage]) -> str:
    sources = sorted({(p.source, p.source_version, p.source_url) for p in packages})
    lines = [
        f"Source offer for Slate Operations {version}",
        "",
        "The server image (slateops-server) contains the Debian binary packages listed in",
        "THIRD-PARTY-NOTICES.txt. Each line below names one Debian source package, its",
        "version, and the snapshot.debian.org page that holds its source files.",
        "",
        *(f"{name} {source_version} {url}" for name, source_version, url in sources),
    ]
    return "\n".join(lines) + "\n"


_RULE = "=" * 72
_THIN = "-" * 72


def _blocks(notices: Iterable[Notice]) -> list[str]:
    lines: list[str] = []
    for notice in notices:
        lines += [_RULE, f"{notice.name} {notice.version}", f"License: {notice.license}"]
        if notice.source:
            lines.append(f"Source: {notice.source}")
        for text in notice.texts:
            lines += [_THIN, text.rstrip("\n")]
        lines.append("")
    return lines


def render_notices(
    version: str,
    python: list[Notice],
    npm: list[Notice],
    providers: list[str],
    debian: Sequence[Notice] = (),
    alpine: Sequence[Notice] = (),
) -> str:
    groups = (("python", python), ("npm", npm), ("debian", debian), ("alpine", alpine))
    missing = [
        f"- {kind} {n.name} {n.version}" for kind, group in groups for n in group if not n.texts
    ]
    lines = [
        f"Third-party notices for Slate Operations {version}",
        "",
        "1. Python packages in the server image: backend/uv.lock without development",
        "   packages, read from their installed license metadata and files.",
        "2. npm packages of the web client: the production packages of",
        "   frontend/package-lock.json, read from their installed license files.",
        "3. Debian packages in the server image (from its python:3.14-slim base), read",
        "   from the image's dpkg status and copyright files. SOURCE-OFFER.txt lists",
        "   their source packages.",
        "4. Alpine packages in the Caddy image (from its caddy base), read from the",
        "   image's apk database.",
        "5. Provider images that an installation pulls from their publishers. This",
        "   release does not contain them; their license terms are in each image and",
        "   at its publisher's source repository.",
        "",
        "Not listed yet: the Python runtime under /usr/local in the server image, and",
        "the Caddy program and its Go modules in the Caddy image.",
        "",
        "Packages without a license text in their installed files:",
        *(missing or ["- none"]),
        "",
        "1. Python packages",
        "",
        *_blocks(python),
        "2. npm packages",
        "",
        *_blocks(npm),
        "3. Debian packages in the server image",
        "",
        *_blocks(debian),
        "4. Alpine packages in the Caddy image",
        "",
        *_blocks(alpine),
        "5. Provider images",
        "",
        *providers,
    ]
    return "\n".join(lines) + "\n"


def release_notes(
    tag: str, prerelease: bool, identity: str, repository: str, server_image: str, caddy_image: str
) -> str:
    keyless = f"--certificate-identity {identity} --certificate-oidc-issuer {OIDC_ISSUER}"
    # The same exact signer identity as cosign: this workflow file at this tag.
    attested = f"--repo {repository} --cert-identity {identity} --deny-self-hosted-runners"
    lines: list[str] = []
    if prerelease:
        lines += [
            f"**{TEST_BUILD_TITLE}.** Do not publish, link or offer this release. It contains "
            "no edition limits and no installer yet.",
            "",
        ]
    lines += [
        f"## Verify {tag}",
        "",
        "Use cosign v3 and the GitHub CLI. Run the commands in a folder with the release "
        "assets. Each command must succeed.",
        "",
        "```sh",
        f"cosign verify-blob --bundle {MANIFEST_BUNDLE} {keyless} release-manifest.json",
        "sha256sum --check SHA256SUMS",
        "```",
        "",
        "`release-manifest.json` gives the SHA-256 and the manifest digest of each image "
        "archive. The registry copies need read access to the GHCR packages while they "
        "are private (`docker login ghcr.io`):",
        "",
        "```sh",
        f"cosign verify {keyless} {server_image}",
        f"cosign verify {keyless} {caddy_image}",
        f"gh attestation verify oci://{server_image} {attested}",
        f"gh attestation verify oci://{caddy_image} {attested}",
        "```",
        "",
        "A failed build of this workflow is never re-run. The fix is a new tag with the next "
        "rc number.",
    ]
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    tag = commands.add_parser("tag", help="check the tag and write the step outputs")
    tag.add_argument("--tag", required=True)
    tag.add_argument("--owner", required=True)
    tag.add_argument("--commit", required=True, help="the tagged commit")
    tag.add_argument("--main-ref", required=True, help="for example origin/main")
    tag.add_argument("--repository-root", type=Path, default=Path("."))
    tag.add_argument("--github-output", type=Path, required=True)

    info = commands.add_parser("image-info", help="check an image archive; write its entry")
    info.add_argument("--reference", required=True, help="the pushed name:tag@sha256:...")
    info.add_argument("--archive", type=Path, required=True)
    info.add_argument("--output", type=Path, required=True)
    info.add_argument("--summary", type=Path, help="append the size line (workflow summary)")

    manifest = commands.add_parser("manifest", help="write release-manifest.json")
    manifest.add_argument("--version", required=True)
    manifest.add_argument("--server-info", type=Path, required=True)
    manifest.add_argument("--caddy-info", type=Path, required=True)
    manifest.add_argument("--compose", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)

    notices = commands.add_parser("notices", help="write THIRD-PARTY-NOTICES.txt")
    notices.add_argument("--version", required=True)
    notices.add_argument("--python-site-packages", type=Path, required=True)
    notices.add_argument("--npm-root", type=Path, required=True)
    notices.add_argument("--server-files", type=Path, required=True)
    notices.add_argument("--caddy-files", type=Path, required=True)
    notices.add_argument("--compose", type=Path, required=True)
    notices.add_argument("--output", type=Path, required=True)
    notices.add_argument("--source-offer", type=Path, required=True)

    notes = commands.add_parser("notes", help="write the release notes")
    notes.add_argument("--tag", required=True)
    notes.add_argument("--prerelease", choices=("true", "false"), required=True)
    notes.add_argument("--identity", required=True)
    notes.add_argument("--repository", required=True)
    notes.add_argument("--server-image", required=True)
    notes.add_argument("--caddy-image", required=True)
    notes.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "tag":
            versions = manifest_versions(args.repository_root)
            release = classify_tag(args.tag, args.owner, versions)
            if release.prerelease:
                check_branch_commit(args.commit, args.repository_root)
            else:
                check_stable_commit(args.commit, args.main_ref, args.repository_root)
            with args.github_output.open("a") as output:
                output.write(
                    f"version={release.version}\n"
                    f"prerelease={'true' if release.prerelease else 'false'}\n"
                    f"title={release.title}\n"
                    f"image_prefix={release.image_prefix}\n"
                )
        elif args.command == "image-info":
            entry = image_info(args.reference, args.archive)
            _write(args.output, json.dumps(entry, indent=2) + "\n")
            if args.summary is not None:
                size = int(str(entry["size"]))
                with args.summary.open("a") as summary:
                    summary.write(
                        f"- `{entry['archive']}` (archive): {size} bytes, {size / 2**20:.1f} MiB\n"
                    )
        elif args.command == "manifest":
            providers = provider_images(args.compose.read_text())
            server = json.loads(args.server_info.read_text())
            caddy = json.loads(args.caddy_info.read_text())
            content = build_manifest(args.version, server, caddy, providers)
            _write(args.output, json.dumps(content, indent=2) + "\n")
        elif args.command == "notices":
            python = python_notices(args.python_site_packages)
            npm = npm_notices(args.npm_root)
            debian = debian_notices(args.server_files)
            alpine = alpine_notices(args.caddy_files)
            providers = provider_images(args.compose.read_text())
            text = render_notices(args.version, python, npm, providers, debian, alpine)
            _write(args.output, text)
            status = (args.server_files / "var/lib/dpkg/status").read_text()
            _write(args.source_offer, source_offer(args.version, debian_packages(status)))
            for notice in (n for n in [*python, *npm, *debian, *alpine] if not n.texts):
                print(f"::warning::No license text for {notice.name} {notice.version}")
        else:
            text = release_notes(
                args.tag,
                args.prerelease == "true",
                args.identity,
                args.repository,
                args.server_image,
                args.caddy_image,
            )
            _write(args.output, text)
    except (ReleaseError, ReleaseVersionError) as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
