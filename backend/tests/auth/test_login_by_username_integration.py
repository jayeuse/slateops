"""AC-U1 (REQ-0024 owner addition 6): sign in with the username, against the real Auth."""

from collections.abc import Iterator
from secrets import token_urlsafe
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.integrations.supabase_admin_accounts import create_confirmed_user
from app.core.integrations.supabase_auth import get_supabase_auth_client
from app.main import create_app
from app.systems.access.identity.models import IdentityRateLimitBucket, IdentitySession
from app.systems.access.identity.rate_limits import login_fingerprint, rate_limit_fingerprint
from app.systems.access.users.models import User
from tests.auth.session_policy_support import _local_account

pytestmark = pytest.mark.integration
SOURCE = "198.51.100.61"
UNKNOWN = "nobody_" + uuid4().hex[:12]


@pytest.fixture
def account() -> Iterator[SimpleNamespace]:
    """A real confirmed Auth account bound to an active local member with a username."""
    email = f"username-{uuid4().hex}@example.test"
    password = token_urlsafe(24)
    client = get_supabase_auth_client()
    provider = create_confirmed_user(client, email, password)
    local = _local_account(email)
    try:
        local_id, owner = next(local)
        with Session(owner) as db:
            user = db.get(User, local_id)
            assert user is not None
            user.supabase_user_id = provider.id
            username = user.username
            db.commit()
        settings = get_settings()
        browser = TestClient(
            create_app(), base_url=settings.public_origin, client=(SOURCE, 50000),
            raise_server_exceptions=False,
        )
        browser.headers["Origin"] = settings.public_origin
        yield SimpleNamespace(
            email=email, password=password, username=username, owner=owner, id=local_id,
            browser=browser,
        )
        browser.close()
        buckets = [
            rate_limit_fingerprint("login-source", SOURCE, None),
            *(rate_limit_fingerprint("login-account", name, None) for name in (email, UNKNOWN)),
            *(login_fingerprint(name, SOURCE) for name in (email, UNKNOWN)),
        ]
        with Session(owner) as db:
            db.execute(delete(IdentityRateLimitBucket).where(
                IdentityRateLimitBucket.fingerprint.in_(buckets)
            ))
            db.commit()
    finally:
        for _ in local:  # the local account's own cleanup
            pass
        client.admin_delete_user(provider.id)


def _budget(world: SimpleNamespace, name: str) -> int | None:
    with Session(world.owner) as db:
        row = db.get(IdentityRateLimitBucket, rate_limit_fingerprint("login-account", name, None))
        return None if row is None else row.attempt_count


def _sign_in(world: SimpleNamespace, name: str, password: str) -> Response:
    return world.browser.post("/api/auth/login", json={"email": name, "password": password})


def test_ac_u1_a_username_signs_in_and_an_unknown_one_is_refused_like_a_wrong_password(
    account: SimpleNamespace,
) -> None:
    wrong = _sign_in(account, account.username.upper(), "not-the-password")
    unknown = _sign_in(account, UNKNOWN, account.password)

    assert (wrong.status_code, unknown.status_code) == (401, 401)
    assert wrong.json()["detail"] == unknown.json()["detail"] == (
        "Invalid authentication credentials"
    )
    assert wrong.headers.get_list("set-cookie") == unknown.headers.get_list("set-cookie") == []
    # The username's failure counts against the account's email budget, not its own.
    assert (_budget(account, account.email), _budget(account, account.username)) == (1, None)

    signed_in = _sign_in(account, account.username, account.password)

    assert signed_in.status_code == 200
    assert signed_in.json() == {"authenticated": True, "setup_required": False}
    with Session(account.owner) as db:
        assert db.scalar(select(IdentitySession.id).where(
            IdentitySession.user_id == account.id, IdentitySession.revoked_at.is_(None),
        )) is not None
    assert _budget(account, account.email) is None  # a success clears the account budget
