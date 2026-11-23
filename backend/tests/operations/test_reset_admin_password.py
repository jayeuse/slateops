"""AC-B8 (TASK-0097, DEC-0042): the first administrator's password from the server PC.

``operations/reset_admin_password.py`` runs in a one-shot server-image container that the
engine job ``admin-password`` starts; the password arrives on standard input only.
"""

import io
import json
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.config import get_settings
from app.core.integrations.supabase_auth import (
    InvalidProviderCredentials,
    get_supabase_auth_client,
)
from app.systems.access.identity.models import IdentitySession
from app.systems.access.users.models import User
from app.systems.access.users.schemas import InvitationCreate
from app.systems.manage.audit.models import SecurityEvent
from operations import bootstrap_admin as bootstrap
from operations import reset_admin_password as reset
from tests.access.user_admin_support import add_session

ADMIN_EMAIL = "Owner.Person@Harbor.example"
ADMIN_USERNAME = "owner_person"
PASSWORD = "Front desk " + 'pa$$ "q" #x'


class _Stdin(io.StringIO):
    def isatty(self) -> bool:
        return False


@pytest.fixture
def job(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The engine's container: env values, the password on stdin, the checks stubbed."""
    monkeypatch.setenv("SLATEOPS_ENV_SOURCE", "process")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_USERNAME", ADMIN_USERNAME)
    monkeypatch.setattr(reset.sys, "stdin", _Stdin(PASSWORD + "\n"))
    monkeypatch.setattr(reset, "get_settings", lambda: SimpleNamespace(
        environment="production", database_url="postgresql+psycopg://slateops_runtime@db/x",
    ))
    monkeypatch.setattr(reset, "instance_target_for_process", lambda *_args: None)
    monkeypatch.setattr(reset, "assert_provider_instance", lambda *_args, **_kwargs: None)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        reset, "reset_admin_password",
        lambda email, password: calls.append((email, password)) or uuid7(),
    )
    return calls


ARGUMENTS = ["--confirm", "--json", "--password-stdin"]


def test_ac_b8_the_stored_admin_gets_the_password_from_standard_input(
    capsys: pytest.CaptureFixture[str], job: list[tuple[str, str]]
) -> None:
    reset.main(ARGUMENTS)

    assert job == [("owner.person@harbor.example", PASSWORD)]
    output = capsys.readouterr()
    assert output.out.splitlines() == ['{"result":"reset"}']
    for private in (PASSWORD, ADMIN_EMAIL.lower(), ADMIN_USERNAME):
        assert private not in output.out + output.err


@pytest.mark.parametrize(("stdin", "arguments"), [
    pytest.param("eleven-char\n", ARGUMENTS, id="short-password"),
    pytest.param("x" * 73 + "\n", ARGUMENTS, id="longer-than-72-bytes"),
    pytest.param("one\ntwo-three-four\n", ARGUMENTS, id="two-lines"),
    pytest.param(PASSWORD + "\n", ["--confirm", "--json"], id="no-password-stdin"),
    pytest.param(PASSWORD + "\n", [*ARGUMENTS, "--provider-user-id=x"], id="unknown-option"),
])
def test_ac_b8_bad_input_is_refused_before_any_change(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    job: list[tuple[str, str]], stdin: str, arguments: list[str],
) -> None:
    monkeypatch.setattr(reset.sys, "stdin", _Stdin(stdin))

    with pytest.raises(SystemExit) as exited:
        reset.main(arguments)

    assert exited.value.code == 2
    assert capsys.readouterr().out.splitlines() == ['{"code":"invalid_input"}']
    assert job == []


@pytest.mark.parametrize(("error", "exit_code", "code"), [
    pytest.param(lambda: reset.AdminMissing("no active first administrator"), 2,
                 "admin_missing", id="admin-missing"),
    pytest.param(lambda: RuntimeError(f"provider refused {PASSWORD}"), 3, "reset_failed",
                 id="failed"),
])
def test_ac_b8_a_refusal_or_failure_is_one_safe_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    job: list[tuple[str, str]], error: Callable[[], Exception], exit_code: int, code: str,
) -> None:
    def fail(email: str, password: str) -> None:
        raise error()

    monkeypatch.setattr(reset, "reset_admin_password", fail)

    with pytest.raises(SystemExit) as exited:
        reset.main(ARGUMENTS)

    assert exited.value.code == exit_code
    output = capsys.readouterr()
    assert output.out.splitlines() == [json.dumps({"code": code}, separators=(",", ":"))]
    assert PASSWORD not in output.out + output.err


def test_ac_b8_an_admin_without_the_installer_mark_is_never_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An Auth account that setup did not create (no marker) belongs to someone else."""
    user = SimpleNamespace(id=uuid7(), email="owner@harbor.example", supabase_user_id=uuid7(),
                           status="active", is_deleted=False)
    db = Mock()
    db.__enter__ = Mock(return_value=db)
    db.__exit__ = Mock(return_value=False)
    db.info = {}
    db.scalar.return_value = user
    monkeypatch.setattr(reset, "AuditSession", lambda _engine: db)
    monkeypatch.setattr(reset, "get_engine", lambda: object())
    monkeypatch.setattr(reset, "administered_membership",
                        lambda *_args: SimpleNamespace(org_id=uuid7()))
    monkeypatch.setattr(reset, "is_active_account", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(reset, "scope_session", lambda *_args: None)
    provider = Mock()
    provider.get_admin_user.return_value = SimpleNamespace(
        id=user.supabase_user_id, email=user.email, app_metadata={},
    )
    monkeypatch.setattr(reset, "get_supabase_auth_client", lambda: provider)
    set_password = Mock()
    monkeypatch.setattr(reset.admin_accounts, "set_password", set_password)
    revoke = Mock()
    monkeypatch.setattr(reset, "revoke_user_sessions", revoke)

    with pytest.raises(reset.AdminMissing):
        reset.reset_admin_password(user.email, PASSWORD)

    set_password.assert_not_called()
    revoke.assert_not_called()
    db.commit.assert_not_called()



def test_ac_b8_the_reset_clears_the_must_choose_a_new_password_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEC-0042: the admin chose this password at the server PC, so no forced change follows."""
    from app.core.integrations.supabase_admin_accounts import FIRST_ADMIN_MARKER

    user = SimpleNamespace(
        id=uuid7(), email="owner@harbor.example", supabase_user_id=uuid7(), status="active",
        is_deleted=False, password_change_required_at=datetime(2026, 11, 23, tzinfo=UTC),
    )
    db = Mock()
    db.__enter__ = Mock(return_value=db)
    db.__exit__ = Mock(return_value=False)
    db.info = {}
    db.scalar.return_value = user
    seen_at_commit: list[object] = []
    db.commit.side_effect = lambda: seen_at_commit.append(user.password_change_required_at)
    monkeypatch.setattr(reset, "AuditSession", lambda _engine: db)
    monkeypatch.setattr(reset, "get_engine", lambda: object())
    monkeypatch.setattr(reset, "administered_membership",
                        lambda *_args: SimpleNamespace(org_id=uuid7()))
    monkeypatch.setattr(reset, "is_active_account", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(reset, "scope_session", lambda *_args: None)
    provider = Mock()
    provider.get_admin_user.return_value = SimpleNamespace(
        id=user.supabase_user_id, email=user.email, app_metadata={FIRST_ADMIN_MARKER: True},
    )
    monkeypatch.setattr(reset, "get_supabase_auth_client", lambda: provider)
    monkeypatch.setattr(reset.admin_accounts, "set_password", Mock())
    monkeypatch.setattr(reset, "revoke_user_sessions", Mock())
    monkeypatch.setattr(reset, "append_security_event", Mock())

    reset.reset_admin_password(user.email, PASSWORD)

    assert seen_at_commit == [None]  # cleared in the same transaction, before its commit

# The real Auth account and database (disposable stack) ------------------------------------

pytest_plugins = ("tests.users.test_first_administrator_integration",)


@pytest.mark.integration
def test_ac_b8_the_admin_signs_in_with_the_new_password_and_old_sessions_end(
    empty_installation: tuple[Engine, list[str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, invited = empty_installation
    monkeypatch.setattr(reset, "get_engine", bootstrap.get_engine)  # the runtime engine
    invitation = InvitationCreate(
        email=f"reset-{uuid7().hex}@example.test", username=f"reset_{uuid7().hex[-12:]}"
    )
    invited.append(invitation.email)
    first_password = "Setup pass " + uuid7().hex[-8:]
    new_password = "Reset pass " + uuid7().hex[-8:]
    client = get_supabase_auth_client()
    provider_id = None
    try:
        provider_id, _ = bootstrap._password_account(invitation, first_password)
        first = bootstrap._provision(get_settings(), invitation, provider_user_id=provider_id,
                                     name="Harbor Supply", slug=f"b8-{uuid7().hex[-12:]}")
        with Session(owner) as db:
            user = db.get(User, first.user_id)
            assert user is not None
            session_id = add_session(db, user).id
            user.password_change_required_at = datetime.now(UTC)  # a temporary password
            db.commit()

        reset.reset_admin_password(invitation.email, new_password)

        assert client.password_grant(invitation.email, new_password).access_token
        with pytest.raises(InvalidProviderCredentials):
            client.password_grant(invitation.email, first_password)
        with Session(owner) as db:
            session = db.get(IdentitySession, session_id)
            assert session is not None and session.revoked_at is not None
            cleared = db.get(User, first.user_id)
            assert cleared is not None and cleared.password_change_required_at is None
            assert db.scalar(select(func.count()).select_from(SecurityEvent).where(
                SecurityEvent.subject_id == first.user_id,
                SecurityEvent.event_type == "identity.local_admin_password_reset",
                SecurityEvent.org_id == first.org_id,
            )) == 1
            db.execute(delete(IdentitySession).where(IdentitySession.id == session_id))
            db.commit()
    finally:
        if provider_id is not None:
            client.admin_delete_user(provider_id)
