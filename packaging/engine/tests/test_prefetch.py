"""``prefetch`` and its worker (plan 4.1 page 4a, 10.7; AC-F1 to AC-F3)."""

from __future__ import annotations

import http.server
import json
import shutil
import socketserver
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from engine import cli, prefetch
from engine.core import Paths, private_dir
from engine.docker_api import DockerApi

from .helpers import (
    RUN_ID,
    VERSION,
    Script,
    call,
    deps,
    fail,
    log_text,
    make_paths,
    progress_lines,
)

DB = "supabase/postgres:17.11.0.004@sha256:" + "6" * 64
AUTH = "supabase/gotrue:v2.196.0@sha256:" + "c" * 64
NAME_LOOKUP = (
    'Get "https://registry-1.docker.io/v2/": dial tcp: lookup registry-1.docker.io '
    "on 127.0.0.11:53: no such host"
)
RATE_LIMIT = (
    "toomanyrequests: You have reached your unauthenticated pull rate limit. "
    "https://www.docker.com/increase-rate-limit"
)
TIMEOUT = (
    'Get "https://registry-1.docker.io/v2/": net/http: request canceled while waiting for '
    "connection (Client.Timeout exceeded while awaiting headers)"
)


def untagged(reference: str) -> str:
    """``name:tag@digest`` as the API request names it: ``name@digest``."""
    name, digest = reference.split("@")
    return f"{name.rsplit(':', 1)[0] if ':' in name.rsplit('/', 1)[-1] else name}@{digest}"


def _events(layer_sizes: list[int]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"status": "Pulling from supabase/postgres", "id": "x"}]
    for index, size in enumerate(layer_sizes):
        layer = f"layer{index}"
        events += [
            {"status": "Pulling fs layer", "id": layer},
            {
                "status": "Downloading",
                "id": layer,
                "progressDetail": {"current": size // 2, "total": size},
            },
            {"status": "Download complete", "id": layer},
            {"status": "Pull complete", "id": layer},
        ]
    return [*events, {"status": "Digest: sha256:" + "6" * 64}]


class FakeDocker:
    """Answers ``POST /images/create`` from a script per image, and image lookups."""

    def __init__(self, socket_path: Path, plan: dict[str, list[Any]]) -> None:
        self.plan = {untagged(reference): answers for reference, answers in plan.items()}
        self.pulled: set[str] = set()
        self.requests: list[tuple[str, str]] = []
        fake = self
        stalled = threading.Event()  # never set: a wait on it is a stalled stream

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return None

            def address_string(self) -> str:
                return "local"

            def do_POST(self) -> None:
                query = parse_qs(urlsplit(self.path).query)
                reference = f"{query['fromImage'][0]}@{query['tag'][0]}"
                fake.requests.append(("POST", reference))
                answer = fake.plan[reference].pop(0)
                if isinstance(answer, int):
                    self.send_response(answer)
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": f"error {answer}"}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                for event in answer:
                    if "_stall" in event:
                        self.wfile.flush()
                        stalled.wait(event["_stall"])
                        return
                    self.wfile.write(json.dumps(event).encode() + b"\r\n")
                if answer and "error" not in answer[-1]:
                    fake.pulled.add(reference)

            def do_GET(self) -> None:
                names = {r.split("@")[0].replace("/", "%2F") for r in fake.pulled}
                found = any(self.path.startswith(f"/images/{name}") for name in names)
                fake.requests.append(("GET", self.path))
                self.send_response(200 if found else 404)
                self.end_headers()
                self.wfile.write(b"{}")

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        self.server = Server(str(socket_path), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def socket_folder() -> Iterator[Path]:
    folder = Path(tempfile.mkdtemp(prefix="se"))  # AF_UNIX paths are short on macOS
    yield folder
    shutil.rmtree(folder)


def _paths(tmp_path: Path, socket_folder: Path, providers: list[str]) -> Paths:
    paths = make_paths(tmp_path)
    paths = Paths(**{**paths.__dict__, "docker_socket": socket_folder / "d.sock"})
    folder = private_dir(paths.releases / VERSION)
    manifest = {"schema_version": 1, "version": VERSION, "images": {"providers": providers}}
    (folder / "release-manifest.json").write_text(json.dumps(manifest))
    return paths


def _worker(paths: Paths, sleeps: list[float]) -> int:
    return cli.main([prefetch.WORKER, RUN_ID, VERSION], deps=deps(paths, sleep=sleeps.append))


def test_ac_f1_prefetch_starts_the_worker_unit_and_returns_at_once(tmp_path: Path) -> None:
    paths = _paths(tmp_path, tmp_path, [DB, AUTH])
    script = Script()

    first = call(["prefetch"], {"run_id": RUN_ID, "version": VERSION}, deps(paths, script))
    second = call(["prefetch"], {"run_id": RUN_ID, "version": VERSION}, deps(paths, script))

    assert first[:2] == (0, {"code": "prefetch_started", "steps_total": 2})
    assert second[:2] == (0, {"code": "prefetch_running"})
    starts = [argv for argv in script.calls if argv[0] == "systemd-run"]
    assert starts == [
        [
            "systemd-run",
            "--unit=slateops-prefetch",
            "--collect",
            "--quiet",
            "--property=Type=exec",
            "--",
            str(paths.engine_command),
            "_prefetch-worker",
            RUN_ID,
            VERSION,
        ]
    ]
    assert prefetch.progress(paths)["code"] == "prefetch_starting"


def test_ac_f1_a_failed_unit_start_is_a_failure(tmp_path: Path) -> None:
    paths = _paths(tmp_path, tmp_path, [DB])
    script = Script({("systemd-run",): fail(1, stderr="Failed to start transient service")})

    code, result, _ = call(
        ["prefetch"], {"run_id": RUN_ID, "version": VERSION}, deps(paths, script)
    )

    assert (code, result["code"]) == (3, "prefetch_start_failed")
    assert prefetch.progress(paths)["code"] == "pull_failed"


def test_ac_f2_the_worker_pulls_by_digest_and_reports_whole_number_progress(
    tmp_path: Path, socket_folder: Path
) -> None:
    paths = _paths(tmp_path, socket_folder, [DB, AUTH])
    docker = FakeDocker(paths.docker_socket, {DB: [_events([1000, 3000])], AUTH: [_events([500])]})
    sleeps: list[float] = []
    try:
        code = _worker(paths, sleeps)
    finally:
        docker.close()

    assert code == 0
    assert [r for r in docker.requests if r[0] == "POST"] == [
        ("POST", "supabase/postgres@sha256:" + "6" * 64),
        ("POST", "supabase/gotrue@sha256:" + "c" * 64),
    ]
    assert prefetch.progress(paths) == {
        "code": "prefetch_done",
        "step": 2,
        "steps_total": 2,
        "bytes_done": 4500,
        "bytes_total": 4500,
        "retry_in_seconds": 0,
    }
    assert sleeps == []
    assert "pull 1/2 " + DB in log_text(paths)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (NAME_LOOKUP, "pull_name_lookup"),
        (
            'Get "https://ghcr.io/v2/": tls: failed to verify certificate: '
            "x509: certificate signed by unknown authority",
            "pull_tls",
        ),
        (TIMEOUT, "pull_timeout"),
        ('Get "https://registry-1.docker.io/v2/": net/http: TLS handshake timeout', "pull_timeout"),
        (RATE_LIMIT, "pull_rate_limited"),
        (
            'Get "https://registry-1.docker.io/v2/": proxyconnect tcp: '
            "dial tcp 10.0.0.1:3128: connect: connection refused",
            "pull_proxy",
        ),
        ("manifest unknown: manifest unknown", "pull_failed"),
        ("docker socket: [Errno 2] No such file or directory", "docker_not_ready"),
    ],
    ids=["name", "tls", "timeout", "tls-timeout", "rate-limit", "proxy", "other", "socket"],
)
def test_ac_f3_pull_errors_get_their_class(message: str, expected: str) -> None:
    assert prefetch.classify(message) == expected


def test_ac_f3_time_outs_and_429_retry_three_times_with_growing_waits(
    tmp_path: Path, socket_folder: Path
) -> None:
    paths = _paths(tmp_path, socket_folder, [DB])
    error = [{"error": RATE_LIMIT, "errorDetail": {"message": RATE_LIMIT}}]
    docker = FakeDocker(paths.docker_socket, {DB: [error, error, error]})
    sleeps: list[float] = []
    try:
        code = _worker(paths, sleeps)
    finally:
        docker.close()

    assert code == 3
    assert sleeps == [30.0, 90.0]
    assert len([r for r in docker.requests if r[0] == "POST"]) == 3
    assert prefetch.progress(paths)["code"] == "pull_rate_limited"


def test_ac_f3_a_retry_that_succeeds_finishes_the_pull(tmp_path: Path, socket_folder: Path) -> None:
    paths = _paths(tmp_path, socket_folder, [DB])
    error = [{"error": TIMEOUT, "errorDetail": {"message": TIMEOUT}}]
    docker = FakeDocker(paths.docker_socket, {DB: [error, _events([10])]})
    sleeps: list[float] = []
    try:
        code = _worker(paths, sleeps)
    finally:
        docker.close()

    assert (code, sleeps) == (0, [30.0])
    assert prefetch.progress(paths)["code"] == "prefetch_done"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [([{"error": NAME_LOOKUP}], "pull_name_lookup"), (404, "pull_failed")],
    ids=["name-lookup", "http-404"],
)
def test_ac_f3_other_classes_stop_at_once(
    tmp_path: Path, socket_folder: Path, answer: Any, expected: str
) -> None:
    paths = _paths(tmp_path, socket_folder, [DB])
    docker = FakeDocker(paths.docker_socket, {DB: [answer]})
    sleeps: list[float] = []
    try:
        code = _worker(paths, sleeps)
    finally:
        docker.close()

    assert (code, sleeps) == (3, [])
    assert prefetch.progress(paths)["code"] == expected


def test_ac_f3_no_docker_socket_is_docker_not_ready(tmp_path: Path, socket_folder: Path) -> None:
    paths = _paths(tmp_path, socket_folder, [DB])

    assert _worker(paths, []) == 3
    assert prefetch.progress(paths)["code"] == "docker_not_ready"


def test_ac_f2_the_client_sends_the_name_and_the_digest_only(socket_folder: Path) -> None:
    docker = FakeDocker(socket_folder / "d.sock", {"a/b@sha256:" + "0" * 64: [_events([1])]})
    try:
        list(DockerApi(socket_folder / "d.sock").pull("a/b", "sha256:" + "0" * 64))
    finally:
        docker.close()

    assert docker.requests == [("POST", "a/b@sha256:" + "0" * 64)]


def test_architect_1_an_unexpected_worker_error_is_logged_redacted(
    tmp_path: Path, socket_folder: Path
) -> None:
    paths = _paths(tmp_path, socket_folder, [DB])
    leaked = "Wk" + "9pQ2xL7rT4vN8sZ1cY6"
    paths.etc.mkdir(parents=True)
    (paths.etc / "app.env").write_text(f"PUBLICATION_SIGNING_KEY={leaked}\n")

    def broken(path: Path) -> DockerApi:
        raise RuntimeError(f"client setup failed near {leaked}")

    code = cli.main([prefetch.WORKER, RUN_ID, VERSION], deps=deps(paths, docker_api=broken))

    logs = log_text(paths)
    assert code == 3
    assert "RuntimeError: client setup failed near [REDACTED]" in logs
    assert leaked not in logs
    assert prefetch.progress(paths)["code"] == "pull_failed"


def test_architect_9_a_stalled_pull_stream_is_a_time_out(
    tmp_path: Path, socket_folder: Path
) -> None:
    paths = _paths(tmp_path, socket_folder, [DB])
    stall = [{"status": "Pulling fs layer", "id": "l0"}, {"_stall": 1.0}]
    docker = FakeDocker(paths.docker_socket, {DB: [stall, stall, stall]})
    sleeps: list[float] = []
    try:
        code = cli.main(
            [prefetch.WORKER, RUN_ID, VERSION],
            deps=deps(paths, sleep=sleeps.append, docker_api=lambda p: DockerApi(p, timeout=0.2)),
        )
    finally:
        docker.close()

    assert (code, sleeps) == (3, [30.0, 90.0])
    assert prefetch.progress(paths)["code"] == "pull_timeout"


def test_w14_d5_prefetch_reports_the_worker_start(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _paths(tmp_path, tmp_path, [DB, AUTH])

    code, _, _ = call(["prefetch"], {"run_id": RUN_ID, "version": VERSION}, deps(paths, Script()))

    assert code == 0
    assert progress_lines(capsys.readouterr().err) == ["progress prefetch 1/1 start_pull start"]
