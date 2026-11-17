"""What a job gets: its paths, run log, runner, redactor, clock and the outside clients.

``Dependencies`` holds the parts that tests replace (paths, runner, clock, sleep, TLS
context, Docker API client); ``Context`` adds the run.
"""

from __future__ import annotations

import shutil
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


@dataclass
class Dependencies:
    paths: Paths = field(default_factory=Paths)
    make_runner: Callable[[RunLog], Runner] = Runner
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep
    tls_context: Callable[[], ssl.SSLContext] = ssl.create_default_context
    docker_api: Callable[[Path], DockerApi] = DockerApi
    disk_free: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free


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
