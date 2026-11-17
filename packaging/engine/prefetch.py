"""``prefetch``: pull the provider images by digest in the background (plan 4.1 page 4a, 10.7).

The job returns at once: the ``Exec`` task runs one job at a time, so a blocking pull would
stop ``smtp-test`` on the next page (TASK-0080 item 1). It starts the worker in a transient
systemd unit; the worker holds the prefetch lock, pulls each image of the verified
manifest through the Docker API and writes whole-number progress for ``status``.

``bytes_total`` is the sum of the layer sizes that the daemon has reported so far, so it
grows during the pull; the Windows side shows it for display only (plan 3.2 rule 2).
Time-outs and HTTP 429 get three tries in all (two retries, after 30 s and then 90 s);
the other classes stop at once (plan 10.7).
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from datetime import datetime
from typing import Any

from engine import release
from engine.context import Context, Dependencies
from engine.core import (
    JobError,
    Paths,
    failed,
    held_lock,
    is_run_id,
    is_version,
    lock_is_held,
    private_dir,
    refused,
    write_private,
)
from engine.docker_api import DockerApi, DockerError
from engine.held import load_held
from engine.logs import RunLog
from engine.redaction import Redactor

KEYS = {"run_id": is_run_id, "version": is_version}
REQUIRED = frozenset(KEYS)
WORKER = "_prefetch-worker"
UNIT = "slateops-prefetch"
TRIES = 3
WAITS = (30.0, 90.0)  # planning values: growing waits before tries 2 and 3
RETRIED = frozenset({"pull_timeout", "pull_rate_limited"})
STARTING_GRACE_SECONDS = 60.0
CODES = frozenset(
    {
        "prefetch_not_started",
        "prefetch_starting",
        "prefetch_running",
        "prefetch_retrying",
        "prefetch_done",
        "prefetch_interrupted",
        "pull_name_lookup",
        "pull_tls",
        "pull_timeout",
        "pull_rate_limited",
        "pull_proxy",
        "pull_failed",
        "docker_not_ready",
        "manifest_missing",
        "manifest_invalid",
    }
)
NUMBERS = ("step", "steps_total", "bytes_done", "bytes_total", "retry_in_seconds")


def classify(message: str) -> str:
    """The plan 10.7 class of a daemon pull error (Go net/http and registry texts)."""
    text = message.lower()
    if text.startswith("docker socket"):
        return "docker_not_ready"
    if "proxyconnect" in text:
        return "pull_proxy"
    if "toomanyrequests" in text or "too many requests" in text or " 429" in text:
        return "pull_rate_limited"
    if "timeout" in text or "deadline exceeded" in text or "timed out" in text:
        return "pull_timeout"
    if "no such host" in text or "server misbehaving" in text or "name resolution" in text:
        return "pull_name_lookup"
    if "x509" in text or "certificate" in text or "tls:" in text:
        return "pull_tls"
    return "pull_failed"


def read_state(paths: Paths) -> dict[str, Any]:
    try:
        data = json.loads(paths.prefetch_state.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(paths: Paths, state: dict[str, Any]) -> None:
    private_dir(paths.state)
    write_private(paths.prefetch_state, (json.dumps(state, sort_keys=True) + "\n").encode())


def progress(paths: Paths) -> dict[str, Any]:
    """Safe values only: a fixed code and whole numbers."""
    state = read_state(paths)
    code = state.get("code") if state.get("code") in CODES else "prefetch_not_started"
    running = lock_is_held(paths.prefetch_lock, paths.proc)
    if code in {"prefetch_running", "prefetch_retrying"} and not running:
        code = "prefetch_interrupted"
    numbers = {
        name: value
        if isinstance(value := state.get(name), int) and not isinstance(value, bool) and value >= 0
        else 0
        for name in NUMBERS
    }
    return {"code": code, **numbers}


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    paths, version = ctx.paths, request["version"]
    images = release.providers(release.require(paths, version))
    state = read_state(paths)
    if lock_is_held(paths.prefetch_lock, paths.proc):
        return {"code": "prefetch_running"}
    if state.get("code") == "prefetch_done" and state.get("version") == version:
        return {"code": "prefetch_done"}
    if state.get("code") == "prefetch_starting" and state.get("version") == version:
        started = datetime.fromisoformat(str(state.get("at")))
        if (ctx.deps.clock() - started).total_seconds() < STARTING_GRACE_SECONDS:
            return {"code": "prefetch_running"}
    write_state(
        paths,
        {
            "run_id": ctx.run_id,
            "version": version,
            "code": "prefetch_starting",
            "at": ctx.deps.clock().isoformat(),
            "step": 0,
            "steps_total": len(images),
        },
    )
    result = ctx.runner.run(
        ctx.step(1, "start"),
        [
            "systemd-run",
            f"--unit={UNIT}",
            "--collect",
            "--quiet",
            "--property=Type=exec",
            "--",
            str(paths.engine_command),
            WORKER,
            ctx.run_id,
            version,
        ],
        timeout=60,
    )
    if not result.ok:
        write_state(paths, {"run_id": ctx.run_id, "version": version, "code": "pull_failed"})
        raise failed("prefetch_start_failed")
    return {"code": "prefetch_started", "steps_total": len(images)}


class _Progress:
    def __init__(self, paths: Paths, base: dict[str, Any], clock: Callable[[], datetime]) -> None:
        self.paths, self.base, self.clock = paths, base, clock
        self.finished_bytes = 0
        self.layers: dict[str, tuple[int, int]] = {}
        self.written: datetime | None = None

    def totals(self) -> tuple[int, int]:
        return (
            self.finished_bytes + sum(current for current, _ in self.layers.values()),
            self.finished_bytes + sum(total for _, total in self.layers.values()),
        )

    def save(self, *, force: bool = False, **fields: Any) -> None:
        now = self.clock()
        if not force and self.written and (now - self.written).total_seconds() < 1:
            return
        done, total = self.totals()
        write_state(self.paths, {**self.base, **fields, "bytes_done": done, "bytes_total": total})
        self.written = now

    def event(self, event: dict[str, Any]) -> None:
        layer, status = str(event.get("id", "")), str(event.get("status", ""))
        detail = event.get("progressDetail") or {}
        current, total = detail.get("current"), detail.get("total")
        if status == "Downloading" and isinstance(current, int) and isinstance(total, int):
            self.layers[layer] = (min(current, total), total)
        elif status in ("Download complete", "Pull complete") and layer in self.layers:
            self.layers[layer] = (self.layers[layer][1], self.layers[layer][1])


def _pull(api: DockerApi, reference: str, tracker: _Progress) -> None:
    match = release.REFERENCE.match(reference)
    if match is None:
        raise refused("manifest_invalid")
    for event in api.pull(match.group("name"), match.group("digest")):
        tracker.event(event)
        tracker.save()
    if not api.image_exists(reference):
        raise DockerError("the pulled image is not present by its digest")


def worker(deps: Dependencies, run_id: str, version: str) -> int:
    """The background pull; exit 0 done, 2 refused, 3 failed. It prints nothing."""
    if not is_run_id(run_id) or not is_version(version):
        return 2
    paths = deps.paths
    log = RunLog(paths, run_id, "prefetch", Redactor(*load_held(paths)), deps.clock)
    step = "prefetch.02.pull"
    lock = held_lock(paths.prefetch_lock, "prefetch_running")
    try:
        lock.__enter__()
    except JobError:
        log.line(step, "WARN", "another pull holds the prefetch lock")
        return 2
    try:
        code = pull_all(deps, log, step, run_id, version)
    except Exception as error:
        code = error.code if isinstance(error, JobError) else "pull_failed"
        log.line(step, "ERROR", traceback.format_exc())  # redacted by the run log
        write_state(paths, {"run_id": run_id, "version": version, "code": code})
    finally:
        lock.__exit__(None, None, None)
    log.line(step, "INFO" if code == "prefetch_done" else "ERROR", f"result {code}")
    return 0 if code == "prefetch_done" else 3


def pull_all(deps: Dependencies, log: RunLog, step: str, run_id: str, version: str) -> str:
    paths = deps.paths
    images = release.providers(release.require(paths, version))
    base = {"run_id": run_id, "version": version, "steps_total": len(images)}
    tracker = _Progress(paths, {**base, "code": "prefetch_running", "step": 1}, deps.clock)
    tracker.save(force=True)
    api = deps.docker_api(paths.docker_socket)
    for index, reference in enumerate(images, start=1):
        tracker.base.update(code="prefetch_running", step=index, retry_in_seconds=0)
        for attempt in range(1, TRIES + 1):
            log.line(step, "INFO", f"pull {index}/{len(images)} {reference} try {attempt}")
            try:
                _pull(api, reference, tracker)
                break
            except DockerError as error:
                code = classify(error.message)
                log.line(step, "WARN", f"{code} try {attempt}: {error.message}")
                if code not in RETRIED or attempt == TRIES:
                    tracker.save(force=True, code=code)
                    return code
                wait = WAITS[attempt - 1]
                tracker.save(force=True, code="prefetch_retrying", retry_in_seconds=int(wait))
                deps.sleep(wait)
        tracker.finished_bytes += sum(total for _, total in tracker.layers.values())
        tracker.layers.clear()
    tracker.save(force=True, code="prefetch_done", step=len(images), retry_in_seconds=0)
    return "prefetch_done"
