"""Revocation stays immediate while the real worker removes the exact Auth session."""

from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database.session import get_engine
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    get_supabase_auth_client,
)
from app.main import create_app
from app.systems.access.identity.models import IdentitySession
from app.systems.access.identity.provider_signout_worker import ProviderSignoutWorker
from app.systems.access.users.models import User, UserStatus

pytest_plugins = ("tests.auth.provider_account_support",)
pytestmark = pytest.mark.integration


def test_signout_worker_removes_revoked_provider_session_and_preserves_other_session(
    provider_account,
):
    # Failure inventory: delayed local denial, lost durable work, wrong provider
    # session deleted, or global logout accidentally invalidating the survivor.
    email, password, provider_id, local_id, owner = provider_account
    settings = get_settings()
    with Session(owner) as db:
        user = db.get(User, local_id)
        assert user is not None
        user.supabase_user_id = provider_id
        db.commit()

    current = TestClient(create_app(), base_url=settings.public_origin)
    revoked = TestClient(create_app(), base_url=settings.public_origin)
    try:
        for browser in (current, revoked):
            browser.headers["Origin"] = settings.public_origin
            response = browser.post("/api/auth/login", json={"email": email, "password": password})
            assert response.status_code == 200, "Both independent browser logins must succeed"
        inventory = revoked.get("/api/auth/sessions")
        assert inventory.status_code == 200
        target_id = next(UUID(item["id"]) for item in inventory.json() if item["current"])
        with Session(owner) as db:
            target = db.get(IdentitySession, target_id)
            assert target is not None and target.provider_session_id is not None
            provider_session_id = target.provider_session_id

        csrf = current.cookies.get("slateops_csrf")
        assert csrf is not None, "The active browser must have CSRF protection"
        response = current.delete(f"/api/auth/sessions/{target_id}", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 204
        assert revoked.get("/api/auth/me").status_code == 401
        assert current.get("/api/auth/me").status_code == 200
        with Session(owner) as db:
            target = db.get(IdentitySession, target_id)
            assert target is not None and target.revoked_at is not None
            assert target.provider_signout_pending_at is not None
            assert target.provider_signout_completed_at is None
        with Session(get_engine()) as db:
            assert (
                db.scalar(
                    text("SELECT id FROM auth.sessions WHERE id = :id AND user_id = :user_id"),
                    {"id": provider_session_id, "user_id": provider_id},
                )
                is not None
            ), "Local revocation must persist work before provider cleanup"

        ProviderSignoutWorker(settings).run_once()

        with Session(owner) as db:
            target = db.get(IdentitySession, target_id)
            assert target is not None and target.revoked_at is not None
            assert target.provider_signout_pending_at is None
            assert target.provider_signout_completed_at is not None
        with Session(get_engine()) as db:
            assert (
                db.scalar(
                    text("SELECT id FROM auth.sessions WHERE id = :id AND user_id = :user_id"),
                    {"id": provider_session_id, "user_id": provider_id},
                )
                is None
            ), "The worker must remove the exact revoked Supabase session"
        assert revoked.get("/api/auth/me").status_code == 401
        assert current.get("/api/auth/me").status_code == 200
        refreshed = current.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf})
        assert refreshed.status_code == 200, "A different provider session must survive cleanup"
        assert current.get("/api/auth/me").status_code == 200
    finally:
        current.close()
        revoked.close()


def _provider_session_row(provider_session_id: UUID, provider_id: UUID) -> UUID | None:
    with Session(get_engine()) as db:
        row: UUID | None = db.scalar(
            text("SELECT id FROM auth.sessions WHERE id = :id AND user_id = :user_id"),
            {"id": provider_session_id, "user_id": provider_id},
        )
    return row


def test_a_refused_refresh_signs_the_live_provider_session_out_a46b(provider_account):
    # Before 4.6 a refresh refused by local policy revoked the session and left its provider
    # session live: nothing scheduled the sign-out (contract K88).
    email, password, provider_id, local_id, owner = provider_account
    settings = get_settings()
    with Session(owner) as db:
        db.get_one(User, local_id).supabase_user_id = provider_id
        db.commit()
    browser = TestClient(create_app(), base_url=settings.public_origin)
    browser.headers["Origin"] = settings.public_origin
    try:
        assert browser.post(
            "/api/auth/login", json={"email": email, "password": password}
        ).status_code == 200
        csrf = browser.cookies.get("slateops_csrf")
        assert csrf is not None
        with Session(owner) as db:
            [session] = db.query(IdentitySession).filter_by(user_id=local_id).all()
            session_id, provider_session_id = session.id, session.provider_session_id
            assert provider_session_id is not None
            # Local policy now refuses the account; its provider session stays live.
            db.get_one(User, local_id).status = UserStatus.DISABLED.value
            db.commit()

        refused = browser.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf})

        assert refused.status_code == 401
        with Session(owner) as db:
            session = db.get_one(IdentitySession, session_id)
            assert session.revoked_at is not None
            assert session.provider_signout_pending_at is not None
        assert _provider_session_row(provider_session_id, provider_id) is not None

        ProviderSignoutWorker(settings).run_once()

        with Session(owner) as db:
            session = db.get_one(IdentitySession, session_id)
            assert session.provider_signout_completed_at is not None
            assert session.provider_signout_pending_at is None
        assert _provider_session_row(provider_session_id, provider_id) is None
    finally:
        browser.close()
        with Session(owner) as db:
            db.get_one(User, local_id).status = UserStatus.ACTIVE.value
            db.commit()


def test_auths_error_code_reaches_the_client_through_the_gateway_a46e(record_property):
    # The sign-out rule reads Auth's exact code. Through Envoy (`api-gw`), the body field and
    # the `x-sb-error-code` header are the two carriers; this proves which ones arrive.
    settings = get_settings()
    with httpx.Client(timeout=15) as http:
        response = http.post(
            settings.supabase_url.rstrip("/") + "/auth/v1/token",
            params={"grant_type": "refresh_token"},
            headers={"apikey": settings.supabase_publishable_key.get_secret_value()},
            json={"refresh_token": "a" * 12},
        )
    body = response.json()
    carriers = {
        "body": body.get("error_code") if isinstance(body, dict) else None,
        "header": response.headers.get("x-sb-error-code"),
    }
    record_property("auth_error_code_carriers", repr(carriers))

    assert (response.status_code, carriers) == (
        400, {"body": "refresh_token_not_found", "header": "refresh_token_not_found"}
    )
    with pytest.raises(InvalidProviderCredentials) as refused:
        get_supabase_auth_client().refresh("a" * 12)
    assert refused.value.error_code == "refresh_token_not_found"
