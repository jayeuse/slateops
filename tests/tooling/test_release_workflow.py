"""Contracts for the release workflow (docs/plans/windows-installer.md 5.2, 5.3; W3-1 to W3-4, W4).

The workflow runs only on a release tag, so these checks read its text. The first rc tag
run proves the runtime parts (push, signatures, attestations, the draft release).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"
JOBS = (
    "check",
    "images",
    "engine-bundle",
    "linux-image",
    "manifest",
    "notices",
    "source-packages",
    "install-proof",
    "release",
)


def job_blocks(source: str) -> dict[str, str]:
    body = source.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][a-z0-9-]*):\n", body)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def mapping(block: str, key: str, indent: int) -> dict[str, str]:
    match = re.search(rf"(?m)^{' ' * indent}{key}:\n((?:{' ' * (indent + 2)}\S.*\n)+)", block)
    if match is None:
        return {}
    pairs = (line.strip().split(": ", 1) for line in match[1].splitlines())
    return {name: value for name, value in pairs}


def run_bodies(source: str) -> list[str]:
    bodies: list[str] = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:- )?run: ?(.*)$", line)
        if match is None:
            continue
        indent = len(match[1])
        body = [match[2]]
        for following in lines[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        bodies.append("\n".join(body))
    return bodies


class ReleaseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text()
        cls.jobs = job_blocks(cls.source)

    def test_runs_only_on_a_version_tag_push(self):
        trigger = self.source.split("\non:\n", 1)[1].split("\n\n", 1)[0]

        self.assertEqual(trigger, '  push:\n    tags:\n      - "v*"')

    def test_permissions_are_least_privilege_per_job_under_a_read_default(self):
        self.assertEqual(mapping(self.source, "permissions", 0), {"contents": "read"})
        self.assertEqual(tuple(self.jobs), JOBS)
        expected = {
            "check": {"contents": "read"},
            "images": {
                "contents": "read",
                "packages": "write",
                "id-token": "write",
                "attestations": "write",
            },
            "linux-image": {"contents": "read"},
            "manifest": {"contents": "read", "id-token": "write"},
            "notices": {"contents": "read", "packages": "read"},
            "source-packages": {"contents": "read"},
            "release": {"contents": "write"},
        }
        for job, permissions in expected.items():
            with self.subTest(job=job):
                self.assertEqual(mapping(self.jobs[job], "permissions", 4), permissions)

    def test_every_action_is_pinned_by_full_commit_sha(self):
        uses = re.findall(r"(?m)^\s+(?:- )?uses: (\S+)(.*)$", self.source)

        self.assertTrue(uses)
        for action, comment in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"^[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}$")
                self.assertRegex(comment, r"^ # v\d+\.\d+\.\d+$")

    def test_every_action_is_allowed_by_the_repository_policy(self):
        # Repository Actions policy (gh api repos/<repo>/actions/permissions/selected-actions,
        # 2026-11-16): GitHub-owned actions and three patterns; a run that uses another
        # action ends in startup_failure (run 43884616032).
        allowed = ("astral-sh/setup-uv", "docker/setup-buildx-action", "docker/build-push-action")
        for action in re.findall(r"(?m)^\s+(?:- )?uses: (\S+)", self.source):
            name, _, revision = action.partition("@")
            with self.subTest(action=action):
                self.assertTrue(name.startswith("actions/") or name in allowed)
                self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_registry_login_and_cosign_install_are_checked_run_steps(self):
        login = (
            'printf \'%s\' "$GHCR_TOKEN" | docker login ghcr.io --username "$GITHUB_ACTOR" '
            "--password-stdin"
        )
        for job in ("images", "notices"):
            with self.subTest(job=job):
                block = self.jobs[job]
                self.assertIn("GHCR_TOKEN: ${{ github.token }}", block)
                self.assertIn(login, block)
                self.assertRegex(block, r"if: always\(\)\n\s+run: docker logout ghcr.io\n")
        for job in ("images", "manifest"):
            with self.subTest(job=job):
                block = self.jobs[job]
                self.assertIn(
                    "https://github.com/sigstore/cosign/releases/download/v3.1.4/"
                    "cosign-linux-amd64",
                    block,
                )
                self.assertIn(
                    'echo "424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa  '
                    '$bin/cosign"',
                    block,
                )
                check = block.index("sha256sum --check --strict --status -")
                self.assertLess(check, block.index('chmod +x "$bin/cosign"'))
                signing = re.search(r"(?m)^\s+(?:run: )?cosign sign", block)
                self.assertIsNotNone(signing)
                self.assertLess(block.index('chmod +x "$bin/cosign"'), signing.start())

    def test_no_secret_beyond_the_workflow_token_and_no_expression_in_shell(self):
        self.assertNotIn("secrets.", self.source)
        for body in run_bodies(self.source):
            with self.subTest(body=body.splitlines()[0]):
                self.assertNotIn("${{", body)
        checkouts = self.source.count("uses: actions/checkout@")
        self.assertEqual(checkouts, self.source.count("persist-credentials: false"))

    def test_the_tag_guard_runs_first_and_every_other_job_waits_for_it(self):
        check = self.jobs["check"]
        # D3: the license-work guard is a tracked constant, not a repository setting.
        self.assertNotIn("vars.", self.source)
        self.assertNotIn("--license-work-merged", self.source)
        # N-5: one step checks the tag and gives the one validated version.
        self.assertIn("TAG: ${{ github.ref_name }}", check)
        self.assertIn("python3 scripts/release_artifacts.py tag", check)
        for body in run_bodies(self.source):
            self.assertNotIn("check_release_version.py", body)
        # D4 and plan 5.1: full history brings origin/main and the pushed branches.
        self.assertIn("fetch-depth: 0\n", check)
        self.assertIn('--commit "$GITHUB_SHA" --main-ref origin/main', check)
        self.assertNotIn("needs:", check)
        for job in JOBS[1:]:
            with self.subTest(job=job):
                self.assertRegex(self.jobs[job], r"(?m)^    needs: (check|\[check, .*\])$")

    def test_one_digest_is_archived_signed_attested_and_listed(self):
        # N-3: every consumer reads the digest of the same build step, through one output.
        images = self.jobs["images"]
        for role in ("server", "caddy"):
            with self.subTest(role=role):
                self.assertEqual(images.count(f"${{{{ steps.{role}.outputs.digest }}}}"), 2)
                self.assertIn(
                    f"{role.upper()}_DIGEST: ${{{{ steps.{role}.outputs.digest }}}}", images
                )
                self.assertIn(f"subject-digest: ${{{{ steps.{role}.outputs.digest }}}}", images)
                self.assertIn(f"{role}: ${{{{ steps.refs.outputs.{role} }}}}", images)
                self.assertEqual(
                    images.count(f"{role.upper()}: ${{{{ steps.refs.outputs.{role} }}}}"), 2
                )
                for job in ("manifest", "notices"):
                    self.assertIn(
                        f"{role.upper()}_IMAGE: ${{{{ needs.images.outputs.{role} }}}}",
                        self.jobs[job],
                    )
        self.assertIn("--server-info image-info/server.json", self.jobs["manifest"])
        self.assertIn("--caddy-info image-info/caddy.json", self.jobs["manifest"])

    def test_archives_are_copied_from_the_pushed_digest_and_checked_before_signing(self):
        # D1 and W3-2: the archive holds the pushed digest; a bad archive signs nothing.
        images = self.jobs["images"]
        self.assertEqual(images.count("outputs: type=image,oci-mediatypes=true\n"), 2)
        self.assertIn(
            'skopeo copy --preserve-digests --src-authfile "$HOME/.docker/config.json"', images
        )
        self.assertIn('"docker://$source" "oci-archive:$archive:$tagged"', images)
        self.assertIn("python3 scripts/release_artifacts.py image-info", images)
        self.assertIn('--summary "$GITHUB_STEP_SUMMARY"', images)
        self.assertLess(images.index("image-info --reference"), images.index("cosign sign --yes"))
        self.assertLess(images.index("image-info --reference"), images.index("attest-build"))
        self.assertIn("name: asset-images\n          path: archives/", images)

    def test_archive_step_gives_skopeo_a_digest_only_source_and_keeps_the_tagged_name(self):
        # Run 43885232153: skopeo 1.13 refuses "docker://name:tag@digest" ("Docker
        # references with both a tag and digest are currently not supported").
        images = self.jobs["images"]
        step = images.split("      - name: Write and check the image archives", 1)[1]
        body = textwrap.dedent(step.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        server = f"ghcr.io/jayeuse/slateops-server:0.1.0-rc.2@sha256:{'a' * 64}"
        caddy = f"ghcr.io/jayeuse/slateops-caddy:0.1.0-rc.2@sha256:{'b' * 64}"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stubs = root / "stubs"
            stubs.mkdir()
            calls = root / "calls"
            (stubs / "skopeo").write_text(
                "#!/bin/bash\n"
                'for argument in "$@"; do\n'
                '  if [[ "$argument" =~ ^docker://.*:[^/@]+@sha256: ]]; then\n'
                '    echo "both a tag and digest are currently not supported" >&2; exit 1\n'
                "  fi\n"
                "done\n"
                f'echo "skopeo $*" >> "{calls}"\n'
            )
            (stubs / "python3").write_text(f'#!/bin/bash\necho "python3 $*" >> "{calls}"\n')
            for stub in stubs.iterdir():
                stub.chmod(0o755)
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", body],
                cwd=root,
                env={
                    "PATH": f"{stubs}:{os.environ['PATH']}",
                    "HOME": "/home/runner",
                    "SERVER": server,
                    "CADDY": caddy,
                    "VERSION": "0.1.0-rc.2",
                    "GITHUB_STEP_SUMMARY": str(root / "summary"),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            authfile = "--src-authfile /home/runner/.docker/config.json"
            self.assertEqual(
                calls.read_text().splitlines(),
                [
                    f"skopeo copy --preserve-digests {authfile} "
                    f"docker://ghcr.io/jayeuse/slateops-server@sha256:{'a' * 64} "
                    "oci-archive:archives/slateops-server-0.1.0-rc.2-amd64.oci.tar:"
                    "ghcr.io/jayeuse/slateops-server:0.1.0-rc.2",
                    f"python3 scripts/release_artifacts.py image-info --reference {server} "
                    "--archive archives/slateops-server-0.1.0-rc.2-amd64.oci.tar "
                    f"--output image-info/server.json --summary {root / 'summary'}",
                    f"skopeo copy --preserve-digests {authfile} "
                    f"docker://ghcr.io/jayeuse/slateops-caddy@sha256:{'b' * 64} "
                    "oci-archive:archives/slateops-caddy-0.1.0-rc.2-amd64.oci.tar:"
                    "ghcr.io/jayeuse/slateops-caddy:0.1.0-rc.2",
                    f"python3 scripts/release_artifacts.py image-info --reference {caddy} "
                    "--archive archives/slateops-caddy-0.1.0-rc.2-amd64.oci.tar "
                    f"--output image-info/caddy.json --summary {root / 'summary'}",
                ],
            )

    def test_a_failed_run_is_never_re_run_and_an_existing_release_stops_the_job(self):
        # D5: the rule heads the file and the release job refuses an existing release.
        header = self.source.split("\non:\n", 1)[0]
        self.assertIn('never use "Re-run all jobs"', header)
        release = self.jobs["release"]
        guard = release.index('gh api "repos/$GITHUB_REPOSITORY/releases" --paginate')
        self.assertLess(guard, release.index("gh release create"))
        self.assertIn('grep -Fxq -- "$TAG"', release)

    def test_notices_install_python_packages_like_the_image(self):
        # N-11: the uv version and the lock flag of infra/docker/backend.Dockerfile.
        dockerfile = (ROOT / "infra/docker/backend.Dockerfile").read_text()
        notices = self.jobs["notices"]
        uv = re.search(r"ghcr\.io/astral-sh/uv:(\d+\.\d+\.\d+)@", dockerfile)
        self.assertIsNotNone(uv)
        self.assertIn(f'version: "{uv[1]}"', notices)
        self.assertIn("uv sync --frozen --no-dev", dockerfile)
        self.assertIn("uv sync --frozen --no-dev --no-install-project", notices)

    def test_both_images_are_amd64_pushed_with_only_the_tag_version_and_signed(self):
        images = self.jobs["images"]
        for name, dockerfile in (
            ("slateops-server", "infra/docker/backend.Dockerfile"),
            ("slateops-caddy", "infra/docker/caddy.Dockerfile"),
        ):
            step = next(
                step for step in re.split(r"(?m)^      - ", images) if f"file: {dockerfile}" in step
            )
            with self.subTest(image=name):
                self.assertIn("context: .\n", step)
                self.assertIn("platforms: linux/amd64\n", step)
                self.assertIn("push: true\n", step)
                self.assertIn("provenance: false\n", step)
                self.assertIn("sbom: false\n", step)
                self.assertIn("no-cache: true\n", step)
                tags = re.findall(r"(?m)^          tags: (.+)$", step)
                self.assertEqual(
                    tags,
                    [
                        "${{ needs.check.outputs.image_prefix }}/"
                        f"{name}:${{{{ needs.check.outputs.version }}}}"
                    ],
                )
                self.assertIn(
                    f"subject-name: ${{{{ needs.check.outputs.image_prefix }}}}/{name}\n", images
                )
        self.assertIn("SLATEOPS_VERSION=${{ needs.check.outputs.version }}", images)
        self.assertEqual(images.count('cosign sign --yes "'), 2)
        self.assertEqual(images.count("push-to-registry: true"), 2)
        self.assertEqual(images.count("create-storage-record: false"), 2)

    def test_image_packages_are_read_from_the_pushed_digests_without_running_the_images(self):
        notices = self.jobs["notices"]
        self.assertRegex(notices, r"(?m)^    needs: \[check, images, linux-image\]$")
        self.assertIn("SERVER_IMAGE: ${{ needs.images.outputs.server }}", notices)
        self.assertIn("CADDY_IMAGE: ${{ needs.images.outputs.caddy }}", notices)
        self.assertIn('docker create "$image"', notices)
        self.assertIn("docker cp", notices)
        self.assertIn('extract server "$SERVER_IMAGE" /var/lib/dpkg/status /usr/share/doc', notices)
        self.assertIn('extract caddy "$CADDY_IMAGE" /lib/apk/db/installed', notices)
        self.assertIn("--source-offer dist/SOURCE-OFFER.txt", notices)
        self.assertNotIn("docker run", self.source)

    def test_backend_ci_type_checks_the_release_scripts(self):
        backend = (ROOT / ".github/workflows/backend.yml").read_text()
        mypy = backend.split("      - name: Run mypy\n", 1)[1].split("\n      - ", 1)[0]

        for script in ("../scripts/release_artifacts.py", "../scripts/check_release_version.py"):
            with self.subTest(script=script):
                self.assertIn(script, mypy)

    def test_linux_image_is_hashed_then_checked_then_booted_and_attached(self):
        # W4: the build needs only the tag check; the tarball's entry is written before
        # any check, the static check runs before the boot, and only a copy boots.
        job = self.jobs["linux-image"]
        tarball = '"dist/slateops-linux-$VERSION-amd64.tar.gz"'
        self.assertRegex(job, r"(?m)^    needs: \[check, engine-bundle\]$")
        steps = [
            'packaging/linux-image/build.sh --arch amd64 --version "$VERSION" --output dist',
            "python3 scripts/release_linux_image.py outputs",
            "python3 scripts/release_linux_image.py check",
            f"packaging/linux-image/boot-check.sh --arch amd64 --tarball {tarball}",
            "name: asset-linux\n          path: dist/",
        ]
        positions = [job.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(job.count(f"--tarball {tarball} --arch amd64"), 2)
        self.assertIn("--pins packaging/linux-image/pins.env", job)
        self.assertIn("--entry linux-info/linux-image.json --files linux-files", job)
        self.assertIn("name: linux-info\n          path: linux-info/", job)
        self.assertIn("name: linux-files\n          path: linux-files/", job)
        self.assertIn("### Linux image size (10.2)", job)

    def test_manifest_lists_the_linux_image_and_notices_read_its_package_files(self):
        manifest = self.jobs["manifest"]
        self.assertRegex(
            manifest, r"(?m)^    needs: \[check, images, linux-image, engine-bundle\]$"
        )
        self.assertIn("name: linux-info\n          path: linux-info", manifest)
        self.assertIn("--linux-info linux-info/linux-image.json", manifest)
        notices = self.jobs["notices"]
        self.assertIn("name: linux-files\n          path: image-files/linux", notices)
        for argument in (
            "--linux-files image-files/linux",
            '--python-version "$PYTHON_VERSION"',
            '--python-license "image-files/server/usr/local/lib/'
            'python${PYTHON_VERSION%.*}/LICENSE.txt"',
            '--caddy-version "$CADDY_VERSION" --caddy-binary image-files/caddy/usr/bin/caddy',
            "--caddy-license image-files/caddy-LICENSE",
        ):
            with self.subTest(argument=argument):
                self.assertIn(argument, notices)
        self.assertIn("/lib/apk/db/installed /etc/alpine-release /usr/bin/caddy", notices)

    def test_image_versions_are_checked_before_they_become_a_path_or_url(self):
        # W4-7: PYTHON_VERSION and CADDY_VERSION come from the pushed images' settings.
        notices = self.jobs["notices"]
        step = notices.split(
            "      - name: Copy the package databases out of the pushed images", 1
        )[1]
        body = textwrap.dedent(step.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        guard = body.split('echo "python_version=', 1)[0]
        for python, caddy, expected in (
            ("3.14.10", "v2.10.2", 0),
            ("3.14.10/../../x", "v2.10.2", 1),
            ("3.14.10", "v2.10.2; rm -rf /", 1),
            ("", "v2.10.2", 1),
        ):
            with self.subTest(python=python, caddy=caddy), tempfile.TemporaryDirectory() as root:
                stubs = Path(root)
                (stubs / "docker").write_text(
                    "#!/bin/bash\n"
                    'if [ "$1" = image ]; then\n'
                    f'  case "$5" in server) echo "PYTHON_VERSION={python}";; '
                    f'*) echo "CADDY_VERSION={caddy}";; esac\n'
                    "fi\n"
                )
                (stubs / "docker").chmod(0o755)
                result = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", guard],
                    env={
                        "PATH": f"{stubs}:{os.environ['PATH']}",
                        "SERVER_IMAGE": "server",
                        "CADDY_IMAGE": "caddy",
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_caddy_license_is_pinned_next_to_the_caddy_image_and_checked(self):
        # S83-2: the license comes from GitHub, so its SHA-256 is pinned beside the image.
        dockerfile = (ROOT / "infra/docker/caddy.Dockerfile").read_text().splitlines()
        pin = next(line for line in dockerfile if line.startswith("# caddy-license: "))
        self.assertTrue(dockerfile[dockerfile.index(pin) + 1].startswith("FROM caddy@sha256:"))
        _, version, digest = pin.removeprefix("# ").split()
        notices = self.jobs["notices"]
        step = notices.split(
            "      - name: Download the Caddy license of the image's release tag", 1
        )[1]
        body = textwrap.dedent(step.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        license_text = b"Apache License\n"
        for case, image_version, served, expected in (
            ("pinned", version, None, 0),
            ("changed license", version, b"other text\n", 1),
            ("other Caddy version", "v9.9.9", None, 1),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "infra/docker").mkdir(parents=True)
                (root / "image-files").mkdir()
                lines = [f"# caddy-license: {version} {hashlib.sha256(license_text).hexdigest()}"]
                (root / "infra/docker/caddy.Dockerfile").write_text("\n".join(lines) + "\n")
                stubs = root / "stubs"
                stubs.mkdir()
                (root / "license").write_bytes(served or license_text)
                (stubs / "curl").write_text(
                    "#!/bin/bash\n"
                    'while [ "$1" != --output ]; do shift; done\n'
                    f'cp "{root / "license"}" "$2"\n'
                )
                (stubs / "curl").chmod(0o755)
                result = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", body],
                    cwd=root,
                    env={"PATH": f"{stubs}:{os.environ['PATH']}", "CADDY_VERSION": image_version},
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertEqual((root / "image-files/caddy-LICENSE").exists(), expected == 0)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_source_packages_are_fetched_from_the_three_package_databases(self):
        # H4 and W4-7: Debian sources of the Linux and server images, Alpine of Caddy.
        notices = self.jobs["notices"]
        for path in (
            "image-files/linux/var/lib/dpkg/status",
            "image-files/server/var/lib/dpkg/status",
            "image-files/caddy/lib/apk/db/installed",
            "image-files/caddy/etc/alpine-release",
        ):
            with self.subTest(path=path):
                self.assertIn(f"            {path}\n", notices)
        job = self.jobs["source-packages"]
        self.assertRegex(job, r"(?m)^    needs: \[check, notices\]$")
        self.assertIn("name: package-databases\n          path: databases", job)
        for argument in (
            "python3 scripts/release_sources.py fetch",
            "--debian-status databases/linux/var/lib/dpkg/status",
            "--debian-status databases/server/var/lib/dpkg/status",
            "--apk-installed databases/caddy/lib/apk/db/installed",
            "--alpine-release databases/caddy/etc/alpine-release",
            "--output dist",
        ):
            with self.subTest(argument=argument):
                self.assertIn(argument, job)
        self.assertIn("name: asset-sources\n          path: dist/", job)

    def test_the_engine_bundle_is_built_first_then_the_image_then_the_manifest(self):
        # TASK-0085 AC-B2 (W4 carry): bundle, then linux-image, then manifest; no manifest
        # in the bundle; the image records the bundle's SHA-256 and the check compares it.
        bundle = self.jobs["engine-bundle"]
        self.assertRegex(bundle, r"(?m)^    needs: check$")
        self.assertEqual(mapping(bundle, "permissions", 4), {"contents": "read"})
        self.assertIn("REPOSITORY: ${{ github.repository }}", bundle)
        self.assertIn(
            'python3 scripts/release_engine_bundle.py build --version "$VERSION"\n'
            '          --repository "$REPOSITORY" --output dist'
            " --entry engine-info/engine-bundle.json",
            bundle,
        )
        self.assertIn("name: asset-engine\n          path: dist/", bundle)
        self.assertIn("name: engine-info\n          path: engine-info/", bundle)
        image = self.jobs["linux-image"]
        self.assertIn("name: asset-engine\n          path: engine-dist", image)
        self.assertIn(
            '--output dist --engine-bundle "engine-dist/slateops-engine-$VERSION.tar.gz"', image
        )
        self.assertIn("--engine-info engine-info/engine-bundle.json", image)
        manifest = self.jobs["manifest"]
        self.assertIn("name: engine-info\n          path: engine-info", manifest)
        self.assertIn("--engine-info engine-info/engine-bundle.json", manifest)
        jobs = ("engine-bundle", "linux-image", "manifest")
        order = [self.source.index(f"\n  {job}:\n") for job in jobs]
        self.assertEqual(order, sorted(order))

    def test_backend_ci_type_checks_the_engine_bundle_script(self):
        backend = (ROOT / ".github/workflows/backend.yml").read_text()
        mypy = backend.split("      - name: Run mypy\n", 1)[1].split("\n      - ", 1)[0]

        self.assertIn("../scripts/release_engine_bundle.py", mypy)

    def test_release_waits_for_every_asset_and_refuses_one_of_2_gib_or_more(self):
        release = self.jobs["release"]
        self.assertRegex(
            release,
            r"(?m)^    needs: \[check, images, linux-image, manifest, notices, source-packages,"
            r" install-proof\]$",
        )
        step = release.split("      - name: Refuse an asset of 2 GiB or more", 1)[1]
        body = textwrap.dedent(step.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        self.assertLess(
            release.index("Refuse an asset of 2 GiB"), release.index("gh release create")
        )
        for size, expected in ((2 * 1024**3 - 1, 0), (2 * 1024**3, 1)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                with open(Path(directory) / "asset.tar", "wb") as asset:
                    asset.truncate(size)  # A sparse file: no disk space used.
                result = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", body],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(result.returncode, expected, result.stdout)

    def test_backend_ci_type_checks_the_w4_scripts(self):
        backend = (ROOT / ".github/workflows/backend.yml").read_text()
        mypy = backend.split("      - name: Run mypy\n", 1)[1].split("\n      - ", 1)[0]

        for script in ("../scripts/release_linux_image.py", "../scripts/release_sources.py"):
            with self.subTest(script=script):
                self.assertIn(script, mypy)

    def test_manifest_is_signed_and_the_release_is_a_draft_with_checksums(self):
        manifest = self.jobs["manifest"]
        self.assertIn("python3 scripts/release_artifacts.py manifest", manifest)
        self.assertIn(
            "cosign sign-blob --yes --bundle dist/release-manifest.json.sigstore.json "
            "dist/release-manifest.json",
            manifest,
        )
        release = self.jobs["release"]
        self.assertIn("sha256sum --", release)
        self.assertIn('gh release create "$TAG"', release)
        for flag in ("--draft", "--verify-tag", '--title "$TITLE"'):
            with self.subTest(flag=flag):
                self.assertIn(flag, release)
        self.assertRegex(
            release,
            r'if \[ "\$PRERELEASE" = "true" \]; then\n\s+flags\+=\(--prerelease --latest=false\)',
        )
        self.assertNotIn("actions/checkout@", release)


if __name__ == "__main__":
    unittest.main()


class InstallProofTests(unittest.TestCase):
    """TASK-0086 AC-P1, AC-P2: every test build installs itself on a Linux host (W5b-1)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text()
        cls.job = job_blocks(cls.source)["install-proof"]

    def test_ac_p1_the_proof_installs_from_this_builds_own_artifacts(self) -> None:
        self.assertRegex(
            self.job, r"(?m)^    needs: \[check, images, linux-image, engine-bundle, manifest\]$"
        )
        self.assertEqual(mapping(self.job, "permissions", 4), {"contents": "read"})
        for name in ("asset-images", "asset-engine", "asset-manifest"):
            self.assertIn(f"name: {name}\n          path: payload", self.job)
        self.assertIn("name: asset-linux\n          path: linux", self.job)
        self.assertIn(
            'packaging/linux-image/install-proof.sh --version "$VERSION"\n'
            '          --tarball "linux/slateops-linux-$VERSION-amd64.tar.gz" --payload payload'
            " --output proof",
            self.job,
        )
        self.assertIn("runs-on: ubuntu-latest", self.job)

    def test_ac_p1_a_failed_proof_keeps_its_redacted_diagnostics(self) -> None:
        name = "      - name: Keep the redacted diagnostics of a failed proof\n"
        upload = self.job.split(name, 1)[1]
        self.assertTrue(upload.startswith("        if: failure()\n"))
        self.assertIn("name: install-proof-diagnostics", upload)
        for name in ("proof/log-bundle.tar.gz", "proof/console.log", "proof/journal.txt"):
            self.assertIn(name, upload)
        self.assertNotIn("proof/payload", upload)

    def test_ac_p2_the_reader_test_runs_with_the_images_docker_cli_and_compose(self) -> None:
        step = self.job.split("      - name: Read the env files with the image's Docker CLI", 1)[1]
        body = step.split("\n      - ", 1)[0]
        self.assertIn("*usr/bin/docker", body)
        self.assertIn("*usr/libexec/docker/cli-plugins/docker-compose", body)
        self.assertIn('DOCKER_CONFIG="$config"', body)
        self.assertIn("tests/operations/test_installer_env_docker_readers.py", body)
        self.assertIn("-m integration --no-cov", body)
        self.assertIn("docker compose version", body)

    def test_ac_p1_the_harness_boots_the_image_and_checks_each_promise(self) -> None:
        script = (ROOT / "packaging/linux-image/install-proof.sh").read_text()
        for promise in (
            "docker import",
            "systemctl is-system-running --wait",
            "io.containerd.snapshotter.v1",
            "slateops-engine receive",
            "prefetch_done",
            '"${engine[@]}" install)',
            "--cacert /etc/slateops/ca/current/root.crt",
            'fail "expected one invitation in Mailpit',
            "the second install changed a file",
            "the second install sent mail",
            "resend-invitation",
            "chronyd -x",
            "owners and modes differ from the installation rules",
            "/etc/slateops/Caddyfile 1000:1000 600",
            "/var/log/slateops/app 10001:10001 700",
            # TASK-0089 (W6a): the trust routes, the security code, Realtime, the renewal.
            "port 80 serves exactly three trust paths",
            "the trust page does not show the engine's security code",
            "every other :80 path and name redirects to HTTPS",
            "/trust/ok sets a cookie or CORS header",
            '-H "Origin: https://$host"',
            '[ "$upgrade" = 101 ]',
            "Caddy still serves the old certificate",
            "the renewal outage was longer than a reload",
        ):
            with self.subTest(promise=promise):
                self.assertIn(promise.replace("slateops-engine receive", "receive"), script)


class ScriptModeTests(unittest.TestCase):
    def test_every_script_the_release_runs_by_path_is_executable_in_git(self) -> None:
        # A script committed without its executable bit fails the job with exit 126
        # (test build v0.1.0-rc.10, install-proof.sh).
        pattern = r"(?<![\w./-])(packaging/[\w./-]+\.sh)\b"
        paths = sorted(set(re.findall(pattern, WORKFLOW.read_text())))
        self.assertTrue(paths)
        listing = subprocess.run(
            ["git", "ls-files", "-s", "--", *paths],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        modes = {line.split("\t", 1)[1]: line.split()[0] for line in listing}
        self.assertEqual({path: modes.get(path) for path in paths}, dict.fromkeys(paths, "100755"))
