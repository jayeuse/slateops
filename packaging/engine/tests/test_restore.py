"""``restore``: the one-click restore of the newest backup (plan 8.4; owner decision
2026-11-24). The fake world is the update world: the install's first backup is snapshot 1."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from engine import update

from .test_update import SERVICES, Installed

RESTORE = "maintenance-20261124T120000Z-ab12cd"


@pytest.fixture
def machine(tmp_path: Path) -> Installed:
    return Installed(tmp_path)


def _restore(machine: Installed) -> tuple[int, dict[str, Any]]:
    return machine.job("restore", {"run_id": RESTORE})


def _journal(machine: Installed) -> dict[str, Any]:
    found: dict[str, Any] = json.loads(
        (machine.paths.state / "update" / f"{RESTORE}.json").read_text()
    )
    return found


def test_restore_puts_the_newest_backup_back_in_a_new_project(machine: Installed) -> None:
    fake, old = machine.fake, machine.project
    [first] = fake.snapshots
    fake.data[f"{old}_supabase-db-data"] = "damaged"

    code, result = _restore(machine)

    new = f"{old}-r1"
    assert (code, result["code"], result["project"]) == (0, "restored", new)
    # The settings program shows the backup's time (first snapshot: 12:00 at +08:00).
    when = datetime(2026, 11, 17, 4, 0, 0, 500000, tzinfo=UTC).astimezone()
    assert result["backup_time"] == when.strftime("%d %b %Y, %H:%M")
    assert fake.data[f"{new}_supabase-db-data"] == "install-data"
    assert fake.data[f"{old}_supabase-db-data"] == "damaged"  # kept for support
    assert fake.containers.get(old, {}) == {}
    assert set(machine.running(new)) == SERVICES
    assert machine.installation()["project"] == new
    assert machine.env("provider.env")["SLATEOPS_INSTANCE_ID"] == new
    assert json.loads((machine.paths.etc / "backup.json").read_text())["project_name"] == new
    journal = _journal(machine)
    assert (journal["state"], journal["snapshot_id"]) == ("restored", first)


def test_restore_chooses_the_newest_snapshot(machine: Installed) -> None:
    fake = machine.fake
    fake.data[f"{machine.project}_supabase-db-data"] = "later-data"
    fake.snapshots["f" * 64] = {**next(iter(fake.snapshots.values())),
                                "data": dict(fake.data)}  # fmt: skip

    code, _ = _restore(machine)

    assert code == 0
    assert _journal(machine)["snapshot_id"] == "f" * 64
    assert fake.data[f"{machine.project}-r1_supabase-db-data"] == "later-data"


def test_a_restore_refused_by_the_tool_starts_the_old_installation_again(
    machine: Installed,
) -> None:
    fake, old = machine.fake, machine.project
    next(iter(fake.snapshots.values()))["source"] = "another-installation"

    code, result = _restore(machine)

    assert (code, result["code"], result["restore"]) == (3, "restore_failed", "failed")
    assert set(machine.running(old)) == SERVICES
    assert machine.installation()["project"] == old
    assert fake.data[f"{old}_supabase-db-data"] == "install-data"


def test_a_restore_with_no_backup_drive_changes_nothing(machine: Installed) -> None:
    (machine.paths.state / "backup-target.json").unlink()

    code, result = _restore(machine)

    assert (code, result["code"], result["restore"]) == (3, "backup_target_missing", "failed")
    assert set(machine.running(machine.project)) == SERVICES


def test_a_finished_restore_resolves_an_update_that_waits_for_support(
    machine: Installed,
) -> None:
    waiting = {"schema": 1, "run_id": "update-20261117T120000Z-ab12cd", "state": "needs_support",
               "project": machine.project}  # fmt: skip
    folder = machine.paths.state / "update"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{waiting['run_id']}.json").write_text(json.dumps(waiting))
    assert update.needs_support(machine.paths)

    code, _ = _restore(machine)

    assert code == 0
    assert not update.needs_support(machine.paths)
    resolved = json.loads((folder / f"{waiting['run_id']}.json").read_text())
    assert (resolved["state"], resolved["resolved_by"]) == ("resolved", RESTORE)
