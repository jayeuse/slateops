"""The engine bundle (TASK-0085 AC-B1; plan 3.1, 5.2; W4 carries: no manifest inside)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts import release_engine_bundle as bundle

VERSION = "0.2.0-rc.1"


def build(output: Path, repository: str = "jayeuse/slateops", version: str = VERSION) -> int:
    return bundle.main(
        [
            "build",
            "--version",
            version,
            "--repository",
            repository,
            "--output",
            str(output / "dist"),
            "--entry",
            str(output / "info/engine-bundle.json"),
        ]
    )


class EngineBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def archive(self) -> Path:
        return self.root / "dist" / f"slateops-engine-{VERSION}.tar.gz"

    def test_the_bundle_holds_the_engine_compose_files_and_no_manifest(self):
        self.assertEqual(build(self.root), 0)

        with tarfile.open(self.archive()) as tar:
            members = {member.name: member for member in tar.getmembers()}
            version = tar.extractfile(members["engine/VERSION"])
            assert version is not None
            self.assertEqual(version.read().decode(), f"{VERSION}\n")
        names = set(members)
        self.assertIn("slateops-engine", names)
        self.assertIn("engine/cli.py", names)
        self.assertIn("engine/templates/provider.env", names)
        self.assertIn("infra/supabase/compose.yaml", names)
        self.assertIn("infra/supabase/compose.production.yaml", names)
        self.assertIn("infra/supabase/upstream/envoy/envoy.yaml", names)
        self.assertNotIn("infra/supabase/compose.dev.yaml", names)
        self.assertFalse([name for name in names if "release-manifest" in name])
        self.assertFalse([name for name in names if "/tests" in name or "__pycache__" in name])
        self.assertEqual(members["slateops-engine"].mode, 0o755)
        self.assertEqual(members["engine/cli.py"].mode, 0o644)
        for member in members.values():
            self.assertEqual(
                (member.uid, member.gid, member.uname, member.gname), (0, 0, "root", "root")
            )
            self.assertEqual(member.mtime, 0)

    def test_two_builds_are_identical_and_the_entry_names_the_hash(self):
        build(self.root)
        first = self.archive().read_bytes()
        build(self.root)
        second = self.archive().read_bytes()

        entry = json.loads((self.root / "info/engine-bundle.json").read_text())
        self.assertEqual(first, second)
        self.assertEqual(
            entry,
            {
                "archive": f"slateops-engine-{VERSION}.tar.gz",
                "sha256": hashlib.sha256(first).hexdigest(),
                "size": len(first),
            },
        )

    def test_the_bundled_launcher_runs_with_the_standard_library_only(self):
        build(self.root)
        target = self.root / "bundle"
        with tarfile.open(self.archive()) as tar:
            tar.extractall(target, filter="data")

        # -S: no site-packages, so only the standard library can be imported (W5b-5).
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(target / "slateops-engine"), "unknown-job"],
            input=b"{}",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"code": "job_unknown", "message_key": "engine.job_unknown"},
        )

    def test_a_build_for_another_repository_or_a_bad_version_is_refused(self):
        self.assertEqual(build(self.root, repository="someone/fork"), 1)
        self.assertEqual(build(self.root, version="0.2.0-dev"), 1)
        self.assertFalse((self.root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
