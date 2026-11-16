"""Contracts for the attached source packages (docs/plans/windows-installer.md W4-7, H4).

scripts/release_sources.py downloads the source files of the Debian packages of the Linux
image and the server image from snapshot.debian.org, and of the Alpine packages of the
Caddy image from aports and Alpine's distfiles, checks each file against its published
hash, and packs them into release assets below the size limit. These tests replace the
network with a table of URLs.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import subprocess
import tarfile
import tempfile
import textwrap
import threading
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
    def fetch(url: str, check=None) -> bytes:
        if url not in pages:
            raise release_sources.NotFoundError(f"HTTP 404 {url}")
        if check is not None:
            check(pages[url])
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


DISTFILE = "https://distfiles.alpinelinux.org/distfiles/v3.22/busybox-1.37.0.tar.bz2"


def busybox_apkbuild() -> bytes:
    return APKBUILD.format(
        tarball=hashlib.sha512(UPSTREAM).hexdigest(), patch=hashlib.sha512(PATCH).hexdigest()
    ).encode()


def git(*arguments: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.org", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def aports_mirror(root: Path, folders: dict[str, dict[str, bytes]]) -> tuple[str, str]:
    """A local git repository in place of Alpine's aports mirror; return its URL and commit.

    It allows what GitHub allows: a fetch by commit SHA, with a blob filter.
    """
    repository = root / "aports"
    repository.mkdir()
    git("init", "--quiet", cwd=repository)
    for folder, files in folders.items():
        for name, content in files.items():
            path = repository / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    (repository / "README").write_text("aports\n")
    git("add", "--all", cwd=repository)
    git("commit", "--quiet", "--message", "release", cwd=repository)
    git("config", "uploadpack.allowFilter", "true", cwd=repository)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=repository)
    return repository.as_uri(), git("rev-parse", "HEAD", cwd=repository)


def busybox_mirror(root: Path, repository: str = "main") -> tuple[str, str]:
    return aports_mirror(
        root,
        {
            f"{repository}/busybox": {"APKBUILD": busybox_apkbuild(), "0001-fix.patch": PATCH},
            "main/other": {"APKBUILD": b"pkgname=other\n"},
        },
    )


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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            url, commit = busybox_mirror(root)
            package = AlpinePackage("busybox", "1.37.0-r20", commit)
            checkout = release_sources.AportsMirror(url, root / "work").checkout(
                commit, ["busybox"]
            )
            folder = root / "out"

            release_sources.fetch_alpine(
                package, "v3.22", folder, fetcher({DISTFILE: UPSTREAM}), checkout
            )

            self.assertEqual(
                sorted(path.name for path in folder.iterdir()),
                ["0001-fix.patch", "APKBUILD", "busybox-1.37.0.tar.bz2"],
            )
            self.assertEqual((folder / "busybox-1.37.0.tar.bz2").read_bytes(), UPSTREAM)

    def test_a_distfile_that_differs_from_its_sha512_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            url, commit = busybox_mirror(root)
            package = AlpinePackage("busybox", "1.37.0-r20", commit)
            checkout = release_sources.AportsMirror(url, root / "work").checkout(
                commit, ["busybox"]
            )
            site = {DISTFILE: b"tampered"}
            with self.assertRaisesRegex(
                SourceError, "busybox-1.37.0.tar.bz2 does not match its SHA-512"
            ):
                release_sources.fetch_alpine(
                    package, "v3.22", root / "out", fetcher(site), checkout
                )

    def test_branch_comes_from_the_alpine_release(self):
        self.assertEqual(release_sources.alpine_branch("3.22.3\n"), "v3.22")


class AportsMirrorTests(unittest.TestCase):
    """Run 43927846839 (rc.7): gitlab.alpinelinux.org answers GitHub's runners with HTTP 418.

    The aports files now come by git, at the pinned commit, from Alpine's mirror, so each
    file is bound to the commit. A local repository stands in for the mirror.
    """

    def setUp(self) -> None:
        patcher = mock.patch("time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_the_folder_at_the_commit_is_read_from_main_or_community(self):
        for repository in ("main", "community"):
            with self.subTest(repository=repository):
                root = self.root / repository
                root.mkdir()
                url, commit = busybox_mirror(root, repository)
                mirror = release_sources.AportsMirror(url, root / "work")
                checkout = mirror.checkout(commit, ["busybox"])

                files = release_sources.aports_folder(
                    checkout, AlpinePackage("busybox", "1.37.0-r20", commit)
                )

                self.assertEqual(files, {"APKBUILD": busybox_apkbuild(), "0001-fix.patch": PATCH})
                # The sparse checkout holds only the requested folders.
                self.assertFalse((checkout / "main/other").exists())
        self.sleep.assert_not_called()

    def test_a_folder_missing_at_the_commit_fails_as_no_folder(self):
        url, commit = busybox_mirror(self.root)
        checkout = release_sources.AportsMirror(url, self.root / "work").checkout(commit, ["gone"])

        with self.assertRaisesRegex(SourceError, f"aports has no folder for gone at {commit}"):
            release_sources.aports_folder(checkout, AlpinePackage("gone", "1.0-r0", commit))
        self.sleep.assert_not_called()

    def test_a_commit_missing_from_the_mirror_fails_at_once_and_names_the_commit(self):
        url, _ = busybox_mirror(self.root)
        missing = "0123456789abcdef0123456789abcdef01234567"

        with self.assertRaisesRegex(SourceError, f"commit {missing} is not in {url}"):
            release_sources.AportsMirror(url, self.root / "work").checkout(missing, ["busybox"])
        self.sleep.assert_not_called()

    def test_an_unreachable_mirror_is_tried_again_and_fails_with_its_cause(self):
        url = (self.root / "no-such-repository").as_uri()
        commit = "0123456789abcdef0123456789abcdef01234567"

        with self.assertRaisesRegex(SourceError, "git fetch .* after 6 tries"):
            release_sources.AportsMirror(url, self.root / "work").checkout(commit, ["busybox"])
        self.assertEqual(self.sleep.call_count, 5)


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


Answer = tuple[int, dict[str, str], bytes]


class FakeServer:
    """A local HTTP server that gives each path its scripted answers in order.

    The last answer of a path repeats. An answer with status 0 sleeps past the client's
    time-out; one with the header "X-Truncate" sends fewer bytes than Content-Length.
    """

    def __init__(self, answers: dict[str, list[Answer]]) -> None:
        self.answers = answers
        self.calls: dict[str, int] = {}
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def answer(self) -> None:
                count = server.calls.get(self.path, 0)
                server.calls[self.path] = count + 1
                script = server.answers.get(self.path, [(404, {}, b"not found")])
                status, headers, body = script[min(count, len(script) - 1)]
                if status == 0:
                    threading.Event().wait(0.5)  # not time.sleep: the tests patch it
                    status = 200
                self.send_response(status)
                length = len(body) + (100 if "X-Truncate" in headers else 0)
                self.send_header("Content-Length", str(length))
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            do_GET = answer  # the method name that http.server calls for a GET

            def log_message(self, *args: object) -> None:
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> FakeServer:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class TransientAnswerTests(unittest.TestCase):
    """Run 43925764551 (rc.6): a transient answer must be tried again and name its cause.

    Each answer below reaches the real download() through a local server; the waits are
    recorded, not slept.
    """

    def setUp(self) -> None:
        patcher = mock.patch("time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_rate_limit_and_server_errors_are_tried_again_with_growing_waits(self):
        main = "/distfiles/v3.22/busybox-1.37.0.tar.bz2"
        answers = [(429, {"Retry-After": "7"}, b""), (503, {}, b""), (502, {}, b"")]
        with FakeServer({main: [*answers, (200, {}, UPSTREAM)]}) as server:
            content = release_sources.download(f"{server.url}{main}")

        self.assertEqual(content, UPSTREAM)
        self.assertEqual(server.calls[main], 4)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [7, 4, 8])

    def test_a_persistent_transient_answer_fails_with_its_cause_not_no_folder(self):
        main = "/mr/package/bash/5.2.37-2/srcfiles?fileinfo=1"
        for case, answer, cause in (
            ("rate limit", (429, {}, b""), "HTTP 429 after 6 tries"),
            ("forbidden", (403, {}, b"blocked"), "HTTP 403 after 6 tries"),
            ("server error", (500, {}, b""), "HTTP 500 after 6 tries"),
            ("challenge page", (200, {}, b"<html>checking</html>"), "unusable answer"),
            ("truncated body", (200, {"X-Truncate": "1"}, b"{}"), "after 6 tries"),
        ):
            self.sleep.reset_mock()
            with (
                self.subTest(case=case),
                FakeServer({main: [answer]}) as server,
                self.assertRaisesRegex(SourceError, cause) as raised,
            ):
                release_sources.download(f"{server.url}{main}", release_sources._json)
            self.assertNotIn("no folder", str(raised.exception))
            self.assertEqual(server.calls[main], 6)

    def test_a_time_out_is_tried_again(self):
        with FakeServer({"/slow": [(0, {}, b""), (200, {}, b"content")]}) as server:
            content = release_sources.download(f"{server.url}/slow", timeout=0.2)

        self.assertEqual((content, server.calls["/slow"]), (b"content", 2))

    def test_a_snapshot_answer_that_is_not_json_is_tried_again(self):
        page = "/mr/package/bash/5.2.37-2/srcfiles?fileinfo=1"
        site = debian_site()
        answers: dict[str, list[Answer]] = {
            url.removeprefix(SNAPSHOT): [(200, {}, body)] for url, body in site.items()
        }
        answers[page] = [(200, {}, b"<html>busy</html>"), *answers[page]]
        with (
            FakeServer(answers) as server,
            mock.patch.object(release_sources, "SNAPSHOT", server.url),
            tempfile.TemporaryDirectory() as directory,
        ):
            release_sources.fetch_debian(
                "bash", "5.2.37-2", Path(directory), release_sources.download
            )

        self.assertEqual(server.calls[page], 2)
        self.sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
