"""The engine job contract (plan 3.2 rule 1, 6.1): paths, errors, run IDs, request input.

Exit codes follow the backup runner: 0 done, 2 refused (input or a precondition), 3 failed.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Plan 10.1 item 1: <kind>-<UTC time>-<6 random characters>. The Windows side makes it.
RUN_KINDS = (
    "install",
    "update",
    "uninstall",
    "maintenance",
    "report",
    "boot",
    "backup",
    "package-night",
    "renewal",
)
RUN_ID = re.compile(r"(" + "|".join(RUN_KINDS) + r")-[0-9]{8}T[0-9]{6}Z-[a-z0-9]{6}\Z")
_NUMBER = r"(?:0|[1-9][0-9]{0,3})"
VERSION = re.compile(rf"{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:-rc\.[1-9][0-9]{{0,3}})?\Z")
INPUT_LIMIT = 64 * 1024
REFUSED, FAILED = 2, 3


class JobError(Exception):
    """A safe code; ``exit_code`` 2 for a refusal, 3 for a failure."""

    def __init__(self, code: str, exit_code: int, **fields: int | str | bool) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code
        self.fields = fields


def refused(code: str, **fields: int | str | bool) -> JobError:
    return JobError(code, REFUSED, **fields)


def failed(code: str, **fields: int | str | bool) -> JobError:
    return JobError(code, FAILED, **fields)


@dataclass(frozen=True)
class Paths:
    """Every location the engine reads or writes; tests point them at a temporary folder."""

    etc: Path = Path("/etc/slateops")
    state: Path = Path("/var/lib/slateops")
    logs: Path = Path("/var/log/slateops")
    run: Path = Path("/run/slateops")
    engine_home: Path = Path(__file__).resolve().parent
    engine_command: Path = Path("/usr/local/bin/slateops-engine")
    image_record: Path = Path("/usr/share/slateops/linux-image.json")
    proc: Path = Path("/proc")
    passwd: Path = Path("/etc/passwd")
    docker_socket: Path = Path("/run/docker.sock")
    extra: Mapping[str, Path] = field(default_factory=dict)

    @property
    def staging(self) -> Path:
        return self.state / "staging"

    @property
    def releases(self) -> Path:
        return self.state / "release"

    @property
    def report(self) -> Path:
        return self.state / "report.json"

    @property
    def prefetch_state(self) -> Path:
        return self.state / "prefetch.json"

    @property
    def answers(self) -> Path:
        return self.state / "install-answers.json"

    @property
    def staged_smtp(self) -> Path:
        return self.etc / "new" / "smtp.env"

    @property
    def engine_lock(self) -> Path:
        return self.run / "engine.lock"

    @property
    def prefetch_lock(self) -> Path:
        return self.run / "prefetch.lock"


def engine_version(paths: Paths) -> str:
    """The bundle's version (``engine/VERSION``, written by the bundle build)."""
    try:
        text = (paths.engine_home / "VERSION").read_text().strip()
    except OSError:
        return "0.0.0"
    return text if VERSION.match(text) else "0.0.0"


def run_kind(run_id: str) -> str:
    match = RUN_ID.match(run_id)
    if match is None:
        raise refused("invalid_input")
    return match.group(1)


Validator = Callable[[Any], bool]


def read_request(
    data: bytes, keys: Mapping[str, Validator], required: frozenset[str]
) -> dict[str, Any]:
    """One JSON object within the limit, with only known keys, each valid."""
    if len(data) > INPUT_LIMIT:
        raise refused("invalid_input")
    try:
        request = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise refused("invalid_input") from error
    if not isinstance(request, dict) or not required <= request.keys() <= keys.keys():
        raise refused("invalid_input")
    if not all(keys[name](value) for name, value in request.items()):
        raise refused("invalid_input")
    if not isinstance(request.get("run_id"), str) or not RUN_ID.match(request["run_id"]):
        raise refused("invalid_input")
    return request


def is_run_id(value: Any) -> bool:
    return isinstance(value, str) and RUN_ID.match(value) is not None


def is_version(value: Any) -> bool:
    return isinstance(value, str) and VERSION.match(value) is not None


def private_dir(path: Path) -> Path:
    """Create ``path`` (and missing parents) as root-only folders; refuse a symlink."""
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise failed("unsafe_path")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise failed("unsafe_path")
    return path


def write_private(path: Path, data: bytes) -> None:
    """Write ``data`` to a new temporary file (0600), fsync, then replace ``path``."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def held_lock(path: Path, busy_code: str) -> Iterator[None]:
    """Hold an exclusive ``flock`` on ``path`` or refuse with ``busy_code``."""
    private_dir(path.parent)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise refused(busy_code) from error
        yield
    finally:
        os.close(descriptor)


def lock_state(path: Path, proc: Path) -> bool | None:
    """Read ``/proc/locks`` for a FLOCK on ``path`` without taking it (status stays read-only).

    False when ``path`` does not exist (no job has run); None when ``/proc/locks`` cannot
    be read, so a caller can treat the state as unknown."""
    try:
        status = path.stat()
    except OSError:
        return False
    try:
        lines = (proc / "locks").read_text().splitlines()
    except OSError:
        return None
    # "1: FLOCK  ADVISORY  WRITE 1234 08:01:5678 0 EOF"; the device is major:minor in hex.
    wanted = f"{os.major(status.st_dev):02x}:{os.minor(status.st_dev):02x}:{status.st_ino}"
    return any(
        len(words) >= 6 and words[1] == "FLOCK" and words[5] == wanted
        for words in (line.split() for line in lines)
    )


def lock_is_held(path: Path, proc: Path) -> bool:
    return lock_state(path, proc) is True
