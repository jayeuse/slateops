"""The installer report ``/var/lib/slateops/report.json`` (plan 10.2): safe values only.

Sections this task fills: ``versions`` (Windows part, WSL, kernel) with a capped list of
change ``events``, ``time_sync`` (the offset that ``prepare`` measured) and ``disk``
(``log-bundle``). Memory samples (W10b) and ready times (install, boot) are added by the
slices that measure them.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from engine.core import Paths, private_dir, write_private

EVENT_LIMIT = 200


def load(paths: Paths) -> dict[str, Any]:
    try:
        data = json.loads(paths.report.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update(paths: Paths, mutate: Callable[[dict[str, Any]], None]) -> None:
    private_dir(paths.state)
    descriptor = os.open(paths.state / "report.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        data = load(paths)
        mutate(data)
        write_private(paths.report, (json.dumps(data, indent=2, sort_keys=True) + "\n").encode())
    finally:
        os.close(descriptor)


def record_versions(paths: Paths, now: datetime, versions: dict[str, str]) -> None:
    """Keep the current versions; add an event for each change (plan 10.2, 7.4 rule 4).
    ``status`` is polled, so the file is written only when a version changed."""
    current = load(paths).get("versions")
    if isinstance(current, dict) and all(current.get(k) == v for k, v in versions.items()):
        return

    def mutate(data: dict[str, Any]) -> None:
        current = data.setdefault("versions", {})
        events = data.setdefault("events", [])
        for name, value in versions.items():
            if current.get(name) != value:
                events.append(
                    {
                        "at": now.isoformat(),
                        "kind": f"{name}_changed",
                        "from": current.get(name),
                        "to": value,
                    }
                )
                current[name] = value
        del events[:-EVENT_LIMIT]

    update(paths, mutate)


def record(paths: Paths, section: str, values: dict[str, Any]) -> None:
    update(paths, lambda data: data.__setitem__(section, values))
