"""The install journal ``/var/lib/slateops/install-journal.json`` (plan 6.1; W5b-2).

Each step writes its completion here (0600, written to a new file, fsynced, then renamed)
before the next step starts; a rerun skips completed steps and repeats only the step that
did not complete. The journal also keeps the values that a rerun must not choose again:
the release version, the app subnet (W5b-7), the Compose project and our two image names.
It holds no secret and no personal value.
"""

from __future__ import annotations

import json
from typing import Any

from engine.core import Paths, private_dir, write_private

SCHEMA = 1


def load(paths: Paths) -> dict[str, Any] | None:
    try:
        data = json.loads(paths.journal.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"schema": None}
    return data if isinstance(data, dict) else {"schema": None}


def new(version: str, run_id: str, at: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "version": version, "started_at": at, "runs": [run_id], "steps": {}}


def save(paths: Paths, state: dict[str, Any]) -> None:
    private_dir(paths.state)
    write_private(paths.journal, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())


def done(state: dict[str, Any], number: int) -> bool:
    steps = state.get("steps")
    return isinstance(steps, dict) and f"{number:02d}" in steps


def mark(paths: Paths, state: dict[str, Any], number: int, name: str, at: str) -> None:
    state.setdefault("steps", {})[f"{number:02d}"] = {"name": name, "done_at": at}
    save(paths, state)
