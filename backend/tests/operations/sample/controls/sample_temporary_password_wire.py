"""Closed temporary-password transport fixture; never real provider or gate proof."""

import json
from contextlib import contextmanager
from datetime import date
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.systems.access.identity.schemas import PasswordChangeRequest
from app.systems.access.users.schemas import TemporaryPasswordRequest
from operations.sample.client import SampleClient
from operations.sample.packs.registry import get_pack
from operations.sample.phases.actions import PhaseExecutionContext
from operations.sample.population.people import SampleActorCredential
from operations.sample.scenario import build_dataset

ORIGIN = "http://127.0.0.1:3000"
PASSWORD = "Owned-member-fixture-password-7"
OPERATION = "temporary_password_roundtrip"
STAMP = "2026-10-07T12:00:00Z"
GATED = "/api/notifications/unread-count"


def identifier(key):
    return str(uuid5(NAMESPACE_URL, "temporary-password:" + key))


def dataset(pack="harbor"):
    return build_dataset("small", 42, date(2026, 10, 1), organization=get_pack(pack))


def planned(source):
    from operations.sample.controls.actions import plan_controls

    actions = [row for row in plan_controls(source) if row.values.get("operation") == OPERATION]
    assert len(actions) == 1, "The temporary-password route lacks a planned sample journey"
    return actions[0]


class TemporaryPasswordWire:
    """Holds the person's password and mark the way Auth and the gate would."""

    def __init__(self, source, action, fault=None):
        self.action, self.fault = action, fault
        self.person = next(
            p for p in source.organization.actors.people if p.key == action.target_key
        )
        self.admin, self.target = identifier("admin"), identifier(self.person.key)
        self.password, self.marked = PASSWORD, False
        self.requests, self.writes, self.chosen = [], [], []
        self.fault_hits, self.sessions = set(), {}

    def response(self, body, status=200, headers=()):
        return httpx.Response(
            status,
            json=body,
            headers=[
                ("X-Request-ID", identifier(f"request:{len(self.requests)}")),
                ("Cache-Control", "private, no-store"),
                *headers,
            ],
        )

    def hit(self, fault):
        if self.fault == fault:
            self.fault_hits.add(fault)
            return True
        return False

    def identity(self, request):
        cookies = dict(
            part.split("=", 1)
            for part in request.headers.get("cookie", "").split("; ")
            if "=" in part
        )
        session = cookies.get("slateops_access")
        return session, self.sessions.get(session)

    def me(self, actor):
        email = self.person.email if actor == self.target else "owner@example.test"
        role = "member" if actor == self.target else "admin"
        profile = {
            "id": actor,
            "email": email,
            "username": "owned-person",
            "display_name": "Owned person",
            "job_title": None,
            "created_at": STAMP,
            "updated_at": STAMP,
            "deleted_at": None,
            "is_deleted": False,
            "performed_by": self.admin,
            "status": "active",
        }
        org = {"org_id": self.admin, "name": "Example", "slug": "example", "role": role}
        marked = self.marked and actor == self.target
        if marked and self.hit("mark_missing"):
            marked = False
        if actor == self.target and not self.marked and self.writes[-1:] == ["change"]:
            marked = self.hit("mark_kept") or marked
        return {
            **profile,
            "role": role,
            "access": [],
            "sponsor_user_id": None,
            "expires_at": None,
            "invitation_sent_at": STAMP,
            "account": profile,
            "memberships": [org],
            "pending_invitations": [],
            "current_organization": {**org, "access": []},
            "default_organization_blocked": None,
            "password_change_required": marked,
        }

    def handle(self, request):
        self.requests.append(request)
        method, path = request.method, request.url.path
        assert request.headers["origin"] == ORIGIN
        if path == "/api/auth/login":
            body = json.loads(request.content)
            actor = self.target if body["email"] == self.person.email else self.admin
            if actor == self.target and body["password"] != self.password:
                return self.response({"detail": "Invalid login credentials"}, 401)
            session = identifier(f"session:{len(self.requests)}")
            self.sessions[session] = actor
            return self.response(
                {"authenticated": True, "setup_required": False},
                headers=[
                    ("Set-Cookie", f"slateops_access={session}; Path=/; HttpOnly"),
                    ("Set-Cookie", "slateops_csrf=owned-csrf; Path=/"),
                ],
            )
        session, actor = self.identity(request)
        if path == "/api/auth/session":
            return self.response(
                {"authenticated": actor is not None, **({"user_id": actor} if actor else {})}
            )
        if path == "/api/auth/refresh":
            raise AssertionError("A temporary or revoked session must not be refreshed")
        assert actor is not None, f"Unexpected unauthenticated fixture operation {path}"
        if method != "GET":
            assert request.headers["x-csrf-token"] == "owned-csrf"
        if path == "/api/auth/me":
            return self.response(self.me(actor))
        if path == "/api/auth/logout":
            self.sessions.pop(session)
            return httpx.Response(204, headers={"X-Request-ID": identifier("logout")})
        if path == GATED:
            if actor == self.target and self.marked and not self.hit("gate_open"):
                code = "forbidden" if self.hit("gate_code") else "password_change_required"
                return self.response(
                    {
                        "detail": {
                            "code": code,
                            "message": "Choose a new password to continue.",
                        }
                    },
                    403,
                )
            return self.response({"unread_count": 0})
        if path == "/api/auth/password/change":
            assert actor == self.target
            body = PasswordChangeRequest.model_validate_json(request.content, strict=True)
            self.writes.append("change")
            if self.writes.count("change") == 1 and self.hit("change_refused"):
                return self.response({"detail": "Password cannot be changed"}, 403)
            if body.current_password != self.password or body.password == self.password:
                return self.response({"detail": "Password cannot be changed"}, 403)
            self.password, self.marked = body.password, False
            self.sessions = {
                key: owner
                for key, owner in self.sessions.items()
                if owner != self.target or key == session
            }
            return self.response({"authenticated": True, "setup_required": False})
        assert actor == self.admin, f"Only the administrator reads {path}"
        if path == f"/api/users/{self.target}/security":
            return self.response(
                {
                    "user_id": self.target,
                    "verified_factor_count": 1 if self.hit("verified_factor") else 0,
                    "target_eligible": True,
                    "smtp_configured": True,
                }
            )
        if path == f"/api/users/{self.target}/temporary-password":
            return self.temporary_password(request)
        raise AssertionError(f"Unexpected temporary-password fixture route {method} {path}")

    def temporary_password(self, request):
        body = TemporaryPasswordRequest.model_validate_json(request.content, strict=True)
        assert body.password is not None, "The sample types its temporary password"
        self.writes.append("temporary")
        self.chosen.append(body.password)
        revoked = sum(owner == self.target for owner in self.sessions.values())
        self.sessions = {k: v for k, v in self.sessions.items() if v != self.target}
        self.marked = True
        if self.hit("provider_failed"):  # The mark commits before Auth refuses the password.
            return self.response({"detail": {"code": "security_action_incomplete"}}, 503)
        self.password = body.password
        receipt = {
            "operation_id": identifier("operation"),
            "user_id": self.target,
            "temporary_password": body.password if self.hit("receipt_password") else None,
            "local_revocation": "committed",
            "revoked_sessions": 0 if self.hit("receipt_revocation") else revoked,
        }
        if self.hit("unknown_write"):
            raise httpx.ReadTimeout("Owned fixture response lost", request=request)
        return self.response(receipt)


@contextmanager
def journey(tmp_path, pack="harbor", fault=None):
    source = dataset(pack)
    action = planned(source)
    server = TemporaryPasswordWire(source, action, fault)
    clients = {}

    def client():
        transport = httpx.MockTransport(server.handle)
        made = SampleClient(ORIGIN, ORIGIN, tmp_path / "requests.jsonl", transport=transport)
        clients[f"extra-{len(clients)}"] = made
        return made

    admin, primary = client(), client()
    admin.login("owner@example.test", PASSWORD)
    primary.login(server.person.email, PASSWORD)
    credential = SampleActorCredential(server.target, server.person.email, PASSWORD)
    context = PhaseExecutionContext(
        clients={"admin": admin, action.target_key: primary},
        user_ids={"admin": server.admin, action.target_key: server.target},
        group_ids={},
        department_ids={},
        module_ids={},
        field_ids={},
        mappings={},
        admin_password=PASSWORD,
        private_values={"credentials": {action.target_key: credential}, "new_client": client},
    )
    try:
        yield source, action, context, server
    finally:
        for made in clients.values():
            made.close()
