"""Contracts for the attached source packages (docs/plans/windows-installer.md W4-7, H4).

scripts/release_sources.py downloads the source files of the Debian packages of the Linux
image and the server image from snapshot.debian.org, and of the Alpine packages of the
Caddy image from aports and Alpine's distfiles, checks each file against its published
hash, and packs them into release assets below the size limit. These tests replace the
network with a table of URLs.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import textwrap
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

from scripts import release_sources
from scripts.release_artifacts import AlpinePackage
from scripts.release_sources import SourceError

ORIG = b"upstream source"
DEBIAN_TAR = b"debian folder"
SNAPSHOT = "https://snapshot.debian.org"


def sha1(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


def dsc(files: dict[str, bytes]) -> bytes:
    lines = "".join(
        f" {hashlib.sha256(data).hexdigest()} {len(data)} {name}\n" for name, data in files.items()
    )
    return f"Format: 3.0 (quilt)\nSource: bash\nChecksums-Sha256:\n{lines}\n".encode()


def debian_site(dsc_files: dict[str, bytes] | None = None, served: dict[str, bytes] | None = None):
    """The snapshot.debian.org answers for bash 5.2.37-2 (dsc, orig, debian tar)."""
    files = {"bash_5.2.37.orig.tar.xz": ORIG, "bash_5.2.37-2.debian.tar.xz": DEBIAN_TAR}
    description = dsc(dsc_files or files)
    published = {**files, "bash_5.2.37-2.dsc": description}
    content = {**published, **(served or {})}
    info = {
        sha1(data): [{"name": name, "archive_name": "debian", "size": len(data)}]
        for name, data in published.items()
    }
    pages = {
        f"{SNAPSHOT}/mr/package/bash/5.2.37-2/srcfiles?fileinfo=1": json.dumps(
            {"result": [{"hash": digest} for digest in info], "fileinfo": info}
        ).encode()
    }
    pages.update(
        {f"{SNAPSHOT}/file/{sha1(data)}": content[name] for name, data in published.items()}
    )
    return pages


def fetcher(pages: dict[str, bytes]):
    def fetch(url: str) -> bytes:
        if url not in pages:
            raise SourceError(f"404 {url}")
        return pages[url]

    return fetch


APKBUILD = textwrap.dedent(
    """\
    pkgname=busybox
    pkgver=1.37.0
    source="https://busybox.net/downloads/busybox-$pkgver.tar.bz2
        0001-fix.patch
        "
    sha512sums="
    {tarball}  busybox-1.37.0.tar.bz2
    {patch}  0001-fix.patch
    "
    """
)
PATCH = b"--- a\n+++ b\n"
UPSTREAM = b"busybox tarball"
COMMIT = "2e97d754a30d558f15524b8e422303c8a96832df"


def aports_archive(apkbuild: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        top = f"aports-{COMMIT}-main-busybox/main/busybox"
        for name, data in (("APKBUILD", apkbuild.encode()), ("0001-fix.patch", PATCH)):
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def alpine_site(tarball: bytes = UPSTREAM) -> dict[str, bytes]:
    apkbuild = APKBUILD.format(
        tarball=hashlib.sha512(UPSTREAM).hexdigest(), patch=hashlib.sha512(PATCH).hexdigest()
    )
    base = "https://gitlab.alpinelinux.org/alpine/aports/-/archive"
    return {
        f"{base}/{COMMIT}/aports-{COMMIT}.tar.gz?path=main/busybox": aports_archive(apkbuild),
        "https://distfiles.alpinelinux.org/distfiles/v3.22/busybox-1.37.0.tar.bz2": tarball,
    }


class DebianSourceTests(unittest.TestCase):
    def test_sources_are_unique_across_images_and_skip_docker_packages(self):
        linux = textwrap.dedent(
            """\
            Package: bash
            Status: install ok installed
            Version: 5.2.37-2+b5
            Source: bash (5.2.37-2)

            Package: docker-ce
            Status: install ok installed
            Version: 5:29.8.2-1~debian.13~trixie
            """
        )
        server = "Package: bash\nStatus: install ok installed\nVersion: 5.2.37-2\n"

        self.assertEqual(
            release_sources.debian_sources([linux, server], exclude={"docker-ce"}),
            [("bash", "5.2.37-2")],
        )

    def test_fetch_checks_every_file_against_snapshot_and_the_dsc(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            size = release_sources.fetch_debian("bash", "5.2.37-2", folder, fetcher(debian_site()))

            self.assertEqual(
                sorted(path.name for path in folder.iterdir()),
                ["bash_5.2.37-2.debian.tar.xz", "bash_5.2.37-2.dsc", "bash_5.2.37.orig.tar.xz"],
            )
            self.assertEqual((folder / "bash_5.2.37.orig.tar.xz").read_bytes(), ORIG)
            self.assertEqual(size, sum(path.stat().st_size for path in folder.iterdir()))

    def test_a_file_that_differs_from_its_hash_or_its_dsc_is_refused(self):
        for case, site, reason in (
            (
                "changed download",
                debian_site(served={"bash_5.2.37.orig.tar.xz": b"tampered"}),
                "does not match its SHA-1",
            ),
            (
                "dsc names other content",
                debian_site(dsc_files={"bash_5.2.37.orig.tar.xz": b"other", "x.tar.xz": b"y"}),
                "does not match the dsc",
            ),
        ):
            with (
                self.subTest(case=case),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaisesRegex(SourceError, reason),
            ):
                release_sources.fetch_debian("bash", "5.2.37-2", Path(directory), fetcher(site))

    def test_a_package_folder_is_named_like_debian_files_without_the_epoch(self):
        # Found on the first real run: "attr 1:2.5.2-3" gave an unsafe folder name.
        self.assertEqual(release_sources.debian_folder("attr", "1:2.5.2-3"), "attr_2.5.2-3")
        self.assertEqual(release_sources.debian_folder("bash", "5.2.37-2"), "bash_5.2.37-2")

    def test_an_unpublished_source_version_is_refused(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(SourceError, "404"):
            release_sources.fetch_debian("bash", "9.9-1", Path(directory), fetcher(debian_site()))


class AlpineSourceTests(unittest.TestCase):
    def test_apkbuild_checksums_are_read_from_the_sha512sums_block(self):
        # alpine-keys names its files after the key owner's address (found on 3.22.3).
        key = "alpine-devel@lists.alpinelinux.org-4a6a0840.rsa.pub"
        text = APKBUILD.format(tarball="a" * 128, patch="b" * 128).replace(
            "  0001-fix.patch\n", f"  0001-fix.patch\n{'c' * 128}  {key}\n{'e' * 128}  _apk\n"
        )

        self.assertEqual(
            release_sources.apkbuild_checksums(text),
            [
                ("a" * 128, "busybox-1.37.0.tar.bz2"),
                ("b" * 128, "0001-fix.patch"),
                ("c" * 128, key),
                ("e" * 128, "_apk"),
            ],
        )
        for name in ("../APKBUILD", ".hidden", "a/b", "-option"):
            with self.subTest(name=name), self.assertRaisesRegex(SourceError, "unsafe file name"):
                release_sources.apkbuild_checksums(f'sha512sums="{"d" * 128}  {name}"')

    def test_fetch_takes_the_aports_folder_and_the_distfiles_with_their_hashes(self):
        package = AlpinePackage("busybox", "1.37.0-r20", COMMIT)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            release_sources.fetch_alpine(package, "v3.22", folder, fetcher(alpine_site()))

            self.assertEqual(
                sorted(path.name for path in folder.iterdir()),
                ["0001-fix.patch", "APKBUILD", "busybox-1.37.0.tar.bz2"],
            )
            self.assertEqual((folder / "busybox-1.37.0.tar.bz2").read_bytes(), UPSTREAM)

    def test_a_distfile_that_differs_from_its_sha512_is_refused(self):
        package = AlpinePackage("busybox", "1.37.0-r20", COMMIT)
        site = alpine_site(tarball=b"tampered")
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(
                SourceError, "busybox-1.37.0.tar.bz2 does not match its SHA-512"
            ),
        ):
            release_sources.fetch_alpine(package, "v3.22", Path(directory), fetcher(site))

    def test_branch_comes_from_the_alpine_release(self):
        self.assertEqual(release_sources.alpine_branch("3.22.3\n"), "v3.22")


class PackTests(unittest.TestCase):
    def test_packages_are_packed_whole_into_archives_below_the_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            for folder, size in (
                ("debian/a_1", 40_000),
                ("debian/b_1", 40_000),
                ("alpine/c-1", 30_000),
            ):
                (staging / folder).mkdir(parents=True)
                (staging / folder / "file").write_bytes(b"x" * size)
            output = Path(directory) / "out"

            archives = release_sources.pack(staging, output, "0.2.0-rc.1", limit=200_000)

            self.assertEqual(
                [path.name for path in archives], ["slateops-sources-0.2.0-rc.1-1.tar"]
            )
            archives = release_sources.pack(staging, output, "0.2.0-rc.1", limit=60_000)
            self.assertEqual(len(archives), 3)
            for archive in archives:
                with self.subTest(archive=archive.name):
                    self.assertLess(archive.stat().st_size, 60_000)
            with tarfile.open(archives[0]) as tar:
                self.assertEqual(tar.getnames(), ["alpine/c-1", "alpine/c-1/file"])

    def test_a_package_larger_than_the_limit_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            (staging / "debian/big_1").mkdir(parents=True)
            (staging / "debian/big_1/file").write_bytes(b"x" * 5_000)

            with self.assertRaisesRegex(SourceError, "debian/big_1 is larger than"):
                release_sources.pack(staging, Path(directory) / "out", "0.2.0-rc.1", limit=4_000)

    def test_the_default_limit_keeps_each_asset_below_github_s_2_gib(self):
        self.assertLess(release_sources.ASSET_LIMIT, 2 * 1024**3)


class DownloadTests(unittest.TestCase):
    def test_server_errors_are_tried_again_and_a_missing_file_is_not(self):
        def error(code: int) -> urllib.error.HTTPError:
            return urllib.error.HTTPError("https://x", code, "error", Message(), None)

        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"content"
        with (
            mock.patch("urllib.request.urlopen", side_effect=[error(503), response]) as urlopen,
            mock.patch("time.sleep") as sleep,
        ):
            self.assertEqual(release_sources.download("https://x"), b"content")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()

        with (
            mock.patch("urllib.request.urlopen", side_effect=[error(404)]) as urlopen,
            self.assertRaisesRegex(SourceError, "404"),
        ):
            release_sources.download("https://x")
        self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
