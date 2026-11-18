"""The installer's default backup policy (decision H2): daily at 02:00, written once."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.users.models import PlatformOperator
from app.systems.manage.backups.models import BackupPolicy
from app.systems.manage.backups.service import BackupStateError, future_due
from app.systems.manage.workspace.models import PlatformSettings, WorkspaceProfile

DEFAULT_SCHEDULE = "daily"
DEFAULT_RETENTION_DAYS = 30


def _owner_organization_timezone(db: Session) -> str:
    """The bridge binds no organization: use the installation owner's first organization."""
    timezone = db.scalar(
        select(WorkspaceProfile.timezone)
        .join(PlatformOperator, PlatformOperator.user_id == WorkspaceProfile.owner_user_id)
        .where(PlatformOperator.is_deleted.is_(False))
        .order_by(WorkspaceProfile.created_at, WorkspaceProfile.id)
        .limit(1)
    )
    return timezone or "UTC"


def write_default_policy(db: Session, instance: str, *, now: datetime | None = None) -> bool:
    """Add the default policy only when no policy row exists; never change one. Never commits.

    The installation settings lock comes first, in the same order as ``lock_policy``, so a
    concurrent first policy write waits instead of racing the singleton.
    """
    if db.scalar(select(PlatformSettings.id).where(
        PlatformSettings.singleton_key.is_(True)
    ).with_for_update()) is None:
        raise BackupStateError("backup_unavailable")
    if db.scalar(select(BackupPolicy.id).limit(1)) is not None:
        return False
    timezone = _owner_organization_timezone(db)
    db.add(BackupPolicy(
        installation_id=instance,
        timezone=timezone,
        schedule=DEFAULT_SCHEDULE,
        retention_days=DEFAULT_RETENTION_DAYS,
        revision=1,
        next_due_at=future_due(DEFAULT_SCHEDULE, timezone, now or utc_now()),
    ))
    db.flush()
    return True
