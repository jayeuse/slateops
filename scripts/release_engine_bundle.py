"""Build the engine bundle ``slateops-engine-<version>.tar.gz`` (plan 3.1, 5.2; slice W5b).

The bundle holds the launcher ``slateops-engine``, the ``engine`` package of
``packaging/engine/`` without its tests, its env templates and ``engine/VERSION``, and the
Compose files the engine starts (``infra/supabase/compose.yaml``,
``compose.production.yaml`` and ``upstream/``), at the same relative paths as in the
repository. It holds no ``release-manifest.json``: the manifest names the bundle's SHA-256,
the Linux image records it, and the engine reads the signed manifest only from the setup
payload (TASK-0083 W4 code review).

The archive is deterministic: sorted entries, owner root (0), time 0, fixed modes, and
``gzip`` with no name and no time. It refuses a repository other than the one whose
release identity the engine checks (``engine.release.REPOSITORY``).

Standard library only: the release workflow runs it with a plain Python.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "packaging" / "engine"
SUPABASE = ROOT / "infra" / "supabase"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-rc\.[1-9][0-9]*)?\Z")


class BundleError(Exception):
    pass


def repository() -> str:
    """``engine.release.REPOSITORY``, read without importing the engine."""
    text = (ENGINE / "release.py").read_text()
    found = re.search(r'^REPOSITORY = "([^"]+)"$', text, re.M)
    if found is None:
        raise BundleError("packaging/engine/release.py has no REPOSITORY")
    return found.group(1)


def members(version: str) -> list[tuple[str, bytes, int]]:
    """(name in the bundle, content, mode) for every file, sorted by name."""
    files: list[tuple[str, bytes, int]] = [
        ("slateops-engine", (ENGINE / "slateops-engine").read_bytes(), 0o755),
        ("engine/VERSION", f"{version}\n".encode(), 0o644),
    ]
    for path in sorted(ENGINE.rglob("*")):
        relative = path.relative_to(ENGINE)
        if (
            not path.is_file()
            or relative.parts[0] == "tests"
            or "__pycache__" in relative.parts
            or path.name == "slateops-engine"
            or path.suffix not in (".py", ".env")
        ):
            continue
        files.append((f"engine/{relative.as_posix()}", path.read_bytes(), 0o644))
    sources = [SUPABASE / "compose.yaml", SUPABASE / "compose.production.yaml"]
    sources += [path for path in sorted((SUPABASE / "upstream").rglob("*")) if path.is_file()]
    for path in sources:
        mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
        files.append((path.relative_to(ROOT).as_posix(), path.read_bytes(), mode))
    names = [name for name, _, _ in files]
    if len(set(names)) != len(names) or any("release-manifest" in name for name in names):
        raise BundleError("the bundle file list is not unique or names a manifest")
    return sorted(files)


def _info(name: str, mode: int, size: int = 0, directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode, info.size, info.mtime = mode, size, 0
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    return info


def build(version: str) -> bytes:
    files = members(version)
    folders = sorted({str(Path(name).parent) for name, _, _ in files} - {"."})
    folders = sorted({str(p) for f in folders for p in (Path(f), *Path(f).parents)} - {"."})
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for folder in folders:
            tar.addfile(_info(folder, 0o755, directory=True))
        for name, content, mode in files:
            tar.addfile(_info(name, mode, len(content)), io.BytesIO(content))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as archive:
        archive.write(tar_bytes.getvalue())
    return compressed.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("build", help="write the bundle and its manifest entry")
    command.add_argument("--version", required=True)
    command.add_argument("--repository", required=True, help="the GITHUB_REPOSITORY value")
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--entry", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not VERSION.match(args.version):
            raise BundleError(f"version {args.version!r} is not X.Y.Z or X.Y.Z-rc.N")
        if args.repository != repository():
            raise BundleError(
                f"repository {args.repository!r} is not {repository()!r}, the identity that "
                "the engine checks; change packaging/engine/release.py first"
            )
        data = build(args.version)
    except BundleError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    name = f"slateops-engine-{args.version}.tar.gz"
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / name).write_bytes(data)
    entry = {"archive": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    args.entry.parent.mkdir(parents=True, exist_ok=True)
    args.entry.write_text(json.dumps(entry, indent=2) + "\n")
    print(f"{name}: {len(data)} bytes, sha256 {entry['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
