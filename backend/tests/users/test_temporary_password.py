"""AC-T1 (DEC-0042): the temporary password rule and the server's choice.

``tests/access/test_temporary_password_integration.py`` owns the journey: admission, owner
and self refusals, session end, the forced change (AC-T2) and the audit (AC-T3).
"""

import json
from uuid import UUID

import httpx
import pytest

from app.core.integrations.supabase_admin_accounts import set_password_by_administrator
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    ProviderUserNotFound,
    SupabaseAuthClient,
    SupabaseAuthUnavailable,
)
from app.systems.access.users.temporary_password import (
    check_temporary_password,
    generate_temporary_password,
)
from app.systems.manage.workspace.models import PlatformSettings
from app.systems.manage.workspace.security_policy import PasswordPolicyViolation
from tests.auth.provider_jwt_support import provider_settings

LOOK_ALIKE = set("0O1lI")


def _policy(minimum: int = 12, mixed: bool = True, number: bool = True) -> PlatformSettings:
    return PlatformSettings(
        password_min_length=minimum,
        password_require_mixed_case=mixed,
        password_require_number=number,
    )


@pytest.mark.parametrize("minimum", [12, 16, 40, 72])
def test_ac_t1_a_server_chosen_password_meets_the_policy_and_the_provider_limit(
    minimum: int,
) -> None:
    policy = _policy(minimum)
    chosen = {generate_temporary_password(policy) for _ in range(50)}

    assert len(chosen) == 50
    for password in chosen:
        check_temporary_password(policy, password)
        assert len(password) == max(16, minimum)
        assert not LOOK_ALIKE & set(password)
        assert password.isascii() and password.isalnum()


def test_ac_t1_no_password_can_meet_a_policy_longer_than_the_provider_limit() -> None:
    with pytest.raises(PasswordPolicyViolation, match="72"):
        generate_temporary_password(_policy(73))


@pytest.mark.parametrize(
    ("password", "message"),
    [
        pytest.param("Aa1" + "é" * 35, "at most 72 bytes", id="38-characters-73-bytes"),
        pytest.param("Short1a", "at least 12 characters", id="policy-length"),
        pytest.param("alllowercase123", "uppercase and lowercase", id="policy-mixed-case"),
    ],
)
def test_ac_t1_an_administrator_password_outside_the_rule_is_refused(
    password: str, message: str
) -> None:
    with pytest.raises(PasswordPolicyViolation, match=message):
        check_temporary_password(_policy(), password)


def test_ac_t1_a_password_of_exactly_72_bytes_is_accepted() -> None:
    check_temporary_password(_policy(), "Aa1" + "é" * 34 + "x")


PROVIDER_ID = UUID("0192f0c1-0000-7000-8000-000000000001")


def _provider(status: int, body: object, seen: list[httpx.Request]) -> SupabaseAuthClient:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return SupabaseAuthClient(provider_settings(), transport=httpx.MockTransport(respond))


def test_ac_t1_the_provider_gets_the_password_by_the_admin_update_and_no_email() -> None:
    seen: list[httpx.Request] = []

    user = set_password_by_administrator(
        _provider(200, {"id": str(PROVIDER_ID)}, seen), PROVIDER_ID, "Temporary-Pass-1"
    )

    assert user.id == PROVIDER_ID
    assert [(request.method, request.url.path) for request in seen] == [
        ("PUT", f"/auth/v1/admin/users/{PROVIDER_ID}")
    ]
    assert json.loads(seen[0].content) == {"password": "Temporary-Pass-1"}
    assert seen[0].headers["apikey"] == "sb_secret_test"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        pytest.param(404, {}, ProviderUserNotFound, id="gone"),
        pytest.param(422, {"error_code": "weak_password"}, InvalidProviderCredentials,
                     id="refused"),
        pytest.param(200, {"id": "0192f0c1-0000-7000-8000-000000000009"},
                     SupabaseAuthUnavailable, id="another-user"),
        pytest.param(500, {}, SupabaseAuthUnavailable, id="outage"),
    ],
)
def test_ac_t1_a_refused_or_unexpected_password_update_fails_closed(
    status: int, body: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        set_password_by_administrator(_provider(status, body, []), PROVIDER_ID, "x" * 16)
