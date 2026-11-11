"""Usage read boundaries, visible pagination and retained-reference archive refusal."""

from uuid import UUID

import pytest
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.policy.models import AccessLevel
from app.systems.openview.charts.models import Chart
from app.systems.openview.dashboards.models import Dashboard, DashboardWidget
from tests.charts.chart_route_support import chart_world as chart_world
from tests.rbac.support import add_department, make_group_access

pytestmark = pytest.mark.integration


def _consumers(world, chart_id):
    # Owned retained references model a post-move foreign Dashboard too. This
    # does not claim B2's public attachment behavior or a sample/live write.
    visible_dashboard = Dashboard(
        org_id=world.module.org_id,
        department_id=world.module.department_id,
        name="Visible %_ dashboard",
    )
    second_dashboard = Dashboard(
        org_id=world.module.org_id,
        department_id=world.module.department_id,
        name="Visible second dashboard",
    )
    private_dashboard = Dashboard(
        org_id=world.other_module.org_id,
        department_id=world.other_module.department_id,
        name="PRIVATE DASHBOARD CANARY",
        is_deleted=True,
        deleted_at=utc_now(),
    )
    world.db.add_all([visible_dashboard, second_dashboard, private_dashboard])
    world.db.flush()
    refs = []
    for dashboard, position, deleted in [
        (visible_dashboard, 0, False),
        (visible_dashboard, 1, True),
        (second_dashboard, 0, False),
        (private_dashboard, 0, False),
    ]:
        row = DashboardWidget(
            org_id=dashboard.org_id,
            dashboard_id=dashboard.id,
            position=position,
            widget_type="chart",
            chart_id=chart_id,
            config=None,
            is_deleted=deleted,
            deleted_at=utc_now() if deleted else None,
        )
        refs.append(row)
        world.db.add(row)
    world.db.commit()
    return visible_dashboard, second_dashboard, private_dashboard, refs


def test_usage_filters_distinct_consumers_before_count_page_and_search(chart_world):
    world = chart_world
    with world.client("manager") as client:
        created = client.post("/api/charts", json=world.body()).json()
        chart_id = UUID(created["id"])
        dashboard, second, hidden_dashboard, _ = _consumers(world, chart_id)
        expected = {("dashboard", str(dashboard.id)), ("dashboard", str(second.id))}
        seen = set()
        for offset in (0, 1):
            response = client.get(
                f"/api/charts/{chart_id}/usage", params={"limit": 1, "offset": offset}
            )
            assert response.status_code == 200
            body = response.json()
            seen.add((body["items"][0]["kind"], body["items"][0]["id"]))
            assert body["pagination"] == {
                "limit": 1,
                "offset": offset,
                "count": 1,
                "total": 2,
                "total_is_capped": False,
                "has_more": offset == 0,
            }
            assert body["has_restricted_usage"] is True
            for canary in ("PRIVATE", str(hidden_dashboard.id)):
                assert canary not in response.text
        assert seen == expected
        searched = client.get(f"/api/charts/{chart_id}/usage", params={"search": "%_"}).json()
        assert [item["id"] for item in searched["items"]] == [str(dashboard.id)]
        assert searched["pagination"]["total"] == 1 and searched["has_restricted_usage"] is True
        empty = client.get(f"/api/charts/{chart_id}/usage", params={"search": "No match"}).json()
        assert empty["items"] == [] and empty["pagination"]["total"] == 0
        assert empty["has_restricted_usage"] is True
    with world.client("admin") as admin:
        response = admin.get(f"/api/charts/{chart_id}/usage")
        assert response.json()["pagination"]["total"] == 3
        assert response.json()["has_restricted_usage"] is False
        assert {item["id"] for item in response.json()["items"]} == {
            str(item.id) for item in (dashboard, second, hidden_dashboard)
        }


def test_inaccessible_and_deleted_references_still_block_archive_without_leaking(chart_world):
    world = chart_world
    with world.client("manager") as client:
        created = client.post("/api/charts", json=world.body()).json()
        chart_id = UUID(created["id"])
        dashboard, second, hidden_dashboard, refs = _consumers(world, chart_id)
        blocked = client.delete(f"/api/charts/{chart_id}", params={"revision": 1})
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["code"] == "chart_in_use"
        assert detail["usage"]["pagination"]["total"] == 2
        assert detail["usage"]["has_restricted_usage"] is True
        for canary in ("PRIVATE", str(hidden_dashboard.id)):
            assert canary not in blocked.text
        for row in refs:
            if row.dashboard_id in {dashboard.id, second.id}:
                world.db.delete(row)
        world.db.commit()
        still_blocked = client.delete(f"/api/charts/{chart_id}", params={"revision": 1})
        assert still_blocked.status_code == 409
        usage = still_blocked.json()["detail"]["usage"]
        assert usage["items"] == [] and usage["pagination"]["total"] == 0
        assert usage["has_restricted_usage"] is True
        for row in refs:
            if row.dashboard_id == hidden_dashboard.id:
                world.db.delete(row)
        world.db.commit()
        assert client.delete(f"/api/charts/{chart_id}", params={"revision": 1}).status_code == 204
        world.db.expire_all()
        assert world.db.get(Chart, chart_id).revision == 2


def test_referenced_chart_can_change_visualization_but_not_widget_category(chart_world):
    world = chart_world
    with world.client("manager") as client:
        created = client.post("/api/charts", json=world.body()).json()
        chart_id = UUID(created["id"])
        _consumers(world, chart_id)
        pie = client.patch(f"/api/charts/{chart_id}", json={"revision": 1, "chart_type": "pie"})
        assert pie.status_code == 200 and pie.json()["revision"] == 2
        records = {"module_id": str(world.module.id), "definition": {"columns": [], "filters": []}}
        rejected = client.patch(
            f"/api/charts/{chart_id}",
            json={"revision": 2, "chart_type": "records", "query": records},
        )
        assert rejected.status_code == 409 and "PRIVATE" not in rejected.text
        assert client.get(f"/api/charts/{chart_id}").json()["chart_type"] == "pie"


def test_usage_lists_only_open_department_dashboards_for_non_administrators(chart_world):
    """OQ1-C3: chart usage lists only dashboards of open departments for non-administrators."""

    world = chart_world
    closed = add_department(world.db, "Closed consumer " + uuid7().hex)
    make_group_access(world.db, [world.users["manager"]], closed, level=AccessLevel.READ)
    world.db.flush()
    with world.client("manager") as client:
        chart_id = UUID(client.post("/api/charts", json=world.body()).json()["id"])
        open_dashboard = Dashboard(
            org_id=world.module.org_id,
            department_id=world.module.department_id,
            name="Open consumer",
        )
        closed_dashboard = Dashboard(
            org_id=closed.org_id, department_id=closed.id, name="CLOSED CONSUMER CANARY"
        )
        world.db.add_all([open_dashboard, closed_dashboard])
        world.db.flush()
        world.db.add_all(
            DashboardWidget(
                org_id=dashboard.org_id,
                dashboard_id=dashboard.id,
                position=0,
                widget_type="chart",
                chart_id=chart_id,
                config=None,
            )
            for dashboard in (open_dashboard, closed_dashboard)
        )
        closed.is_deleted = True
        closed.deleted_at = utc_now()
        world.db.commit()

        listed = client.get(f"/api/charts/{chart_id}/usage")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [str(open_dashboard.id)]
        assert listed.json()["pagination"]["total"] == 1
        assert listed.json()["has_restricted_usage"] is True
        blocked = client.delete(f"/api/charts/{chart_id}", params={"revision": 1})
        assert blocked.status_code == 409
        usage = blocked.json()["detail"]["usage"]
        assert [item["id"] for item in usage["items"]] == [str(open_dashboard.id)]
        for response in (listed, blocked):
            for canary in ("CLOSED CONSUMER", str(closed_dashboard.id)):
                assert canary not in response.text
    with world.client("admin") as admin:
        everything = admin.get(f"/api/charts/{chart_id}/usage").json()
        assert {item["id"] for item in everything["items"]} == {
            str(open_dashboard.id),
            str(closed_dashboard.id),
        }
        assert everything["has_restricted_usage"] is False
