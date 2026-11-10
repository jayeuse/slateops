"""Supabase Auth settings on the runner-owned stack (plan steps 4.5 and 4.6).

Each check reads one named variable from the Auth container's environment and compares it here.
The environment also holds provider secrets: never print, log or attach it, and never put it in
an assertion message (SEC-R3; the Security Engineer's C18 rule).

The runner gives these tests no bootstrap connection, so they cannot count the rows of
`auth.audit_log_entries`; QA counts them on development after the change (contract A45).
"""

import json
import os
import re
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import create_app
from app.systems.access.users.models import User

pytest_plugins = ("tests.auth.provider_account_support",)
pytestmark = pytest.mark.integration


def _auth_variable(name: str) -> str | None:
    """One named variable of the runner-owned Auth container, or None when it is unset."""

    try:
        manifest = json.loads(
            Path(os.environ["SLATEOPS_TEST_DATABASE_MANIFEST"]).read_text(encoding="utf-8")
        )
        auth_id = manifest["ownership"]["service_ids"]["auth"]
    except (OSError, KeyError, TypeError, ValueError):
        pytest.fail("Owned Supabase Auth runtime manifest is unavailable", pytrace=False)
    if not isinstance(auth_id, str) or re.fullmatch(r"[a-f0-9]{12,64}", auth_id) is None:
        pytest.fail("Owned Supabase Auth container identity is invalid", pytrace=False)
    try:
        inspected = subprocess.run(
            ["docker", "inspect", auth_id, "--format", "{{json .Config.Env}}"],
            check=False, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.fail("Owned Supabase Auth configuration could not be inspected", pytrace=False)
    if inspected.returncode != 0:
        pytest.fail("Owned Supabase Auth configuration could not be inspected", pytrace=False)
    try:
        entries = json.loads(inspected.stdout)
    except ValueError:
        pytest.fail("Owned Supabase Auth configuration is unreadable", pytrace=False)
    prefix = f"{name}="
    values = [entry[len(prefix):] for entry in entries if entry.startswith(prefix)]
    return values[0] if len(values) == 1 else None


def _sign_ins(owner, user_id: UUID) -> int:
    with owner.connect() as connection:
        count: int = connection.scalar(
            text(
                "SELECT count(*) FROM public.security_events "
                "WHERE event_type = 'identity.sign_in' AND outcome = 'success' "
                "AND subject_id = :user"
            ),
            {"user": user_id},
        )
    return count


def test_auth_keeps_its_audit_events_out_of_the_database_and_sign_in_works_a45(
    provider_account,
) -> None:
    email, password, provider_id, local_id, owner = provider_account
    if _auth_variable("GOTRUE_AUDIT_LOG_DISABLE_POSTGRES") != "true":
        pytest.fail("Auth must set GOTRUE_AUDIT_LOG_DISABLE_POSTGRES to true", pytrace=False)

    settings = get_settings()
    with Session(owner) as db:
        user = db.get_one(User, local_id)
        user.supabase_user_id = provider_id
        db.commit()
    browser = TestClient(create_app(), base_url=settings.public_origin)
    browser.headers["Origin"] = settings.public_origin
    try:
        for _round in range(2):
            login = browser.post("/api/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200, "Real Supabase email login must succeed"
            logout = browser.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": browser.cookies.get("slateops_csrf") or ""},
            )
            assert logout.status_code == 204, "Logout must end the session"

        # Slate Operations keeps its own record of each sign-in.
        assert _sign_ins(owner, local_id) == 2
    finally:
        browser.close()
        with owner.begin() as connection:
            connection.execute(
                text("DELETE FROM public.security_events WHERE subject_id = :user "
                     "OR actor_id = :user"),
                {"user": local_id},
            )
