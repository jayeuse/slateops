"""Durable sign-out follows immediate local denial."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.systems.access.identity.models import IdentitySession
from app.systems.access.identity.session_revocation import revoke_session


def test_provider_outage_persists_bounded_signout_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.integrations.supabase_auth import SupabaseAuthUnavailable
    from app.systems.access.identity.provider_signout import attempt_provider_signout

    now = datetime.now(UTC)
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        "app.systems.access.identity.provider_signout.get_settings",
        lambda: SimpleNamespace(supabase_session_encryption_key=SecretStr(key)),
    )
    session = IdentitySession(
        id=uuid4(),
        user_id=uuid4(),
        provider_user_id=uuid4(),
        provider_session_id=uuid4(),
        provider_refresh_token_encrypted=Fernet(key).encrypt(b"provider-refresh").decode(),
        refresh_token_digest="x" * 64,
        csrf_token_digest="y" * 64,
        expires_at=now + timedelta(days=1),
        revoked_at=now,
        provider_signout_pending_at=now,
        provider_signout_next_attempt_at=now,
        provider_signout_attempts=0,
    )
    db = Mock(spec=Session)
    db.get.return_value = session
    db.execute.return_value.scalar_one.return_value = True
    client = Mock()
    client.refresh.side_effect = SupabaseAuthUnavailable("offline")

    assert not attempt_provider_signout(db, session.id, client, now=now)
    assert session.provider_signout_attempts == 1
    assert session.provider_signout_next_attempt_at == now + timedelta(minutes=1)
    db.commit.assert_called_once()

    for attempt in range(2, 6):
        next_time = session.provider_signout_next_attempt_at
        assert next_time is not None
        assert not attempt_provider_signout(db, session.id, client, now=next_time)
        assert session.provider_signout_attempts == attempt
    assert session.provider_signout_next_attempt_at is None
    assert session.provider_signout_pending_at == now


def test_revocation_marks_provider_signout_due_without_waiting_for_network() -> None:
    now = datetime.now(UTC)
    user_id = uuid4()
    session = IdentitySession(
        id=uuid4(),
        user_id=user_id,
        provider_user_id=uuid4(),
        provider_session_id=uuid4(),
        provider_refresh_token_encrypted="encrypted-refresh",
        refresh_token_digest="x" * 64,
        csrf_token_digest="y" * 64,
        expires_at=now + timedelta(days=1),
        provider_signout_attempts=0,
    )
    db = Mock(spec=Session)
    db.get.return_value = session

    assert revoke_session(db, session.id, user_id, now=now)
    assert session.revoked_at == now
    assert session.provider_signout_pending_at == now
    assert session.provider_signout_next_attempt_at == now
    assert session.provider_signout_attempts == 0


@pytest.mark.parametrize(
    ("step", "error_code", "row_after_refusal", "completes"),
    [
        # Auth will never issue a token from this session again (contract 5.2 item 4).
        ("refresh", "session_expired", True, True),
        ("refresh", None, False, True),
        ("refresh", "refresh_token_not_found", False, True),
        # Every other refusal keeps the retry path while the provider row remains.
        ("refresh", None, True, False),
        ("refresh", "refresh_token_not_found", True, False),
        ("refresh", "validation_failed", True, False),
        ("refresh", "user_banned", True, False),
        ("refresh", "session_expired_soon", True, False),
        ("outage", None, True, False),
        # Only a refusal of the refresh qualifies, never one of the later steps (C9).
        ("verify", None, True, False),
        ("sign_out", "session_expired", True, False),
    ],
)
def test_signout_completes_only_when_auth_can_issue_no_token_a46e(
    monkeypatch: pytest.MonkeyPatch, step, error_code, row_after_refusal, completes
) -> None:
    from app.core.integrations.supabase_auth import (
        InvalidProviderCredentials,
        InvalidProviderToken,
        ProviderAccessIdentity,
        ProviderTokens,
        SupabaseAuthUnavailable,
    )
    from app.systems.access.identity.provider_signout import attempt_provider_signout

    now = datetime.now(UTC)
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        "app.systems.access.identity.provider_signout.get_settings",
        lambda: SimpleNamespace(supabase_session_encryption_key=SecretStr(key)),
    )
    provider_user, provider_session = uuid4(), uuid4()
    session = IdentitySession(
        id=uuid4(),
        user_id=uuid4(),
        provider_user_id=provider_user,
        provider_session_id=provider_session,
        provider_refresh_token_encrypted=Fernet(key).encrypt(b"provider-refresh").decode(),
        refresh_token_digest="x" * 64,
        csrf_token_digest="y" * 64,
        expires_at=now + timedelta(days=1),
        revoked_at=now,
        provider_signout_pending_at=now,
        provider_signout_next_attempt_at=now,
        provider_signout_attempts=0,
    )
    db = Mock(spec=Session)
    db.get.return_value = session
    # The row exists before the attempt; the second read is the re-check after a refusal.
    db.execute.return_value.scalar_one.side_effect = [True, row_after_refusal, True]
    client = Mock()
    client.refresh.return_value = ProviderTokens("access", "refresh", provider_user, 600)
    client.verify_access_token.return_value = ProviderAccessIdentity(
        provider_user, provider_session, now, now + timedelta(minutes=10)
    )
    refusal = InvalidProviderCredentials("refused", error_code=error_code)
    if step == "refresh":
        client.refresh.side_effect = refusal
    elif step == "outage":
        client.refresh.side_effect = SupabaseAuthUnavailable("offline")
    elif step == "verify":
        client.verify_access_token.side_effect = InvalidProviderToken("expired")
    else:
        client.sign_out.side_effect = refusal

    assert attempt_provider_signout(db, session.id, client, now=now) is completes

    if completes:
        assert session.provider_signout_completed_at == now
        assert (session.provider_signout_pending_at, session.provider_signout_attempts) == (
            None, 0
        )
    else:
        assert session.provider_signout_completed_at is None
        assert (session.provider_signout_pending_at, session.provider_signout_attempts) == (
            now, 1
        )
    db.commit.assert_called_once()
