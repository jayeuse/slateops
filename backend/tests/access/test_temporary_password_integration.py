"""AC-T1, AC-T2 and AC-T3 (DEC-0042) through real sign-in, PostgreSQL and the provider wire.

An administrator sets a temporary password; the person's sessions end; the next session can
only read its identity, change its password and sign out; the change clears the mark; and
the security log names who did it, for whom and when, never the password.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from secrets import token_urlsafe
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import create_app
from app.systems.access.identity.models import IdentitySession
from app.systems.access.users.models import Membership, PlatformOperator, User
from app.systems.manage.audit.models import SecurityEvent
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.platform.events.router import EventPrincipal, _reauthorize_in_database
from tests.conftest import create_member, create_organization, membership_of
from tests.fake_provider_support import FakeProvider, owned_account

pytest_plugins = ("tests.fake_provider_support",)
pytestmark = pytest.mark.integration

GATE = {"code": "password_change_required", "message": "Choose a new password to continue."}


@dataclass
class World:
    owner: Engine
    fake: FakeProvider
    org_id: UUID
    admin_id: UUID
    target_id: UUID
    target_provider_id: UUID
    target_email: str
    target_password: str
    admin: TestClient
    person: TestClient

    def sign_in(self, password: str) -> TestClient:
        client = TestClient(create_app(), base_url=get_settings().public_origin)
        client.headers["Origin"] = get_settings().public_origin
        signed = client.post(
            "/api/auth/login", json={"email": self.target_email, "password": password}
        )
        if signed.status_code == 200:
            client.headers["X-CSRF-Token"] = client.cookies.get("slateops_csrf")
        return client

    def sign_in_status(self, password: str) -> int:
        with TestClient(create_app(), base_url=get_settings().public_origin) as client:
            client.headers["Origin"] = get_settings().public_origin
            return client.post(
                "/api/auth/login", json={"email": self.target_email, "password": password}
            ).status_code

    def events(self) -> list[SecurityEvent]:
        with Session(self.owner) as db:
            return list(db.scalars(
                select(SecurityEvent)
                .where(SecurityEvent.event_type == "identity.temporary_password",
                       SecurityEvent.subject_id == self.target_id)
                .order_by(SecurityEvent.occurred_at, SecurityEvent.id)
            ))

    def set_password(self, body: dict[str, object]) -> httpx.Response:
        return self.admin.post(f"/api/users/{self.target_id}/temporary-password", json=body)


def _admin_password_update(fake: FakeProvider):
    """The pinned GoTrue admin update: ``PUT admin/users/{id}`` with a new password."""

    prefix = "/auth/v1/admin/users/"

    def hook(request: httpx.Request) -> httpx.Response | None:
        parts = request.url.path.removeprefix(prefix).split("/")
        if request.method != "PUT" or not request.url.path.startswith(prefix) or len(parts) != 1:
            return None
        identity = fake.identities.get(UUID(parts[0]))
        if identity is None:
            return httpx.Response(404, json={"error_code": "user_not_found"})
        identity.password = json.loads(request.content)["password"]
        return httpx.Response(200, json=identity.json())

    return hook


@pytest.fixture
def world(fake_provider: FakeProvider) -> Iterator[World]:
    admin_rows = owned_account(fake_provider, prefix="temporary-admin")
    email, password, provider_id, admin_id, owner = next(admin_rows)
    clients: list[TestClient] = []
    target_rows = None
    try:
        with Session(owner) as db:
            db.get(User, admin_id).supabase_user_id = provider_id
            membership = membership_of(db, admin_id)
            membership.role = "admin"
            org_id = membership.org_id
            db.commit()
        target_rows = owned_account(fake_provider, prefix="temporary-person",
                                    organization_id=org_id)
        t_email, t_password, t_provider_id, target_id, _ = next(target_rows)
        with Session(owner) as db:
            db.get(User, target_id).supabase_user_id = t_provider_id
            db.commit()
        fake_provider.hook = _admin_password_update(fake_provider)
        settings = get_settings()
        admin = TestClient(create_app(), base_url=settings.public_origin)
        clients.append(admin)
        admin.headers["Origin"] = settings.public_origin
        assert admin.post(
            "/api/auth/login", json={"email": email, "password": password}
        ).status_code == 200
        admin.headers["X-CSRF-Token"] = admin.cookies.get("slateops_csrf")
        state = World(owner, fake_provider, org_id, admin_id, target_id, t_provider_id,
                      t_email, t_password, admin, admin)
        state.person = state.sign_in(t_password)
        clients.append(state.person)
        assert state.person.get("/api/auth/me").status_code == 200
        yield state
    finally:
        for client in clients:
            client.close()
        if target_rows is not None:
            next(target_rows, None)
        next(admin_rows, None)


def test_ac_t1_t2_t3_server_password_ends_sessions_forces_a_change_and_is_audited(world):
    assert world.person.get("/api/auth/me").json()["password_change_required"] is False

    response = world.set_password({})

    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    temporary = body.pop("temporary_password")
    assert isinstance(temporary, str) and len(temporary) == 16
    assert body == {"operation_id": body["operation_id"], "user_id": str(world.target_id),
                    "local_revocation": "committed", "revoked_sessions": 1}
    assert world.fake.identities[world.target_provider_id].password == temporary
    # AC-T1: the earlier session ended and the earlier password no longer signs in.
    assert world.person.get("/api/auth/me").status_code == 401
    assert world.sign_in_status(world.target_password) == 401
    person = world.sign_in(temporary)
    try:
        # AC-T2: identity, session, refresh and the change stay open; everything else is 403.
        me = person.get("/api/auth/me")
        assert me.status_code == 200 and me.json()["password_change_required"] is True
        assert person.get("/api/auth/session").status_code == 200
        assert person.post("/api/auth/refresh").status_code == 200
        person.headers["X-CSRF-Token"] = person.cookies.get("slateops_csrf")
        # MFA completion stays open (status here); enrolment waits for the new password.
        assert person.get("/api/auth/mfa").status_code == 200
        for method, path in (("GET", f"/api/users/{world.target_id}/preferences"),
                             ("GET", f"/api/users/{world.target_id}/profile"),
                             ("POST", "/api/auth/mfa/factors")):
            blocked = person.request(method, path, json={} if method == "POST" else None)
            assert blocked.status_code == 403, (path, blocked.text)
            assert {key: blocked.json()["detail"][key] for key in GATE} == GATE
        access = person.cookies.get("slateops_access")
        assert _reauthorize_in_database(EventPrincipal(access, None, world.org_id)) is None

        chosen = f"Chosen-{token_urlsafe(16)}"
        changed = person.post("/api/auth/password/change",
                              json={"current_password": temporary, "password": chosen})
        assert changed.status_code == 200, changed.text
        assert person.get("/api/auth/me").json()["password_change_required"] is False
        assert person.get(f"/api/users/{world.target_id}/preferences").status_code == 200
        access = person.cookies.get("slateops_access")
        assert _reauthorize_in_database(EventPrincipal(access, None, world.org_id)) is not None
    finally:
        person.close()
    # AC-T3: who, for whom, when; never the password.
    events = world.events()
    assert [event.outcome for event in events] == ["attempt", "success"]
    for event in events:
        assert (event.actor_id, event.subject_id) == (world.admin_id, world.target_id)
        assert event.occurred_at is not None
        assert event.event_metadata["chosen_by"] == "server"
        assert temporary not in json.dumps(event.event_metadata) + str(event.reason)


def test_ac_t1_an_administrator_choice_follows_the_rule_and_is_not_returned(world):
    refused = world.set_password({"password": "Aa1" + "é" * 35})

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "password_policy_violation"
    assert "é" not in refused.text
    assert world.fake.identities[world.target_provider_id].password == world.target_password
    assert world.person.get("/api/auth/me").status_code == 200

    chosen = f"Chosen-{token_urlsafe(16)}"
    accepted = world.set_password({"password": chosen})

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["temporary_password"] is None
    assert world.fake.identities[world.target_provider_id].password == chosen
    assert [event.event_metadata["chosen_by"] for event in world.events()] == [
        "administrator", "administrator"
    ]


@pytest.mark.parametrize("case", ["self", "organization-owner", "installation-owner", "member"])
def test_ac_t1_self_owners_and_non_administrators_are_refused_without_effect(world, case):
    client, target = world.admin, world.target_id
    expected = {"self": (409, "security_target_self"),
                "organization-owner": (409, "security_target_owner"),
                "installation-owner": (409, "security_target_owner"),
                "member": (403, None)}[case]
    with Session(world.owner) as db:
        if case == "self":
            target = world.admin_id
        elif case == "organization-owner":
            db.get(WorkspaceProfile, world.org_id).owner_user_id = world.target_id
        elif case == "installation-owner":
            db.add(PlatformOperator(user_id=world.target_id))
        db.commit()
    if case == "member":
        client, target = world.person, world.admin_id
    try:
        refused = client.post(f"/api/users/{target}/temporary-password", json={})

        assert refused.status_code == expected[0], refused.text
        if expected[1] is not None:
            assert refused.json()["detail"]["code"] == expected[1]
        assert world.fake.identities[world.target_provider_id].password == world.target_password
        assert world.person.get("/api/auth/me").status_code == 200
        assert world.events() == []
    finally:
        with Session(world.owner) as db:
            db.get(WorkspaceProfile, world.org_id).owner_user_id = None
            for row in db.scalars(select(PlatformOperator).where(
                PlatformOperator.user_id == world.target_id
            )):
                db.delete(row)
            db.commit()


def test_ac_t1_a_provider_failure_after_the_commit_keeps_the_sessions_ended_and_the_mark(world):
    def refuse(request: httpx.Request) -> httpx.Response | None:
        if request.method == "PUT" and "/admin/users/" in request.url.path:
            return httpx.Response(500, json={"error_code": "unexpected_failure"})
        return None

    world.fake.hook = refuse

    response = world.set_password({})

    assert response.status_code == 503, response.text
    assert response.headers["Cache-Control"] == "no-store"
    detail = response.json()["detail"]
    assert (detail["code"], detail["local_revocation"]) == ("security_action_incomplete",
                                                            "committed")
    assert "temporary_password" not in response.text
    assert [event.outcome for event in world.events()] == ["attempt", "partial"]
    assert world.person.get("/api/auth/me").status_code == 401
    # The earlier password still signs in, and that session must choose a new password.
    person = world.sign_in(world.target_password)
    try:
        assert person.get("/api/auth/me").json()["password_change_required"] is True
        blocked = person.get(f"/api/users/{world.target_id}/preferences")
        assert blocked.status_code == 403
    finally:
        person.close()


def test_ac_t1_a_password_changed_during_the_provider_call_is_ended_and_marked_again(world):
    # R24-2: after the first commit and before Auth sets the temporary password, the old
    # password still signs in; that session changes it, which clears the mark.
    racer: dict[str, object] = {}
    update = _admin_password_update(world.fake)

    def race(request: httpx.Request) -> httpx.Response | None:
        if request.method == "PUT" and "/admin/users/" in request.url.path and not racer:
            racer["client"] = person = world.sign_in(world.target_password)
            racer["changed"] = person.post("/api/auth/password/change", json={
                "current_password": world.target_password,
                "password": f"Racer-{token_urlsafe(16)}",
            }).status_code
            racer["me"] = person.get("/api/auth/me").json()["password_change_required"]
        return update(request)

    world.fake.hook = race
    try:
        response = world.set_password({})

        assert response.status_code == 200, response.text
        assert (racer["changed"], racer["me"]) == (200, False)
        racer_client = racer["client"]
        assert isinstance(racer_client, TestClient)
        assert racer_client.get("/api/auth/me").status_code == 401
        with Session(world.owner) as db:
            target = db.get(User, world.target_id)
            assert target.password_change_required_at is not None
            live = db.scalars(select(IdentitySession).where(
                IdentitySession.user_id == world.target_id,
                IdentitySession.revoked_at.is_(None),
            )).all()
            assert live == []
        temporary = response.json()["temporary_password"]
        assert world.fake.identities[world.target_provider_id].password == temporary
    finally:
        client = racer.get("client")
        if isinstance(client, TestClient):
            client.close()


@pytest.fixture
def other_organization(world):
    """Organization B with one active and one pending person; ``world.admin`` is A's admin."""

    with Session(world.owner) as db:
        org = create_organization(db)
        provider_id = world.fake.add(f"b-active-{token_urlsafe(8)}@example.test",
                                     token_urlsafe(16))
        active, _ = create_member(db, org, supabase_user_id=provider_id)
        pending, _ = create_member(db, org, status="pending")
        ids = (org.id, active.id, pending.id, provider_id)
        db.commit()
    try:
        yield ids
    finally:
        with Session(world.owner) as db:
            people = (ids[1], ids[2], world.target_id)
            for row in db.scalars(select(Membership).where(
                Membership.org_id == ids[0], Membership.user_id.in_(people)
            )):
                db.delete(row)
            db.flush()
            for person_id in ids[1:3]:
                db.delete(db.get(User, person_id))
            db.flush()
            db.delete(db.get(WorkspaceProfile, ids[0]))
            db.commit()


def test_ac_t1_l2_an_admin_of_one_organization_cannot_reach_a_person_of_another(
    world, other_organization
):
    # R24-3: a person of organization B is hidden from organization A's administrator.
    _org, active, pending, provider_id = other_organization
    world.fake.calls.clear()

    password = world.admin.post(f"/api/users/{active}/temporary-password", json={})
    link = world.admin.post(f"/api/auth/invitations/{pending}/link", json={})

    assert password.status_code == 404, password.text
    assert password.json()["detail"]["code"] == "security_target_missing"
    assert link.status_code == 404, link.text
    assert link.json()["detail"] == "Invitation not found"
    assert not any(str(provider_id) in path or "generate_link" in path
                   for _method, path in world.fake.calls)


def test_ac_t1_a_person_who_also_belongs_to_another_organization_is_refused(
    world, other_organization
):
    # R24-3: a password reaches every organization of the person; only an installation
    # owner may set it then (``security_target_shared``).
    with Session(world.owner) as db:
        create_member(db, db.get(WorkspaceProfile, other_organization[0]),
                      user=db.get(User, world.target_id))
        for row in db.scalars(select(PlatformOperator).where(
            PlatformOperator.user_id == world.admin_id
        )):
            db.delete(row)
        db.commit()

    refused = world.set_password({})

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "security_target_shared"
    assert world.fake.identities[world.target_provider_id].password == world.target_password
    assert world.person.get("/api/auth/me").status_code == 200
    assert world.events() == []
