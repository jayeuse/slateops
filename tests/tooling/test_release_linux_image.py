"""Contracts for the Linux image checks (docs/plans/windows-installer.md W4-2 to W4-6, AC-W4-8).

The release workflow builds the image with packaging/linux-image/build.sh and then runs
scripts/release_linux_image.py on the tarball. These tests build small tarballs that hold
the repository's own image files (packaging/linux-image/rootfs/) plus synthetic package
data, so they check the shipped configuration and every refusal rule.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from scripts import release_linux_image
from scripts.release_linux_image import ImageError

ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "packaging/linux-image"
SNAPSHOT = "https://snapshot.debian.org/package"
COSIGN = b"\x7fELF cosign"
LICENSE = b"Apache License\nVersion 2.0\n"


def test_pins() -> dict[str, str]:
    pins = release_linux_image.read_pins(IMAGE / "pins.env")
    pins["COSIGN_SHA256_AMD64"] = hashlib.sha256(COSIGN).hexdigest()
    pins["COSIGN_LICENSE_SHA256"] = hashlib.sha256(LICENSE).hexdigest()
    return pins


def dpkg_status(pins: dict[str, str], extra: str = "") -> str:
    docker = "Maintainer: Docker <support@docker.com>"
    stanzas = [
        ("bash", "5.2.37-2+b5", "Source: bash (5.2.37-2)", "Maintainer: Debian"),
        ("chrony", "4.6.1-3", "", "Maintainer: Debian"),
        ("python3", "3.13.5-1", "Source: python3-defaults", "Maintainer: Debian"),
        ("restic", "0.18.0-1", "", "Maintainer: Debian"),
        ("systemd-sysv", "257.9-1", "Source: systemd", "Maintainer: Debian"),
        ("iproute2", "6.15.0-1", "", "Maintainer: Debian"),
        ("docker-ce", pins["DOCKER_CE_VERSION"], "", docker),
        ("docker-ce-cli", pins["DOCKER_CE_CLI_VERSION"], "", docker),
        ("containerd.io", pins["CONTAINERD_IO_VERSION"], "", docker),
        ("docker-compose-plugin", pins["DOCKER_COMPOSE_PLUGIN_VERSION"], "", docker),
    ]
    blocks = [
        "\n".join(
            line
            for line in (
                f"Package: {name}",
                "Status: install ok installed",
                f"{maintainer} <maintainer@example.org>" if "Debian" in maintainer else maintainer,
                "Architecture: amd64",
                f"Version: {version}",
                source,
            )
            if line
        )
        for name, version, source, maintainer in stanzas
    ]
    return "\n\n".join(blocks) + "\n" + extra


Files = dict[str, bytes | str | None]


def valid_files(pins: dict[str, str]) -> Files:
    """The members of a tarball that passes every check (None marks a folder)."""
    files: Files = {
        path.relative_to(IMAGE / "rootfs").as_posix(): path.read_bytes()
        for path in sorted((IMAGE / "rootfs").rglob("*"))
        if path.is_file()
    }
    files.update(
        {
            "var/lib/dpkg/status": dpkg_status(pins),
            "usr/share/doc/bash/copyright": "bash copyright\n",
            "usr/local/bin/cosign": COSIGN,
            "usr/share/doc/cosign/LICENSE": LICENSE,
            "etc/machine-id": "",
            "etc/apt/keyrings/docker.asc": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n",
            "etc/shadow": "root:*:20000:0:99999:7:::\nnobody:!:20000::::::\n",
            "etc/chrony/chrony.keys": "# This file holds no key.\n",
            "etc/slateops": None,
            "var/lib/slateops": None,
            "var/log/slateops": None,
            "opt/slateops/engine": None,
            "etc/ssl/private": None,
            "usr/share/slateops/linux-image.json": json.dumps({"version": "0.2.0-rc.1"}),
        }
    )
    return files


UNITS = ("containerd.service", "docker.service", "chrony.service")


def write_tarball(
    path: Path, files: Files, units: tuple[str, ...] = UNITS, links: dict[str, str] | None = None
) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"./{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
        for name, content in sorted(files.items()):
            info = tarfile.TarInfo(f"./{name}")
            if content is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o700 if name.startswith(("etc/slateops", "var/")) else 0o755
                tar.addfile(info)
                continue
            data = content.encode() if isinstance(content, str) else content
            info.size = len(data)
            info.mode = 0o755 if name == "usr/local/bin/cosign" else 0o644
            tar.addfile(info, io.BytesIO(data))
        for unit in units:
            info = tarfile.TarInfo(f"./etc/systemd/system/multi-user.target.wants/{unit}")
            info.type = tarfile.SYMTYPE
            info.linkname = f"/usr/lib/systemd/system/{unit}"
            tar.addfile(info)


def replace(files: Files, name: str, old: str, new: str) -> None:
    content = files[name]
    assert content is not None
    text = content.decode() if isinstance(content, bytes) else content
    assert old in text, (name, old)
    files[name] = text.replace(old, new)


class RootFileSystemCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pins = test_pins()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tarball = Path(self.directory.name) / "slateops-linux-0.2.0-rc.1-amd64.tar.gz"

    def problems(self, files: Files, units: tuple[str, ...] = UNITS) -> list[str]:
        write_tarball(self.tarball, files, units)
        return release_linux_image.check_rootfs(self.tarball, self.pins, "amd64")

    def test_the_repository_image_files_with_valid_package_data_pass(self):
        self.assertEqual(self.problems(valid_files(self.pins)), [])

    def test_each_refused_state_names_its_criterion(self):
        def edit(name: str, old: str, new: str) -> Callable[[Files], None]:
            return lambda files: replace(files, name, old, new)

        def put(name: str, content: bytes | str | None) -> Callable[[Files], None]:
            return lambda files: files.__setitem__(name, content)

        def drop(name: str) -> Callable[[Files], None]:
            return lambda files: files.pop(name)

        def add_package(stanza: str) -> Callable[[Files], None]:
            return lambda files: files.__setitem__(
                "var/lib/dpkg/status", dpkg_status(self.pins, "\n" + stanza)
            )

        cases: list[tuple[str, Callable[[Files], None], str]] = [
            # W4-3 wsl.conf: systemd on, interop off, no Windows PATH, no automount.
            ("systemd off", edit("etc/wsl.conf", "systemd=true", "systemd=false"), "W4-3"),
            (
                "interop on",
                edit("etc/wsl.conf", "enabled=false\nappend", "enabled=true\nappend"),
                "W4-3",
            ),
            (
                "Windows PATH",
                edit("etc/wsl.conf", "appendWindowsPath=false", "appendWindowsPath=true"),
                "W4-3",
            ),
            (
                "automount on",
                edit("etc/wsl.conf", "[automount]\nenabled=false", "[automount]\nenabled=true"),
                "W4-3",
            ),
            ("no wsl.conf", drop("etc/wsl.conf"), "W4-3"),
            # AC-W4-8: the containerd image store.
            (
                "classic store",
                edit(
                    "etc/docker/daemon.json",
                    '"containerd-snapshotter": true',
                    '"containerd-snapshotter": false',
                ),
                "AC-W4-8",
            ),
            ("no daemon.json", drop("etc/docker/daemon.json"), "AC-W4-8"),
            # W4-3: no SSH server, no secret, no identity.
            (
                "ssh server package",
                add_package(
                    "Package: openssh-server\nStatus: install ok installed\nVersion: 1:10.0p1-7"
                ),
                "W4-3",
            ),
            ("sshd binary", put("usr/sbin/sshd", b"\x7fELF"), "W4-3"),
            ("host key", put("etc/ssh/ssh_host_ed25519_key.pub", "ssh-ed25519 AAAA"), "W4-3"),
            ("machine ID", put("etc/machine-id", "0123456789abcdef0123456789abcdef\n"), "W4-3"),
            ("no machine-id file", drop("etc/machine-id"), "W4-3"),
            ("random seed", put("var/lib/systemd/random-seed", b"\x01" * 32), "W4-3"),
            ("private key", put("root/key.pem", "-----BEGIN " + "PRIVATE KEY-----\nMII\n"), "W4-3"),
            (
                "OpenSSH private key",
                put("opt/slateops/engine/id", "-----BEGIN OPENSSH PRIVATE KEY-----\n"),
                "W4-3",
            ),
            ("ssl private file", put("etc/ssl/private/ssl-cert-snakeoil.key", "x"), "W4-3"),
            ("root password", edit("etc/shadow", "root:*:", "root:$y$j9T$abc$def:"), "W4-3"),
            ("empty password", edit("etc/shadow", "root:*:", "root::"), "W4-3"),
            ("chrony key", put("etc/chrony/chrony.keys", "1 SHA1 HEX:0123456789\n"), "W4-3"),
            ("secret in /etc/slateops", put("etc/slateops/app.env", "KEY=value\n"), "W4-3"),
            # W4-3 cosign pinned and licensed.
            ("cosign changed", put("usr/local/bin/cosign", b"\x7fELF other"), "W4-3"),
            ("no cosign", drop("usr/local/bin/cosign"), "W4-3"),
            ("cosign license changed", put("usr/share/doc/cosign/LICENSE", "MIT"), "W4-3"),
            # W4-1: build-only apt settings never ship.
            (
                "snapshot source",
                put(
                    "etc/apt/sources.list",
                    "deb http://snapshot.debian.org/archive/debian/x trixie main\n",
                ),
                "W4-1",
            ),
            (
                "validity check off",
                put("etc/apt/apt.conf.d/99mmdebstrap", 'Acquire::Check-Valid-Until "false";\n'),
                "W4-1",
            ),
            ("build host name", put("etc/hostname", "buildkitsandbox\n"), "W4-1"),
            ("build resolver", put("etc/resolv.conf", "nameserver 192.168.65.7\n"), "W4-1"),
            # W4-2: Docker from Docker's repository at the pinned versions, and only those.
            (
                "Docker version",
                lambda files: files.__setitem__(
                    "var/lib/dpkg/status",
                    dpkg_status({**self.pins, "DOCKER_CE_VERSION": "5:29.10.0-1~debian.13~trixie"}),
                ),
                "W4-2",
            ),
            (
                "other Docker package",
                add_package(
                    "Package: docker-buildx-plugin\nStatus: install ok installed\n"
                    "Maintainer: Docker <support@docker.com>\nVersion: 0.29.1-1~debian.13~trixie"
                ),
                "W4-2",
            ),
            ("no apt pin", drop("etc/apt/preferences.d/slateops-docker"), "W4-2"),
            # W4-6: time sync with NTS only, listening on no port, offset logged.
            (
                "server without NTS",
                edit(
                    "etc/chrony/chrony.conf",
                    "server nts.netnod.se iburst nts",
                    "pool 2.debian.pool.ntp.org iburst",
                ),
                "W4-6",
            ),
            (
                "NTP server port",
                edit("etc/chrony/chrony.conf", "\nport 0\n", "\nallow 0/0\n"),
                "W4-6",
            ),
            ("command port", edit("etc/chrony/chrony.conf", "cmdport 0\n", ""), "W4-6"),
            ("offset not logged", edit("etc/chrony/chrony.conf", "log tracking\n", ""), "W4-6"),
            # Section 10: the journal is capped.
            ("journal cap", drop("etc/systemd/journald.conf.d/slateops.conf"), "section 10"),
            # W4-3 and plan 3.1: the parts that the image must hold.
            ("no engine folder", drop("opt/slateops/engine"), "W4-3"),
        ]
        for name, mutate, criterion in cases:
            with self.subTest(case=name):
                files = valid_files(self.pins)
                mutate(files)

                problems = self.problems(files)

                self.assertTrue(problems)
                self.assertTrue(
                    all(problem.startswith(f"{criterion}: ") for problem in problems), problems
                )

    def test_each_service_must_be_enabled(self):
        # W4-5 (static part): systemd starts containerd, Docker and the time client.
        for unit in UNITS:
            with self.subTest(unit=unit):
                units = tuple(other for other in UNITS if other != unit)

                self.assertEqual(
                    self.problems(valid_files(self.pins), units),
                    [f"W4-5: {unit} is not enabled in multi-user.target"],
                )

    def test_a_missing_required_package_is_named(self):
        for package in ("python3", "restic", "chrony", "systemd-sysv", "iproute2"):
            files = valid_files(self.pins)
            status = str(files["var/lib/dpkg/status"])
            files["var/lib/dpkg/status"] = re.sub(
                rf"(?ms)^Package: {re.escape(package)}\n.*?(?:\n\n|\Z)", "", status
            )
            with self.subTest(package=package):
                self.assertEqual(
                    self.problems(files), [f"W4-3: package {package} is not installed"]
                )


class PinTests(unittest.TestCase):
    def test_cosign_pin_is_the_release_workflow_pin(self):
        # W4-3: the image's cosign is the release that release.yml uses.
        pins = release_linux_image.read_pins(IMAGE / "pins.env")
        workflow = (ROOT / ".github/workflows/release.yml").read_text()

        self.assertIn(f"/releases/download/v{pins['COSIGN_VERSION']}/cosign-linux-amd64", workflow)
        self.assertIn(f'echo "{pins["COSIGN_SHA256_AMD64"]}  $bin/cosign"', workflow)

    def test_pins_file_holds_only_quoted_assignments(self):
        lines = (IMAGE / "pins.env").read_text().splitlines()
        assignments = [line for line in lines if line and not line.startswith("#")]

        self.assertTrue(assignments)
        for line in assignments:
            with self.subTest(line=line):
                self.assertRegex(line, r'^[A-Z0-9_]+="[^"$`\\]*"$')

    def test_the_build_checks_the_keys_and_pins_every_input(self):
        # W4-1 and W4-2: the build fails closed on a key or a download that differs.
        build = (IMAGE / "build-rootfs.sh").read_text()
        hooks = (IMAGE / "hooks.sh").read_text()
        for key in ("DEBIAN_KEY_ARCHIVE", "DEBIAN_KEY_SECURITY", "DEBIAN_KEY_RELEASE"):
            with self.subTest(key=key):
                self.assertIn(f'"${key}"', build)
        self.assertIn('[ "$found" = "$DOCKER_KEY_FINGERPRINT" ]', build)
        self.assertIn("--variant=important", build)
        for line in re.findall(r'(?m)^    "deb \[signed-by=[^]]+\] (\S+) ', build):
            with self.subTest(source=line):
                self.assertIn(line, ("$debian", "$security", "$DOCKER_REPOSITORY"))
        self.assertIn('debian="http://snapshot.debian.org/archive/debian/$SNAPSHOT"', build)
        self.assertIn("sha256sum --check --strict --status", hooks)
        self.assertIn("gzip -n", build)


class ImageOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pins = test_pins()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.tarball = self.root / "slateops-linux-0.2.0-rc.1-amd64.tar.gz"
        # Debian links some doc folders to another package's folder (libfoo1 -> foo).
        write_tarball(self.tarball, valid_files(self.pins), links={"usr/share/doc/login": "bash"})

    def test_package_list_names_each_package_with_its_origin_and_cosign(self):
        # W4-4: the package list.
        text = release_linux_image.package_list(self.tarball, self.pins, "amd64")

        lines = [line for line in text.splitlines() if line and not line.startswith("#")]
        self.assertEqual(lines[0], "bash 5.2.37-2+b5 amd64 debian")
        self.assertIn(f"docker-ce {self.pins['DOCKER_CE_VERSION']} amd64 docker", lines)
        self.assertEqual(
            lines[-1],
            "cosign 3.1.4 amd64 github.com/sigstore/cosign "
            f"sha256:{self.pins['COSIGN_SHA256_AMD64']}",
        )
        self.assertEqual(len(lines), 11)

    def test_source_list_gives_each_source_once_with_where_to_get_it(self):
        # W4-4: the source list; Debian sources at snapshot.debian.org, the others upstream.
        text = release_linux_image.source_list(self.tarball, self.pins)

        lines = [line for line in text.splitlines() if line and not line.startswith("#")]
        self.assertEqual(
            lines,
            [
                f"bash 5.2.37-2 {SNAPSHOT}/bash/5.2.37-2/",
                f"chrony 4.6.1-3 {SNAPSHOT}/chrony/4.6.1-3/",
                f"iproute2 6.15.0-1 {SNAPSHOT}/iproute2/6.15.0-1/",
                f"python3-defaults 3.13.5-1 {SNAPSHOT}/python3-defaults/3.13.5-1/",
                f"restic 0.18.0-1 {SNAPSHOT}/restic/0.18.0-1/",
                f"systemd 257.9-1 {SNAPSHOT}/systemd/257.9-1/",
                "containerd.io 2.3.6-1~debian.13~trixie "
                "https://github.com/containerd/containerd/tree/v2.3.6",
                "docker-ce 5:29.8.2-1~debian.13~trixie https://github.com/moby/moby/tree/docker-v29.8.2",
                "docker-ce-cli 5:29.8.2-1~debian.13~trixie https://github.com/docker/cli/tree/v29.8.2",
                "docker-compose-plugin 5.7.1-1~debian.13~trixie "
                "https://github.com/docker/compose/tree/v5.7.1",
                "cosign 3.1.4 https://github.com/sigstore/cosign/tree/v3.1.4",
            ],
        )

    def test_outputs_command_writes_the_lists_the_image_entry_and_the_package_files(self):
        output = self.root / "out"

        status = release_linux_image.main(
            [
                "outputs",
                "--tarball",
                str(self.tarball),
                "--arch",
                "amd64",
                "--pins",
                str(IMAGE / "pins.env"),
                "--output",
                str(output),
                "--entry",
                str(self.root / "linux-image.json"),
                "--files",
                str(self.root / "files"),
            ]
        )

        # The real pins do not match the synthetic cosign, but outputs does not check it;
        # the check command does, before outputs runs.
        self.assertEqual(status, 0)
        entry = json.loads((self.root / "linux-image.json").read_text())
        self.assertEqual(
            entry,
            {
                "archive": "slateops-linux-0.2.0-rc.1-amd64.tar.gz",
                "sha256": hashlib.sha256(self.tarball.read_bytes()).hexdigest(),
                "size": self.tarball.stat().st_size,
            },
        )
        self.assertEqual(
            sorted(path.name for path in output.iterdir()),
            [
                "slateops-linux-0.2.0-rc.1-amd64.packages.txt",
                "slateops-linux-0.2.0-rc.1-amd64.sources.txt",
            ],
        )
        files = self.root / "files"
        self.assertEqual((files / "var/lib/dpkg/status").read_text(), dpkg_status(self.pins))
        self.assertEqual((files / "usr/share/doc/bash/copyright").read_text(), "bash copyright\n")
        login = files / "usr/share/doc/login/copyright"
        self.assertEqual((login.read_text(), login.is_symlink()), ("bash copyright\n", False))
        self.assertEqual((files / "usr/share/doc/cosign/LICENSE").read_bytes(), LICENSE)
        self.assertFalse((files / "usr/local/bin/cosign").exists())

    def test_check_command_fails_closed_on_any_problem(self):
        files = valid_files(self.pins)
        files["etc/machine-id"] = "0123\n"
        write_tarball(self.tarball, files)
        pins = self.root / "pins.env"
        pins.write_text("".join(f'{key}="{value}"\n' for key, value in self.pins.items()))

        with self.assertLogs(release_linux_image.LOG, "ERROR") as logs:
            status = release_linux_image.main(
                ["check", "--tarball", str(self.tarball), "--arch", "amd64", "--pins", str(pins)]
            )

        self.assertEqual(status, 1)
        self.assertEqual(
            logs.output, ["ERROR:release_linux_image:W4-3: /etc/machine-id is not empty"]
        )

    def test_an_unknown_docker_package_or_architecture_is_refused(self):
        with self.assertRaisesRegex(ImageError, "no cosign pin for riscv64"):
            release_linux_image.package_list(self.tarball, self.pins, "riscv64")


class BootCheckTests(unittest.TestCase):
    def test_the_boot_check_proves_systemd_docker_the_store_and_no_listener(self):
        # W4-5 and W4-6 at runtime: systemd-nspawn boots a throwaway copy; the guest script
        # reports the system state, Docker's store and every listening socket.
        guest = (IMAGE / "boot-check-guest.sh").read_text()
        host = (IMAGE / "boot-check.sh").read_text()
        for expected in (
            "systemctl is-system-running --wait",
            "systemctl is-active",
            "docker info --format",
            "ss -H -ltn",
            "ss -H -lun",
            "systemctl poweroff",
        ):
            with self.subTest(guest=expected):
                self.assertIn(expected, guest)
        for expected in ("systemd-nspawn", "--boot", "--private-network", "--register=no"):
            with self.subTest(host=expected):
                self.assertIn(expected, host)
        self.assertNotIn("CAP_SYS_TIME", host)
        self.assertIn("chronyd -x", host)


if __name__ == "__main__":
    unittest.main()
