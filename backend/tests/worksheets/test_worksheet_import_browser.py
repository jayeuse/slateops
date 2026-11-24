"""Routes 21 and 22 refuse a browser request without the CSRF token or from another origin
(D14 E5). The person signs in through the real login route against the fake provider, so
the cookie session, the token and the origin check are the production ones."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import create_app
from app.systems.access.users.models import User
from app.systems.openview.worksheets import import_router
from tests.fake_provider_support import fake_provider as fake_provider
from tests.fake_provider_support import fake_provider_account as fake_provider_account

pytestmark = pytest.mark.integration
REQUESTS: dict[str, tuple[str, dict[str, Any], dict[str, str]]] = {
    "route 21": ("/api/worksheet-import-files", {"content": b"not a workbook"},
                 {"content-type": "application/octet-stream"}),
    "route 22": ("/api/worksheet-import-matches", {"json": {
        "module_id": str(uuid4()), "field_id": str(uuid4()), "keys": ["Alice"]}}, {}),
}


@pytest.fixture
def browser(fake_provider_account: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(import_router, "append_committed_security_event",
                        lambda *_args, **_kwargs: None)
    email, password, provider_id, actor_id, owner = fake_provider_account
    with Session(owner) as db:
        actor = db.get(User, actor_id)
        assert actor is not None
        actor.supabase_user_id = provider_id
        db.commit()
    settings = get_settings()
    client = TestClient(create_app(), base_url=settings.public_origin,
                        raise_server_exceptions=False)
    client.headers["Origin"] = settings.public_origin
    try:
        login = client.post("/api/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        yield client
    finally:
        client.close()


@pytest.mark.parametrize("route", list(REQUESTS))
def test_a_cookie_request_needs_the_csrf_token_and_the_exact_origin(
    browser: TestClient, route: str,
) -> None:
    path, body, headers = REQUESTS[route]
    token = {"X-CSRF-Token": browser.cookies["slateops_csrf"]}
    assert browser.post(path, **body, headers=headers).status_code == 401  # no token
    other = {**headers, **token, "Origin": "https://elsewhere.example.test"}
    assert browser.post(path, **body, headers=other).status_code == 401
    allowed = browser.post(path, **body, headers={**headers, **token})
    # Past the checks, refused on content: an unreadable file, an unknown module.
    assert allowed.status_code == (422 if route == "route 21" else 404), allowed.text
