"""``receive`` (plan 3.2 rule 1, 5.2, W5b-8; W4 carries; AC-R1 to AC-R7)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path
from typing import Any

import pytest

from engine import receive, release
from engine.core import Paths, held_lock
from engine.runner import Result

from .helpers import (
    RUN_ID,
    VERSION,
    Response,
    Script,
    call,
    deps,
    fail,
    log_text,
    make_paths,
    ok,
    progress_lines,
)

SERVER_DIGEST = "sha256:" + "1" * 64
CADDY_DIGEST = "sha256:" + "2" * 64
OWNER = "ghcr.io/jayeuse"
IDENTITY = "https://github.com/jayeuse/slateops/.github/workflows/release.yml@refs/tags/v" + VERSION


def _parts(version: str = VERSION) -> dict[str, bytes]:
    return {
        f"slateops-server-{version}-amd64.oci.tar": b"server archive " * 100,
        f"slateops-caddy-{version}-amd64.oci.tar": b"caddy archive " * 50,
        f"slateops-engine-{version}.tar.gz": b"engine bundle",
    }


def _entry(name: str, data: bytes, **extra: Any) -> dict[str, Any]:
    return {"archive": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), **extra}


def manifest_for(parts: dict[str, bytes], version: str = VERSION, **changes: Any) -> dict[str, Any]:
    server, caddy, bundle = list(parts)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "version": version,
        "images": {
            "server": _entry(
                server,
                parts[server],
                ref=f"{OWNER}/slateops-server:{version}@{SERVER_DIGEST}",
                config_digest="sha256:" + "9" * 64,
            ),
            "caddy": _entry(
                caddy,
                parts[caddy],
                ref=f"{OWNER}/slateops-caddy:{version}@{CADDY_DIGEST}",
                config_digest="sha256:" + "8" * 64,
            ),
            "providers": [],
        },
        "engine_bundle": _entry(bundle, parts[bundle]),
    }
    manifest.update(changes)
    return manifest


def payload(
    members: list[tuple[str, bytes]] | None = None,
    *,
    request: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> bytes:
    parts = _parts()
    if members is None:
        members = [
            (
                "request.json",
                json.dumps(request or {"run_id": RUN_ID, "setup_version": VERSION}).encode(),
            ),
            ("release-manifest.json", json.dumps(manifest or manifest_for(parts)).encode()),
            ("release-manifest.json.sigstore.json", b'{"mediaType": "bundle"}'),
            *parts.items(),
        ]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w|") as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _inspect(argv: list[str]) -> Result:
    digest = SERVER_DIGEST if "slateops-server" in argv[-1] else CADDY_DIGEST
    return ok(f'{digest} ["{argv[-1].split(":")[0]}@{digest}"]\n')


def script(**answers: Response) -> Script:
    base: dict[tuple[str, ...], Any] = {
        ("cosign",): ok(),
        ("docker", "load"): ok("Loaded image\n"),
        ("docker", "image", "inspect"): _inspect,
    }
    base.update({tuple(key.split("_")): value for key, value in answers.items()})
    return Script(base)


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return make_paths(tmp_path)


def _receive(
    paths: Paths, data: bytes, runs: Script, **overrides: Any
) -> tuple[int, dict[str, Any]]:
    code, result, _ = call(["receive"], data, deps(paths, runs, **overrides))
    return code, result


def _no_staging(paths: Paths) -> bool:
    return not paths.staging.exists() or not any(paths.staging.iterdir())


def test_ac_r3_to_r7_a_valid_payload_is_verified_loaded_and_kept(paths: Paths) -> None:
    runs = script()

    code, result = _receive(paths, payload(), runs)

    assert (code, result) == (0, {"code": "received", "version": VERSION})
    cosign = [argv for argv in runs.calls if argv[0] == "cosign"]
    assert len(cosign) == 1
    staging = paths.staging / RUN_ID
    assert cosign[0] == [
        "cosign",
        "verify-blob",
        "--bundle",
        str(staging / "release-manifest.json.sigstore.json"),
        "--certificate-identity",
        IDENTITY,
        "--certificate-oidc-issuer",
        "https://token.actions.githubusercontent.com",
        str(staging / "release-manifest.json"),
    ]
    loads = [argv for argv in runs.calls if argv[:2] == ["docker", "load"]]
    assert [argv[-1].rsplit("/", 1)[1] for argv in loads] == list(_parts())[:2]
    inspects = [argv for argv in runs.calls if argv[:3] == ["docker", "image", "inspect"]]
    assert inspects[0][3:] == [
        "--platform",
        "linux/amd64",
        "--format",
        "{{.Id}} {{json .RepoDigests}}",
        f"{OWNER}/slateops-server:{VERSION}",
    ]
    kept = paths.releases / VERSION
    assert sorted(p.name for p in kept.iterdir()) == sorted(
        [
            "release-manifest.json",
            "release-manifest.json.sigstore.json",
            f"slateops-engine-{VERSION}.tar.gz",
        ]
    )
    assert stat.S_IMODE(os.stat(kept).st_mode) == 0o700
    assert _no_staging(paths)
    assert (paths.logs / "receive" / RUN_ID / "engine.log").exists()


def test_ac_r3_no_option_skips_the_signature_check(paths: Paths) -> None:
    runs = script()

    _receive(paths, payload(), runs)

    cosign = next(argv for argv in runs.calls if argv[0] == "cosign")
    assert not [flag for flag in cosign if flag.startswith("--insecure") or "regexp" in flag]
    assert release.REPOSITORY == "jayeuse/slateops"


@pytest.mark.parametrize(
    ("stderr", "exit_code", "expected"),
    [
        ("Error: none of the expected identities matched", 2, "manifest_signature_invalid"),
        (
            "Error: getting trusted root: Get ...: dial tcp: lookup tuf-repo-cdn: no such host",
            3,
            "manifest_check_unreachable",
        ),
    ],
    ids=["bad-identity", "no-network"],
)
def test_ac_r3_a_failed_signature_loads_nothing_and_keeps_nothing(
    paths: Paths, stderr: str, exit_code: int, expected: str
) -> None:
    runs = script(cosign=fail(1, stderr=stderr))

    code, result = _receive(paths, payload(), runs)

    assert (code, result["code"]) == (exit_code, expected)
    assert not [argv for argv in runs.calls if argv[:2] == ["docker", "load"]]
    assert not (paths.releases / VERSION).exists()
    assert _no_staging(paths)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"schema_version": 2}, "manifest_unsupported"),
        ({"schema_version": "1"}, "manifest_invalid"),
        ({"version": "0.1.0-rc.8"}, "version_mismatch"),
    ],
)
def test_ac_r4_schema_and_version_must_match(
    paths: Paths, changes: dict[str, Any], expected: str
) -> None:
    runs = script()

    code, result = _receive(paths, payload(manifest=manifest_for(_parts(), **changes)), runs)

    assert (code, result["code"]) == (2, expected)
    assert not [argv for argv in runs.calls if argv[:2] == ["docker", "load"]]
    assert _no_staging(paths)


@pytest.mark.parametrize("part", ["server", "caddy", "engine_bundle"])
def test_ac_r5_each_sha256_is_checked_before_any_load(paths: Paths, part: str) -> None:
    manifest = manifest_for(_parts())
    entry = manifest["engine_bundle"] if part == "engine_bundle" else manifest["images"][part]
    entry["sha256"] = "0" * 64
    runs = script()

    code, result = _receive(paths, payload(manifest=manifest), runs)

    assert (code, result) == (
        2,
        {"code": "payload_mismatch", "message_key": "receive.payload_mismatch", "part": part},
    )
    assert not [argv for argv in runs.calls if argv[:2] == ["docker", "load"]]
    assert _no_staging(paths)


def test_ac_r6_a_loaded_image_with_another_digest_is_removed_and_refused(paths: Paths) -> None:
    runs = script(docker_image_inspect=ok("sha256:" + "f" * 64 + " []\n"))

    code, result = _receive(paths, payload(), runs)

    assert (code, result["code"], result["part"]) == (2, "image_digest_mismatch", "server")
    assert ["docker", "image", "rm", f"{OWNER}/slateops-server:{VERSION}"] in runs.calls
    assert not (paths.releases / VERSION).exists()
    assert _no_staging(paths)


def _member(name: str, data: bytes = b"x", kind: bytes = tarfile.REGTYPE) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size, info.type = len(data), kind
    return info


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        ("extra-name", "payload_unexpected_part"),
        ("path-name", "payload_unexpected_part"),
        ("duplicate", "payload_unexpected_part"),
        ("symlink", "payload_unexpected_part"),
        ("missing-part", "payload_incomplete"),
        ("request-not-first", "invalid_input"),
        ("request-bad-key", "invalid_input"),
        ("request-bad-version", "invalid_input"),
    ],
)
def test_ac_r1_only_expected_regular_files_in_the_stream(
    paths: Paths, build: str, expected: str
) -> None:
    parts = _parts()
    request = json.dumps({"run_id": RUN_ID, "setup_version": VERSION}).encode()
    good = [
        ("request.json", request),
        ("release-manifest.json", json.dumps(manifest_for(parts)).encode()),
        ("release-manifest.json.sigstore.json", b"{}"),
        *parts.items(),
    ]
    members: list[tuple[str, bytes]] = list(good)
    if build == "extra-name":
        members.append(("notes.txt", b"x"))
    elif build == "path-name":
        members[1] = ("../release-manifest.json", members[1][1])
    elif build == "duplicate":
        members.append(good[1])
    elif build == "missing-part":
        members.pop()
    elif build == "request-not-first":
        members = [members[1], members[0], *members[2:]]
    elif build == "request-bad-key":
        members[0] = (
            "request.json",
            json.dumps({"run_id": RUN_ID, "setup_version": VERSION, "x": 1}).encode(),
        )
    elif build == "request-bad-version":
        members[0] = (
            "request.json",
            json.dumps({"run_id": RUN_ID, "setup_version": "../x"}).encode(),
        )
    data = payload(members)
    if build == "symlink":
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w|") as tar:
            tar.addfile(_member("request.json", request), io.BytesIO(request))
            link = _member("release-manifest.json", b"", tarfile.SYMTYPE)
            link.linkname, link.size = "/etc/shadow", 0
            tar.addfile(link)
        data = buffer.getvalue()
    runs = script()

    code, result = _receive(paths, data, runs)

    assert (code, result["code"]) == (2, expected)
    assert not [argv for argv in runs.calls if argv[0] in ("cosign", "docker")]
    assert _no_staging(paths)
    assert not (paths.etc).exists()


def test_ac_r1_limits_per_part_and_for_the_stream(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(receive, "IMAGE_LIMIT", 1000)
    big = payload()
    monkeypatch.setattr(receive, "IMAGE_LIMIT", 2 * 1024**3)
    monkeypatch.setattr(receive, "STREAM_LIMIT", 4096)

    per_part = _receive(paths, big, script())
    monkeypatch.setattr(receive, "STREAM_LIMIT", receive.TOTAL_LIMIT + 16 * 1024**2)
    monkeypatch.setattr(
        receive,
        "expected_parts",
        lambda version: {
            **{name: 64 for name in _parts(version)},
            "release-manifest.json": 1024**2,
            "release-manifest.json.sigstore.json": 1024**2,
        },
    )
    too_big_part = _receive(paths, payload(), script())

    assert (per_part[0], per_part[1]["code"]) == (2, "payload_too_large")
    assert (too_big_part[0], too_big_part[1]["code"]) == (2, "payload_too_large")
    assert _no_staging(paths)


def test_ac_r2_free_space_is_checked_before_staging(paths: Paths) -> None:
    runs = script()

    code, result = _receive(paths, payload(), runs, disk_free=lambda path: 5 * 1024**3)

    assert (code, result["code"]) == (3, "insufficient_space")
    assert not runs.calls or all(
        argv[0] in ("systemctl", "docker", "journalctl") for argv in runs.calls
    )
    assert _no_staging(paths)
    assert "free 5368709120 bytes, need 12884901888" in log_text(paths)


def test_ac_r2_staging_is_private_and_old_staging_is_cleared(paths: Paths) -> None:
    old = paths.staging / "install-20261101T000000Z-zzzzzz"
    old.mkdir(parents=True)
    (old / "slateops-server-0.1.0-rc.1-amd64.oci.tar").write_bytes(b"old")
    seen: dict[str, int] = {}

    def capture(argv: list[str]) -> Result:
        folder = Path(argv[3]).parent
        seen["mode"] = stat.S_IMODE(os.stat(folder).st_mode)
        seen["files"] = len(list(folder.iterdir()))
        return ok()

    runs = script(cosign=capture)

    code, _ = _receive(paths, payload(), runs)

    assert code == 0
    assert seen == {"mode": 0o700, "files": 5}
    assert not old.exists()


def test_ac_r2_a_busy_receive_leaves_the_running_jobs_staging_alone(paths: Paths) -> None:
    running = paths.staging / RUN_ID
    running.mkdir(parents=True)
    (running / "release-manifest.json").write_bytes(b"{}")

    with held_lock(paths.engine_lock, "engine_busy"):
        code, result = _receive(paths, payload(), script())

    assert (code, result["code"]) == (2, "engine_busy")
    assert (running / "release-manifest.json").exists()


def test_w14_d5_receive_reports_each_step(paths: Paths, capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _receive(paths, payload(), script())

    assert code == 0
    assert progress_lines(capsys.readouterr().err) == [
        "progress receive 1/6 space start",
        "progress receive 2/6 stage start",
        "progress receive 3/6 signature start",
        "progress receive 4/6 check start",
        "progress receive 5/6 load start",
        "progress receive 6/6 keep start",
    ]
