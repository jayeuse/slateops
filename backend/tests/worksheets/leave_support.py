"""The real user-administration routes over a sheet world, with captured security outcomes."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid6 import uuid7

import app.systems.access.users.account_operations as account_operations
from app.common.dependencies.auth import CurrentIdentity, get_current_identity, get_current_user
from app.core.database import get_db
from app.core.database.organization_scope import scope_session
from app.main import create_app
from app.systems.access.users.models import User
from app.systems.manage.audit.context import set_audit_actor
from app.systems.openview.worksheets.models import Worksheet
from tests.conftest import create_member, create_organization
from tests.organization_scope_support import scoped_override
from tests.worksheets.support import SheetWorld, add_sheet, sheet_world


@dataclass
class LeaveWorld:
    db: Session
    sheets: SheetWorld
    opening: list[Worksheet]
    actor: list[User]
    events: list[dict[str, Any]] = field(default_factory=list)
    _client: TestClient | None = None

    def client(self, user: User) -> TestClient:
        self.actor[:] = [user]
        set_audit_actor(self.db, user.id)
        assert self._client is not None
        return self._client

    def share_another_organization(self) -> UUID:
        """Give the owner a second organization, so removal and disable stay local."""

        home = self.sheets.sheet.org_id
        other = create_organization(self.db)
        create_member(self.db, other, "member", user=self.sheets.owner)
        scope_session(self.db, home)
        self.db.commit()
        return other.id


@pytest.fixture
def leave_world(
    integration_db: Session, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[LeaveWorld]:
    db = integration_db
    sheets = sheet_world(db)
    # Two sheets open at a leave: the record sheet and a module sheet. A deleted sheet and a
    # sheet on a deleted record stay as they are and are not counted.
    on_module = add_sheet(db, sheets.owner, module=sheets.module)
    deleted = add_sheet(db, sheets.owner, record=sheets.record)
    deleted.is_deleted, deleted.deleted_at = True, deleted.created_at
    db.flush()
    world = LeaveWorld(db, sheets, [sheets.sheet, on_module], [])

    def capture(_db: Session, event_type: str, outcome: Any, operation_id: UUID,
                actor_id: UUID, target_id: UUID, reason: str | None = None,
                **extra: Any) -> None:
        world.events.append({"event_type": event_type, "subject_id": target_id, **extra})

    monkeypatch.setattr(account_operations, "_record_outcome", capture)
    db.commit()  # release the setup savepoint; a refused request rolls back its own work
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = scoped_override(lambda: world.actor[0])
    app.dependency_overrides[get_current_identity] = scoped_override(
        lambda: CurrentIdentity(world.actor[0], uuid7(), False, False)
    )
    with TestClient(app) as client:
        world._client = client
        yield world
    app.dependency_overrides.clear()
