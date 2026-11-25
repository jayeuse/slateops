"""Closing the runs that a restored database copy left open (owner, PR 122)."""

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.manage.backups.models import BackupRun


def close(db: Session, instance: str, marker: dict[str, Any], completed: datetime) -> None:
    """Owner, PR 122: a backup copies the database while its own run says running, so the
    restored copy keeps that run, and any earlier restore's, running for ever. At adoption the
    source installation's running run is the backup that made this snapshot: it finished, so it
    gets the snapshot and succeeds at the restore's time. Every other running run of an earlier
    installation was stopped by the restore. A queued run never claimed stays as it is (the
    claim check needs a claim for any other state)."""
    manifest = marker.get("manifest_sha256")
    restored = False
    runs = db.scalars(
        select(BackupRun)
        .where(BackupRun.state == "running", BackupRun.installation_id != instance)
        .order_by(BackupRun.started_at.desc())
    ).all()
    for run in runs:
        run.finished_at = completed
        if (
            not restored
            and run.installation_id == marker["source_installation_id"]
            and isinstance(manifest, str)
            and re.fullmatch(r"[0-9a-f]{64}", manifest)
        ):
            restored = True
            run.state = "succeeded"
            run.snapshot_id = str(marker["snapshot_id"])
            run.manifest_sha256 = manifest
            run.verified_at = completed
            run.reconciled_at = completed
        else:
            run.state = "interrupted"
            run.failure_code = "backup_interrupted"
    db.flush()
