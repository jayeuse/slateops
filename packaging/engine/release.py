"""The verified release of a version, as ``receive`` keeps it (plan 5.2; W4 carry).

``/var/lib/slateops/release/<version>/`` holds ``release-manifest.json`` (checked with
cosign before it was kept), its signature bundle and the engine bundle. Readers apply the
H11 rules: unknown keys are ignored, a higher ``schema_version`` is refused.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine.core import Paths, refused

# The repository whose release workflow signs the manifest (receive checks this identity;
# scripts/release_engine_bundle.py refuses to build for another repository).
REPOSITORY = "jayeuse/slateops"
MANIFEST = "release-manifest.json"
SIGNATURE = "release-manifest.json.sigstore.json"
SCHEMA_VERSION = 1
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
# One path component per "/" (the separators inside a component are only ".", "_" and
# "-"), so "/" has one meaning and the pattern cannot backtrack exponentially.
REFERENCE = re.compile(
    r"(?P<name>[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]{1,5})?(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*)"
    r"(?::(?P<tag>[A-Za-z0-9_][A-Za-z0-9._-]{0,127}))?@(?P<digest>sha256:[0-9a-f]{64})\Z"
)


def bundle_name(version: str) -> str:
    return f"slateops-engine-{version}.tar.gz"


def archive_name(name: str, version: str) -> str:
    return f"{name}-{version}-amd64.oci.tar"


def release_folder(paths: Paths, version: str) -> Path:
    return paths.releases / version


def load(paths: Paths, version: str) -> dict[str, Any] | None:
    """The kept manifest of ``version``, or None when ``receive`` has not kept one."""
    try:
        data = json.loads((release_folder(paths, version) / MANIFEST).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def require(paths: Paths, version: str) -> dict[str, Any]:
    manifest = load(paths, version)
    if manifest is None:
        raise refused("manifest_missing")
    return manifest


def providers(manifest: dict[str, Any]) -> list[str]:
    images = manifest.get("images")
    found = images.get("providers") if isinstance(images, dict) else None
    if not isinstance(found, list) or not all(
        isinstance(item, str) and REFERENCE.match(item) for item in found
    ):
        raise refused("manifest_invalid")
    return found


def known_bad_wsl(manifest: dict[str, Any] | None) -> list[str]:
    found = (manifest or {}).get("known_bad_wsl_versions", [])
    return [item for item in found if isinstance(item, str)] if isinstance(found, list) else []
