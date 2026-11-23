"""AC-B1 (DEC-0041): the Auth admin calls for the first administrator's own password."""

import json
from uuid import uuid4

import httpx
import pytest

from app.core.integrations.supabase_admin_accounts import (
    FIRST_ADMIN_MARKER,
    ProviderEmailTaken,
    create_confirmed_user,
    find_first_administrator,
    set_password,
)
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    ProviderUser,
    SupabaseAuthClient,
)
from tests.auth.provider_jwt_support import provider_settings

EMAIL = "owner@frontdesk.test"
PASSWORD = "Front desk pass 2026"


def _user(user_id: str, email: str = EMAIL, **metadata: object) -> dict[str, object]:
    return {
        "id": user_id, "email": email, "app_metadata": metadata,
        "email_confirmed_at": "2026-11-18T08:00:00Z", "banned_until": None,
    }  # fmt: skip


def test_ac_b1_the_account_is_created_confirmed_with_the_password_and_the_marker() -> None:
    seen: list[httpx.Request] = []
    user_id = str(uuid4())

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_user(user_id, **{FIRST_ADMIN_MARKER: True}))

    client = SupabaseAuthClient(provider_settings(), transport=httpx.MockTransport(respond))

    created = create_confirmed_user(client, EMAIL, PASSWORD)

    [request] = seen
    assert (request.method, request.url.path) == ("POST", "/auth/v1/admin/users")
    assert request.headers["apikey"] == "sb_secret_test"
    assert json.loads(request.content) == {
        "email": EMAIL, "password": PASSWORD, "email_confirm": True,
        "app_metadata": {FIRST_ADMIN_MARKER: True},
    }  # fmt: skip
    assert (str(created.id), created.email, created.email_confirmed_at is not None) == (
        user_id, EMAIL, True
    )


@pytest.mark.parametrize(
    ("status", "code", "error"),
    [
        pytest.param(422, "email_exists", ProviderEmailTaken, id="email-taken"),
        pytest.param(422, "weak_password", InvalidProviderCredentials, id="weak-password"),
        pytest.param(400, "email_address_invalid", InvalidProviderCredentials, id="bad-email"),
    ],
)
def test_ac_b1_an_auth_refusal_keeps_its_class_and_never_its_text(
    status: int, code: str, error: type[Exception]
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error_code": code, "msg": f"no {PASSWORD}"})

    client = SupabaseAuthClient(provider_settings(), transport=httpx.MockTransport(refuse))

    with pytest.raises(error) as raised:
        create_confirmed_user(client, EMAIL, PASSWORD)

    assert PASSWORD not in str(raised.value)
    if error is InvalidProviderCredentials:
        assert not isinstance(raised.value, ProviderEmailTaken)


def test_ac_b1_a_rerun_finds_only_the_marked_account_and_sets_its_password() -> None:
    marked, other = str(uuid4()), str(uuid4())
    seen: list[tuple[str, str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET":
            assert request.url.params["filter"] == EMAIL
            return httpx.Response(200, json={"users": [
                _user(other, "owner@frontdesk.test.other"),
                _user(other, EMAIL),  # same email, no marker: not ours
                _user(marked, EMAIL, **{FIRST_ADMIN_MARKER: True}),
            ]})  # fmt: skip
        return httpx.Response(200, json=_user(marked, **{FIRST_ADMIN_MARKER: True}))

    client = SupabaseAuthClient(provider_settings(), transport=httpx.MockTransport(respond))

    found = find_first_administrator(client, EMAIL)
    assert found is not None and str(found.id) == marked
    updated = set_password(client, found, PASSWORD)

    assert str(updated.id) == marked
    assert seen[-1] == (
        "PUT", f"/auth/v1/admin/users/{marked}", {"password": PASSWORD, "email_confirm": True}
    )


def test_ac_b1_an_account_of_someone_else_is_not_found() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"users": [_user(str(uuid4()), EMAIL)]})

    client = SupabaseAuthClient(provider_settings(), transport=httpx.MockTransport(respond))

    assert find_first_administrator(client, EMAIL) is None


def test_ac_b1_set_password_refuses_an_account_without_the_marker() -> None:
    client = SupabaseAuthClient(
        provider_settings(), transport=httpx.MockTransport(lambda _request: pytest.fail("sent"))
    )
    stranger = ProviderUser(uuid4(), None, EMAIL, {})

    with pytest.raises(InvalidProviderCredentials):
        set_password(client, stranger, PASSWORD)
