"""Contracts for the release workflow helpers (docs/plans/windows-installer.md 5.2, 5.3; W3)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from scripts import release_artifacts
from scripts.release_artifacts import ReleaseError

ROOT = Path(__file__).resolve().parents[2]
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
SERVER = f"ghcr.io/jayeuse/slateops-server:0.2.0-rc.1@{DIGEST_A}"
CADDY = f"ghcr.io/jayeuse/slateops-caddy:0.2.0-rc.1@{DIGEST_B}"
SERVER_INFO = {
    "ref": SERVER,
    "archive": "slateops-server-0.2.0-rc.1-amd64.oci.tar",
    "sha256": "d" * 64,
    "size": 123456,
    "config_digest": "sha256:" + "e" * 64,
}
CADDY_INFO = {
    "ref": CADDY,
    "archive": "slateops-caddy-0.2.0-rc.1-amd64.oci.tar",
    "sha256": "f" * 64,
    "size": 654321,
    "config_digest": "sha256:" + "1" * 64,
}
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
IDENTITY = "https://github.com/jayeuse/slateops/.github/workflows/release.yml@refs/tags/v0.2.0-rc.1"

COMPOSE = textwrap.dedent(
    f"""\
    name: supabase

    services:
      db:
        image: ghcr.io/supabase/postgres:17.11.0.004@{DIGEST_A}
        restart: unless-stopped
      provider-volume-init:
        image: "ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}"
      storage:
        image: ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}
        environment:
          image: not-an-image-reference
      api-gw:
        image: envoyproxy/envoy:v1.39.1@{DIGEST_C}

    volumes:
      supabase-db-data:
    """
)


VERSIONS = {"backend/pyproject.toml": "0.2.0", "frontend/package.json": "0.2.0"}


class ReleaseTagTests(unittest.TestCase):
    def test_rc_tag_is_a_test_build_pre_release(self):
        tag = release_artifacts.classify_tag("v0.2.0-rc.1", "JayEuse", VERSIONS)

        self.assertEqual(
            tag,
            release_artifacts.ReleaseTag(
                version="0.2.0-rc.1",
                prerelease=True,
                title="Test build, not for customers (v0.2.0-rc.1)",
                image_prefix="ghcr.io/jayeuse",
            ),
        )

    def test_stable_tag_is_refused_while_the_license_work_constant_is_false(self):
        # DEC-0029 item 13 and plan 5.3: the license work's pull request flips the constant.
        with self.assertRaisesRegex(ReleaseError, "license work"):
            release_artifacts.classify_tag("v0.2.0", "jayeuse", VERSIONS)

        self.assertEqual(
            release_artifacts.classify_tag("v0.2.0", "jayeuse", VERSIONS, license_work_merged=True),
            release_artifacts.ReleaseTag(
                version="0.2.0",
                prerelease=False,
                title="Slate Operations v0.2.0",
                image_prefix="ghcr.io/jayeuse",
            ),
        )

    def test_tags_outside_the_release_shape_or_version_are_refused(self):
        for tag, reason in (
            ("v0.2", "is not vX.Y.Z"),
            ("0.2.0", "is not vX.Y.Z"),
            ("v0.2.0-beta.1", "is not vX.Y.Z"),
            ("v0.2.0-rc", "is not vX.Y.Z"),
            ("v0.2.0-rc.01", "is not vX.Y.Z"),
            ("v0.2.0-rc.0", "is not vX.Y.Z"),
            ("v01.2.0", "is not vX.Y.Z"),
            ("v0.2.0+build", "is not vX.Y.Z"),
            ("v0.2.0-rc.1\n", "is not vX.Y.Z"),
            ("v0.3.0-rc.1", "needs version 0.3.0"),
        ):
            with self.subTest(tag=tag), self.assertRaisesRegex(ReleaseError, reason):
                release_artifacts.classify_tag(tag, "jayeuse", VERSIONS, license_work_merged=True)

    def test_tag_command_writes_step_outputs_and_fails_closed_on_a_refused_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            commits = git_history(repository)
            output = Path(directory) / "github-output"
            accepted = tag_command("v0.2.0-rc.1", commits["branch"], repository, output)
            self.assertEqual(accepted, 0)
            self.assertEqual(
                output.read_text(),
                "version=0.2.0-rc.1\n"
                "prerelease=true\n"
                "title=Test build, not for customers (v0.2.0-rc.1)\n"
                "image_prefix=ghcr.io/jayeuse\n",
            )

            refused_output = Path(directory) / "refused-output"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                refused = tag_command("v0.2.0", commits["main"], repository, refused_output)
            self.assertEqual(refused, 1)
            self.assertFalse(refused_output.exists())
            self.assertIn("license work", stderr.getvalue())

    def test_tag_commits_rc_on_a_pushed_branch_and_stable_on_main(self):
        # Parent decisions D3 and D4 on TASK-0079; plan 5.1 rule 1.
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            commits = git_history(repository)
            cases = (
                ("v0.2.0-rc.1", "branch", "origin/main", 0, ""),
                ("v0.2.0-rc.1", "main", "origin/main", 0, ""),
                ("v0.2.0-rc.1", "unpushed", "origin/main", 1, "on no pushed branch"),
                ("v0.2.0", "main", "origin/main", 0, ""),
                ("v0.2.0", "branch", "origin/main", 1, "is not on main"),
                ("v0.2.0", "main", "origin/missing", 1, "cannot check"),
            )
            with mock.patch.object(release_artifacts, "LICENSE_WORK_MERGED", True):
                for index, (tag, commit, main_ref, status, message) in enumerate(cases):
                    with self.subTest(tag=tag, commit=commit, main_ref=main_ref):
                        output = Path(directory) / f"output-{index}"
                        stderr = io.StringIO()
                        with contextlib.redirect_stderr(stderr):
                            result = tag_command(tag, commits[commit], repository, output, main_ref)
                        self.assertEqual(result, status)
                        self.assertEqual(output.exists(), status == 0)
                        self.assertIn(message, stderr.getvalue())

    def test_the_workflow_runs_the_tag_command_as_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            commits = git_history(repository)
            output = Path(directory) / "github-output"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/release_artifacts.py"),
                    *tag_arguments("v0.2.0-rc.1", commits["branch"], repository, output),
                ],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("version=0.2.0-rc.1\n", output.read_text())


def git_history(root: Path) -> dict[str, str]:
    """A repository like the workflow's checkout: origin/main, a pushed branch after it,
    and a commit that no remote branch contains."""

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit(message: str) -> str:
        git("-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", message)
        return git("rev-parse", "HEAD")

    (root / "backend").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "backend/pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.2.0"\n')
    (root / "frontend/package.json").write_text('{"name": "x", "version": "0.2.0"}\n')
    git("init", "-q", "-b", "main")
    git("config", "user.email", "ci@example.invalid")
    git("config", "user.name", "CI Test")
    git("add", ".")
    commits = {"main": commit("on main")}
    git("update-ref", "refs/remotes/origin/main", commits["main"])
    git("switch", "-q", "-c", "feat/windows-installer")
    commits["branch"] = commit("on the branch")
    git("update-ref", "refs/remotes/origin/feat/windows-installer", commits["branch"])
    commits["unpushed"] = commit("not pushed")
    return commits


def tag_arguments(
    tag: str, commit: str, root: Path, output: Path, main_ref: str = "origin/main"
) -> list[str]:
    return [
        "tag",
        "--tag",
        tag,
        "--owner",
        "jayeuse",
        "--commit",
        commit,
        "--main-ref",
        main_ref,
        "--repository-root",
        str(root),
        "--github-output",
        str(output),
    ]


def tag_command(
    tag: str, commit: str, root: Path, output: Path, main_ref: str = "origin/main"
) -> int:
    return release_artifacts.main(tag_arguments(tag, commit, root, output, main_ref))


class ReleaseManifestTests(unittest.TestCase):
    def test_provider_images_are_the_unique_service_references_as_written(self):
        self.assertEqual(
            release_artifacts.provider_images(COMPOSE),
            [
                f"envoyproxy/envoy:v1.39.1@{DIGEST_C}",
                f"ghcr.io/supabase/postgres:17.11.0.004@{DIGEST_A}",
                f"ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}",
            ],
        )

    def test_provider_reference_without_a_pinned_digest_is_refused(self):
        for image in (
            "supabase/gotrue:v2.196.0",
            "supabase/gotrue@sha256:1234",
            "${AUTH_IMAGE}",
            f"${{AUTH_IMAGE:-supabase/gotrue}}@{DIGEST_A}",
        ):
            compose = f"services:\n  auth:\n    image: {image}\n"
            with self.subTest(image=image), self.assertRaisesRegex(ReleaseError, "auth"):
                release_artifacts.provider_images(compose)

    def test_repository_compose_file_has_only_pinned_provider_images(self):
        # The release reads infra/supabase/compose.yaml at the tag; an unpinned reference
        # would stop the release after the images were already pushed.
        compose = (ROOT / "infra/supabase/compose.yaml").read_text()

        image_lines = set(re.findall(r"(?m)^    image:\s*(\S+)\s*$", compose))

        self.assertEqual(len(release_artifacts.provider_images(compose)), len(image_lines))

    def test_manifest_has_schema_version_image_objects_and_omits_later_fields(self):
        manifest = release_artifacts.build_manifest(
            "0.2.0-rc.1", SERVER_INFO, CADDY_INFO, release_artifacts.provider_images(COMPOSE)
        )

        self.assertEqual(
            manifest,
            {
                "schema_version": 1,
                "version": "0.2.0-rc.1",
                "images": {
                    "server": SERVER_INFO,
                    "caddy": CADDY_INFO,
                    "providers": [
                        f"envoyproxy/envoy:v1.39.1@{DIGEST_C}",
                        f"ghcr.io/supabase/postgres:17.11.0.004@{DIGEST_A}",
                        f"ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}",
                    ],
                },
            },
        )

    def test_manifest_refuses_an_image_entry_that_is_not_the_tagged_archive(self):
        for field, value in (
            ("ref", f"ghcr.io/jayeuse/slateops-server@{DIGEST_A}"),
            ("ref", f"ghcr.io/jayeuse/slateops-server:0.2.0-rc.2@{DIGEST_A}"),
            ("ref", "ghcr.io/jayeuse/slateops-server:0.2.0-rc.1"),
            ("ref", f"ghcr.io/jayeuse/slateops-caddy:0.2.0-rc.1@{DIGEST_A}"),
            ("archive", "slateops-server-0.2.0-rc.2-amd64.oci.tar"),
            ("sha256", "A" * 64),
            ("sha256", "a" * 63),
            ("size", 0),
            ("size", True),
            ("size", "10"),
            ("config_digest", "c" * 64),
            ("extra", "x"),
        ):
            entry = {**SERVER_INFO, field: value}
            with (
                self.subTest(field=field, value=value),
                self.assertRaisesRegex(ReleaseError, "server image"),
            ):
                release_artifacts.build_manifest("0.2.0-rc.1", entry, CADDY_INFO, [])
        missing = {key: value for key, value in SERVER_INFO.items() if key != "config_digest"}
        with self.assertRaisesRegex(ReleaseError, "server image fields"):
            release_artifacts.build_manifest("0.2.0-rc.1", missing, CADDY_INFO, [])

    def test_manifest_command_writes_the_manifest_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text(COMPOSE)
            (root / "server.json").write_text(json.dumps(SERVER_INFO))
            (root / "caddy.json").write_text(json.dumps(CADDY_INFO))
            output = root / "dist" / "release-manifest.json"

            status = release_artifacts.main(
                [
                    "manifest",
                    "--version",
                    "0.2.0-rc.1",
                    "--server-info",
                    str(root / "server.json"),
                    "--caddy-info",
                    str(root / "caddy.json"),
                    "--compose",
                    str(root / "compose.yaml"),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.read_text())["images"]["caddy"], CADDY_INFO)


ENGINE_INFO = {
    "archive": "slateops-engine-0.2.0-rc.1.tar.gz",
    "sha256": "3" * 64,
    "size": 61234,
}
STARTED_COMPOSE = textwrap.dedent(
    f"""\
    services:
      db:
        image: ghcr.io/supabase/postgres:17.11.0.004@{DIGEST_A}
      imgproxy:
        image: darthsim/imgproxy:v3.31.4@sha256:{"e" * 64}
      provider-volume-init:
        image: ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}
      storage:
        image: ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}
      meta:
        image: supabase/postgres-meta:v0.100.0@sha256:{"f" * 64}
      studio:
        image: supabase/studio:2026.10.05@sha256:{"d" * 64}
      api-gw:
        image: envoyproxy/envoy:v1.39.1@{DIGEST_C}
    """
)


class EngineManifestTests(unittest.TestCase):
    """TASK-0085 AC-B4 and design choice 4 (space-cut carry in TASK-0083 Notes)."""

    def test_manifest_adds_the_engine_bundle_and_the_known_bad_wsl_list(self):
        manifest = release_artifacts.build_manifest(
            "0.2.0-rc.1", SERVER_INFO, CADDY_INFO, [], engine=ENGINE_INFO, known_bad_wsl=[]
        )

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["engine_bundle"], ENGINE_INFO)
        self.assertEqual(manifest["known_bad_wsl_versions"], [])

    def test_manifest_refuses_an_engine_entry_that_is_not_the_tagged_bundle(self):
        for field, value in (
            ("archive", "slateops-engine-0.2.0-rc.2.tar.gz"),
            ("sha256", "A" * 64),
            ("size", 0),
            ("size", True),
            ("extra", "x"),
        ):
            entry = {**ENGINE_INFO, field: value}
            with (
                self.subTest(field=field, value=value),
                self.assertRaisesRegex(ReleaseError, "engine bundle"),
            ):
                release_artifacts.build_manifest(
                    "0.2.0-rc.1", SERVER_INFO, CADDY_INFO, [], engine=entry
                )

    def test_every_install_provider_service_exists_in_the_repository_compose_file(self):
        # Architect finding 5: a renamed service would drop its image from the pull list.
        compose = (ROOT / "infra/supabase/compose.yaml").read_text()
        services = set(
            re.findall(r"(?m)^  ([A-Za-z0-9_.-]+):\s*$", compose.split("\nvolumes:", 1)[0])
        )

        self.assertEqual(release_artifacts.INSTALL_PROVIDER_SERVICES - services, set())

    def test_the_manifest_lists_only_the_providers_that_customer_installs_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text(STARTED_COMPOSE)
            for name, info in (
                ("server", SERVER_INFO),
                ("caddy", CADDY_INFO),
                ("engine", ENGINE_INFO),
            ):
                (root / f"{name}.json").write_text(json.dumps(info))
            output = root / "release-manifest.json"

            status = release_artifacts.main(
                [
                    "manifest", "--version", "0.2.0-rc.1",
                    "--server-info", str(root / "server.json"),
                    "--caddy-info", str(root / "caddy.json"),
                    "--engine-info", str(root / "engine.json"),
                    "--compose", str(root / "compose.yaml"),
                    "--output", str(output),
                ]
            )

            manifest = json.loads(output.read_text())
            self.assertEqual(status, 0)
            self.assertEqual(
                manifest["images"]["providers"],
                [
                    f"envoyproxy/envoy:v1.39.1@{DIGEST_C}",
                    f"ghcr.io/supabase/postgres:17.11.0.004@{DIGEST_A}",
                    f"ghcr.io/supabase/storage-api:v1.81.0@{DIGEST_B}",
                ],
            )
            self.assertEqual(manifest["engine_bundle"], ENGINE_INFO)
            self.assertEqual(manifest["known_bad_wsl_versions"], [])


LINUX_INFO = {
    "archive": "slateops-linux-0.2.0-rc.1-amd64.tar.gz",
    "sha256": "2" * 64,
    "size": 251666497,
}


class LinuxImageManifestTests(unittest.TestCase):
    def test_manifest_adds_the_linux_image_entry_and_keeps_schema_version_1(self):
        # Plan 5.2 and W4: the SHA-256 of the Linux image; an added field keeps version 1.
        manifest = release_artifacts.build_manifest(
            "0.2.0-rc.1", SERVER_INFO, CADDY_INFO, [], linux=LINUX_INFO
        )

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["linux_image"], LINUX_INFO)

    def test_manifest_refuses_a_linux_entry_that_is_not_the_tagged_amd64_tarball(self):
        for field, value in (
            ("archive", "slateops-linux-0.2.0-rc.2-amd64.tar.gz"),
            ("archive", "slateops-linux-0.2.0-rc.1-arm64.tar.gz"),
            ("sha256", "A" * 64),
            ("size", 0),
            ("size", True),
            ("extra", "x"),
        ):
            entry = {**LINUX_INFO, field: value}
            with (
                self.subTest(field=field, value=value),
                self.assertRaisesRegex(ReleaseError, "linux image"),
            ):
                release_artifacts.build_manifest(
                    "0.2.0-rc.1", SERVER_INFO, CADDY_INFO, [], linux=entry
                )

    def test_manifest_command_reads_the_linux_image_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text(COMPOSE)
            (root / "server.json").write_text(json.dumps(SERVER_INFO))
            (root / "caddy.json").write_text(json.dumps(CADDY_INFO))
            (root / "linux.json").write_text(json.dumps(LINUX_INFO))
            output = root / "release-manifest.json"

            status = release_artifacts.main(
                [
                    "manifest",
                    "--version",
                    "0.2.0-rc.1",
                    "--server-info",
                    str(root / "server.json"),
                    "--caddy-info",
                    str(root / "caddy.json"),
                    "--linux-info",
                    str(root / "linux.json"),
                    "--compose",
                    str(root / "compose.yaml"),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.read_text())["linux_image"], LINUX_INFO)


def write_oci_archive(
    path: Path, *, manifests: int = 1, media_type: str = OCI_MANIFEST, tamper: str = ""
) -> str:
    """Write a small OCI layout tar like `skopeo copy oci-archive:`; return its digest."""

    def blob(content: bytes) -> tuple[str, bytes]:
        return "sha256:" + hashlib.sha256(content).hexdigest(), content

    config_digest, config = blob(b'{"architecture":"amd64","os":"linux"}')
    layer_digest, layer = blob(b"layer bytes")
    manifest_digest, manifest = blob(
        json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": OCI_MANIFEST,
                "config": {"digest": config_digest, "size": len(config)},
                "layers": [{"digest": layer_digest, "size": len(layer)}],
            }
        ).encode()
    )
    blobs = {manifest_digest: manifest, config_digest: config, layer_digest: layer}
    if tamper:
        blobs[{"manifest": manifest_digest, "layer": layer_digest}[tamper]] = b"changed"
    entry = {"mediaType": media_type, "digest": manifest_digest, "size": len(manifest)}
    files = {
        "oci-layout": b'{"imageLayoutVersion":"1.0.0"}',
        "index.json": json.dumps({"schemaVersion": 2, "manifests": [entry] * manifests}).encode(),
    }
    files |= {f"blobs/sha256/{d.split(':')[1]}": content for d, content in blobs.items()}
    with tarfile.open(path, "w") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return manifest_digest


class ImageArchiveTests(unittest.TestCase):
    def test_archive_of_the_pushed_digest_gives_its_manifest_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "slateops-server-0.2.0-rc.1-amd64.oci.tar"
            digest = write_oci_archive(archive)
            reference = f"ghcr.io/jayeuse/slateops-server:0.2.0-rc.1@{digest}"

            entry = release_artifacts.image_info(reference, archive)

            self.assertEqual(
                entry,
                {
                    "ref": reference,
                    "archive": "slateops-server-0.2.0-rc.1-amd64.oci.tar",
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "size": archive.stat().st_size,
                    "config_digest": "sha256:"
                    + hashlib.sha256(b'{"architecture":"amd64","os":"linux"}').hexdigest(),
                },
            )

    def test_archive_that_is_not_exactly_the_pushed_digest_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            for case, options, reason in (
                ("other digest", {}, "not sha256:"),
                ("two manifests", {"manifests": 2}, "exactly one OCI image manifest"),
                (
                    "image index",
                    {"media_type": "application/vnd.oci.image.index.v1+json"},
                    "exactly one OCI image manifest",
                ),
                ("changed manifest", {"tamper": "manifest"}, "does not match its digest"),
                ("changed layer", {"tamper": "layer"}, "does not match its digest"),
            ):
                archive = Path(directory) / f"{case}.oci.tar"
                digest = write_oci_archive(archive, **options)
                if case == "other digest":
                    digest = DIGEST_A
                reference = f"ghcr.io/jayeuse/slateops-server:0.2.0-rc.1@{digest}"
                with self.subTest(case=case), self.assertRaisesRegex(ReleaseError, reason):
                    release_artifacts.image_info(reference, archive)

    def test_image_info_command_writes_the_entry_and_the_size_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "slateops-caddy-0.2.0-rc.1-amd64.oci.tar"
            digest = write_oci_archive(archive)
            summary = root / "summary.md"

            status = release_artifacts.main(
                [
                    "image-info",
                    "--reference",
                    f"ghcr.io/jayeuse/slateops-caddy:0.2.0-rc.1@{digest}",
                    "--archive",
                    str(archive),
                    "--output",
                    str(root / "caddy.json"),
                    "--summary",
                    str(summary),
                ]
            )

            self.assertEqual(status, 0)
            size = archive.stat().st_size
            self.assertEqual(json.loads((root / "caddy.json").read_text())["size"], size)
            self.assertEqual(
                summary.read_text(),
                f"- `slateops-caddy-0.2.0-rc.1-amd64.oci.tar` (archive): {size} bytes, "
                f"{size / 2**20:.1f} MiB\n",
            )


def write_distribution(
    site: Path, name: str, version: str, metadata: str, files: dict[str, str]
) -> None:
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata}"
    )
    record = [f"{info.name}/METADATA,,"]
    for relative, text in files.items():
        path = site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        record.append(f"{relative},,")
    record.append(f"{info.name}/RECORD,,")
    (info / "RECORD").write_text("\n".join(record) + "\n")


class ThirdPartyNoticeTests(unittest.TestCase):
    def test_python_notices_read_installed_license_metadata_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            write_distribution(
                site,
                "fastapi",
                "0.120.0",
                "License-Expression: MIT\n",
                {
                    "fastapi-0.120.0.dist-info/licenses/LICENSE": "MIT text\n",
                    "fastapi/__init__.py": "",
                },
            )
            write_distribution(
                site,
                "anyio",
                "4.11.0",
                "License: BSD\n",
                {"anyio-4.11.0.dist-info/LICENSE.txt": "BSD text\n"},
            )
            write_distribution(
                site,
                "bare",
                "1.0",
                "Classifier: License :: OSI Approved :: Apache Software License\n",
                {"bare/__init__.py": ""},
            )

            self.assertEqual(
                release_artifacts.python_notices(site),
                [
                    release_artifacts.Notice("anyio", "4.11.0", "BSD", ("BSD text\n",)),
                    release_artifacts.Notice(
                        "bare", "1.0", "OSI Approved :: Apache Software License", ()
                    ),
                    release_artifacts.Notice("fastapi", "0.120.0", "MIT", ("MIT text\n",)),
                ],
            )

    def test_npm_notices_cover_installed_production_packages_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "frontend", "version": "0.1.0"},
                    "node_modules/react": {"version": "19.2.0", "license": "MIT"},
                    "node_modules/typescript": {
                        "version": "5.9.0",
                        "license": "Apache-2.0",
                        "dev": True,
                    },
                    "node_modules/next/node_modules/react": {"version": "19.2.0", "license": "MIT"},
                    "node_modules/@next/swc-win32-x64-msvc": {
                        "version": "16.0.0",
                        "license": "MIT",
                        "optional": True,
                    },
                    "node_modules/next": {"version": "16.0.0", "license": "MIT"},
                    "node_modules/playwright": {
                        "version": "1.57.0",
                        "license": "Apache-2.0",
                        "devOptional": True,
                    },
                    "node_modules/local": {"resolved": "../local", "link": True},
                    "node_modules/nolicense": {"version": "1.0.0"},
                },
            }
            (root / "package-lock.json").write_text(json.dumps(lock))
            for package, files in {
                "react": {"LICENSE": "React MIT\n", "index.js": ""},
                "next": {"license.md": "Next MIT\n", "NOTICE": "Next notice\n"},
                "next/node_modules/react": {"LICENSE": "React MIT\n"},
                "nolicense": {"index.js": ""},
            }.items():
                folder = root / "node_modules" / package
                folder.mkdir(parents=True)
                for name, text in files.items():
                    (folder / name).write_text(text)

            self.assertEqual(
                release_artifacts.npm_notices(root),
                [
                    release_artifacts.Notice(
                        "next", "16.0.0", "MIT", ("Next notice\n", "Next MIT\n")
                    ),
                    release_artifacts.Notice("nolicense", "1.0.0", "UNKNOWN", ()),
                    release_artifacts.Notice("react", "19.2.0", "MIT", ("React MIT\n",)),
                ],
            )

    def test_npm_notices_refuse_a_production_package_that_is_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = {"packages": {"node_modules/react": {"version": "19.2.0", "license": "MIT"}}}
            (root / "package-lock.json").write_text(json.dumps(lock))

            with self.assertRaisesRegex(ReleaseError, "node_modules/react"):
                release_artifacts.npm_notices(root)

    def test_rendered_notices_name_each_source_and_list_packages_without_a_license_text(self):
        text = release_artifacts.render_notices(
            "0.2.0-rc.1",
            [release_artifacts.Notice("anyio", "4.11.0", "BSD", ("BSD text\n",))],
            [release_artifacts.Notice("nolicense", "1.0.0", "UNKNOWN", ())],
            [f"envoyproxy/envoy:v1.39.1@{DIGEST_C}"],
            debian=[
                release_artifacts.Notice(
                    "tzdata", "2025b-4", "UNKNOWN", (), f"{SNAPSHOT}/tzdata/2025b-4/"
                )
            ],
            alpine=[release_artifacts.Notice("musl", "1.2.5-r10", "MIT", ())],
        )

        self.assertTrue(text.startswith("Third-party notices for Slate Operations 0.2.0-rc.1\n"))
        for expected in (
            "anyio 4.11.0\nLicense: BSD\n",
            "BSD text\n",
            "nolicense 1.0.0\nLicense: UNKNOWN\n",
            f"envoyproxy/envoy:v1.39.1@{DIGEST_C}\n",
            "Packages without a license text in their installed files:\n"
            "- npm nolicense 1.0.0\n- debian tzdata 2025b-4\n- alpine musl 1.2.5-r10\n",
            f"tzdata 2025b-4\nLicense: UNKNOWN\nSource: {SNAPSHOT}/tzdata/2025b-4/\n",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)


DPKG_STATUS = textwrap.dedent(
    """\
    Package: bash
    Status: install ok installed
    Architecture: amd64
    Version: 5.2.37-2+b5
    Source: bash (5.2.37-2)
    Description: GNU Bourne Again SHell
     A continuation line: with a colon

    Package: libc6
    Status: install ok installed
    Version: 2.41-12
    Source: glibc

    Package: tzdata
    Status: install ok installed
    Version: 2025b-4

    Package: login
    Status: install ok installed
    Version: 1:4.16.0-2+really2.41-5
    Source: shadow (1:4.17.4-2)

    Package: removed
    Status: deinstall ok config-files
    Version: 1.0-1
    """
)
APK_INSTALLED = textwrap.dedent(
    """\
    C:Q1abc=
    P:musl
    V:1.2.5-r10
    A:x86_64
    L:MIT
    o:musl
    T:the musl c library

    P:busybox-binsh
    V:1.37.0-r19
    L:GPL-2.0-only
    o:busybox
    """
)
SNAPSHOT = "https://snapshot.debian.org/package"


def write_image_files(server: Path, caddy: Path) -> None:
    """Write the files that the workflow copies out of the two images."""
    status = server / "var/lib/dpkg/status"
    status.parent.mkdir(parents=True)
    status.write_text(DPKG_STATUS)
    for package, text in (("bash", "bash copyright\n"), ("libc6", "glibc copyright\n")):
        folder = server / "usr/share/doc" / package
        folder.mkdir(parents=True)
        (folder / "copyright").write_text(text)
    (server / "usr/share/doc/login").symlink_to("bash")
    installed = caddy / "lib/apk/db/installed"
    installed.parent.mkdir(parents=True)
    installed.write_text(APK_INSTALLED)


class ImagePackageTests(unittest.TestCase):
    def test_debian_notices_list_installed_packages_with_copyright_and_snapshot_source(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "server"
            write_image_files(server, Path(directory) / "caddy")

            self.assertEqual(
                release_artifacts.debian_notices(server),
                [
                    release_artifacts.Notice(
                        "bash",
                        "5.2.37-2+b5",
                        "/usr/share/doc/bash/copyright",
                        ("bash copyright\n",),
                        f"{SNAPSHOT}/bash/5.2.37-2/",
                    ),
                    release_artifacts.Notice(
                        "libc6",
                        "2.41-12",
                        "/usr/share/doc/libc6/copyright",
                        ("glibc copyright\n",),
                        f"{SNAPSHOT}/glibc/2.41-12/",
                    ),
                    release_artifacts.Notice(
                        "login",
                        "1:4.16.0-2+really2.41-5",
                        "/usr/share/doc/login/copyright",
                        ("bash copyright\n",),
                        f"{SNAPSHOT}/shadow/1%3A4.17.4-2/",
                    ),
                    release_artifacts.Notice(
                        "tzdata", "2025b-4", "UNKNOWN", (), f"{SNAPSHOT}/tzdata/2025b-4/"
                    ),
                ],
            )

    def test_source_offer_lists_each_debian_source_package_once(self):
        offer = release_artifacts.source_offer(
            "0.2.0-rc.1", release_artifacts.debian_packages(DPKG_STATUS)
        )

        self.assertTrue(offer.startswith("Source offer for Slate Operations 0.2.0-rc.1\n"))
        self.assertEqual(
            offer.split("\n\n")[-1],
            f"bash 5.2.37-2 {SNAPSHOT}/bash/5.2.37-2/\n"
            f"glibc 2.41-12 {SNAPSHOT}/glibc/2.41-12/\n"
            f"shadow 1:4.17.4-2 {SNAPSHOT}/shadow/1%3A4.17.4-2/\n"
            f"tzdata 2025b-4 {SNAPSHOT}/tzdata/2025b-4/\n",
        )

    def test_alpine_notices_list_the_installed_packages_and_their_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            caddy = Path(directory) / "caddy"
            write_image_files(Path(directory) / "server", caddy)

            self.assertEqual(
                release_artifacts.alpine_notices(caddy),
                [
                    release_artifacts.Notice(
                        "busybox-binsh",
                        "1.37.0-r19",
                        "GPL-2.0-only",
                        (),
                        "Alpine source package busybox 1.37.0-r19",
                    ),
                    release_artifacts.Notice(
                        "musl", "1.2.5-r10", "MIT", (), "Alpine source package musl 1.2.5-r10"
                    ),
                ],
            )

    def test_notices_command_writes_the_notices_and_the_source_offer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_distribution(root / "site", "anyio", "4.11.0", "License: BSD\n", {})
            (root / "npm").mkdir()
            (root / "npm/package-lock.json").write_text(json.dumps({"packages": {}}))
            write_image_files(root / "server", root / "caddy")
            (root / "compose.yaml").write_text(COMPOSE)

            with contextlib.redirect_stdout(io.StringIO()):
                status = release_artifacts.main(
                    [
                        "notices",
                        "--version",
                        "0.2.0-rc.1",
                        "--python-site-packages",
                        str(root / "site"),
                        "--npm-root",
                        str(root / "npm"),
                        "--server-files",
                        str(root / "server"),
                        "--caddy-files",
                        str(root / "caddy"),
                        "--compose",
                        str(root / "compose.yaml"),
                        "--output",
                        str(root / "dist/THIRD-PARTY-NOTICES.txt"),
                        "--source-offer",
                        str(root / "dist/SOURCE-OFFER.txt"),
                    ]
                )

            self.assertEqual(status, 0)
            notices = (root / "dist/THIRD-PARTY-NOTICES.txt").read_text()
            self.assertIn("glibc copyright\n", notices)
            self.assertIn("musl 1.2.5-r10\nLicense: MIT\n", notices)
            offer = (root / "dist/SOURCE-OFFER.txt").read_text()
            self.assertIn(f"glibc 2.41-12 {SNAPSHOT}/glibc/2.41-12/\n", offer)


LINUX_STATUS = textwrap.dedent(
    """\
    Package: chrony
    Status: install ok installed
    Architecture: amd64
    Version: 4.6.1-3

    Package: docker-ce
    Status: install ok installed
    Maintainer: Docker <support@docker.com>
    Architecture: amd64
    Version: 5:29.8.2-1~debian.13~trixie

    Package: containerd.io
    Status: install ok installed
    Maintainer: Docker <support@docker.com>
    Architecture: amd64
    Version: 2.3.6-1~debian.13~trixie
    """
)
GO_MODULES = (
    b"\x00\xff Go buildinf:\x08\x02 junk path\tgithub.com/caddyserver/caddy/v2/cmd/caddy\n"
    b"mod\tgithub.com/caddyserver/caddy/v2\tv2.10.2\th1:abc=\n"
    b"dep\tgithub.com/klauspost/compress\tv1.18.0\th1:def=\n"
    b"dep\tgolang.org/x/crypto\tv0.40.0\th1:ghi=\n"
    b"=>\tgithub.com/example/crypto-fork\tv0.40.1\th1:jkl=\n"
    b"build\tGOOS=linux\n\x00 more binary"
)


def write_linux_files(files: Path) -> None:
    """Write the package files that release_linux_image.py outputs copies out of the image."""
    status = files / "var/lib/dpkg/status"
    status.parent.mkdir(parents=True)
    status.write_text(LINUX_STATUS)
    for package, text in (("chrony", "chrony copyright\n"), ("containerd.io", "containerd\n")):
        folder = files / "usr/share/doc" / package
        folder.mkdir(parents=True)
        (folder / "copyright").write_text(text)
    (files / "usr/share/doc/cosign").mkdir(parents=True)
    (files / "usr/share/doc/cosign/LICENSE").write_text("Apache License 2.0\n")
    record = files / "usr/share/slateops/linux-image.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"version": "0.2.0-rc.1", "cosign": "3.1.4"}))


class LinuxImageNoticeTests(unittest.TestCase):
    def test_linux_notices_give_debian_docker_and_cosign_their_source_and_license(self):
        # W4-7: Docker's packages are not in the Debian archive, so their source is upstream.
        with tempfile.TemporaryDirectory() as directory:
            files = Path(directory)
            write_linux_files(files)

            notices = release_artifacts.linux_notices(files)

        self.assertEqual(
            notices,
            [
                release_artifacts.Notice(
                    "chrony",
                    "4.6.1-3",
                    "/usr/share/doc/chrony/copyright",
                    ("chrony copyright\n",),
                    f"{SNAPSHOT}/chrony/4.6.1-3/",
                ),
                release_artifacts.Notice(
                    "containerd.io",
                    "2.3.6-1~debian.13~trixie",
                    "/usr/share/doc/containerd.io/copyright",
                    ("containerd\n",),
                    "https://github.com/containerd/containerd/tree/v2.3.6",
                ),
                release_artifacts.Notice(
                    "docker-ce",
                    "5:29.8.2-1~debian.13~trixie",
                    "Apache-2.0",
                    (),
                    "https://github.com/moby/moby/tree/docker-v29.8.2",
                ),
                release_artifacts.Notice(
                    "cosign",
                    "3.1.4",
                    "Apache-2.0",
                    ("Apache License 2.0\n",),
                    "https://github.com/sigstore/cosign/tree/v3.1.4",
                ),
            ],
        )

    def test_python_runtime_notice_reads_the_license_of_the_image(self):
        with tempfile.TemporaryDirectory() as directory:
            license_file = Path(directory) / "LICENSE.txt"
            license_file.write_text("PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n")

            notice = release_artifacts.python_runtime_notice("3.14.10", license_file)

        self.assertEqual(
            notice,
            release_artifacts.Notice(
                "Python",
                "3.14.10",
                "PSF-2.0",
                ("PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n",),
                "https://www.python.org/ftp/python/3.14.10/Python-3.14.10.tar.xz",
            ),
        )

    def test_caddy_notices_list_caddy_and_the_go_modules_built_into_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "caddy").write_bytes(GO_MODULES)
            (root / "LICENSE").write_text("Apache License\n")

            notices = release_artifacts.caddy_notices("v2.10.2", root / "caddy", root / "LICENSE")

        self.assertEqual(
            notices,
            [
                release_artifacts.Notice(
                    "Caddy",
                    "2.10.2",
                    "Apache-2.0",
                    ("Apache License\n",),
                    "https://github.com/caddyserver/caddy/tree/v2.10.2",
                ),
                release_artifacts.Notice(
                    "github.com/example/crypto-fork",
                    "v0.40.1",
                    "UNKNOWN",
                    (),
                    "https://pkg.go.dev/github.com/example/crypto-fork@v0.40.1",
                ),
                release_artifacts.Notice(
                    "github.com/klauspost/compress",
                    "v1.18.0",
                    "UNKNOWN",
                    (),
                    "https://pkg.go.dev/github.com/klauspost/compress@v1.18.0",
                ),
            ],
        )

    def test_caddy_binary_without_module_data_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "caddy"
            binary.write_bytes(b"\x7fELF no build info")

            with self.assertRaisesRegex(ReleaseError, "no Go module data"):
                release_artifacts.caddy_notices("v2.10.2", binary, binary)

    def test_rendered_notices_add_the_linux_image_and_the_runtimes(self):
        text = release_artifacts.render_notices(
            "0.2.0-rc.1",
            [],
            [],
            [],
            linux=[release_artifacts.Notice("docker-ce", "5:29.8.2-1", "Apache-2.0", ())],
            runtimes=[release_artifacts.Notice("Python", "3.14.10", "PSF-2.0", ("PSF\n",))],
        )

        for expected in (
            "6. Linux image (slateops-linux)",
            "docker-ce 5:29.8.2-1\nLicense: Apache-2.0\n",
            "7. Python runtime, Caddy and its Go modules",
            "Python 3.14.10\nLicense: PSF-2.0\n",
            "- linux docker-ce 5:29.8.2-1\n",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertNotIn("Not listed yet", text)

    def test_source_offer_covers_the_linux_image_the_caddy_image_and_upstream_parts(self):
        linux = [release_artifacts.DebianPackage("chrony", "4.6.1-3", "chrony", "4.6.1-3")]
        server = release_artifacts.debian_packages(DPKG_STATUS)
        alpine = release_artifacts.alpine_packages(
            APK_INSTALLED.replace("o:busybox\n", "o:busybox\nc:2e97d754\n").replace(
                "o:musl\n", "o:musl\nc:1a5f5e69\n"
            )
        )

        offer = release_artifacts.source_offer(
            "0.2.0-rc.1",
            server,
            linux=linux,
            alpine=alpine,
            upstream=["cosign 3.1.4 https://github.com/sigstore/cosign/tree/v3.1.4"],
        )

        for expected in (
            "slateops-sources-0.2.0-rc.1-",
            "Linux image (slateops-linux-0.2.0-rc.1-amd64.tar.gz), Debian source packages:\n"
            f"chrony 4.6.1-3 {SNAPSHOT}/chrony/4.6.1-3/\n",
            "Caddy image (slateops-caddy), Alpine source packages:\n"
            "busybox 1.37.0-r19 https://github.com/alpinelinux/aports/tree/2e97d754\n",
            "Other parts, at their upstream source:\n"
            "cosign 3.1.4 https://github.com/sigstore/cosign/tree/v3.1.4\n",
            f"Server image (slateops-server), Debian source packages:\nbash 5.2.37-2 {SNAPSHOT}",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, offer)

    def test_an_alpine_package_without_its_aports_commit_is_refused(self):
        with self.assertRaisesRegex(ReleaseError, "musl has no aports commit"):
            release_artifacts.alpine_packages(APK_INSTALLED)

    def test_notices_command_adds_the_linux_image_python_and_caddy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_distribution(root / "site", "anyio", "4.11.0", "License: BSD\n", {})
            (root / "npm").mkdir()
            (root / "npm/package-lock.json").write_text(json.dumps({"packages": {}}))
            write_image_files(root / "server", root / "caddy")
            installed = root / "caddy/lib/apk/db/installed"
            installed.write_text(installed.read_text().replace("o:musl\n", "o:musl\nc:1a5f5e69\n"))
            installed.write_text(
                installed.read_text().replace("o:busybox\n", "o:busybox\nc:2e97d754\n")
            )
            write_linux_files(root / "linux")
            (root / "compose.yaml").write_text(COMPOSE)
            (root / "PYTHON-LICENSE.txt").write_text("PSF text\n")
            (root / "caddy-bin").write_bytes(GO_MODULES)
            (root / "CADDY-LICENSE").write_text("Apache text\n")

            with contextlib.redirect_stdout(io.StringIO()):
                status = release_artifacts.main(
                    [
                        "notices",
                        "--version",
                        "0.2.0-rc.1",
                        "--python-site-packages",
                        str(root / "site"),
                        "--npm-root",
                        str(root / "npm"),
                        "--server-files",
                        str(root / "server"),
                        "--caddy-files",
                        str(root / "caddy"),
                        "--linux-files",
                        str(root / "linux"),
                        "--python-version",
                        "3.14.10",
                        "--python-license",
                        str(root / "PYTHON-LICENSE.txt"),
                        "--caddy-version",
                        "v2.10.2",
                        "--caddy-binary",
                        str(root / "caddy-bin"),
                        "--caddy-license",
                        str(root / "CADDY-LICENSE"),
                        "--compose",
                        str(root / "compose.yaml"),
                        "--output",
                        str(root / "dist/THIRD-PARTY-NOTICES.txt"),
                        "--source-offer",
                        str(root / "dist/SOURCE-OFFER.txt"),
                    ]
                )

            self.assertEqual(status, 0)
            notices = (root / "dist/THIRD-PARTY-NOTICES.txt").read_text()
            for expected in ("chrony copyright\n", "PSF text\n", "Apache text\n", "cosign 3.1.4\n"):
                with self.subTest(expected=expected):
                    self.assertIn(expected, notices)
            offer = (root / "dist/SOURCE-OFFER.txt").read_text()
            for expected in (
                f"chrony 4.6.1-3 {SNAPSHOT}/chrony/4.6.1-3/\n",
                "musl 1.2.5-r10 https://github.com/alpinelinux/aports/tree/1a5f5e69\n",
                "docker-ce 5:29.8.2-1~debian.13~trixie https://github.com/moby/moby/tree/docker-v29.8.2\n",
                "Python 3.14.10 https://www.python.org/ftp/python/3.14.10/Python-3.14.10.tar.xz\n",
                "Caddy 2.10.2 https://github.com/caddyserver/caddy/tree/v2.10.2\n",
                f"glibc 2.41-12 {SNAPSHOT}/glibc/2.41-12/\n",
            ):
                with self.subTest(expected=expected):
                    self.assertIn(expected, offer)


class ReleaseNotesTests(unittest.TestCase):
    def test_notes_give_cosign_verify_commands_with_the_workflow_identity(self):
        notes = release_artifacts.release_notes(
            "v0.2.0-rc.1", True, IDENTITY, "jayeuse/slateops", SERVER, CADDY
        )

        self.assertTrue(notes.startswith("**Test build, not for customers.**"))
        self.assertTrue(
            notes.endswith(
                "A failed build of this workflow is never re-run. The fix is a new tag with "
                "the next rc number.\n"
            )
        )
        issuer = "--certificate-oidc-issuer https://token.actions.githubusercontent.com"
        for expected in (
            f"cosign verify --certificate-identity {IDENTITY} {issuer} {SERVER}",
            f"cosign verify --certificate-identity {IDENTITY} {issuer} {CADDY}",
            "cosign verify-blob --bundle release-manifest.json.sigstore.json "
            f"--certificate-identity {IDENTITY} {issuer} release-manifest.json",
            f"gh attestation verify oci://{SERVER} --repo jayeuse/slateops "
            f"--cert-identity {IDENTITY} --deny-self-hosted-runners",
            f"gh attestation verify oci://{CADDY} --repo jayeuse/slateops "
            f"--cert-identity {IDENTITY} --deny-self-hosted-runners",
            "sha256sum --check SHA256SUMS",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, notes)

    def test_stable_notes_carry_no_test_build_warning(self):
        notes = release_artifacts.release_notes(
            "v0.2.0", False, IDENTITY, "jayeuse/slateops", SERVER, CADDY
        )

        self.assertNotIn("Test build", notes)


if __name__ == "__main__":
    unittest.main()
