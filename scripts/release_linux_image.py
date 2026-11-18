"""Checks and outputs of the Linux image (docs/plans/windows-installer.md 5.2, slice W4).

`.github/workflows/release.yml` runs packaging/linux-image/build.sh, then this script on
the tarball that the build wrote:

- `check` reads the tarball as it ships and refuses it on any problem. Each problem names
  its criterion: W4-1 (no build-only apt setting or build-host file), W4-2 (Docker from
  Docker's repository at the pinned versions, and only those), W4-3 (`wsl.conf`, no SSH
  server, no secret or identity, cosign pinned and licensed, the required packages and
  folders), W4-5 (the services are enabled), W4-6 (NTS time sync that listens on no
  port, with its offset logged), AC-W4-8 (the containerd image store) and section 10
  (the journal cap).
- `outputs` writes the package list and the source list (W4-4), the manifest entry of the
  image, and the package files that the notices job reads (regular files only).

The pins come from packaging/linux-image/pins.env, the file that the build reads.
Standard library only: the workflow runs it with a plain Python.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import logging
import posixpath
import re
import sys
import tarfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

# Run as a file, the script directory is first on sys.path; the repository root lets both
# ways (file and `scripts.release_linux_image`) share the Debian package model.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release_artifacts import (  # noqa: E402
    COSIGN_SOURCE,
    DebianPackage,
    docker_source,
)

LOG = logging.getLogger("release_linux_image")

# Docker's packages (sources: DOCKER_SOURCES in release_artifacts.py) and their pins.
# Any other package must come from Debian.
DOCKER_PINS = {
    "docker-ce": "DOCKER_CE_VERSION",
    "docker-ce-cli": "DOCKER_CE_CLI_VERSION",
    "containerd.io": "CONTAINERD_IO_VERSION",
    "docker-compose-plugin": "DOCKER_COMPOSE_PLUGIN_VERSION",
}
REQUIRED_PACKAGES = ("systemd-sysv", "python3", "restic", "chrony", "iproute2")
REMOTE_LOGIN_PACKAGES = frozenset(
    {"openssh-server", "dropbear", "dropbear-bin", "tinysshd", "telnetd", "inetutils-telnetd"}
)
UNITS = ("containerd.service", "docker.service", "chrony.service")
WANTS = "etc/systemd/system/multi-user.target.wants"
# Folders where a private key would be a secret of the image. A key is small; larger
# files (cosign, for example, holds the PEM marker text) are not read.
SECRET_ROOTS = ("etc/", "root/", "var/", "opt/", "usr/local/", "home/", "srv/")
SECRET_SIZE_LIMIT = 1 << 20
_PRIVATE_KEY = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----")
_PIN = re.compile(r'([A-Z0-9_]+)="([^"]*)"')


class ImageError(Exception):
    """A Linux image input that the workflow must refuse."""


def read_pins(path: Path) -> dict[str, str]:
    """Read the KEY="value" lines of pins.env."""
    pins: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if found := _PIN.fullmatch(line):
            pins[found[1]] = found[2]
    return pins


def cosign_pin(pins: Mapping[str, str], arch: str) -> str:
    pin = pins.get(f"COSIGN_SHA256_{arch.upper()}")
    if not pin:
        raise ImageError(f"no cosign pin for {arch}")
    return pin


class RootFileSystem:
    """The members of an image tarball, by path without the leading "./"."""

    def __init__(self, tar: tarfile.TarFile) -> None:
        self.tar = tar
        self.members: dict[str, tarfile.TarInfo] = {}
        for member in tar.getmembers():
            name = member.name.removeprefix("./").rstrip("/")
            if name and name != ".":
                self.members[name] = member

    def read(self, path: str) -> bytes | None:
        member = self.members.get(path)
        if member is None or not member.isfile():
            return None
        file = self.tar.extractfile(member)
        return None if file is None else file.read()

    def text(self, path: str) -> str | None:
        content = self.read(path)
        return None if content is None else content.decode(errors="replace")

    def under(self, folder: str) -> list[str]:
        prefix = folder.rstrip("/") + "/"
        return [name for name in self.members if name.startswith(prefix)]


def _stanzas(status_text: str) -> list[dict[str, str]]:
    stanzas: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", status_text):
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if not line.startswith(" ") and ": " in line
        )
        if fields.get("Status", "").endswith(" installed"):
            stanzas.append(fields)
    return sorted(stanzas, key=lambda fields: fields["Package"])


def installed_packages(root: RootFileSystem) -> list[dict[str, str]]:
    status = root.text("var/lib/dpkg/status")
    if status is None:
        raise ImageError("the image has no /var/lib/dpkg/status")
    return _stanzas(status)


def _wsl_conf_problems(root: RootFileSystem) -> list[str]:
    text = root.text("etc/wsl.conf")
    if text is None:
        return ["W4-3: /etc/wsl.conf is missing"]
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    expected = (
        ("boot", "systemd", "true"),
        ("user", "default", "root"),
        ("interop", "enabled", "false"),
        ("interop", "appendwindowspath", "false"),
        ("automount", "enabled", "false"),
    )
    return [
        f"W4-3: /etc/wsl.conf [{section}] {key} must be {value}"
        for section, key, value in expected
        if parser.get(section, key, fallback="").strip().lower() != value
    ]


# The reviewed Docker settings (S83-4). Any other key, a TCP socket in "hosts" for
# example, could open a port or weaken the daemon, so the check refuses it.
DAEMON_KEYS: dict[str, frozenset[str] | None] = {
    "features": frozenset({"containerd-snapshotter"}),
    "log-driver": None,
    "log-opts": frozenset({"max-size", "max-file"}),
}


def _daemon_problems(root: RootFileSystem) -> list[str]:
    text = root.text("etc/docker/daemon.json")
    try:
        settings = json.loads(text or "null")
        enabled = settings["features"]["containerd-snapshotter"] is True
    except (TypeError, KeyError, ValueError):
        settings, enabled = None, False
    problems: list[str] = []
    if not enabled:
        problems.append(
            "AC-W4-8: /etc/docker/daemon.json does not turn on the containerd image store"
        )
    if isinstance(settings, dict):
        unknown = sorted(set(settings) - set(DAEMON_KEYS))
        for key, allowed in DAEMON_KEYS.items():
            value = settings.get(key)
            if allowed is not None and isinstance(value, dict):
                unknown += [f"{key}.{name}" for name in sorted(set(value) - allowed)]
        if unknown:
            problems.append(f"W4-3: /etc/docker/daemon.json has unreviewed keys {unknown}")
    return problems


def _secret_problems(root: RootFileSystem, packages: Iterable[str]) -> list[str]:
    problems = [
        f"W4-3: remote login package {name} is installed"
        for name in sorted(REMOTE_LOGIN_PACKAGES.intersection(packages))
    ]
    problems += [
        f"W4-3: /{path} exists"
        for path in ("usr/sbin/sshd", "usr/sbin/dropbear")
        if path in root.members
    ]
    problems += [
        f"W4-3: SSH host key /{path} exists"
        for path in root.under("etc/ssh")
        if PurePosixPath(path).name.startswith("ssh_host_")
    ]
    machine_id = root.members.get("etc/machine-id")
    if machine_id is None or not machine_id.isfile():
        problems.append("W4-3: /etc/machine-id must exist as an empty file")
    elif machine_id.size:
        problems.append("W4-3: /etc/machine-id is not empty")
    dbus_id = root.members.get("var/lib/dbus/machine-id")
    if dbus_id is not None and dbus_id.isfile() and dbus_id.size:
        problems.append("W4-3: /var/lib/dbus/machine-id is not empty")
    problems += [
        f"W4-3: /{path} exists"
        for path in ("var/lib/systemd/random-seed", "var/lib/systemd/credential.secret")
        if path in root.members
    ]
    problems += [
        f"W4-3: /{path} exists"
        for path in root.under("etc/ssl/private")
        if root.members[path].isfile()
    ]
    problems += [f"W4-3: /{path} exists" for path in root.under("etc/slateops")]
    shadow = root.text("etc/shadow") or ""
    for line in shadow.splitlines():
        fields = line.split(":")
        if len(fields) > 1 and not fields[1].startswith(("*", "!")):
            problems.append(f"W4-3: account {fields[0]} has a password or an empty password")
    keys = root.text("etc/chrony/chrony.keys") or ""
    if any(line.strip() and not line.lstrip().startswith("#") for line in keys.splitlines()):
        problems.append("W4-3: /etc/chrony/chrony.keys holds a key")
    for path, member in sorted(root.members.items()):
        if not path.startswith(SECRET_ROOTS) or not member.isfile():
            continue
        if member.size > SECRET_SIZE_LIMIT:
            continue
        if _PRIVATE_KEY.search(root.read(path) or b""):
            problems.append(f"W4-3: /{path} holds a private key")
    return problems


def _cosign_problems(root: RootFileSystem, pins: Mapping[str, str], arch: str) -> list[str]:
    problems: list[str] = []
    member = root.members.get("usr/local/bin/cosign")
    content = root.read("usr/local/bin/cosign")
    if member is None or content is None:
        problems.append("W4-3: /usr/local/bin/cosign is missing")
    elif hashlib.sha256(content).hexdigest() != cosign_pin(pins, arch):
        problems.append(f"W4-3: /usr/local/bin/cosign is not cosign {pins['COSIGN_VERSION']}")
    elif member.mode & 0o111 != 0o111:
        problems.append("W4-3: /usr/local/bin/cosign is not executable")
    license_text = root.read("usr/share/doc/cosign/LICENSE")
    if license_text is None or hashlib.sha256(license_text).hexdigest() != pins.get(
        "COSIGN_LICENSE_SHA256"
    ):
        problems.append("W4-3: /usr/share/doc/cosign/LICENSE is not the pinned cosign license")
    return problems


# Content checks, not URL checks: any mention of the snapshot host in the shipped apt
# configuration is refused, and a Docker package is one whose maintainer address is at
# docker.com.
_SNAPSHOT_HOST = re.compile(rb"snapshot\.debian\.org")
_DOCKER_MAINTAINER = re.compile(r"@docker\.com>?\s*$")


def _apt_problems(root: RootFileSystem) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.under("etc/apt")):
        content = root.read(path)
        if content is None or path.startswith(("etc/apt/keyrings/", "etc/apt/trusted.gpg.d/")):
            continue
        lowered = content.lower()
        if _SNAPSHOT_HOST.search(lowered):
            problems.append(f"W4-1: /{path} names snapshot.debian.org")
        if b"check-valid-until" in lowered:
            problems.append(f"W4-1: /{path} changes Check-Valid-Until")
    problems += [
        f"W4-1: /{path} comes from the build"
        for path in ("etc/hostname", "etc/resolv.conf")
        if path in root.members
    ]
    return problems


def _docker_problems(
    root: RootFileSystem, stanzas: list[dict[str, str]], pins: Mapping[str, str]
) -> list[str]:
    problems: list[str] = []
    versions = {fields["Package"]: fields.get("Version", "") for fields in stanzas}
    for package, key in DOCKER_PINS.items():
        if versions.get(package) != pins.get(key):
            problems.append(
                f"W4-2: {package} is {versions.get(package, 'not installed')}, not {pins.get(key)}"
            )
    for fields in stanzas:
        if _DOCKER_MAINTAINER.search(fields.get("Maintainer", "")) and (
            fields["Package"] not in DOCKER_PINS
        ):
            problems.append(f"W4-2: {fields['Package']} from Docker is not a pinned package")
    if "etc/apt/preferences.d/slateops-docker" not in root.members:
        problems.append("W4-2: /etc/apt/preferences.d/slateops-docker is missing")
    if "etc/apt/keyrings/docker.asc" not in root.members:
        problems.append("W4-2: /etc/apt/keyrings/docker.asc is missing")
    return problems


def _time_problems(root: RootFileSystem) -> list[str]:
    text = root.text("etc/chrony/chrony.conf")
    if text is None:
        return ["W4-6: /etc/chrony/chrony.conf is missing"]
    lines = [
        line.split() for line in text.splitlines() if line.strip() and not line.startswith("#")
    ]
    problems: list[str] = []
    sources = [words for words in lines if words[0] in ("server", "pool", "peer")]
    if not sources:
        problems.append("W4-6: chrony.conf names no time source")
    problems += [
        f"W4-6: chrony source {' '.join(words[:2])} does not use NTS"
        for words in sources
        if words[0] != "server" or "nts" not in words[2:]
    ]
    for directive in ("port", "cmdport"):
        if [directive, "0"] not in lines:
            problems.append(f"W4-6: chrony.conf lacks '{directive} 0' (chronyd would listen)")
    problems += [
        f"W4-6: chrony.conf has '{' '.join(words)}'"
        for words in lines
        # S83-4: include, confdir and sourcedir would read more files (Debian ships
        # /etc/chrony/conf.d and sources.d), which could add sources or open a port.
        if words[0] in ("allow", "cmdallow", "bindcmdaddress", "include", "confdir", "sourcedir")
    ]
    if not any(words[0] == "log" and "tracking" in words[1:] for words in lines):
        problems.append("W4-6: chrony.conf does not log the tracking (offset) data")
    return problems


ENGINE_LINK = "usr/local/bin/slateops-engine"
IMAGE_RECORD = "usr/share/slateops/linux-image.json"
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _engine_problems(root: RootFileSystem, engine_sha256: str | None) -> list[str]:
    """W5b: the bundle under /opt/slateops/engine/<version>/, its link and its record."""
    try:
        record = json.loads(root.text(IMAGE_RECORD) or "null")
    except ValueError:
        record = None
    record = record if isinstance(record, dict) else {}
    version = str(record.get("version", ""))
    bundle = record.get("engine_bundle")
    recorded = str(bundle.get("sha256", "")) if isinstance(bundle, dict) else ""
    problems: list[str] = []
    if not _HEX64.fullmatch(recorded):
        problems.append(f"W5b: /{IMAGE_RECORD} records no engine bundle SHA-256")
    elif engine_sha256 is not None and recorded != engine_sha256:
        problems.append(f"W5b: the image holds engine bundle {recorded}, not {engine_sha256}")
    home = f"opt/slateops/engine/{version}"
    launcher = root.members.get(f"{home}/slateops-engine")
    if launcher is None or not launcher.isfile() or launcher.mode & 0o111 != 0o111:
        problems.append(f"W5b: /{home}/slateops-engine is missing or not executable")
    if (root.text(f"{home}/engine/VERSION") or "").strip() != version:
        problems.append(f"W5b: /{home}/engine/VERSION is not {version}")
    link = root.members.get(ENGINE_LINK)
    if link is None or not link.issym() or link.linkname != f"/{home}/slateops-engine":
        problems.append(f"W5b: /{ENGINE_LINK} does not link /{home}/slateops-engine")
    return problems


def check_rootfs(
    tarball: Path, pins: Mapping[str, str], arch: str, engine_sha256: str | None = None
) -> list[str]:
    """Return every problem of the image tarball; an empty list means it passes."""
    with tarfile.open(tarball) as tar:
        root = RootFileSystem(tar)
        stanzas = installed_packages(root)
        names = [fields["Package"] for fields in stanzas]
        problems = [
            *_wsl_conf_problems(root),
            *_daemon_problems(root),
            *_secret_problems(root, names),
            *_cosign_problems(root, pins, arch),
            *_apt_problems(root),
            *_docker_problems(root, stanzas, pins),
            *_time_problems(root),
            *_engine_problems(root, engine_sha256),
        ]
        problems += [
            f"W4-3: package {package} is not installed"
            for package in REQUIRED_PACKAGES
            if package not in names
        ]
        problems += [
            f"W4-5: {unit} is not enabled in multi-user.target"
            for unit in UNITS
            if not (member := root.members.get(f"{WANTS}/{unit}")) or not member.issym()
        ]
        engine = root.members.get("opt/slateops/engine")
        if engine is None or not engine.isdir():
            problems.append("W4-3: /opt/slateops/engine is missing")
        secrets = root.members.get("etc/slateops")
        if secrets is None or not secrets.isdir() or secrets.mode & 0o777 != 0o700:
            problems.append("W4-3: /etc/slateops must be a folder with mode 0700")
        journald = root.text("etc/systemd/journald.conf.d/slateops.conf") or ""
        if "SystemMaxUse=" not in journald:
            problems.append("section 10: the journal has no size cap")
    return problems


def package_list(tarball: Path, pins: Mapping[str, str], arch: str) -> str:
    """The installed packages with their origin, and cosign (W4-4)."""
    cosign = cosign_pin(pins, arch)
    with tarfile.open(tarball) as tar:
        stanzas = installed_packages(RootFileSystem(tar))
    lines = [
        f"# Packages of {tarball.name}: name, version, architecture, origin.",
        f"# debian: snapshot.debian.org at {pins['SNAPSHOT']};"
        f" docker: {pins['DOCKER_REPOSITORY']}.",
    ]
    lines += [
        f"{fields['Package']} {fields['Version']} {fields.get('Architecture', 'unknown')} "
        f"{'docker' if fields['Package'] in DOCKER_PINS else 'debian'}"
        for fields in stanzas
    ]
    lines.append(
        f"cosign {pins['COSIGN_VERSION']} {arch} github.com/sigstore/cosign sha256:{cosign}"
    )
    return "\n".join(lines) + "\n"


def source_list(tarball: Path, pins: Mapping[str, str]) -> str:
    """Each source package once, with where to get it (W4-4)."""
    with tarfile.open(tarball) as tar:
        stanzas = installed_packages(RootFileSystem(tar))
    debian: set[tuple[str, str, str]] = set()
    docker: list[str] = []
    for fields in stanzas:
        name, version = fields["Package"], fields["Version"]
        if name in DOCKER_PINS:
            docker.append(f"{name} {version} {docker_source(name, version)}")
            continue
        found = re.fullmatch(r"(\S+)(?: \((\S+)\))?", fields.get("Source", name))
        if found is None:
            raise ImageError(f"package {name}: unreadable Source field")
        package = DebianPackage(name, version, found[1], found[2] or version)
        debian.add((package.source, package.source_version, package.source_url))
    lines = [
        f"# Sources of {tarball.name}: source package, version, where to get it.",
        "# Debian sources are attached to the release; the others are at their upstream tags.",
        *(f"{name} {version} {url}" for name, version, url in sorted(debian)),
        *sorted(docker),
        f"cosign {pins['COSIGN_VERSION']} {COSIGN_SOURCE.format(version=pins['COSIGN_VERSION'])}",
    ]
    return "\n".join(lines) + "\n"


def image_entry(tarball: Path) -> dict[str, object]:
    digest, size = hashlib.sha256(), 0
    with tarball.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return {"archive": tarball.name, "sha256": digest.hexdigest(), "size": size}


def write_package_files(tarball: Path, output: Path) -> None:
    """Copy the dpkg status, the copyright files and the image record out of the tarball.

    The output holds regular files only: a doc folder that Debian links to another
    package's folder gets a copy of that folder's copyright file.
    """
    with tarfile.open(tarball) as tar:
        root = RootFileSystem(tar)
        wanted: dict[str, str] = {
            "var/lib/dpkg/status": "var/lib/dpkg/status",
            "usr/share/slateops/linux-image.json": "usr/share/slateops/linux-image.json",
        }
        for path, member in root.members.items():
            parts = PurePosixPath(path).parts
            if len(parts) == 5 and parts[:3] == ("usr", "share", "doc") and member.isfile():
                if parts[4] in ("copyright", "LICENSE"):
                    wanted[path] = path
            elif len(parts) == 4 and parts[:3] == ("usr", "share", "doc") and member.issym():
                folder = PurePosixPath(path).parent / member.linkname
                if member.linkname.startswith("/"):
                    folder = PurePosixPath(member.linkname.lstrip("/"))
                source = posixpath.normpath(f"{folder}/copyright")
                if root.read(source) is not None:
                    wanted[f"{path}/copyright"] = source
        for target, source in sorted(wanted.items()):
            content = root.read(source)
            if content is None:
                raise ImageError(f"the image has no /{source}")
            destination = output.joinpath(*PurePosixPath(target).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("check", "refuse the image tarball on any problem"),
        ("outputs", "write the lists, the manifest entry and the package files"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--tarball", type=Path, required=True)
        command.add_argument("--arch", required=True)
        command.add_argument("--pins", type=Path, required=True)
        if name == "check":
            command.add_argument(
                "--engine-info", type=Path, help="the engine bundle entry the image must hold"
            )
        if name == "outputs":
            command.add_argument("--output", type=Path, required=True, help="the two lists")
            command.add_argument("--entry", type=Path, required=True, help="the manifest entry")
            command.add_argument("--files", type=Path, required=True, help="the package files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    pins = read_pins(args.pins)
    try:
        if args.command == "check":
            engine = json.loads(args.engine_info.read_text()) if args.engine_info else {}
            problems = check_rootfs(args.tarball, pins, args.arch, engine.get("sha256"))
            for problem in problems:
                LOG.error(problem)
            if problems:
                return 1
            LOG.info("%s passed every check", args.tarball.name)
        else:
            stem = args.tarball.name.removesuffix(".tar.gz")
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / f"{stem}.packages.txt").write_text(
                package_list(args.tarball, pins, args.arch)
            )
            (args.output / f"{stem}.sources.txt").write_text(source_list(args.tarball, pins))
            entry = image_entry(args.tarball)
            args.entry.parent.mkdir(parents=True, exist_ok=True)
            args.entry.write_text(json.dumps(entry, indent=2) + "\n")
            write_package_files(args.tarball, args.files)
    except ImageError as error:
        LOG.error("%s", error)
        return 1
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
