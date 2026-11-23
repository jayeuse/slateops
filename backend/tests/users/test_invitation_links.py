"""AC-L1 and AC-L2 (DEC-0042): an invitation link to copy, with no email.

The provider wire (``admin/generate_link``), the link's URL and the HTTP contract of the two
routes that return it. ``tests/auth/test_invitation_link_integration.py`` owns the journey
on the real provider: the link completes, a new link or a cancel ends the old one, and a
link stops after 24 hours.
"""

import json
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies.auth import CurrentIdentity, get_current_identity
from app.core.base_model import utc_now
from app.core.config import get_settings
from app.core.database import get_db
from app.core.integrations.supabase_admin_accounts import generate_invitation_link
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    SupabaseAuthClient,
    SupabaseAuthUnavailable,
)
from app.systems.access.auth import router as auth_routes
from app.systems.access.auth.aggregate_router import router as access_router
from app.systems.access.users import invitation_links, invitations_router
from app.systems.access.users import router as users_routes
from app.systems.access.users.coordination import (
    InvitationConflict,
    InvitationError,
    InvitationNotFound,
)
from app.systems.access.users.models import UserStatus
from app.systems.manage.workspace.models import WorkspaceProfile
from tests.auth.provider_jwt_support import provider_settings
from tests.conftest import create_member
from tests.organization_scope_support import scoped_override

PROVIDER_ID = UUID("0192f0c1-0000-7000-8000-000000000001")
HASH = "a" * 56
EMAIL = "person@example.test"


def _provider(status: int, body: object, seen: list[httpx.Request]) -> SupabaseAuthClient:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return SupabaseAuthClient(provider_settings(), transport=httpx.MockTransport(respond))


def test_ac_l1_generate_link_asks_auth_for_an_invite_link_and_sends_no_email() -> None:
    seen: list[httpx.Request] = []
    body = {"id": str(PROVIDER_ID), "email": EMAIL, "hashed_token": HASH,
            "verification_type": "invite", "action_link": "http://auth/verify?token=x"}

    link = generate_invitation_link(_provider(200, body, seen), EMAIL)

    assert (link.user.id, link.hashed_token) == (PROVIDER_ID, HASH)
    assert [(request.method, request.url.path) for request in seen] == [
        ("POST", "/auth/v1/admin/generate_link")
    ]
    assert json.loads(seen[0].content) == {"type": "invite", "email": EMAIL}
    assert seen[0].headers["apikey"] == "sb_secret_test"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        pytest.param(422, {"error_code": "email_exists"}, InvalidProviderCredentials,
                     id="confirmed-account"),
        pytest.param(200, {"id": str(PROVIDER_ID), "hashed_token": HASH,
                           "verification_type": "signup"}, SupabaseAuthUnavailable,
                     id="wrong-type"),
        pytest.param(200, {"id": str(PROVIDER_ID), "hashed_token": "A" * 56,
                           "verification_type": "invite"}, SupabaseAuthUnavailable,
                     id="hash-not-lower-hex"),
        pytest.param(200, {"id": str(PROVIDER_ID), "hashed_token": "a" * 55,
                           "verification_type": "invite"}, SupabaseAuthUnavailable,
                     id="hash-too-short"),
        pytest.param(500, {}, SupabaseAuthUnavailable, id="outage"),
    ],
)
def test_ac_l1_generate_link_fails_closed_on_a_refused_or_unexpected_answer(
    status: int, body: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        generate_invitation_link(_provider(status, body, []), EMAIL)


def test_ac_l1_the_link_lands_on_the_invitation_completion_page() -> None:
    assert invitation_links.invitation_url(HASH) == (
        f"{get_settings().public_origin}/auth/setup#token_hash={HASH}&type=invite"
    )


def _admin_client(db: Mock) -> TestClient:
    admin, membership = create_member(
        None, WorkspaceProfile(id=uuid7()), "admin", id=uuid7(), email="admin@example.test",
        username="admin", status=UserStatus.ACTIVE.value,
    )
    db.scalars.return_value.all.return_value = [membership]
    app = FastAPI()
    app.include_router(access_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    identity = CurrentIdentity(admin, uuid7(), True, False)
    app.dependency_overrides[get_current_identity] = scoped_override(lambda: identity)
    return TestClient(app)


def _pending_person() -> tuple[object, object]:
    person, membership = create_member(
        None, WorkspaceProfile(id=uuid7()), id=uuid7(), email=EMAIL, username="person",
        status=UserStatus.PENDING.value,
    )
    for row in (person, membership):
        row.created_at = row.updated_at = utc_now()
        row.is_deleted = False
    return person, membership


@pytest.mark.parametrize("path", ["/api/users", "/api/auth/invitations"])
def test_ac_l1_invite_by_link_returns_the_link_once_and_uncached(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    person, membership = _pending_person()
    url = invitation_links.invitation_url(HASH)
    invite = Mock(return_value=(person, url))
    email_invite = Mock()
    module = users_routes if path == "/api/users" else auth_routes
    monkeypatch.setattr(module, "invite_with_link", invite)
    monkeypatch.setattr(module, "invite_user", email_invite)
    monkeypatch.setattr(module, "bound_organization", lambda db: membership.org_id)
    db = Mock(spec=Session)
    client = _admin_client(db)
    db.scalars.return_value.one.return_value = membership

    response = client.post(path, json={"email": EMAIL, "username": "person", "delivery": "link"})

    assert response.status_code == 201, response.text
    assert response.json()["delivery"] == "link"
    assert response.json()["invitation_url"] == url
    assert response.headers["Cache-Control"] == "no-store"
    assert invite.call_args.args[1].delivery == "link"
    email_invite.assert_not_called()


def test_ac_l1_email_invitation_keeps_its_answer_without_a_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person, membership = _pending_person()
    invite = Mock(return_value=person)
    monkeypatch.setattr(users_routes, "invite_user", invite)
    monkeypatch.setattr(users_routes, "invite_with_link", Mock())
    monkeypatch.setattr(users_routes, "bound_organization", lambda db: membership.org_id)
    db = Mock(spec=Session)
    client = _admin_client(db)
    db.scalars.return_value.one.return_value = membership

    response = client.post("/api/users", json={"email": EMAIL, "username": "person"})

    assert response.status_code == 201, response.text
    assert (response.json()["delivery"], response.json()["invitation_url"]) == ("email", None)
    users_routes.invite_with_link.assert_not_called()


def test_ac_l1_an_unknown_delivery_is_a_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    invite = Mock()
    monkeypatch.setattr(users_routes, "invite_user", invite)
    client = _admin_client(Mock(spec=Session))

    response = client.post(
        "/api/users", json={"email": EMAIL, "username": "person", "delivery": "sms"}
    )

    assert response.status_code == 422
    invite.assert_not_called()


def test_ac_l2_a_new_link_for_a_pending_person_is_returned_uncached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    person, membership = _pending_person()
    url = invitation_links.invitation_url(HASH)
    renew = Mock(return_value=(person, url))
    monkeypatch.setattr(invitations_router, "new_invitation_link", renew)
    monkeypatch.setattr(invitations_router, "bound_organization", lambda db: membership.org_id)
    db = Mock(spec=Session)
    client = _admin_client(db)
    db.scalars.return_value.one.return_value = membership

    response = client.post(f"/api/auth/invitations/{person.id}/link", json={})

    assert response.status_code == 200, response.text
    assert response.json()["delivery"] == "link"
    assert response.json()["invitation_url"] == url
    assert response.json()["user"]["id"] == str(person.id)
    assert response.headers["Cache-Control"] == "no-store"
    assert renew.call_args.args[1] == person.id


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        pytest.param(InvitationNotFound("x"), 404, "Invitation not found", id="none-pending"),
        pytest.param(InvitationConflict("x"), 409, "Invitation is not pending", id="in-app"),
        pytest.param(InvitationError("x"), 503, "Unable to create invitation link",
                     id="unavailable"),
    ],
)
def test_ac_l2_a_new_link_maps_its_refusals(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: int, detail: str
) -> None:
    monkeypatch.setattr(invitations_router, "new_invitation_link", Mock(side_effect=error))
    client = _admin_client(Mock(spec=Session))

    response = client.post(f"/api/auth/invitations/{uuid7()}/link", json={})

    assert response.status_code == status
    assert response.json() == {"detail": detail}
