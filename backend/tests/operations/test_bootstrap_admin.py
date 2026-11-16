import io
import json
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from uuid6 import uuid7

from app.core.config import Settings
from app.systems.access.users.models import UserRole
from app.systems.access.users.schemas import InvitationCreate
from operations import bootstrap_admin as bootstrap


@pytest.mark.parametrize("existing_profile,admin_count", [(False, 0), (True, 0), (False, 1)])
def test_bootstrap_invites_once_and_recovers_the_exact_pending_reservation(
    monkeypatch, existing_profile, admin_count
) -> None:
    member = UserRole.MEMBER.value
    admin = UserRole.ADMIN.value
    invitation = InvitationCreate(email="admin@example.test", username="first-admin")
    profile = SimpleNamespace(
        id=uuid7(),
        role=admin if existing_profile else member,
        status="pending",
        email=invitation.email,
        username=invitation.username,
        is_deleted=False,
        invitation_sent_at=None,
        provider_invitation_operation_id=uuid7(),
        invitation_accepted_at=None,
    )
    database = MagicMock()
    database.__enter__.return_value = database
    existing = profile if existing_profile else None
    org = SimpleNamespace(id=uuid7(), slug="slateops")
    database.scalar.side_effect = (
        [None, None, existing, existing, org, profile, None] if existing_profile else
        [None, None, None, None, None, None, admin_count, profile, None]
    )
    database.scalars.return_value.all.return_value = [profile] if existing_profile else []
    monkeypatch.setattr(bootstrap, "AuditSession", lambda _: database)
    monkeypatch.setattr(bootstrap, "get_engine", lambda: object())
    invite = Mock(return_value=org)
    monkeypatch.setattr(bootstrap, "provision", invite)
    reconcile = Mock(return_value=profile)
    monkeypatch.setattr(bootstrap, "reconcile_invitation", reconcile, raising=False)
    if admin_count:
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap._provision(Mock(spec=Settings), invitation)
        invite.assert_not_called()
        reconcile.assert_not_called()
    elif existing_profile:
        result = bootstrap._provision(Mock(spec=Settings), invitation)
        assert result == bootstrap.BootstrapResult(
            user_id=profile.id,
            email=profile.email,
            username=profile.username,
            status=profile.status,
            org_id=org.id,
            slug=org.slug,
        )
        invite.assert_called_once_with(database, name="Slate Operations", slug="slateops",
                                       invitation=invitation, provider_user_id=None)
        reconcile.assert_not_called()
    else:
        result = bootstrap._provision(Mock(spec=Settings), invitation)
        assert result == bootstrap.BootstrapResult(
            user_id=profile.id,
            email=profile.email,
            username=profile.username,
            status=profile.status,
            org_id=org.id,
            slug=org.slug,
        )
        assert invite.call_args.kwargs["invitation"].role == UserRole.ADMIN
        assert invite.call_args.kwargs["provider_user_id"] is None
    assert profile.role == (admin if existing_profile else member)
    assert profile.status == "pending"
    if not existing_profile and not admin_count:
        # Bootstrap now commits the first operator after the durable invitation reservation.
        database.commit.assert_called_once()


def test_bootstrap_requires_explicit_confirmation_outside_local_environments() -> None:
    settings = SimpleNamespace(environment="production")

    with pytest.raises(bootstrap.BootstrapError, match="--confirm"):
        bootstrap._validate_confirmation(settings, False)

    bootstrap._validate_confirmation(settings, True)


class _NoTerminal(io.StringIO):
    """Standard input of a one-shot container: any prompt or terminal check fails."""

    def read(self, *_args: object) -> str:
        raise AssertionError("bootstrap read standard input")

    readline = read

    def isatty(self) -> bool:
        raise AssertionError("bootstrap checked for a terminal")


ADMIN_EMAIL = "owner.person@harbor.example"
ADMIN_USERNAME = "owner_person"


@pytest.fixture
def engine_job(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """The engine's step 11 container: env values, no terminal, provider and database stubbed."""
    monkeypatch.setenv("SLATEOPS_ENV_SOURCE", "process")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_USERNAME", ADMIN_USERNAME)
    monkeypatch.setenv("SLATEOPS_RUN_ID", "install-20261116T175200Z-a1b2c3")
    monkeypatch.setattr(bootstrap.sys, "stdin", _NoTerminal())
    monkeypatch.setattr(bootstrap, "get_settings", lambda: SimpleNamespace(
        environment="production", database_url="postgresql+psycopg://slateops_runtime@db/x",
    ))
    monkeypatch.setattr(bootstrap, "instance_target_for_process", lambda *_args: None)
    monkeypatch.setattr(bootstrap, "assert_provider_instance", lambda *_args, **_kwargs: None)
    calls: list[dict[str, object]] = []
    return calls


def _result(status: str) -> bootstrap.BootstrapResult:
    return bootstrap.BootstrapResult(
        uuid7(), ADMIN_EMAIL, ADMIN_USERNAME, status, uuid7(), "harbor-supply"
    )


@pytest.mark.parametrize(("status", "expected"), [
    pytest.param("pending", {"result": "sent"}, id="invitation-sent"),
    pytest.param("active", {"result": "already_active"}, id="already-active"),
])
def test_w5a_1_w5a_4_engine_job_runs_without_a_terminal_and_prints_only_safe_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    engine_job: list[dict[str, object]], status: str, expected: dict[str, str],
) -> None:
    result = _result(status)
    monkeypatch.setattr(bootstrap, "_provision", lambda _settings, invitation, **kwargs: (
        engine_job.append({"invitation": invitation, **kwargs}) or result
    ))

    bootstrap.main(["--confirm", "--name", "Harbor Supply", "--slug", "harbor-supply", "--json"])

    (call,) = engine_job
    assert call["invitation"] == InvitationCreate(email=ADMIN_EMAIL, username=ADMIN_USERNAME)
    assert (call["name"], call["slug"], call["provider_user_id"]) == (
        "Harbor Supply", "harbor-supply", None
    )
    output = capsys.readouterr()
    assert output.out.splitlines() == [json.dumps(expected, separators=(",", ":"))]
    for private in (ADMIN_EMAIL, ADMIN_USERNAME, "owner.person", str(result.user_id)):
        assert private not in output.out + output.err
    assert "install-20261116T175200Z-a1b2c3 bootstrap info " + expected["result"] in output.err


@pytest.mark.parametrize(("error", "exit_code", "code"), [
    pytest.param(lambda: bootstrap.BootstrapError("Organization bootstrap identity does not match"),
                 2, "bootstrap_refused", id="refused"),
    pytest.param(lambda: bootstrap.BootstrapFailure("Unable to finalize administrator profile"),
                 3, "bootstrap_failed", id="finalize-failed"),
    pytest.param(lambda: RuntimeError(f"provider said no to {ADMIN_EMAIL}"),
                 3, "bootstrap_failed", id="unexpected"),
])
def test_w5a_4_engine_job_failure_prints_a_safe_code_and_exit_meaning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    engine_job: list[dict[str, object]], error: Callable[[], Exception], exit_code: int,
    code: str,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> bootstrap.BootstrapResult:
        raise error()

    monkeypatch.setattr(bootstrap, "_provision", fail)

    with pytest.raises(SystemExit) as exited:
        bootstrap.main(["--confirm", "--name", "Harbor Supply", "--slug", "harbor-supply",
                        "--json"])

    assert exited.value.code == exit_code
    output = capsys.readouterr()
    assert output.out.splitlines() == [json.dumps({"code": code}, separators=(",", ":"))]
    assert ADMIN_EMAIL not in output.out + output.err


def test_operator_output_without_json_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    engine_job: list[dict[str, object]],
) -> None:
    result = _result("pending")
    monkeypatch.setattr(bootstrap, "_provision", lambda *_args, **_kwargs: result)

    bootstrap.main(["--confirm", "--name", "Harbor Supply", "--slug", "harbor-supply"])

    output = capsys.readouterr()
    assert output.out.splitlines() == [
        f"user_id={result.user_id} email={ADMIN_EMAIL} username={ADMIN_USERNAME} "
        f"status=pending org_id={result.org_id} slug=harbor-supply",
        "Complete the emailed invitation to activate the administrator account.",
    ]
    assert output.err == ""


@pytest.mark.parametrize(("arguments", "time_zone"), [
    pytest.param(["--time-zone", "Asia/Manila"], "Asia/Manila", id="pc-time-zone"),
    pytest.param([], "UTC", id="no-option-unchanged"),
])
def test_d4_time_zone_option_reaches_the_organization_create_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    engine_job: list[dict[str, object]], arguments: list[str], time_zone: str,
) -> None:
    result = _result("pending")
    monkeypatch.setattr(bootstrap, "_provision", lambda _settings, invitation, **kwargs: (
        engine_job.append({"invitation": invitation, **kwargs}) or result
    ))

    bootstrap.main(["--confirm", "--name", "Harbor Supply", "--slug", "harbor-supply", "--json",
                    *arguments])

    (call,) = engine_job
    assert call["time_zone"] == time_zone
    assert capsys.readouterr().out.splitlines() == ['{"result":"sent"}']


@pytest.mark.parametrize("time_zone", [
    pytest.param("Mars/Olympus_Mons", id="unknown"),
    pytest.param("../../etc/passwd", id="path"),
    pytest.param("", id="empty"),
    pytest.param("America/" + "A" * 60, id="longer-than-the-column"),
])
def test_d4_unknown_time_zone_is_refused_before_any_provisioning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    engine_job: list[dict[str, object]], time_zone: str,
) -> None:
    monkeypatch.setattr(bootstrap, "_provision", lambda *_args, **_kwargs: pytest.fail(
        "an unknown time zone reached provisioning"
    ))

    with pytest.raises(SystemExit) as exited:
        bootstrap.main(["--confirm", "--name", "Harbor Supply", "--slug", "harbor-supply",
                        "--json", "--time-zone", time_zone])

    assert exited.value.code == 2
    assert capsys.readouterr().out.splitlines() == ['{"code":"bootstrap_refused"}']


@pytest.mark.parametrize(("name", "slug"), [
    pytest.param("  ", "harbor-supply", id="blank-name"),
    pytest.param("N" * 201, "harbor-supply", id="name-too-long"),
    pytest.param("Harbor Supply", "Harbor Supply", id="slug-with-capitals-and-space"),
    pytest.param("Harbor Supply", "-harbor", id="slug-leading-hyphen"),
    pytest.param("Harbor Supply", "h" * 201, id="slug-too-long"),
])
def test_n5_invalid_name_or_slug_is_refused_before_any_provisioning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    engine_job: list[dict[str, object]], name: str, slug: str,
) -> None:
    monkeypatch.setattr(bootstrap, "_provision", lambda *_args, **_kwargs: pytest.fail(
        "an invalid name or slug reached provisioning"
    ))

    with pytest.raises(SystemExit) as exited:
        bootstrap.main(["--confirm", "--name", name, "--slug", slug, "--json"])

    assert exited.value.code == 2
    assert capsys.readouterr().out.splitlines() == ['{"code":"bootstrap_refused"}']


@pytest.mark.parametrize(("arguments", "stdout", "stderr_has"), [
    pytest.param(["--json", "--confirm", "--unknown"], ['{"code":"bootstrap_refused"}'],
                 "bootstrap error bootstrap_refused", id="json-mode"),
    pytest.param(["--confirm", "--unknown"], [], "error: unrecognized arguments: --unknown",
                 id="operator-mode-unchanged"),
])
def test_n6_argument_errors_follow_the_output_mode(
    capsys: pytest.CaptureFixture[str], engine_job: list[dict[str, object]],
    arguments: list[str], stdout: list[str], stderr_has: str,
) -> None:
    with pytest.raises(SystemExit) as exited:
        bootstrap.main(arguments)

    assert exited.value.code == 2
    output = capsys.readouterr()
    assert output.out.splitlines() == stdout
    assert stderr_has in output.err
