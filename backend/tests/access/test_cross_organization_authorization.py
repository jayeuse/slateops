"""An administrator of one organization has no administrator power in another (S07)."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import get_current_user
from app.common.dependencies.auth import require_admin
from app.core.database.session import get_db
from app.main import create_app
from app.systems.access.users.models import User
from app.systems.manage.audit.models import AuditAction, AuditLog, SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.audit.security_events import append_security_event
from app.systems.manage.workspace.models import WorkspaceProfile
from tests.conftest import create_member, create_organization
from tests.organization_scope_support import scoped_override

pytestmark = pytest.mark.integration


def _depends_on(dependant: Dependant, target: Any) -> bool:
    return any(
        dependency.call is target or _depends_on(dependency, target)
        for dependency in dependant.dependencies
    )


def _administrator_routes(application: FastAPI) -> list[tuple[str, str]]:
    """Every route that requires an administrator, with placeholder path values.

    Dependencies are resolved before path and body validation, so a refused
    administrator is answered with 403 whatever the placeholders are.
    """

    routes = set()
    for included in application.routes:
        # Included routers expose their routes with the full prefixed path.
        contexts = getattr(included, "effective_route_contexts", None)
        for context in contexts() if contexts is not None else ():
            route = context.original_route
            if isinstance(route, APIRoute) and _depends_on(route.dependant, require_admin):
                path = re.sub(r"\{[^}/]+\}", str(uuid7()), context.path)
                routes.update((method, path) for method in route.methods - {"HEAD", "OPTIONS"})
    return sorted(routes)


@pytest.fixture
def two_organizations(
    integration_db: Session,
) -> tuple[Session, User, WorkspaceProfile, WorkspaceProfile]:
    db = integration_db
    home = create_organization(db)
    visited = create_organization(db)
    sponsor, _ = create_member(db, visited, "member")
    actor, _ = create_member(db, home, "admin")
    create_member(
        db, visited, "guest", user=actor, sponsor_user_id=sponsor.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    # Commit into the test's outer transaction so a refused request's rollback keeps it.
    db.commit()
    return db, actor, home, visited


def _client(db: Session, actor: User, organization: WorkspaceProfile) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_current_user] = scoped_override(
        lambda: actor, org_id=organization.id
    )
    return TestClient(application)


def test_every_administrator_route_refuses_an_administrator_of_another_organization(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    db, actor, _home, visited = two_organizations
    routes = _administrator_routes(create_app())
    assert len(routes) > 20, routes
    with _client(db, actor, visited) as client:
        answered = {(method, path): client.request(method, path).status_code
                    for method, path in routes}
    assert {route: code for route, code in answered.items() if code != 403} == {}


def test_the_same_account_still_administers_its_own_organization(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    db, actor, home, visited = two_organizations
    path = "/api/users?limit=1&offset=0"
    with _client(db, actor, home) as client:
        assert client.get(path).status_code == 200
    with _client(db, actor, visited) as client:
        assert client.get(path).status_code == 403


def test_account_rows_are_visible_only_for_people_of_the_bound_organization(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    db, actor, home, visited = two_organizations
    neighbour, _ = create_member(db, home, "member")
    stranger, _ = create_member(db, visited, "member")
    for person in (neighbour, stranger):
        append_security_event(db, SecurityEventIngestRequest(
            event_type="identity.sign_in_failure", outcome=SecurityEventOutcome.DENIED,
            source="tests", operation_id=uuid7(), actor_id=person.id, subject_id=person.id,
        ))
        person.display_name = f"Renamed {person.id.hex[:8]}"  # an account audit row
    db.commit()
    with _client(db, actor, home) as client:
        events = client.get(f"/api/security-events?person_id={neighbour.id}&limit=50")
        hidden_events = client.get(f"/api/security-events?person_id={stranger.id}&limit=50")
        audits = client.get(f"/api/audit-logs?entity_id={neighbour.id}&limit=50")
        hidden_audits = client.get(f"/api/audit-logs?entity_id={stranger.id}&limit=50")
        card = client.get(f"/api/users/{neighbour.id}/card")
        hidden_card = client.get(f"/api/users/{stranger.id}/card")
    assert events.status_code == 200 and events.json()["items"], events.text
    assert hidden_events.status_code == 200 and hidden_events.json()["items"] == []
    assert audits.status_code == 200 and audits.json()["items"], audits.text
    assert hidden_audits.status_code == 200 and hidden_audits.json()["items"] == []
    assert card.status_code == 200, card.text
    assert hidden_card.status_code == 404
    assert hidden_card.json() == {
        "detail": {"code": "person_not_found", "message": "Person not found"},
        "request_id": hidden_card.headers["X-Request-ID"],
    }


def test_an_organization_admin_acts_on_the_membership_of_a_shared_person(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    """Owner decision 11: membership changes only; the account stays for other organizations."""
    db, actor, home, visited = two_organizations
    shared, home_membership = create_member(db, home, "member")
    _, visited_membership = create_member(db, visited, "admin", user=shared)
    db.commit()
    with _client(db, actor, home) as client:
        renamed = client.patch(f"/api/users/{shared.id}", json={"username": "renamed-shared"})
        disabled = client.patch(f"/api/users/{shared.id}", json={"status": "disabled"})
        removed = client.delete(f"/api/users/{shared.id}")
    assert renamed.status_code == 409, renamed.text
    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled", disabled.text
    assert removed.status_code == 204, removed.text
    db.expire_all()
    assert shared.status == "active" and shared.is_deleted is False
    assert home_membership.is_deleted is True
    assert visited_membership.status == "active" and visited_membership.is_deleted is False


def test_account_event_details_match_collection_visibility(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    db, actor, home, visited = two_organizations
    shared, _ = create_member(db, home)
    create_member(db, visited, user=shared)
    foreign, _ = create_member(db, visited)
    events = []
    for person in (shared, foreign, None):
        event = append_security_event(db, SecurityEventIngestRequest(
            event_type="identity.sign_in_failure", outcome=SecurityEventOutcome.DENIED,
            source="tests", operation_id=uuid7(), subject_id=person.id if person else None,
        ))
        events.append(event)
        if person:
            person.display_name = f"Detail {person.id}"
    platform_audit_id = uuid7()
    db.connection().execute(AuditLog.__table__.insert().values(
        id=platform_audit_id, action=AuditAction.UPDATE, entity_type="platform_settings",
        entity_id=uuid7(), before={"revision": 1}, after={"revision": 2},
    ))
    db.commit()
    audits = [db.scalars(select(AuditLog).where(
        AuditLog.entity_type == "users", AuditLog.entity_id == person.id,
    )).one() for person in (shared, foreign)] + [db.scalars(
        select(AuditLog).where(AuditLog.id == platform_audit_id)
    ).one()]
    with _client(db, actor, home) as client:
        for prefix, rows in (("security-events", events), ("audit-logs", audits)):
            listed = client.get(f"/api/{prefix}?limit=100")
            assert listed.status_code == 200, listed.text
            visible_ids = {row["id"] for row in listed.json()["items"]}
            assert str(rows[0].id) in visible_ids
            for index, row in enumerate(rows):
                detail = client.get(f"/api/{prefix}/{row.id}")
                assert detail.status_code == (200 if index == 0 else 404), detail.text
                assert (str(row.id) in visible_ids) is (index == 0)


def _account_row(db: Session, entity_type: str, entity_id: Any, actor: Any) -> str:
    """An installation-wide audit row, as account and platform changes write them."""

    marker = uuid7().hex
    db.connection().execute(AuditLog.__table__.insert().values(
        id=uuid7(), org_id=None, action=AuditAction.UPDATE, entity_type=entity_type,
        entity_id=entity_id, performed_by=actor, after={"marker": marker},
    ))
    return marker


def test_every_audit_read_keeps_other_organizations_and_install_rows_out_h1(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    # H1: row-level security passes every row with no organization, so the application's
    # organization condition is the only thing that hides these rows. Each read must keep it.
    db, actor, home, visited = two_organizations
    shared, _ = create_member(db, home)
    create_member(db, visited, user=shared)
    foreign, _ = create_member(db, visited)
    shown = _account_row(db, "users", shared.id, shared.id)
    hidden = {
        _account_row(db, "users", foreign.id, foreign.id),
        _account_row(db, "platform_settings", uuid7(), foreign.id),
    }
    db.commit()
    rows = {
        row.after["marker"]: str(row.id)
        for row in db.scalars(select(AuditLog).where(AuditLog.org_id.is_(None)))
        if row.after and "marker" in row.after
    }

    with _client(db, actor, home) as client:
        listed = client.get("/api/audit-logs?limit=100")
        exported = client.get("/api/audit-logs/export")
        details = {marker: client.get(f"/api/audit-logs/{rows[marker]}").status_code
                   for marker in {shown, *hidden}}
        options = client.get("/api/audit-logs/options")

    assert listed.status_code == 200, listed.text
    listed_ids = {row["id"] for row in listed.json()["items"]}
    assert rows[shown] in listed_ids
    assert not {rows[marker] for marker in hidden} & listed_ids
    assert exported.status_code == 200, exported.text
    assert f"Marker: {shown}" in exported.text
    assert [marker for marker in hidden if marker in exported.text] == []
    assert details == {shown: 200, **dict.fromkeys(hidden, 404)}
    assert options.status_code == 200, options.text
    assert "platform_settings" not in options.json()["entity_types"]
    assert str(foreign.id) not in {row["performed_by"] for row in options.json()["actors"]}
    assert str(shared.id) in {row["performed_by"] for row in options.json()["actors"]}


def _bulk_rows(db: Session, rows: int, request_id: Any, **values: Any) -> None:
    db.connection().execute(
        text(
            "INSERT INTO public.audit_logs (id, org_id, created_at, action, entity_type, "
            "entity_id, request_id) SELECT gen_random_uuid(), :org_id, "
            "now() - make_interval(secs => step), 'update', :entity_type, :entity_id, "
            ":request_id FROM generate_series(1, :rows) AS step"
        ),
        {"rows": rows, "request_id": request_id, **values},
    )


def test_an_administrators_count_equals_a_walk_of_every_page_c7(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    # H2: the count reads the same organization condition as the page, so the account rows
    # of other organizations' people and install-wide rows are in neither.
    db, actor, home, visited = two_organizations
    shared, _ = create_member(db, home)
    create_member(db, visited, user=shared)
    foreign, _ = create_member(db, visited)
    small, large = uuid7(), uuid7()
    _bulk_rows(db, 3, small, org_id=home.id, entity_type="reports", entity_id=None)
    _bulk_rows(db, 3, small, org_id=None, entity_type="users", entity_id=shared.id)
    _bulk_rows(db, 2, small, org_id=None, entity_type="users", entity_id=foreign.id)
    _bulk_rows(db, 2, small, org_id=None, entity_type="platform_settings", entity_id=uuid7())
    # The count is one statement (K64 form 1), so one condition above the cap caps it. No
    # bulk account rows: their dead index entries would cost every later account-row read.
    _bulk_rows(db, 10_001, large, org_id=home.id, entity_type="reports", entity_id=None)
    _bulk_rows(db, 2, large, org_id=None, entity_type="platform_settings", entity_id=uuid7())
    db.commit()

    with _client(db, actor, home) as client:
        walked: list[str] = []
        while True:
            page = client.get(
                "/api/audit-logs", params={"request_id": str(small), "limit": 2,
                                           "offset": len(walked)},
            ).json()
            walked += [row["id"] for row in page["items"]]
            if not page["pagination"]["has_more"]:
                break
        capped = client.get("/api/audit-logs", params={"request_id": str(large), "limit": 1})

    assert (len(walked), page["pagination"]["total"]) == (6, 6)
    assert page["pagination"]["total_is_capped"] is False
    assert capped.json()["pagination"]["total"] == 10_000
    assert capped.json()["pagination"]["total_is_capped"] is True


def test_people_lifecycle_projects_and_readmits_only_the_bound_membership(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile],
) -> None:
    db, actor, home, visited = two_organizations
    shared, home_member = create_member(db, home, supabase_user_id=uuid7())
    _, peer_member = create_member(db, visited, "admin", user=shared)
    db.commit()
    with _client(db, actor, home) as client:
        changed = client.patch(f"/api/users/{shared.id}", json={"status": "disabled"})
        assert changed.status_code == 200, changed.text
        detail = client.get(f"/api/users/{shared.id}")
        assert detail.status_code == 200 and detail.json()["status"] == "disabled", detail.text
        for status, included in (("active", False), ("disabled", True)):
            listed = client.get(f"/api/users?status={status}&ids={shared.id}")
            assert listed.status_code == 200, listed.text
            assert bool(listed.json()["items"]) is included
        assert client.delete(f"/api/users/{shared.id}").status_code == 204
        listed = client.get("/api/users?deleted=exclude&limit=100")
        assert str(shared.id) not in {row["id"] for row in listed.json()["items"]}
        archived = client.get(f"/api/users?deleted=only&ids={shared.id}")
        assert archived.status_code == 200 and len(archived.json()["items"]) == 1
        assert archived.json()["items"][0]["is_deleted"] is True
        assert archived.json()["items"][0]["deleted_at"] is not None
        removed_detail = client.get(f"/api/users/{shared.id}")
        assert removed_detail.status_code == 200 and removed_detail.json()["is_deleted"] is True


@pytest.mark.parametrize("reentry", ["restore", "invite"])
def test_removed_membership_can_be_readmitted_without_changing_shared_account(
    two_organizations: tuple[Session, User, WorkspaceProfile, WorkspaceProfile], reentry: str,
) -> None:
    db, actor, home, visited = two_organizations
    shared, home_member = create_member(db, home, supabase_user_id=uuid7())
    _, peer_member = create_member(db, visited, "admin", user=shared)
    home_member.is_deleted = True
    home_member.deleted_at = datetime.now(UTC)
    home_member.status = "disabled"
    db.commit()
    with _client(db, actor, home) as client:
        if reentry == "restore":
            restored = client.post(f"/api/users/{shared.id}/restore")
            assert restored.status_code == 200, restored.text
            assert restored.json()["status"] == "active" and not restored.json()["is_deleted"]
        else:
            invited = client.post("/api/users", json={
                "email": shared.email, "username": shared.username, "role": "member",
            })
            assert invited.status_code == 201, invited.text
            assert invited.json()["delivery"] == "in_app"
            assert invited.json()["user"]["status"] == "pending"
    db.expire_all()
    assert shared.status == "active" and shared.is_deleted is False
    assert home_member.is_deleted is False and home_member.deleted_at is None
    assert home_member.status == ("active" if reentry == "restore" else "pending")
    assert peer_member.status == "active" and not peer_member.is_deleted
