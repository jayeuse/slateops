"""Route 20 on committed rows: the export snapshot is its own connection (spec D9.1).

The snapshot cannot see a test's savepoint, so these journeys use the committed sheet of
``committed_support`` (an editor with an Edit share and a text column) and a real runtime
session for each request. The person has a live application session for the recheck.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import CurrentIdentity, get_current_identity, get_current_user
from app.core.base_model import utc_now
from app.core.database import get_db
from app.core.database.session import AuditSession
from app.systems.access.identity.models import IdentitySession
from app.systems.access.users.models import User
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.manage.audit.models import SecurityEvent
from tests.conftest import guarded_create_engine
from tests.organization_scope_support import scoped_override
from tests.route_app_support import route_app
from tests.worksheets.committed_support import CommittedSheet
from tests.worksheets.committed_support import committed_sheet as committed_sheet

EXPORT_EVENT = "worksheets.export.authorized"


@dataclass
class ExportJourney:
    world: CommittedSheet
    application: FastAPI
    runtime: Engine

    def _person(self, user_id: UUID) -> tuple[User, UUID]:
        with Session(self.world.owner_engine, expire_on_commit=False) as setup:
            now = utc_now()
            session = IdentitySession(
                user_id=user_id, refresh_token_digest=uuid7().hex * 2,
                csrf_token_digest=uuid7().hex * 2, created_at=now, refreshed_at=now,
                expires_at=now + timedelta(hours=1),
            )
            setup.add(session)
            setup.commit()
            user = setup.get(User, user_id)
            assert user is not None
            setup.expunge(user)
            return user, session.id

    def export(self, user_id: UUID, format: str) -> Response:
        user, session_id = self._person(user_id)

        def database() -> Iterator[Session]:
            with AuditSession(self.runtime) as db:
                db.info[AUDIT_CONTEXT_KEY] = AuditContext(
                    request_id=uuid7(), request_method="POST", request_path="/api/export",
                )
                yield db

        overrides: dict[Any, Any] = self.application.dependency_overrides
        overrides[get_db] = database
        overrides[get_current_user] = scoped_override(lambda: user)
        overrides[get_current_identity] = scoped_override(
            lambda: CurrentIdentity(user, session_id, False, False)
        )
        with TestClient(self.application) as client:
            return client.post(
                f"/api/worksheets/{self.world.sheet_id}/export", json={"format": format},
            )

    def events(self) -> list[SecurityEvent]:
        with Session(self.world.owner_engine) as db:
            return list(db.scalars(select(SecurityEvent).where(
                SecurityEvent.subject_id == self.world.sheet_id,
                SecurityEvent.event_type == EXPORT_EVENT,
            )))


@pytest.fixture
def journey(committed_sheet: CommittedSheet) -> Iterator[ExportJourney]:
    runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    application = route_app()
    try:
        yield ExportJourney(committed_sheet, application, runtime)
    finally:
        application.dependency_overrides.clear()  # the sheet's cleanup removes the events
        runtime.dispose()
