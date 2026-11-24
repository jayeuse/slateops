"""The sample-run sheet control calls each sheet route of the run's coverage list once,
against the real sheet routes and PostgreSQL, and leaves no live sheet behind."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import CurrentIdentity, get_current_identity, get_current_user
from app.core.base_model import utc_now
from app.core.database import get_db
from app.core.database.session import AuditSession
from app.systems.access.identity.models import IdentitySession
from app.systems.access.users.models import User
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.openview.worksheets import (
    appears_in,
    export_router,
    import_router,
    leave,
    presence,
    row_router,
    share_router,
)
from app.systems.openview.worksheets import router as worksheets
from app.systems.openview.worksheets.models import Worksheet
from app.systems.platform.files.providers import transfer_admission
from app.systems.sandbox.fields.models import Field
from operations.sample.client import SampleClient
from operations.sample.controls.actions import plan_controls
from operations.sample.controls.worksheets import (
    SHEET_ROUTES,
    execute_worksheet_control,
    plan_worksheet_controls,
)
from operations.sample.packs.registry import get_pack
from operations.sample.phases.actions import PhaseExecutionContext
from operations.sample.scenario import build_dataset
from operations.sample.verification.route_coverage import SEEDER_ROUTES, read_route_evidence
from tests.conftest import guarded_create_engine
from tests.organization_scope_support import scoped_override
from tests.worksheets.committed_support import CommittedSheet
from tests.worksheets.committed_support import committed_sheet as committed_sheet

pytestmark = pytest.mark.integration


def _api(runtime: Engine, actor: User, session_id: UUID) -> TestClient:
    app = FastAPI()
    for module in (worksheets, row_router, share_router, export_router, import_router,
                   appears_in, leave, presence):
        app.include_router(module.router, prefix="/api")

    def database() -> Iterator[Session]:
        with AuditSession(runtime) as db:
            db.info[AUDIT_CONTEXT_KEY] = AuditContext(
                request_id=uuid7(), request_method="POST", request_path="/api/worksheets",
                performed_by=actor.id,
            )
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = scoped_override(lambda: actor)
    app.dependency_overrides[get_current_identity] = scoped_override(
        lambda: CurrentIdentity(actor, session_id, False, False))

    @app.middleware("http")
    async def admitted(request, call_next):
        with transfer_admission(len(await request.body())) as lease:
            request.state.file_transfer_lease = lease
            response = await call_next(request)
        response.headers["X-Request-ID"] = str(uuid4())
        return response

    return TestClient(app)


def _client(api: TestClient, journal: Path) -> SampleClient:
    def forward(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"ok": True}, headers=[
                ("Set-Cookie", "slateops_csrf=fixture; Path=/"),
                ("Set-Cookie", "slateops_access=fixture; Path=/; HttpOnly"),
            ])  # fmt: skip
        headers = {key: value for key, value in request.headers.items() if key != "host"}
        response = api.request(request.method, str(request.url), content=request.content,
                               headers=headers)  # fmt: skip
        return httpx.Response(
            response.status_code, headers=response.headers, content=response.content
        )

    client = SampleClient("http://testserver", "http://localhost:3000", journal,
                          transport=httpx.MockTransport(forward))  # fmt: skip
    assert client.login("fixture@example.test", "fixture-only").status_code == 200
    return client


def test_the_control_owns_every_sheet_route_of_the_coverage_list() -> None:
    """A sheet route added to the run's coverage list must be added to this control."""

    sheets = {route for route in SEEDER_ROUTES if "worksheet" in route[1]}
    assert sheets == SHEET_ROUTES
    dataset = build_dataset("small", 42, date(2026, 10, 1), organization=get_pack("harbor"))
    [action] = plan_worksheet_controls(dataset)
    assert action in plan_controls(dataset)


def test_the_sheet_control_calls_each_sheet_route_and_leaves_no_live_sheet(
    committed_sheet: CommittedSheet, tmp_path: Path,
) -> None:
    world = committed_sheet
    dataset = build_dataset("small", 42, date(2026, 10, 1), organization=get_pack("harbor"))
    [action] = plan_worksheet_controls(dataset)
    values = action.values
    field_id = uuid7()
    with Session(world.owner_engine, expire_on_commit=False) as setup:
        record_id, module_id = setup.execute(text(
            "SELECT r.id, r.module_id FROM worksheets AS w JOIN records AS r "
            "ON r.id = w.record_id WHERE w.id = :sheet"), {"sheet": world.sheet_id}).one()
        setup.execute(Field.__table__.insert().values(
            id=field_id, org_id=world.org_id, module_id=module_id, name="Name", type="text",
            position=0, config={}))
        now = utc_now()
        session = IdentitySession(
            user_id=world.admin_id, refresh_token_digest=uuid7().hex * 2,
            csrf_token_digest=uuid7().hex * 2, created_at=now, refreshed_at=now,
            expires_at=now + timedelta(hours=1))
        setup.add(session)
        setup.commit()
        admin = setup.get(User, world.admin_id)
        assert admin is not None
        setup.expunge(admin)
    runtime = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    journal = tmp_path / "admin.jsonl"
    try:
        context = PhaseExecutionContext(
            clients={"admin": _client(_api(runtime, admin, session.id), journal)},
            user_ids={"admin": str(admin.id), str(values["member_key"]): str(world.editor_id)},
            group_ids={}, department_ids={}, module_ids={}, field_ids={},
            mappings={
                "record": {str(values["record_key"]): str(record_id)},
                "modules": {str(values["module_key"]): str(module_id)},
                "fields": {str(values["field_key"]): str(field_id)},
            },
            admin_password="fixture-only",
        )  # fmt: skip

        result = execute_worksheet_control(action, dataset, context)
    finally:
        runtime.dispose()

    assert result["outcome"] == "completed" and result["sheet_routes"] == len(SHEET_ROUTES)
    evidence = result["request_evidence"]
    assert isinstance(evidence, list)
    assert all(row["status_code"] == row["expected_status"] for row in evidence)
    covered = {(row["method"], row["path"]) for row in read_route_evidence(journal)["covered"]}
    assert covered >= SHEET_ROUTES
    with Session(world.owner_engine) as check:
        sheets = check.execute(select(Worksheet.title, Worksheet.is_deleted).where(
            Worksheet.org_id == world.org_id)).all()
    assert sorted(sheets) == [("Race", False), ("Route check 2", True)]
