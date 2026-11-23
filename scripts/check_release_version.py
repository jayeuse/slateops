#!/usr/bin/env python3
"""Refuse a release tag whose version differs from the backend and frontend manifests.

Run from the repository root: ``python3 scripts/check_release_version.py <tag>``.

A tag is ``vX.Y.Z`` or ``vX.Y.Z-rc.N``: X, Y and Z are integers with no leading zero, N is a
positive integer with no leading zero. ``X.Y.Z`` must equal ``version`` in
``backend/pyproject.toml`` and in ``frontend/package.json``. On success the tag without the
leading ``v`` is printed; the release workflow passes it to ``infra/docker/backend.Dockerfile``
as the ``SLATEOPS_VERSION`` build argument.

Exit codes: 0 accepted, 1 refused (reason on stderr), 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_NUMBER = r"(?:0|[1-9][0-9]*)"
TAG = re.compile(rf"v(?P<base>{_NUMBER}\.{_NUMBER}\.{_NUMBER})(?:-rc\.[1-9][0-9]*)?")


class ReleaseVersionError(Exception):
    """The tag cannot be released from this checkout."""


def manifest_versions(root: Path) -> dict[str, object]:
    """Return the ``version`` of each manifest, keyed by its repository path."""

    versions: dict[str, object] = {}
    path = "backend/pyproject.toml"
    try:
        versions[path] = tomllib.loads((root / path).read_text(encoding="utf-8"))["project"][
            "version"
        ]
        path = "frontend/package.json"
        versions[path] = json.loads((root / path).read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, TypeError, ValueError):
        raise ReleaseVersionError(f"cannot read the version in {path}") from None
    return versions


def release_version(tag: str, versions: Mapping[str, object]) -> str:
    """Return the release version of ``tag`` when its base matches every manifest."""

    match = TAG.fullmatch(tag)
    if match is None:
        raise ReleaseVersionError(f"tag {tag!r} is not vX.Y.Z or vX.Y.Z-rc.N")
    for path, version in versions.items():
        if version != match["base"]:
            raise ReleaseVersionError(
                f"tag {tag} needs version {match['base']} in {path}, which has {version!r}"
            )
    return tag.removeprefix("v")


def main(argv: Sequence[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        description="Check a release tag against the backend and frontend manifest versions."
    )
    parser.add_argument("tag", help="the pushed tag, for example v0.2.0 or v0.2.0-rc.1")
    arguments = parser.parse_args(argv)
    try:
        version = release_version(arguments.tag, manifest_versions(root))
    except ReleaseVersionError as error:
        print(f"Release version refused: {error}", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
