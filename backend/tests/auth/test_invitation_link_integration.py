"""AC-L1 and AC-L2 (DEC-0042) on the real provider: an invitation link, with no email set up.

The link lands on the existing completion page and works once; a new link ends the old one;
a cancel ends it; and it stops 24 hours after it was made. No email leaves the server.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from secrets import token_urlsafe
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.config import get_settings
from app.core.integrations.supabase_auth import SupabaseAuthUnavailable
from app.main import create_app
from app.systems.access.identity.models import IdentitySession
from app.systems.access.users import invitation_links
from app.systems.access.users.models import Membership, User
from app.systems.manage.audit.models import SecurityEvent
from app.systems.platform.scheduling.models import InAppNotification

pytest_plugins = ("tests.auth.test_provider_email_integration",)
pytestmark = pytest.mark.integration


@dataclass
class Inviter:
    owner: Engine
    mail: httpx.Client
    admin: TestClient
    recipient: TestClient
    emails: list[str] = field(default_factory=list)

    def invite(self, delivery: str = "link") -> tuple[httpx.Response, str]:
        email = f"link-{uuid4().hex}@example.test"
        self.emails.append(email)
        response = self.admin.post("/api/users", json={
            "email": email, "username": f"link_{uuid4().hex[:16]}", "delivery": delivery,
        })
        return response, email

    def complete(self, token: str, password: str) -> int:
        return self.recipient.post(
            "/api/auth/invitations/complete", json={"token_hash": token, "password": password}
        ).status_code

    def signs_in(self, email: str, password: str) -> bool:
        return self.recipient.post(
            "/api/auth/login", json={"email": email, "password": password}
        ).status_code == 200

    def mail_to(self, email: str) -> list[object]:
        messages = self.mail.get("/api/v1/messages").json().get("messages", [])
        return [message for message in messages
                if any(item.get("Address") == email for item in message.get("To", []))]


def _token(url: str) -> str:
    link = urlsplit(url)
    fragment = parse_qs(link.fragment)
    assert f"{link.scheme}://{link.netloc}" == get_settings().public_origin
    assert (link.path, link.query, fragment["type"]) == ("/auth/setup", "", ["invite"])
    return fragment["token_hash"][0]


@pytest.fixture
def inviter(provider_account, provider_mail, monkeypatch) -> Iterator[Inviter]:
    email, password, provider_id, local_id, owner = provider_account
    settings = get_settings()
    with Session(owner) as db:
        db.get(User, local_id).supabase_user_id = provider_id
        db.scalars(select(Membership).where(Membership.user_id == local_id)).one().role = "admin"
        db.commit()
    source = uuid4().bytes
    address = (f"198.18.{source[0]}.{source[1]}", 50000)
    admin = TestClient(create_app(), base_url=settings.public_origin, client=address)
    recipient = TestClient(create_app(), base_url=settings.public_origin, client=address)
    admin.headers["Origin"] = recipient.headers["Origin"] = settings.public_origin
    state = Inviter(owner, provider_mail, admin, recipient)
    try:
        assert admin.post(
            "/api/auth/login", json={"email": email, "password": password}
        ).status_code == 200
        admin.headers["X-CSRF-Token"] = admin.cookies.get("slateops_csrf")
        # Email is not set up on this installation (DEC-0041).
        monkeypatch.setattr(settings, "smtp_host", None)
        yield state
    finally:
        admin.close()
        recipient.close()
        _remove_people(owner, state.emails)


def _remove_people(owner: Engine, emails: list[str]) -> None:
    settings = get_settings()
    with Session(owner) as db:
        for user in db.scalars(select(User).where(User.email.in_(emails))):
            for notice in db.scalars(select(InAppNotification).where(
                InAppNotification.subject_id == user.id
            )):
                db.delete(notice)
            if user.supabase_user_id is not None:
                removed = httpx.delete(
                    settings.supabase_url + f"/auth/v1/admin/users/{user.supabase_user_id}",
                    headers={"apikey": settings.supabase_secret_key.get_secret_value()},
                    timeout=10,
                )
                assert removed.status_code in {200, 204, 404}
            for session in db.scalars(
                select(IdentitySession).where(IdentitySession.user_id == user.id)
            ):
                db.delete(session)
            for membership in db.scalars(select(Membership).where(Membership.user_id == user.id)):
                db.delete(membership)
            db.flush()
            db.delete(user)
        db.commit()


def test_ac_l1_a_link_invitation_without_email_completes_once_and_sends_nothing(inviter):
    created, email = inviter.invite("link")

    assert created.status_code == 201, created.text
    assert created.json()["delivery"] == "link"
    token = _token(created.json()["invitation_url"])
    refused, _ = inviter.invite("email")
    assert refused.status_code == 503
    assert refused.json()["detail"]["code"] == "email_not_configured"
    assert inviter.mail_to(email) == []
    person_id = UUID(created.json()["user"]["id"])
    with Session(inviter.owner) as db:
        events = db.scalars(select(SecurityEvent).where(SecurityEvent.subject_id == person_id))
        recorded = " ".join(json.dumps(event.event_metadata) + str(event.reason)
                            for event in events)
    assert token not in recorded

    chosen = token_urlsafe(32)
    assert inviter.complete(token, chosen) == 204
    assert inviter.complete(token, chosen) == 400
    assert inviter.signs_in(email, chosen)


def test_ac_l2_a_new_link_a_cancel_and_24_hours_each_end_the_link(inviter):
    created, email = inviter.invite("link")
    assert created.status_code == 201, created.text
    person_id = created.json()["user"]["id"]
    path = f"/api/auth/invitations/{person_id}"
    chosen = token_urlsafe(32)

    def new_link() -> str:
        renewed = inviter.admin.post(f"{path}/link", json={})
        assert renewed.status_code == 200, renewed.text
        assert renewed.json()["delivery"] == "link"
        return _token(renewed.json()["invitation_url"])

    first = _token(created.json()["invitation_url"])
    second = new_link()
    assert second != first
    assert inviter.complete(first, chosen) == 400

    assert inviter.admin.delete(path).status_code == 204
    assert inviter.complete(second, chosen) == 400

    third = new_link()
    with Session(inviter.owner) as db:
        membership = db.scalars(select(Membership).where(
            Membership.user_id == UUID(person_id))).one()
        membership.invitation_sent_at -= timedelta(hours=24, seconds=1)
        db.commit()
    assert inviter.complete(third, chosen) == 400

    assert inviter.admin.post(f"/api/auth/invitations/{uuid7()}/link", json={}).status_code == 404
    fourth = new_link()
    assert inviter.complete(fourth, chosen) == 204
    assert inviter.signs_in(email, chosen)
    assert inviter.admin.post(f"{path}/link", json={}).status_code == 404
    assert inviter.mail_to(email) == []


def test_ac_l2_a_failed_new_link_leaves_the_current_link_working(inviter, monkeypatch):
    created, email = inviter.invite("link")
    assert created.status_code == 201, created.text
    token = _token(created.json()["invitation_url"])

    def unavailable(*_args: object) -> object:
        raise SupabaseAuthUnavailable("Supabase Auth is unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(invitation_links, "generate_invitation_link", unavailable)
        failed = inviter.admin.post(
            f"/api/auth/invitations/{created.json()['user']['id']}/link", json={}
        )

    assert failed.status_code == 503
    assert failed.json()["detail"] == "Unable to create invitation link"
    chosen = token_urlsafe(32)
    assert inviter.complete(token, chosen) == 204
    assert inviter.signs_in(email, chosen)


def test_ac_t1_a_temporary_password_reaches_the_real_provider(inviter):
    created, email = inviter.invite("link")
    assert created.status_code == 201, created.text
    first = token_urlsafe(32)
    assert inviter.complete(_token(created.json()["invitation_url"]), first) == 204

    response = inviter.admin.post(
        f"/api/users/{created.json()['user']['id']}/temporary-password", json={}
    )

    assert response.status_code == 200, response.text
    temporary = response.json()["temporary_password"]
    assert not inviter.signs_in(email, first)
    assert inviter.signs_in(email, temporary)
    me = inviter.recipient.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["password_change_required"] is True
    assert inviter.mail_to(email) == []
