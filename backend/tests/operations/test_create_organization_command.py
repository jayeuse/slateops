from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from uuid6 import uuid7

from operations import create_organization as command


@pytest.fixture
def provision(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Run `main` up to `provision` with no settings file, provider or database."""
    database = MagicMock()
    database.__enter__.return_value = database
    monkeypatch.setattr(
        command,
        "get_settings",
        lambda: SimpleNamespace(environment="development", database_url="unused"),
    )
    monkeypatch.setattr(command, "environment_inputs", lambda _path: {})
    monkeypatch.setattr(command, "assert_provider_instance", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "AuditSession", lambda _engine: database)
    monkeypatch.setattr(command, "get_engine", lambda: object())
    created = Mock(return_value=SimpleNamespace(id=uuid7(), slug="x-org"))
    monkeypatch.setattr(command, "provision", created)
    return created


@pytest.mark.parametrize(
    ("email", "username"),
    [
        ("first.admin@x.test", "first_admin"),
        ("..Jo-Ann+ops..@x.test", "jo-ann_ops"),
        (f"{'A' * 120}@x.test", "a" * 100),
    ],
)
def test_email_without_username_invites_the_derived_username(
    provision: Mock, email: str, username: str
) -> None:
    command.main(["--name", "X", "--slug", "x-org", "--email", email])

    invitation = provision.call_args.kwargs["invitation"]
    assert invitation.username == username


@pytest.mark.parametrize("email", ["ab@x.test", "+.+@x.test"])
def test_email_without_a_usable_username_asks_for_one(
    provision: Mock, email: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        command.main(["--name", "X", "--slug", "x-org", "--email", email])

    assert stopped.value.code == 2
    assert "Pass --username: the email gives no usable username" in capsys.readouterr().err
    provision.assert_not_called()


def test_explicit_username_is_invited_unchanged(provision: Mock) -> None:
    command.main(
        ["--name", "X", "--slug", "x-org", "--email", "first.admin@x.test", "--username", "chosen"]
    )

    invitation = provision.call_args.kwargs["invitation"]
    assert invitation.username == "chosen"
