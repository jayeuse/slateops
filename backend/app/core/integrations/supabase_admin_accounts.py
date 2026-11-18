"""The first administrator's account, created with its password (DEC-0041).

The installer has no email when it runs, so the first administrator gets a confirmed Auth
account with the password that setup asked for, never an invitation. The account carries
``FIRST_ADMIN_MARKER`` in its ``app_metadata``, so a rerun of the install step finds the
account that an earlier, interrupted run created and gives it the password again. An
account with the same email and no marker belongs to someone else and is never changed.
"""

from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    ProviderUser,
    SupabaseAuthClient,
    SupabaseAuthUnavailable,
    _error_code,
    _json_response,
    _provider_user,
)

FIRST_ADMIN_MARKER = "slateops_first_administrator"
_PAGE = 200
_PAGES = 50


class ProviderEmailTaken(InvalidProviderCredentials):
    """Auth already has an account with this email."""


def create_confirmed_user(client: SupabaseAuthClient, email: str, password: str) -> ProviderUser:
    """A confirmed account with this password; no email is sent."""

    response = client._request(
        "POST",
        "admin/users",
        admin=True,
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {FIRST_ADMIN_MARKER: True},
        },
    )
    code = _error_code(response)
    if response.status_code == 422 and code == "email_exists":
        raise ProviderEmailTaken("Provider email is in use", error_code=code)
    if response.status_code in {400, 409, 422}:
        raise InvalidProviderCredentials("Provider account was refused", error_code=code)
    return _provider_user(_json_response(response))


def find_first_administrator(client: SupabaseAuthClient, email: str) -> ProviderUser | None:
    """The marked account with exactly this email, from an earlier run of the install step."""

    for page in range(1, _PAGES + 1):
        response = client._request(
            "GET",
            "admin/users",
            admin=True,
            params={"filter": email, "page": str(page), "per_page": str(_PAGE)},
        )
        users = _json_response(response).get("users")
        if not isinstance(users, list) or len(users) > _PAGE:
            raise SupabaseAuthUnavailable("Invalid Supabase user list")
        for raw_user in users:
            if not isinstance(raw_user, dict):
                raise SupabaseAuthUnavailable("Invalid Supabase user list")
            user = _provider_user(raw_user)
            if user.email == email and user.app_metadata.get(FIRST_ADMIN_MARKER) is True:
                return user
        if len(users) < _PAGE:
            return None
    raise SupabaseAuthUnavailable("Supabase user search is incomplete")


def set_password(client: SupabaseAuthClient, user: ProviderUser, password: str) -> ProviderUser:
    """Give the marked account the password of this run (and keep it confirmed)."""

    if user.app_metadata.get(FIRST_ADMIN_MARKER) is not True:
        raise InvalidProviderCredentials("Provider account is not the first administrator")
    response = client._request(
        "PUT",
        f"admin/users/{user.id}",
        admin=True,
        json={"password": password, "email_confirm": True},
    )
    if response.status_code in {400, 404, 409, 422}:
        raise InvalidProviderCredentials(
            "Provider account was refused", error_code=_error_code(response)
        )
    return _provider_user(_json_response(response))
