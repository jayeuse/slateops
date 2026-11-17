"""What a job gets: its paths, run log, runner, redactor, clock and the outside clients.

``Dependencies`` holds the parts that tests replace (paths, runner, clock, sleep, TLS
context, Docker API client); ``Context`` adds the run.
"""

from __future__ import annotations

import http.client
import os
import shutil
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from engine.core import Paths
from engine.docker_api import DockerApi
from engine.logs import RunLog, utc_now
from engine.redaction import Redactor
from engine.runner import Runner

RESPONSE_LIMIT = 64 * 1024


def tls_client_context(cafile: Path | None = None) -> ssl.SSLContext:
    """A verifying client context that refuses TLS older than 1.2."""
    context = ssl.create_default_context(cafile=None if cafile is None else str(cafile))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def https_get(host: str, path: str, cafile: Path, timeout: float) -> tuple[int, bytes]:
    """GET ``https://<host><path>`` through 127.0.0.1:443 with ``host`` as the TLS server
    name and the Host header, trusting only ``cafile`` (plan 6.2 step 10, F2)."""
    context = tls_client_context(cafile)
    raw = socket.create_connection(("127.0.0.1", 443), timeout=timeout)
    try:
        wrapped = context.wrap_socket(raw, server_hostname=host)
    except BaseException:
        raw.close()
        raise
    connection = http.client.HTTPConnection(host, 443, timeout=timeout)
    connection.sock = wrapped
    try:
        connection.request("GET", path, headers={"Host": host, "Connection": "close"})
        response = connection.getresponse()
        return response.status, response.read(RESPONSE_LIMIT)
    finally:
        connection.close()


def served_certificate(host: str, cafile: Path, timeout: float) -> bytes:
    """The DER of the leaf that 127.0.0.1:443 serves for ``host``, checked against ``cafile``
    (TASK-0089: a renewal reloads Caddy when it serves another leaf than ``server.crt``)."""
    context = tls_client_context(cafile)
    raw = socket.create_connection(("127.0.0.1", 443), timeout=timeout)
    with context.wrap_socket(raw, server_hostname=host) as connection:
        return connection.getpeercert(binary_form=True) or b""


@dataclass
class Dependencies:
    paths: Paths = field(default_factory=Paths)
    make_runner: Callable[[RunLog], Runner] = Runner
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep
    tls_context: Callable[[], ssl.SSLContext] = tls_client_context
    docker_api: Callable[[Path], DockerApi] = DockerApi
    disk_free: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free
    chown: Callable[[Path, int, int], None] = os.chown
    https_get: Callable[[str, str, Path, float], tuple[int, bytes]] = https_get
    served_certificate: Callable[[str, Path, float], bytes] = served_certificate


@dataclass
class Context:
    deps: Dependencies
    job: str
    run_id: str
    log: RunLog
    runner: Runner
    redactor: Redactor
    started: datetime
    stdin: BinaryIO | None = None
    # Values for this run's result only, never written to a file (the recovery key, 8.3).
    outputs: dict[str, str] = field(default_factory=dict)
    # False when the job did nothing worth a log (an idle tick): its run folder is removed.
    keep_log: bool = True

    @property
    def paths(self) -> Paths:
        return self.deps.paths

    def step(self, number: int, name: str) -> str:
        return f"{self.job}.{number:02d}.{name}"
