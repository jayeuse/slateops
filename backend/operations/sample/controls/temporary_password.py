"""An owned temporary password and its forced change through the UI APIs (DEC-0042).

The administrator types a temporary password for the People security target. The person
signs in with it on a separate session, meets the password-change gate, chooses their
original sample password again (Auth refuses only the current password) and signs in with
it on their primary session. The temporary password is never journaled, kept in the
result or put in an error. A failure after the administrator write is never replayed; the
person is restored with the temporary password only when Auth already holds it.
"""

import secrets
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.systems.access.users.schemas import (
    AuthMeResponse,
    TemporaryPasswordResponse,
    UserSecurityResponse,
)
from operations.sample.blueprint import SampleDataset
from operations.sample.client import SampleClient, SampleClientError
from operations.sample.controls.people_security import plan_people_security_controls
from operations.sample.packs.phase_types import PhaseAction
from operations.sample.phases.actions import (
    PhaseExecutionContext,
    PhaseSubstep,
    SamplePhaseActionError,
    _request_id,
    _result,
)
from operations.sample.population.people import SampleActorCredential

OPERATION = "temporary_password_roundtrip"
ADMIN_STEP = "set_temporary_password"
CONTROL_ROUTES = frozenset({("POST", "/api/users/{user_id}/temporary-password")})
# A session-admitted read outside the gate's allow-list: 403 until a password is chosen.
_GATED = "/api/notifications/unread-count"


def _require(condition: bool, step: str) -> None:
    if not condition:
        raise SamplePhaseActionError("Temporary password state differs from its plan", step=step)


def _dto[T: BaseModel](response: httpx.Response, model: type[T], step: str) -> T:
    try:
        return model.model_validate_json(response.content, strict=True)
    except ValidationError:
        raise SamplePhaseActionError("Temporary password response is invalid", step=step) from None


def _detail_code(response: httpx.Response) -> object:
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail.get("code") if isinstance(detail, dict) else None


def plan_temporary_password_controls(dataset: SampleDataset) -> tuple[PhaseAction, ...]:
    """The People security target; recovery already proved it eligible and single-org."""
    target = plan_people_security_controls(dataset)[0].target_key
    return (
        PhaseAction(
            key="control:temporary-password",
            phase="admin",
            kind="access_controls",
            actor_key=target,
            target_key=target,
            values={"operation": OPERATION, "admin_steps": [ADMIN_STEP]},
            expected_status=200,
            expected_detail=None,
            expected_end_state={
                "original_password_restored": True,
                "password_change_required": False,
            },
        ),
    )


def execute_temporary_password_control(
    action: PhaseAction,
    dataset: SampleDataset,
    context: PhaseExecutionContext,
    *,
    on_substep: PhaseSubstep | None = None,
) -> dict[str, object]:
    _require(action in plan_temporary_password_controls(dataset), "temporary_plan")
    key = action.target_key
    target, admin_id = context.user_ids.get(key), context.user_ids.get("admin")
    person = next((p for p in dataset.organization.actors.people if p.key == key), None)
    credentials = context.private_values.get("credentials")
    credential = credentials.get(key) if isinstance(credentials, Mapping) else None
    factory = context.private_values.get("new_client")
    admin, primary = context.clients.get("admin"), context.clients.get(key)
    if (
        not isinstance(credential, SampleActorCredential)
        or person is None
        or target is None
        or admin_id is None
        or credential.user_id != target
        or credential.email != person.email
        or not credential.password
        or target == admin_id
        or admin is None
        or primary is None
        or not callable(factory)
    ):
        raise SamplePhaseActionError(
            "Temporary password prerequisites are unavailable", step="temporary_setup"
        )
    original = credential.password
    # At most 72 bytes, mixed case and a digit, so any password policy of the run admits it.
    temporary = "Tp7" + secrets.token_urlsafe(27)
    evidence: list[dict[str, object]] = []

    def observe(
        actor: str, step: str, method: str, path: str, response: httpx.Response, expected: int
    ) -> httpx.Response:
        request_id = _request_id(response)
        if method != "GET":
            evidence.append(
                {
                    "step": step,
                    "actor_key": actor,
                    "actor_id": admin_id if actor == "admin" else target,
                    "method": method,
                    "path": path,
                    "expected_status": expected,
                    "status_code": response.status_code,
                    "request_id": request_id,
                }
            )
        if response.status_code != expected or (method != "GET" and request_id is None):
            raise SamplePhaseActionError(
                "Temporary password request did not match its plan",
                step=step,
                status_code=response.status_code,
                request_id=request_id,
            )
        return response

    def send(
        client: SampleClient,
        actor: str,
        step: str,
        method: str,
        path: str,
        *,
        expected: int = 200,
        body: Mapping[str, Any] | None = None,
        refresh_first: bool = True,
    ) -> httpx.Response:
        if on_substep is not None:
            on_substep(step)
        response = client.request(method, path, json_body=body, refresh_first=refresh_first)
        return observe(actor, step, method, path, response, expected)

    def login(client: SampleClient, step: str, password: str) -> None:
        if on_substep is not None:
            on_substep(step)
        response = client.login(credential.email, password)
        observe(key, step, "POST", "/api/auth/login", response, 200)

    def identity(client: SampleClient, step: str, *, marked: bool) -> None:
        me = _dto(send(client, key, step, "GET", "/api/auth/me"), AuthMeResponse, step)
        _require(str(me.id) == target and me.password_change_required is marked, step)

    def restore_with_temporary() -> None:
        # Only a password Auth already took signs in; nothing here repeats the admin write.
        with suppress(SampleClientError, ValueError):
            client = factory()
            if client.login(credential.email, temporary).status_code == 200:
                body = {"current_password": temporary, "password": original}
                client.request("POST", "/api/auth/password/change", json_body=body)
                client.request("POST", "/api/auth/logout", refresh_first=False)

    security = _dto(
        send(admin, "admin", "read_temporary_target", "GET", f"/api/users/{target}/security"),
        UserSecurityResponse,
        "read_temporary_target",
    )
    _require(
        str(security.user_id) == target
        and security.target_eligible
        and security.verified_factor_count == 0,
        "read_temporary_target",
    )
    identity(primary, "read_target_before", marked=False)
    written = finished = False
    try:
        written = True
        receipt = _dto(
            send(
                admin,
                "admin",
                ADMIN_STEP,
                "POST",
                f"/api/users/{target}/temporary-password",
                body={"password": temporary},
            ),
            TemporaryPasswordResponse,
            ADMIN_STEP,
        )
        _require(
            str(receipt.user_id) == target
            and receipt.temporary_password is None
            and receipt.local_revocation == "committed"
            and receipt.revoked_sessions >= 1,
            ADMIN_STEP,
        )
        # An ended session cannot refresh, so the probe reads without refreshing first.
        ended = send(
            primary, key, "read_primary_ended", "GET", "/api/auth/session", refresh_first=False
        ).json()
        _require(isinstance(ended, dict) and ended.get("authenticated") is False, "primary")
        # A new session, so the primary client never remembers the temporary password.
        session = factory()
        login(session, "login_temporary_password", temporary)
        identity(session, "read_marked_identity", marked=True)
        gate = send(session, key, "read_gated", "GET", _GATED, expected=403)
        _require(_detail_code(gate) == "password_change_required", "read_gated")
        send(
            session,
            key,
            "change_temporary_password",
            "POST",
            "/api/auth/password/change",
            body={"current_password": temporary, "password": original},
        )
        identity(session, "read_chosen_identity", marked=False)
        send(session, key, "read_gate_cleared", "GET", _GATED)
        send(session, key, "logout_temporary_session", "POST", "/api/auth/logout", expected=204)
        finished = True
    finally:
        if written:
            if not finished:
                restore_with_temporary()
            login(primary, "login_original_password", original)
            identity(primary, "read_original_identity", marked=False)
    return _result(
        action,
        context,
        evidence,
        [],
        extra={
            "target_id": target,
            "operation_id": str(receipt.operation_id),
            "revoked_sessions": receipt.revoked_sessions,
            "original_password_restored": True,
            "password_change_required": False,
        },
    )
