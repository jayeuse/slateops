"""``prepare`` (plan 10.3 W4-5; W4 carries; AC-P1 to AC-P9)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine import report
from engine.core import Paths, private_dir
from engine.runner import Result

from .helpers import (
    RUN_ID,
    VERSION,
    Script,
    call,
    deps,
    fail,
    log_text,
    make_paths,
    ok,
    progress_lines,
)

BUNDLE_SHA = "b" * 64
SERVER = f"ghcr.io/jayeuse/slateops-server:{VERSION}@sha256:" + "1" * 64
AUTHDATA = (
    "time.cloudflare.com,NTS,1,15,256,33,0,0,8,100\n"
    "nts.netnod.se,NTS,1,15,256,40,0,0,8,100\n"
    "ptbtime1.ptb.de,NTS,1,15,256,52,0,0,8,100\n"
)
TRACKING = (
    "A29FC801,time.cloudflare.com,3,1763374500.123,-0.000123456,0.000045,0.000120,"
    "-12.345,0.001,0.020,0.012345,0.000456,64.2,Normal\n"
)
MOUNTINFO = (
    "22 1 8:32 / / rw,relatime - ext4 /dev/sdc rw\n"
    "35 22 0:30 / /usr/lib/wsl/drivers ro,nosuid - 9p drivers ro,dirsync,aname=drivers\n"
    "40 22 0:5 / /dev rw,nosuid - devtmpfs none rw\n"
)
PASSWD = (
    "root:x:0:0:root:/root:/bin/bash\n"
    "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
    "sync:x:4:65534:sync:/bin:/bin/sync\n"
)


def healthy(**changes: Result) -> Script:
    answers: dict[tuple[str, ...], Any] = {
        ("systemctl", "is-system-running"): ok("running\n"),
        ("systemctl", "is-active", "chrony.service"): ok("active\n"),
        ("docker", "info"): ok('[["driver-type","io.containerd.snapshotter.v1"]]\n'),
        ("docker", "run"): ok(),
        ("wslinfo", "--networking-mode"): ok("mirrored\n"),
        ("chronyc", "-c", "-N", "authdata"): ok(AUTHDATA),
        ("chronyc", "waitsync"): ok(),
        ("chronyc", "-c", "tracking"): ok(TRACKING),
        ("ss",): ok(""),
    }
    answers.update({tuple(key.split("__")): value for key, value in changes.items()})
    return Script(answers)


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    paths = make_paths(tmp_path)
    folder = private_dir(paths.releases / VERSION)
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "images": {"server": {"ref": SERVER}, "providers": []},
        "engine_bundle": {"sha256": BUNDLE_SHA},
    }
    (folder / "release-manifest.json").write_text(json.dumps(manifest))
    paths.image_record.parent.mkdir(parents=True)
    paths.image_record.write_text(
        json.dumps({"version": VERSION, "engine_bundle": {"sha256": BUNDLE_SHA}})
    )
    binfmt = paths.proc / "sys/fs/binfmt_misc"
    binfmt.mkdir(parents=True)
    (binfmt / "status").write_text("enabled\n")
    (paths.proc / "self").mkdir()
    (paths.proc / "self/mountinfo").write_text(MOUNTINFO)
    paths.passwd.parent.mkdir(parents=True, exist_ok=True)
    paths.passwd.write_text(PASSWD)
    return paths


def _kernel_keeps(path: Path, value: str) -> None:
    """A binfmt write that the kernel ignores: the entry stays as it is."""


def _prepare(
    paths: Paths, script: Script, write_binfmt: Any = _kernel_keeps
) -> tuple[int, dict[str, Any]]:
    dependencies = deps(paths, script, write_binfmt=write_binfmt)
    code, result, _ = call(["prepare"], {"run_id": RUN_ID, "version": VERSION}, dependencies)
    return code, result


def test_ac_p1_to_p9_a_healthy_linux_part_passes_and_logs_the_offset(paths: Paths) -> None:
    script = healthy()

    code, result = _prepare(paths, script)

    assert (code, result) == (0, {"code": "prepared"})
    assert [
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
        f"ghcr.io/jayeuse/slateops-server:{VERSION}",
    ] in script.calls
    logs = log_text(paths)
    assert "PASS NTS sync with time.cloudflare.com, stratum 3, offset -0.000123 s" in logs
    assert "mount /usr/lib/wsl/drivers type 9p source drivers" in logs
    assert report.load(paths)["time_sync"]["offset_seconds"] == -0.000123456
    assert (paths.logs / "install" / RUN_ID / "facts.json").exists()


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"systemctl__is-system-running": ok("starting\n")}, "systemd_not_running"),
        ({"systemctl__is-system-running": fail(127)}, "systemd_unknown"),
        ({"docker__info": fail(1)}, "docker_not_ready"),
        ({"docker__info": ok('[["Backing Filesystem","extfs"]]\n')}, "docker_store_not_containerd"),
        ({"docker__run": fail(125)}, "docker_run_failed"),
        ({"wslinfo__--networking-mode": ok("nat\n")}, "networking_not_mirrored"),
        ({"wslinfo__--networking-mode": fail(127)}, "networking_unknown"),
        ({"systemctl__is-active__chrony.service": ok("inactive\n")}, "time_service_inactive"),
        ({"chronyc__-c__-N__authdata": ok(AUTHDATA.replace("NTS", "-", 1))}, "time_not_nts"),
        ({"chronyc__-c__-N__authdata": ok("")}, "time_not_nts"),
        ({"chronyc__waitsync": fail(1)}, "time_not_synced"),
        (
            {"chronyc__-c__tracking": ok(TRACKING.replace("A29FC801", "7F7F0101"))},
            "time_not_synced",
        ),
        ({"ss": ok("tcp LISTEN 0 4096 0.0.0.0:443 0.0.0.0:*\n")}, "unexpected_listener"),
        ({"ss": fail(1)}, "listeners_unknown"),
    ],
    ids=[
        "systemd-starting",
        "systemd-unknown",
        "docker-down",
        "docker-classic-store",
        "docker-run",
        "nat",
        "wslinfo-missing",
        "chrony-inactive",
        "one-source-not-nts",
        "no-source",
        "no-sync",
        "local-clock",
        "listener",
        "ss-fails",
    ],
)
def test_ac_p_each_failed_check_has_its_own_code(
    paths: Paths, changes: dict[str, Result], expected: str
) -> None:
    code, result = _prepare(paths, healthy(**changes))

    assert code == 3
    assert result["code"] == expected
    assert result["message_key"] == f"prepare.{expected}"
    assert f"FAIL {expected}" in log_text(paths)


def test_ac_p1_degraded_passes_only_with_the_core_units_active(paths: Paths) -> None:
    failed_units = ok("systemd-networkd-wait-online.service loaded failed failed Wait\n")
    good = healthy(
        **{
            "systemctl__is-system-running": ok("degraded\n"),
            "systemctl__is-active__containerd.service": ok("active\nactive\nactive\n"),
            "systemctl__--failed": failed_units,
        }
    )
    bad = healthy(
        **{
            "systemctl__is-system-running": ok("degraded\n"),
            "systemctl__is-active__containerd.service": ok("active\nfailed\nactive\n"),
            "systemctl__--failed": failed_units,
        }
    )

    assert _prepare(paths, good)[0] == 0
    assert _prepare(paths, bad)[1]["code"] == "systemd_not_running"
    assert "failed units: systemd-networkd-wait-online.service" in log_text(paths)


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        ("interop", "interop_enabled"),
        ("drvfs", "windows_drive_mounted"),
        ("9p-drive", "windows_drive_mounted"),
        ("9p-mnt", "windows_drive_mounted"),
        ("shell", "login_shell_found"),
        ("bundle", "engine_bundle_mismatch"),
        ("record", "image_record_missing"),
    ],
)
def test_ac_p_windows_boundary_and_image_checks(paths: Paths, setup: str, expected: str) -> None:
    binfmt = paths.proc / "sys/fs/binfmt_misc"
    mountinfo = paths.proc / "self/mountinfo"
    if setup == "interop":
        (binfmt / "WSLInterop").write_text("enabled\ninterpreter /init\nflags: PF\n")
    elif setup == "drvfs":
        mountinfo.write_text(MOUNTINFO + "50 22 0:60 / /backup rw - drvfs E:\\134 rw\n")
    elif setup == "9p-drive":
        mountinfo.write_text(
            MOUNTINFO + "51 22 0:61 / /data rw - 9p C:\\134 rw,aname=drvfs;path=C:\\\n"
        )
    elif setup == "9p-mnt":
        mountinfo.write_text(MOUNTINFO + "52 22 0:62 / /mnt/wslg rw - 9p wslg rw\n")
    elif setup == "shell":
        paths.passwd.write_text(PASSWD + "maria:x:1000:1000::/home/maria:/bin/bash\n")
    elif setup == "bundle":
        paths.image_record.write_text(
            json.dumps({"version": VERSION, "engine_bundle": {"sha256": "c" * 64}})
        )
    elif setup == "record":
        paths.image_record.unlink()

    code, result = _prepare(paths, healthy())

    assert (code, result["code"]) == (3, expected)
    assert "maria" not in log_text(paths)


def test_ac_p_a_disabled_interop_entry_passes(paths: Paths) -> None:
    (paths.proc / "sys/fs/binfmt_misc/WSLInterop").write_text("disabled\ninterpreter /init\n")

    assert _prepare(paths, healthy())[0] == 0


def test_ac_p_prepare_needs_the_verified_manifest(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)

    code, result = _prepare(paths, healthy())

    assert (code, result["code"]) == (2, "manifest_missing")


def test_ac_p_all_failures_are_reported_and_the_first_is_the_code(paths: Paths) -> None:
    script = healthy(
        **{"wslinfo__--networking-mode": ok("nat\n"), "ss": ok("udp UNCONN 0 0 *:123 *:*\n")}
    )

    code, result = _prepare(paths, script)

    assert (code, result["code"], result["failed"]) == (
        3,
        "networking_not_mirrored",
        "networking_not_mirrored,unexpected_listener",
    )


DNS_UDP = "udp   UNCONN 0      0      10.255.255.254:53        0.0.0.0:*"
DNS_TCP = "tcp   LISTEN 0      4096   10.255.255.254:53        0.0.0.0:*"


@pytest.mark.parametrize(
    "lines",
    [[DNS_UDP], [DNS_TCP], [DNS_UDP, DNS_TCP]],
    ids=["udp", "tcp", "both"],
)
def test_dns_the_wsl_dns_tunnel_listener_alone_passes_and_is_logged(
    paths: Paths, lines: list[str]
) -> None:
    code, result = _prepare(paths, healthy(ss=ok("\n".join(lines) + "\n")))

    assert (code, result) == (0, {"code": "prepared"})
    assert log_text(paths).count("allowed WSL DNS listener") == len(lines)


@pytest.mark.parametrize(
    "line",
    [
        "udp   UNCONN 0      0      0.0.0.0:53        0.0.0.0:*",
        "udp   UNCONN 0      0      127.0.0.1:53        0.0.0.0:*",
        "udp   UNCONN 0      0      10.255.255.254:54        0.0.0.0:*",
        "udp   UNCONN 0      0      10.255.255.254%eth0:53        0.0.0.0:*",
        "udp   UNCONN 0      0      [::]:53        [::]:*",
        "tcp   UNCONN 0      0      10.255.255.254:53        0.0.0.0:*",
        "udp   LISTEN 0      0      10.255.255.254:53        0.0.0.0:*",
        "tcp   LISTEN 0      4096   10.255.255.254:53        10.0.0.1:*",
        'tcp   LISTEN 0      4096   10.255.255.254:53        0.0.0.0:* users:(("x",pid=1,fd=3))',
    ],
    ids=[
        "any-address",
        "loopback",
        "port-54",
        "interface-scope",
        "ipv6-any",
        "tcp-unconn",
        "udp-listen",
        "other-peer",
        "extra-field",
    ],
)
def test_dns_every_other_listener_line_is_refused(paths: Paths, line: str) -> None:
    code, result = _prepare(paths, healthy(ss=ok(line + "\n")))

    assert (code, result["code"]) == (3, "unexpected_listener")


def test_dns_an_extra_line_beside_the_allowed_ones_is_refused(paths: Paths) -> None:
    lines = [DNS_UDP, DNS_TCP, "tcp   LISTEN 0      4096   0.0.0.0:443        0.0.0.0:*"]

    code, result = _prepare(paths, healthy(ss=ok("\n".join(lines) + "\n")))

    assert (code, result["code"]) == (3, "unexpected_listener")
    assert "0.0.0.0:443" in log_text(paths)


def test_s85_4_binfmt_misc_not_mounted_is_unknown(paths: Paths) -> None:
    (paths.proc / "sys/fs/binfmt_misc/status").unlink()

    code, result = _prepare(paths, healthy())

    assert (code, result["code"]) == (3, "interop_unknown")


@pytest.mark.parametrize(
    "extra",
    [
        "games:x:5:60:games:/usr/games:\n",
        "toor:x:0:0:root:/root:/bin/bash\n",
        "backup:x:34:34:backup:/var/backups:/usr/bin/zsh\n",
    ],
    ids=["empty-shell", "second-uid-0", "zsh"],
)
def test_s85_4_every_account_but_root_has_a_no_login_shell(paths: Paths, extra: str) -> None:
    paths.passwd.write_text(PASSWD + extra)

    code, result = _prepare(paths, healthy())

    assert (code, result["code"]) == (3, "login_shell_found")


@pytest.mark.parametrize(
    "mount",
    [
        "60 22 0:70 / /mnt/c rw - ext4 /dev/sdd rw\n",
        "61 22 0:71 / /mnt/E/data rw - fuse.x x rw\n",
        "62 22 0:72 / /data rw - virtiofs share rw,path=D:\\134x\n",
    ],
    ids=["mnt-letter-any-type", "mnt-letter-below", "path-option-any-type"],
)
def test_s85_7_drive_mounts_of_any_type_are_refused(paths: Paths, mount: str) -> None:
    (paths.proc / "self/mountinfo").write_text(MOUNTINFO + mount)

    code, result = _prepare(paths, healthy())

    assert (code, result["code"]) == (3, "windows_drive_mounted")


def test_w14_d5_prepare_reports_each_check(
    paths: Paths,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _ = _prepare(paths, healthy())

    assert code == 0
    assert progress_lines(capsys.readouterr().err) == [
        "progress prepare 1/10 systemd start",
        "progress prepare 2/10 docker start",
        "progress prepare 3/10 container start",
        "progress prepare 4/10 networking start",
        "progress prepare 5/10 time start",
        "progress prepare 6/10 listeners start",
        "progress prepare 7/10 interop start",
        "progress prepare 8/10 mounts start",
        "progress prepare 9/10 shells start",
        "progress prepare 10/10 bundle start",
    ]


# TASK-0097 owner item 6 (W14 round 3): on Windows, prepare refused
# `unexpected_listener,interop_enabled` and the engine log was lost.


def _removes(written: list[tuple[str, str]]) -> Any:
    def write(path: Path, value: str) -> None:  # the kernel removes an entry on "-1"
        written.append((path.name, value))
        if value == "-1":
            path.unlink()

    return write


def test_ac_e1_prepare_removes_every_wslinterop_entry_before_the_check(paths: Paths) -> None:
    binfmt = paths.proc / "sys/fs/binfmt_misc"
    for name in ("WSLInterop", "WSLInterop-late"):
        (binfmt / name).write_text("enabled\ninterpreter /init\nflags: PF\n")
    (binfmt / "python3.13").write_text("enabled\ninterpreter /usr/bin/python3.13\n")
    written: list[tuple[str, str]] = []

    code, result = _prepare(paths, healthy(), _removes(written))

    assert (code, result) == (0, {"code": "prepared"})
    assert written == [("WSLInterop", "-1"), ("WSLInterop-late", "-1")]
    assert (binfmt / "python3.13").exists()
    assert "removed WSLInterop entry WSLInterop-late" in log_text(paths)


def test_ac_e1_an_entry_that_the_kernel_keeps_enabled_fails_closed(paths: Paths) -> None:
    (paths.proc / "sys/fs/binfmt_misc/WSLInterop-late").write_text("enabled\n")

    def refuse(path: Path, value: str) -> None:
        raise PermissionError("read-only")

    code, result = _prepare(paths, healthy(), refuse)

    assert (code, result["code"]) == (3, "interop_enabled")
    assert "WSLInterop-late" in result["detail"]


def test_ac_e1_with_binfmt_misc_not_mounted_nothing_is_written_and_the_state_is_unknown(
    paths: Paths,
) -> None:
    (paths.proc / "sys/fs/binfmt_misc/status").unlink()
    written: list[tuple[str, str]] = []

    code, result = _prepare(paths, healthy(), _removes(written))

    assert (code, result["code"], written) == (3, "interop_unknown", [])


def test_ac_e3_a_refusal_names_each_failed_check_and_the_exact_lines(paths: Paths) -> None:
    (paths.proc / "sys/fs/binfmt_misc/WSLInterop").write_text("enabled\n")
    line = "udp   UNCONN 0      0      0.0.0.0:68        0.0.0.0:*"
    owned = line + '   users:(("dhcp\x1bc",pid=88,fd=5))'
    script = healthy(**{"ss__-H__-ltnu": ok(line + "\n"), "ss__-H__-ltnup": ok(owned + "\n")})

    code, result = _prepare(paths, script)

    assert (code, result["code"], result["failed"]) == (
        3, "unexpected_listener", "unexpected_listener,interop_enabled",
    )  # fmt: skip
    detail = result["detail"]
    assert detail.startswith("unexpected_listener: udp UNCONN 0 0 0.0.0.0:68 0.0.0.0:* users:")
    assert '"dhcp\\x1bc"' in detail and "\x1b" not in detail.replace("\\x1b", "")
    assert "; interop_enabled: WSLInterop" in detail
    assert len(detail) <= 1000


def test_ac_e3_a_long_detail_is_cut_to_its_limit(paths: Paths) -> None:
    lines = [f"tcp   LISTEN 0      4096   0.0.0.0:{port}        0.0.0.0:*" for port in range(200)]
    script = healthy(ss=ok("\n".join(lines) + "\n"))

    code, result = _prepare(paths, script)

    assert (code, result["code"]) == (3, "unexpected_listener")
    assert len(result["detail"]) == 1000 and result["detail"].endswith("...")
