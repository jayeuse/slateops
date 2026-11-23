"""Contract tests for the release tag check (W1-3): the tag must match both manifests."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts import check_release_version


class CheckReleaseVersionTests(unittest.TestCase):
    def _root(self, backend: str = "1.2.3", frontend: str | None = "1.2.3") -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "backend").mkdir()
        (root / "backend/pyproject.toml").write_text(
            f'[project]\nname = "slateops-backend"\nversion = "{backend}"\n', encoding="utf-8"
        )
        (root / "frontend").mkdir()
        if frontend is not None:
            (root / "frontend/package.json").write_text(
                json.dumps({"name": "slateops-frontend", "version": frontend}), encoding="utf-8"
            )
        return root

    def _run(self, root: Path, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = check_release_version.main(list(arguments), root=root)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_accepts_the_manifest_version_and_its_release_candidates(self):
        root = self._root()
        for tag, printed in (
            ("v1.2.3", "1.2.3\n"),
            ("v1.2.3-rc.1", "1.2.3-rc.1\n"),
            ("v1.2.3-rc.12", "1.2.3-rc.12\n"),
        ):
            with self.subTest(tag=tag):
                self.assertEqual(self._run(root, tag), (0, printed, ""))

    def test_refuses_a_tag_that_differs_from_either_manifest(self):
        for backend, frontend, tag, named in (
            ("1.2.4", "1.2.3", "v1.2.3", "backend/pyproject.toml"),
            ("1.2.3", "1.2.4", "v1.2.3", "frontend/package.json"),
            ("1.2.3", "1.2.4", "v1.2.3-rc.1", "frontend/package.json"),
            ("1.2.3", "1.2.3", "v1.2.4", "backend/pyproject.toml"),
        ):
            with self.subTest(backend=backend, frontend=frontend, tag=tag):
                code, stdout, stderr = self._run(self._root(backend, frontend), tag)

                self.assertEqual((code, stdout), (1, ""))
                self.assertIn(named, stderr)

    def test_refuses_a_tag_that_is_not_a_release_or_release_candidate(self):
        root = self._root()
        for tag in (
            "1.2.3",
            "v1.2",
            "v01.2.3",
            "v1.2.3-rc",
            "v1.2.3-rc.0",
            "v1.2.3-rc.01",
            "v1.2.3-beta.1",
            "v1.2.3+dev",
            "v1.2.3-rc.1-rc.2",
            "v1.2.3\n",
        ):
            with self.subTest(tag=tag):
                code, stdout, stderr = self._run(root, tag)

                self.assertEqual((code, stdout), (1, ""))
                self.assertIn("vX.Y.Z", stderr)

    def test_refuses_when_a_manifest_version_cannot_be_read(self):
        code, stdout, stderr = self._run(self._root(frontend=None), "v1.2.3")

        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("frontend/package.json", stderr)

    def test_a_missing_tag_is_a_usage_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_:
            check_release_version.main([], root=self._root())

        self.assertEqual(exit_.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
