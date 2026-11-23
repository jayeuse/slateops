"""AC-B3 (DEC-0041): actions that need an email refuse with ``email_not_configured``."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies.auth import CurrentIdentity, get_current_identity
from app.core.config import get_settings
from app.core.database import get_db
from app.systems.access.auth import router as auth_routes
from app.systems.access.auth.aggregate_router import router as access_router
from app.systems.access.users import email_setup, invitations_router
from app.systems.access.users import router as users_routes
from app.systems.access.users.models import UserStatus
from app.systems.manage.workspace.models import WorkspaceProfile
from tests.conftest import create_member
from tests.organization_scope_support import scoped_override

REFUSAL = {
    "detail": {
        "code": "email_not_configured",
        "message": (
            "Email is not set up yet. Set it up in Slate Operations settings on the server PC."
        ),
    }
}


@pytest.mark.parametrize(
    ("module", "service", "path", "body"),
    [
        pytest.param(
            users_routes, "invite_user", "/api/users",
            {"email": "person@example.com", "username": "person"}, id="invite",
        ),
        pytest.param(auth_routes, "resend_invitation", "/api/auth/invitations/{id}/resend", {},
                     id="resend"),
        pytest.param(invitations_router, "reconcile_invitation",
                     "/api/auth/invitations/{id}/reconcile", None, id="reconcile"),
    ],
)
def test_ac_b3_an_invitation_without_email_setup_answers_email_not_configured(
    monkeypatch: pytest.MonkeyPatch, module: object, service: str, path: str, body: object
) -> None:
    admin, membership = create_member(
        None, WorkspaceProfile(id=uuid7()), "admin", id=uuid7(), email="admin@example.test",
        username="admin", status=UserStatus.ACTIVE.value,
    )
    monkeypatch.setattr(module, service, Mock(side_effect=email_setup.EmailNotConfigured("x")))
    app = FastAPI()
    app.include_router(access_router, prefix="/api")
    db = Mock(spec=Session)
    db.scalars.return_value.all.return_value = [membership]
    app.dependency_overrides[get_db] = lambda: db
    identity = CurrentIdentity(admin, uuid7(), True, False)
    app.dependency_overrides[get_current_identity] = scoped_override(lambda: identity)

    response = TestClient(app).post(path.format(id=uuid7()), json=body)

    assert response.status_code == 503
    assert response.json() == REFUSAL


def test_ac_b3_a_password_reset_request_without_email_setup_answers_email_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(email_setup, "email_configured", lambda: False)
    monkeypatch.setattr(auth_routes, "require_allowed_source", Mock())
    provider = Mock()
    monkeypatch.setattr(auth_routes, "get_supabase_auth_client", lambda: provider)
    request_recovery = Mock()
    monkeypatch.setattr(auth_routes.provider_actions, "request_recovery", request_recovery)
    app = FastAPI()
    app.include_router(auth_routes.auth_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: Mock(spec=Session)
    origin = get_settings().public_origin

    response = TestClient(app, base_url=origin).post(
        "/api/auth/recovery/request", json={"email": "person@example.com"},
        headers={"Origin": origin},
    )

    assert response.status_code == 503
    assert response.json() == REFUSAL
    request_recovery.assert_not_called()
    assert provider.mock_calls == []
