"""``prepare``: the page 4a self-check of the Linux part (plan 10.3 W4-5; W4 carries).

It changes nothing. Each check logs PASS or FAIL with what it saw; every check runs, and
the first failure in this order is the result code (all failed codes are in ``failed``).
A value that a check cannot read has its own ``*_unknown`` code and never passes. Each
code has the message key ``prepare.<code>``; the wizard maps it to its copy.

Decisions (TASK-0085 Notes): D-1 accepts systemd ``degraded`` only when containerd, Docker
and chrony are active; D-2 refuses every drvfs mount and every 9p mount of a Windows drive
or under ``/mnt``, and logs each 9p and drvfs mount; S85-7 also refuses any mount on
``/mnt/<letter>`` or with a ``path=<letter>:`` option, whatever its type. The listener check
passes only the WSL DNS tunnel lines (``DNS_LOCAL``) and, with PID 1 in view being systemd, the
two chronyd loopback lines that a process outside this distribution owns (``CHRONY_OUTSIDE``).

TASK-0097 (W14 round 3, the first run on Windows): the interop check first removes every
``WSLInterop*`` binfmt entry as root (``remove_interop``; the image also does this at each
Linux start, ``slateops-interop-off.service``) and still fails closed on an entry that stays
enabled. A refusal carries ``detail``: each failed check with what it saw (the exact listener
lines with their owning process, the enabled entry names), redacted, with control characters
escaped and at most ``DETAIL_LIMIT`` characters, so the Windows side can log it when no report
can be saved. It holds no input value; a listener line can name a LAN address of the PC.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from engine import facts, progress, release, report
from engine.context import Context
from engine.core import failed, is_run_id, is_version

KEYS = {"run_id": is_run_id, "version": is_version}
REQUIRED = frozenset(KEYS)
CORE_UNITS = ("containerd.service", "docker.service", "chrony.service")
SNAPSHOTTER = ["driver-type", "io.containerd.snapshotter.v1"]
DOCKER_TRIES = 30
DOCKER_WAIT_SECONDS = 2.0
LOCAL_REFERENCE_IDS = frozenset({"7F7F0101", "00000000"})
_DRIVE_SOURCE = re.compile(r"[A-Za-z]:(?:\\134|\\|/|\Z)")
_DRIVE_TARGET = re.compile(r"/mnt/[A-Za-z](?:/|\Z)")
_PATH_OPTION = re.compile(r"(?:^|[,;])path=[A-Za-z]:")
_OCTAL = re.compile(r"\\([0-7]{3})")
DETAIL_LIMIT = 1000
_DETAILS = "prepare_detail"  # the failed checks' texts, in ``ctx.outputs`` for this run only

Check = Callable[[Context, str, dict[str, Any], str], str | None]


def _pass(ctx: Context, step: str, text: str) -> None:
    ctx.log.line(step, "INFO", f"PASS {text}")


def _fail(ctx: Context, step: str, code: str, text: str) -> str:
    ctx.log.line(step, "ERROR", f"FAIL {code}: {text}")
    seen = ctx.outputs.get(_DETAILS)
    ctx.outputs[_DETAILS] = f"{seen}; {code}: {text}" if seen else f"{code}: {text}"
    return code


def _escaped(text: str) -> str:
    return "".join(
        character if character.isprintable() else f"\\x{ord(character):02x}"
        for character in text
    )


def detail(ctx: Context) -> str:
    """The failed checks and what each saw, safe for standard output (AC-E3)."""
    text = ctx.redactor(_escaped(" ".join(ctx.outputs.get(_DETAILS, "").split())))
    return text if len(text) <= DETAIL_LIMIT else text[: DETAIL_LIMIT - 3] + "..."


def check_systemd(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    result = ctx.runner.run(step, ["systemctl", "is-system-running", "--wait"], timeout=240)
    state = result.text().strip()
    if result.returncode in (None, 127) or not state:
        return _fail(ctx, step, "systemd_unknown", "no system state")
    if state == "running":
        _pass(ctx, step, "systemd running")
        return None
    if state == "degraded":
        units = ctx.runner.run(step, ["systemctl", "is-active", *CORE_UNITS], timeout=30)
        failed_units = ctx.runner.run(
            step, ["systemctl", "--failed", "--plain", "--no-legend", "--no-pager"], timeout=30
        )
        names = [line.split()[0] for line in failed_units.text().splitlines() if line.split()]
        if units.text().split() == ["active"] * len(CORE_UNITS):
            ctx.log.line(step, "WARN", f"systemd degraded; failed units: {', '.join(names)}")
            _pass(ctx, step, "containerd, docker and chrony are active")
            return None
        return _fail(ctx, step, "systemd_not_running", f"degraded; failed: {', '.join(names)}")
    return _fail(ctx, step, "systemd_not_running", f"state {state}")


def check_docker(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    for attempt in range(1, DOCKER_TRIES + 1):
        result = ctx.runner.run(
            step, ["docker", "info", "--format", "{{json .DriverStatus}}"], timeout=30
        )
        if result.ok:
            try:
                status = json.loads(result.text())
            except ValueError:
                return _fail(ctx, step, "docker_store_unknown", "unreadable driver status")
            if isinstance(status, list) and SNAPSHOTTER in status:
                _pass(ctx, step, "Docker answers; containerd snapshotter active")
                return None
            return _fail(ctx, step, "docker_store_not_containerd", f"driver status {status}")
        if attempt < DOCKER_TRIES:
            ctx.deps.sleep(DOCKER_WAIT_SECONDS)
    return _fail(ctx, step, "docker_not_ready", f"no answer after {DOCKER_TRIES} tries")


def check_container(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    match = release.REFERENCE.match(str(manifest.get("images", {}).get("server", {}).get("ref")))
    if match is None:
        return _fail(ctx, step, "docker_run_failed", "the manifest names no server image")
    image = f"{match.group('name')}:{match.group('tag')}"
    argv = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--pull",
        "never",
        "--platform",
        "linux/amd64",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        "--entrypoint",
        "true",
        image,
    ]
    if ctx.runner.run(step, argv, timeout=120).ok:
        _pass(ctx, step, f"{image} ran with --network none")
        return None
    return _fail(ctx, step, "docker_run_failed", image)


def check_networking(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    result = ctx.runner.run(step, ["wslinfo", "--networking-mode"], timeout=10)
    mode = result.text().strip()
    if not result.ok or not mode:
        return _fail(ctx, step, "networking_unknown", f"exit {result.returncode}")
    if mode != "mirrored":
        return _fail(ctx, step, "networking_not_mirrored", f"mode {mode}")
    _pass(ctx, step, "networking mirrored")
    return None


def _csv(text: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text)) if row]


def check_time(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    active = ctx.runner.run(step, ["systemctl", "is-active", "chrony.service"], timeout=30)
    if active.text().strip() != "active":
        return _fail(ctx, step, "time_service_inactive", active.text().strip() or "no answer")
    sources = ctx.runner.run(step, ["chronyc", "-c", "-N", "authdata"], timeout=30)
    nts = _csv(sources.text())
    if not sources.ok:
        return _fail(ctx, step, "time_unknown", "chronyc authdata failed")
    if not nts or any(len(row) < 2 or row[1] != "NTS" for row in nts):
        modes = ", ".join(f"{row[0]}={row[1] if len(row) > 1 else '?'}" for row in nts)
        return _fail(ctx, step, "time_not_nts", modes or "no source")
    if not ctx.runner.run(step, ["chronyc", "waitsync", "60", "0.5", "0", "2"], timeout=150).ok:
        return _fail(ctx, step, "time_not_synced", "no sync within 120 s")
    tracking = ctx.runner.run(step, ["chronyc", "-c", "tracking"], timeout=30)
    rows = _csv(tracking.text())
    if not tracking.ok or not rows or len(rows[0]) < 14:
        return _fail(ctx, step, "time_unknown", "chronyc tracking failed")
    row = rows[0]
    reference, source, stratum, offset, leap = row[0], row[1], row[2], row[4], row[13]
    if reference.upper() in LOCAL_REFERENCE_IDS or leap != "Normal":
        return _fail(ctx, step, "time_not_synced", f"reference {source}, leap {leap}")
    try:
        offset_seconds = float(offset)
        stratum_number = int(stratum)
    except ValueError:
        return _fail(ctx, step, "time_unknown", "unreadable tracking values")
    report.record(
        ctx.paths,
        "time_sync",
        {
            "at": ctx.deps.clock().isoformat(),
            "offset_seconds": offset_seconds,
            "stratum": stratum_number,
            "nts_sources": len(nts),
        },
    )
    _pass(ctx, step, f"NTS sync with {source}, stratum {stratum}, offset {offset_seconds:+.6f} s")
    return None


# WSL DNS tunneling (on by default; the owner's PC ran with it in REQ-0022) shows a resolver
# on 10.255.255.254:53 that no process in the distribution owns. Only these exact lines
# pass (Security Engineer rule, TASK-0085 correction); W14 is the first proof of the shape.
DNS_TUNNEL = {("tcp", "LISTEN"), ("udp", "UNCONN")}
DNS_LOCAL, DNS_PEER = "10.255.255.254:53", "0.0.0.0:*"


def _is_dns_tunnel(fields: list[str]) -> bool:
    return (
        len(fields) == 6
        and (fields[0], fields[1]) in DNS_TUNNEL
        and fields[4] == DNS_LOCAL
        and fields[5] == DNS_PEER
    )


# AC-E2 (TASK-0097, the owner's rc.30 run): under WSL these two lines appear with no owning
# process. chrony 4.6.1 opens no UDP command socket when ``cmdport`` is 0 (cmdmon.c,
# open_socket; Debian 4.6.1-3+deb13u2 does not patch it), and our chrony.conf has
# ``cmdport 0``, so a chronyd outside this distribution that shares the WSL network
# namespace owns them. They pass only with no process column (a socket of a process of this
# distribution shows its owner, ``ss -p``) and only while PID 1 in view is this
# distribution's systemd, so that the owners of this distribution are in view. On that port
# chronyd answers only monitoring requests (tracking, sources: PERMIT_OPEN in cmdmon.c); it
# refuses every command that changes it over UDP. Mirrored networking shares loopback with
# Windows, so a Windows program on the PC can read that time status.
CHRONY_OUTSIDE = {
    ("udp", "UNCONN", "127.0.0.1:323", "0.0.0.0:*"),
    ("udp", "UNCONN", "[::1]:323", "[::]:*"),
}


def _is_outside_chrony(fields: list[str]) -> bool:
    return len(fields) == 6 and (fields[0], fields[1], fields[4], fields[5]) in CHRONY_OUTSIDE


def owners_in_view(ctx: Context) -> bool:
    """PID 1 in this process's view is this distribution's systemd."""
    try:
        return (ctx.paths.proc / "1/comm").read_text().strip() == "systemd"
    except OSError:
        return False


def unexpected_listeners(
    text: str, *, owners_visible: bool = False
) -> tuple[list[str], list[str]]:
    """(allowed lines, every other line) of ``ss -H -ltnup`` output; each line is its fields
    joined by one space. Allowed: the WSL DNS tunnel lines and, only with ``owners_visible``,
    the two chronyd loopback lines owned outside this distribution. The Linux install proof
    calls this too (without ``owners_visible``)."""
    allowed: list[str] = []
    others: list[str] = []
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        passes = _is_dns_tunnel(fields) or (owners_visible and _is_outside_chrony(fields))
        (allowed if passes else others).append(" ".join(fields))
    return allowed, others


def check_listeners(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    result = ctx.runner.run(step, ["ss", "-H", "-ltnup"], timeout=30)
    if not result.ok:
        return _fail(ctx, step, "listeners_unknown", f"exit {result.returncode}")
    allowed, others = unexpected_listeners(result.text(), owners_visible=owners_in_view(ctx))
    for line in allowed:
        kind = "WSL DNS listener" if _is_dns_tunnel(line.split()) else (
            "chronyd command port outside this distribution"
        )
        ctx.log.line(step, "INFO", f"allowed {kind}: {line}")
    if others:
        seen = [
            f"{line} (owner not visible)" if len(line.split()) == 6 else line for line in others
        ]
        return _fail(ctx, step, "unexpected_listener", " | ".join(seen))
    _pass(ctx, step, "nothing else listens")
    return None


def remove_interop(folder: Path, write: Callable[[Path, str], None]) -> tuple[list[str], list[str]]:
    """Remove every ``WSLInterop*`` binfmt entry (write ``-1``); return (removed, refused).
    Linux never starts a Windows program: ``wsl.conf`` alone did not keep the entry off on
    the owner's PC (TASK-0097). The Linux install proof calls this too."""
    removed: list[str] = []
    refused_names: list[str] = []
    for entry in sorted(folder.glob("WSLInterop*")):
        try:
            write(entry, "-1")
        except OSError:
            refused_names.append(entry.name)
        else:
            removed.append(entry.name)
    return removed, refused_names


def check_interop(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    folder = ctx.paths.proc / "sys/fs/binfmt_misc"
    if not (folder / "status").is_file():
        # Not mounted: an entry could appear later, so the state is unknown (S85-4).
        return _fail(ctx, step, "interop_unknown", "binfmt_misc is not mounted")
    removed, kept = remove_interop(folder, ctx.deps.write_binfmt)
    for name in removed:
        ctx.log.line(step, "INFO", f"removed WSLInterop entry {name}")
    for name in kept:
        ctx.log.line(step, "WARN", f"could not remove WSLInterop entry {name}")
    try:
        entries = sorted(folder.glob("WSLInterop*"))
        enabled = [e.name for e in entries if e.read_text().splitlines()[:1] == ["enabled"]]
    except OSError:
        return _fail(ctx, step, "interop_unknown", "binfmt_misc unreadable")
    if enabled:
        return _fail(ctx, step, "interop_enabled", ", ".join(enabled))
    _pass(ctx, step, f"no enabled WSLInterop entry ({len(entries)} present)")
    return None


def _unescape(text: str) -> str:
    return _OCTAL.sub(lambda match: chr(int(match.group(1), 8)), text)


def check_mounts(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    try:
        lines = (ctx.paths.proc / "self/mountinfo").read_text().splitlines()
    except OSError:
        return _fail(ctx, step, "mounts_unknown", "mountinfo unreadable")
    drives: list[str] = []
    for line in lines:
        left, separator, right = line.partition(" - ")
        fields, tail = left.split(), right.split()
        if not separator or len(fields) < 5 or len(tail) < 2:
            continue
        target, kind, source = _unescape(fields[4]), tail[0], tail[1]
        options = tail[2] if len(tail) > 2 else ""
        if kind not in ("9p", "drvfs"):
            continue
        ctx.log.line(step, "INFO", f"mount {target} type {kind} source {_unescape(source)}")
        if (
            kind == "drvfs"
            or "aname=drvfs" in options
            or _DRIVE_SOURCE.match(source)
            or target == "/mnt"
            or target.startswith("/mnt/")
        ):
            drives.append(target)
    # S85-7: whatever the type, a Windows drive letter under /mnt or in a path= option.
    for line in lines:
        left, _, right = line.partition(" - ")
        fields, tail = left.split(), right.split()
        if len(fields) < 6:
            continue
        target = _unescape(fields[4])
        options = ",".join([fields[5], *tail[2:3]])
        if (_DRIVE_TARGET.match(target) or _PATH_OPTION.search(options)) and target not in drives:
            ctx.log.line(step, "INFO", f"mount {target} type {tail[0] if tail else '?'}")
            drives.append(target)
    if drives:
        return _fail(ctx, step, "windows_drive_mounted", ", ".join(drives))
    _pass(ctx, step, "no Windows drive mounted")
    return None


# S85-4: every account but UID 0 "root" must have a no-login shell. /bin/sync (Debian's
# "sync" account) runs sync and exits; an empty field means /bin/sh.
NO_LOGIN = frozenset(
    {"/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false", "/bin/sync"}
)


def check_shells(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    try:
        accounts = [line.split(":") for line in ctx.paths.passwd.read_text().splitlines()]
    except OSError:
        return _fail(ctx, step, "accounts_unknown", "passwd unreadable")
    others = [
        fields
        for fields in accounts
        if len(fields) >= 7
        and (fields[0], fields[2]) != ("root", "0")
        and (fields[6] or "/bin/sh") not in NO_LOGIN
    ]
    if others:
        return _fail(ctx, step, "login_shell_found", f"{len(others)} account(s) besides root")
    _pass(ctx, step, "only root has a login shell")
    return None


def check_bundle(ctx: Context, step: str, manifest: dict[str, Any], version: str) -> str | None:
    try:
        record = json.loads(ctx.paths.image_record.read_text())
        recorded = record["engine_bundle"]["sha256"]
        recorded_version = record["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return _fail(ctx, step, "image_record_missing", "no engine bundle in the image record")
    expected = (manifest.get("engine_bundle") or {}).get("sha256")
    if recorded_version != version or recorded != expected:
        seen = f"image {recorded_version} {recorded}, manifest {expected}"
        return _fail(ctx, step, "engine_bundle_mismatch", seen)
    _pass(ctx, step, f"image engine bundle {recorded} matches the manifest")
    return None


CHECKS: tuple[tuple[str, Check], ...] = (
    ("systemd", check_systemd),
    ("docker", check_docker),
    ("container", check_container),
    ("networking", check_networking),
    ("time", check_time),
    ("listeners", check_listeners),
    ("interop", check_interop),
    ("mounts", check_mounts),
    ("shells", check_shells),
    ("bundle", check_bundle),
)


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    version = request["version"]
    manifest = release.require(ctx.paths, version)
    facts.record(ctx)
    failures: list[str] = []
    for number, (name, check) in enumerate(CHECKS, start=1):
        step = ctx.step(number, name)
        if name == "container" and {"docker_not_ready", "docker_store_unknown"} & set(failures):
            ctx.log.line(step, "WARN", "not run: Docker does not answer")
            continue
        progress.report(ctx, name)
        code = check(ctx, step, manifest, version)
        if code is not None:
            failures.append(code)
    if failures:
        raise failed(failures[0], failed=",".join(failures), detail=detail(ctx))
    return {"code": "prepared"}
