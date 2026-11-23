"""The installer's ``policy_default`` bridge operation (decision H2) on real PostgreSQL.

The bridge session (``tests/backups/bridge_support.py``) is the runtime role with no bound
organization; each test rolls its transaction back.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text
from uuid6 import uuid7

from app.core.database.session import AuditSession
from app.systems.access.users.models import PlatformOperator, User
from app.systems.manage.audit.models import AuditLog
from app.systems.manage.backups.models import BackupPolicy
from app.systems.manage.workspace.models import WorkspaceProfile
from operations import backup_state
from tests.backups.bridge_support import bridge_session

pytestmark = pytest.mark.integration


@pytest.fixture
def bridge_db() -> Iterator[AuditSession]:
    with bridge_session() as db:
        yield db


def _operator_organization(db: AuditSession, timezone: str) -> None:
    """The installation owner's organization, older than any other in the database."""
    owner = User(email=f"owner-{uuid7().hex}@example.test", username=f"owner_{uuid7().hex}",
                 status="active")
    db.add(owner)
    db.flush()
    db.add(PlatformOperator(user_id=owner.id))
    db.flush()
    identity = uuid7()
    db.connection().execute(WorkspaceProfile.__table__.insert().values(
        id=identity, slug=f"test-{identity}", display_name="Harbor Supply", timezone=timezone,
        locale="en-US", owner_user_id=owner.id, created_at=datetime(2000, 1, 1, tzinfo=UTC),
    ))


def _command(db: AuditSession) -> backup_state.Command:
    instance = db.connection().scalar(text("SELECT current_setting('cluster_name')"))
    return backup_state.COMMAND_ADAPTER.validate_json(json.dumps(
        {"op": "policy_default", "installation_id": instance, "project": "harbor-install"}
    ))


def _audit_rows(db: AuditSession, policy: BackupPolicy) -> list[str]:
    return list(db.scalars(select(AuditLog.action).where(
        AuditLog.entity_type == "backup_policies", AuditLog.entity_id == policy.id,
    )))


def test_w5a_3_policy_default_writes_daily_0200_in_the_owner_organization_timezone_once(
    bridge_db: AuditSession,
) -> None:
    _operator_organization(bridge_db, "Asia/Manila")
    command = _command(bridge_db)

    first = backup_state.execute(bridge_db, command)

    policy = bridge_db.scalars(select(BackupPolicy)).one()
    assert first["written"] is True
    assert {key: first["policy"][key] for key in
            ("schedule", "retention_days", "revision", "timezone", "adopted")} == {
        "schedule": "daily", "retention_days": 30, "revision": 1,
        "timezone": "Asia/Manila", "adopted": True,
    }
    assert policy.next_due_at is not None and policy.next_due_at > datetime.now(UTC)
    assert policy.next_due_at.astimezone(ZoneInfo("Asia/Manila")).time() == time(2)
    assert _audit_rows(bridge_db, policy) == ["create"]
    written = (policy.updated_at, policy.next_due_at)

    second = backup_state.execute(bridge_db, command)

    assert second["written"] is False and second["policy"] == first["policy"]
    bridge_db.refresh(policy)
    assert (policy.updated_at, policy.next_due_at, policy.revision) == (*written, 1)
    assert _audit_rows(bridge_db, policy) == ["create"]


def test_w5a_3_policy_default_never_replaces_an_existing_policy(
    bridge_db: AuditSession,
) -> None:
    _operator_organization(bridge_db, "Asia/Manila")
    command = _command(bridge_db)
    chosen = BackupPolicy(installation_id=command.installation_id, timezone="UTC",
                          schedule="disabled", retention_days=7, revision=3)
    bridge_db.add(chosen)
    bridge_db.flush()

    result = backup_state.execute(bridge_db, command)

    assert result["written"] is False
    bridge_db.refresh(chosen)
    assert (chosen.schedule, chosen.retention_days, chosen.revision, chosen.timezone,
            chosen.next_due_at) == ("disabled", 7, 3, "UTC", None)
    assert _audit_rows(bridge_db, chosen) == ["create"]
