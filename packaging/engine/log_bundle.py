"""``log-bundle``: the Linux part of Save report (plan 10.6; W5b-9).

It records the facts (10.4) and a fresh snapshot (10.5) in its own run folder, then packs
``report.json`` and the run logs, newest first, into one ``.tar.gz`` in memory. Each file
is read, redacted again and checked before it goes in: a file that is not UTF-8 text, or
that still holds a held value after redaction, is left out and listed in
``bundle-index.json``. Nothing unredacted is written to disk.

Wire contract (W7): the result JSON carries the bundle as ``bundle_base64`` with
``bundle_sha256`` and ``bundle_size``, so standard output stays one JSON object. The files
total at most 32 MiB before compression; files past that are listed as left out.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any

from engine import facts, report, snapshot
from engine.context import Context
from engine.core import is_run_id
from engine.logs import cap

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
BUNDLE_LIMIT = 32 * 1024 * 1024
FILE_LIMIT = 4 * 1024 * 1024  # the newest 4 MiB of one file (engine.log can grow)
INDEX = "bundle-index.json"


def _candidates(ctx: Context) -> list[tuple[str, Path]]:
    paths = ctx.paths
    found: list[tuple[str, Path]] = []
    if paths.report.is_file():
        found.append(("report.json", paths.report))
    runs: list[Path] = []
    if paths.logs.is_dir():
        for kind in sorted(p for p in paths.logs.iterdir() if p.is_dir() and not p.is_symlink()):
            runs += [p for p in kind.iterdir() if p.is_dir() and not p.is_symlink()]
    current = ctx.log.folder
    runs.sort(key=lambda run: (run != current, -run.stat().st_mtime, run.name))
    for run in runs:
        for file in sorted(run.rglob("*")):
            if file.is_file() and not file.is_symlink():
                found.append((str(file.relative_to(paths.logs.parent)), file))
    return found


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(data), 0o600
    tar.addfile(info, io.BytesIO(data))


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    facts.record(ctx)
    usage = shutil.disk_usage(ctx.paths.state) if ctx.paths.state.is_dir() else None
    if usage is not None:
        report.record(ctx.paths, "disk", {"at": ctx.deps.clock().isoformat(), **usage._asdict()})
    snapshot.take(ctx, since=None, folder="snapshot")
    included: list[str] = []
    left_out: list[dict[str, str]] = []
    used = 0
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, path in _candidates(ctx):
            raw = cap(path.read_bytes(), FILE_LIMIT)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                left_out.append({"file": name, "reason": "not_text"})
                continue
            clean = ctx.redactor(text)
            if ctx.redactor.leaks(clean):
                left_out.append({"file": name, "reason": "held_value"})
                continue
            data = clean.encode()
            if used + len(data) > BUNDLE_LIMIT:
                left_out.append({"file": name, "reason": "size"})
                continue
            used += len(data)
            _add(tar, name, data)
            included.append(name)
        index = {"run_id": ctx.run_id, "included": included, "left_out": left_out}
        _add(tar, INDEX, (json.dumps(index, indent=2) + "\n").encode())
    bundle = buffer.getvalue()
    ctx.log.line(
        ctx.step(2, "bundle"),
        "INFO",
        f"{len(included)} files, {len(left_out)} left out, {len(bundle)} bytes",
    )
    return {
        "code": "bundle_ready",
        "bundle_base64": base64.b64encode(bundle).decode(),
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "bundle_size": len(bundle),
        "files": len(included),
        "left_out": len(left_out),
    }
