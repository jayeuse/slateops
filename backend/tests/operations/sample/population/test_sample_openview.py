"""UI-payload coverage for shared OpenView sample content."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.systems.openview.dashboards.schemas import DashboardUpdate
from operations.sample.client import SampleClient
from operations.sample.population.content import SampleContentError
from operations.sample.population.openview import populate_openview

ORIGIN = "https://workspace.example.test"
BASE_URL = "https://api.example.test"


def _structure() -> tuple[
    dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, list[dict[str, Any]]]
]:
    departments: dict[str, dict[str, str]] = {}
    modules: dict[str, dict[str, str]] = {}
    fields: dict[str, list[dict[str, Any]]] = {}
    keys = ("sales", "service", "field", "inventory", "purchasing", "finance")
    for department_key in keys:
        department_id = str(uuid4())
        departments[department_key] = {"id": department_id, "name": department_key.title()}
        for index in range(4):
            module_key = f"{department_key}_module_{index}"
            module_id = str(uuid4())
            modules[module_key] = {"id": module_id, "department_id": department_id}
            fields[module_key] = [
                {
                    "id": str(uuid4()),
                    "module_id": module_id,
                    "name": "Title",
                    "type": "text",
                    "position": 0,
                },
                {
                    "id": str(uuid4()),
                    "module_id": module_id,
                    "name": "Status",
                    "type": "select",
                    "position": 1,
                },
                {
                    "id": str(uuid4()),
                    "module_id": module_id,
                    "name": "Created",
                    "type": "date",
                    "position": 2,
                },
                {
                    "id": str(uuid4()),
                    "module_id": module_id,
                    "name": "Due",
                    "type": "datetime",
                    "position": 3,
                },
                {
                    "id": str(uuid4()),
                    "module_id": module_id,
                    "name": "Amount",
                    "type": "number",
                    "position": 4,
                },
            ]
    return departments, modules, fields


def _derived_home(department_id: str, **changes: Any) -> dict[str, Any]:
    """The empty home Dashboard that a publish derives for a new department (SD12)."""
    return {
        "id": str(uuid4()),
        "department_id": department_id,
        "name": "Derived dashboard",
        "position": 0,
        "refresh_cadence": "manual",
        "revision": 1,
        "is_home": True,
        "is_deleted": False,
        "widgets": [],
        **changes,
    }


def _page(items: list[dict[str, Any]], request: httpx.Request) -> httpx.Response:
    limit, offset = int(request.url.params["limit"]), int(request.url.params["offset"])
    rows = items[offset : offset + limit]
    pagination = {"limit": limit, "offset": offset, "count": len(rows), "total": len(items)}
    pagination["has_more"] = offset + len(rows) < len(items)
    return httpx.Response(200, json={"items": rows, "pagination": pagination})


def _login(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"authenticated": True, "setup_required": False},
        headers=[
            ("set-cookie", "slateops_access=sample-access; Path=/; HttpOnly"),
            ("set-cookie", "slateops_refresh=sample-refresh; Path=/api/auth; HttpOnly"),
            ("set-cookie", "slateops_csrf=sample-csrf; Path=/"),
        ],
    )


def test_openview_population_uses_ui_routes_and_captures_disabled_schedule_runs(
    tmp_path: Path,
) -> None:
    departments, modules, fields = _structure()
    # SD-C16: each department already has one Dashboard, the empty derived home.
    homes = {
        department["id"]: _derived_home(department["id"], revision=3)
        for department in departments.values()
    }

    seen: list[httpx.Request] = []
    created_id = 0

    def next_id() -> str:
        nonlocal created_id
        created_id += 1
        return str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/auth/login":
            return _login(request)
        assert request.headers["origin"] == ORIGIN
        body = json.loads(request.content) if request.content else {}
        if request.method == "POST" and request.url.path == "/api/views":
            return httpx.Response(201, json={"id": next_id(), "module_id": body["module_id"]})
        if request.method == "GET" and request.url.path == "/api/dashboards":
            department_id = request.url.params["department_id"]
            return _page([homes[department_id]], request)
        if request.method == "PATCH" and request.url.path.startswith("/api/dashboards/"):
            home = next(row for row in homes.values() if row["id"] == request.url.path[16:])
            widgets = [
                {"id": next_id(), "position": position}
                for position, _ in enumerate(body["widgets"])
            ]
            home.update(name=body["name"], widgets=widgets, revision=home["revision"] + 1)
            return httpx.Response(200, json=home)
        if request.method == "POST" and request.url.path == "/api/reports":
            return httpx.Response(201, json={"id": next_id(), "module_id": body["module_id"]})
        if request.method == "POST" and request.url.path.endswith("/runs"):
            report_id = request.url.path.split("/")[3]
            return httpx.Response(
                201,
                json={
                    "id": next_id(),
                    "report_id": report_id,
                    "row_count": 3,
                    "headings": ["Title"],
                    "created_at": "2026-09-29T00:00:00Z",
                },
            )
        if request.method == "POST" and request.url.path.endswith("/schedule"):
            return httpx.Response(
                201,
                json={
                    "id": next_id(),
                    "report_id": request.url.path.split("/")[3],
                    "enabled": False,
                },
            )
        raise AssertionError(f"Unexpected fixture request: {request.method} {request.url.path}")

    client = SampleClient(
        BASE_URL,
        ORIGIN,
        tmp_path / "private" / "requests.jsonl",
        transport=httpx.MockTransport(handler),
    )
    with client:
        assert client.login("sample@example.test", "synthetic-password").status_code == 200
        counts = populate_openview(
            client,
            departments=departments,
            modules=modules,
            fields=fields,
            anchor_date=date(2026, 9, 29),
            seed=42,
        )

    view_bodies = [
        json.loads(request.content)
        for request in seen
        if request.method == "POST" and request.url.path == "/api/views"
    ]
    dashboard_bodies = [
        json.loads(request.content)
        for request in seen
        if request.method == "PATCH" and request.url.path.startswith("/api/dashboards/")
    ]
    # SD12: population fills the derived home and never posts a second Dashboard.
    assert not [r for r in seen if r.method == "POST" and r.url.path == "/api/dashboards"]
    assert len(dashboard_bodies) == 6
    assert {body["revision"] for body in dashboard_bodies} == {3}
    assert sorted(body["name"] for body in dashboard_bodies) == [
        "Field overview",
        "Finance overview",
        "Inventory overview",
        "Purchasing overview",
        "Sales overview",
        "Service overview",
    ]
    report_bodies = [
        json.loads(request.content)
        for request in seen
        if request.method == "POST" and request.url.path == "/api/reports"
    ]
    run_requests = [request for request in seen if request.url.path.endswith("/runs")]
    schedule_bodies = [
        json.loads(request.content) for request in seen if request.url.path.endswith("/schedule")
    ]

    assert counts == {
        "views": 18,
        "dashboards": 6,
        "dashboard_widgets": 42,  # Seven widgets for each of the six departments.
        "reports": 12,
        "report_runs": 12,
        "schedules": 12,
        "disabled_schedules": 12,
    }
    assert len(view_bodies) == 18
    assert {body["presentation"]["layout"] for body in view_bodies} == {
        "table",
        "grid",
        "gallery",
    }
    assert all(body["definition"]["columns"] for body in view_bodies)
    # One grouped view per department: its Table view, by the status column.
    grouped = [body for body in view_bodies if body["presentation"]["group_by_field_id"]]
    assert [body["presentation"]["layout"] for body in grouped] == ["table"] * 6
    assert all(
        body["presentation"]["group_by_field_id"] in body["presentation"]["column_field_ids"]
        for body in grouped
    )
    for body in dashboard_bodies:
        DashboardUpdate.model_validate(body)
        widgets = body["widgets"]
        # Spec R8: the Overview preset, with the first 2 x 2 of rows 4-5 left free.
        assert [
            (widget["widget_type"], widget["grid_column"], widget["grid_row"])
            + (widget["column_span"], widget["row_span"])
            for widget in widgets
        ] == [
            ("summary", 0, 0, 1, 1),
            ("summary", 1, 0, 1, 1),
            ("summary", 2, 0, 1, 1),
            ("summary", 3, 0, 1, 1),
            ("chart", 0, 1, 2, 2),
            ("workload", 2, 1, 2, 2),
            ("records", 2, 3, 2, 2),
        ]
        queries = [widget["config"]["query"] for widget in widgets]
        assert any(query.get("aggregation") in {"sum", "average"} for query in queries)
        assert widgets[4]["config"]["chart_type"] == "line"
        assert queries[4]["mode"] == "date_series" and queries[4]["bucket"] == "month"
    assert len(report_bodies) == len(run_requests) == len(schedule_bodies) == 12
    assert len({request.headers["idempotency-key"] for request in run_requests}) == 12
    assert {body["cadence"] for body in schedule_bodies} == {"daily", "weekly"}
    assert all(body["enabled"] is False for body in schedule_bodies)


@pytest.mark.parametrize(
    "homes",
    (
        pytest.param([], id="missing-derived-home"),
        pytest.param([{}, {"is_home": False, "position": 1}], id="second-dashboard"),
        pytest.param([{"widgets": [{"id": str(uuid4())}]}], id="home-already-filled"),
        pytest.param([{"is_deleted": True}], id="archived-home"),
    ),
)
def test_openview_population_refuses_a_department_without_one_empty_derived_home(
    tmp_path: Path, homes: list[dict[str, Any]]
) -> None:
    """SD-C16: the pack fills the derived home; it never adds or overwrites another one."""
    departments, modules, fields = _structure()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return _login(request)
        if request.method == "POST" and request.url.path == "/api/views":
            return httpx.Response(201, json={"id": str(uuid4())})
        if request.method == "GET" and request.url.path == "/api/dashboards":
            department_id = request.url.params["department_id"]
            return _page([_derived_home(department_id, **row) for row in homes], request)
        raise AssertionError(f"Unexpected fixture request: {request.method} {request.url.path}")

    client = SampleClient(
        BASE_URL,
        ORIGIN,
        tmp_path / "private" / "requests.jsonl",
        transport=httpx.MockTransport(handler),
    )
    with client:
        assert client.login("sample@example.test", "synthetic-password").status_code == 200
        with pytest.raises(SampleContentError, match="derived home Dashboard"):
            populate_openview(
                client,
                departments=departments,
                modules=modules,
                fields=fields,
                anchor_date=date(2026, 9, 29),
                seed=42,
            )
