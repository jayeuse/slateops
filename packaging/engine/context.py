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


def https_get(host: str, path: str, cafile: Path, timeout: float) -> tuple[int, bytes]:
    """GET ``https://<host><path>`` through 127.0.0.1:443 with ``host`` as the TLS server
    name and the Host header, trusting only ``cafile`` (plan 6.2 step 10, F2)."""
    context = ssl.create_default_context(cafile=str(cafile))
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


@dataclass
class Dependencies:
    paths: Paths = field(default_factory=Paths)
    make_runner: Callable[[RunLog], Runner] = Runner
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep
    tls_context: Callable[[], ssl.SSLContext] = ssl.create_default_context
    docker_api: Callable[[Path], DockerApi] = DockerApi
    disk_free: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free
    chown: Callable[[Path, int, int], None] = os.chown
    https_get: Callable[[str, str, Path, float], tuple[int, bytes]] = https_get


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

    @property
    def paths(self) -> Paths:
        return self.deps.paths

    def step(self, number: int, name: str) -> str:
        return f"{self.job}.{number:02d}.{name}"
