"""Contracts for the release workflow (docs/plans/windows-installer.md 5.2, 5.3; W3-1 to W3-4).

The workflow runs only on a release tag, so these checks read its text. The first rc tag
run proves the runtime parts (push, signatures, attestations, the draft release).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"
JOBS = ("check", "images", "manifest", "notices", "release")


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
            "manifest": {"contents": "read", "id-token": "write"},
            "notices": {"contents": "read", "packages": "read"},
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
        self.assertIn('"docker://$reference" "oci-archive:$archive:${reference%@*}"', images)
        self.assertIn("python3 scripts/release_artifacts.py image-info", images)
        self.assertIn('--summary "$GITHUB_STEP_SUMMARY"', images)
        self.assertLess(images.index("image-info --reference"), images.index("cosign sign --yes"))
        self.assertLess(images.index("image-info --reference"), images.index("attest-build"))
        self.assertIn("name: asset-images\n          path: archives/", images)

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
        self.assertRegex(notices, r"(?m)^    needs: \[check, images\]$")
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
