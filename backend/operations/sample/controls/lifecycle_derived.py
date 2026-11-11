"""Remove the lifecycle fixture's derived items so its department purge can run.

A publish gives the new fixture department its derived set (setup spec R1, R2). A department
with a category or channel cannot be purged (SD20, OQ2 a). So, after the reclose, the control
proves that blocker, then removes what an administrator can remove: it purges the derived
channel (archived by the close, R8), detaches the derived category from the department, and
deletes the three empty derived groups (R7). The department purge then runs as before.

The derived dashboard stays: it is not a blocker, and the purge removes it with the department.
Each preview token is used at once; only the blocked preview's challenge stays pending, and a
later preview displaces the oldest pending challenge, never the new one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

import httpx
from pydantic import ValidationError

from app.systems.sandbox.derived.actions import GROUP_LEVELS, derived_name
from app.systems.sandbox.lifecycle.schemas import (
    LifecycleBlockerCode,
    LifecycleImpactResponse,
    LifecyclePurgePreviewResponse,
)
from operations.sample.client import SampleClient, SampleClientError
from operations.sample.controls.sandbox import fixture_values
from operations.sample.packs.phase_types import PhaseAction
from operations.sample.phases.actions import (
    PhaseExecutionContext,
    PhaseSubstep,
    SamplePhaseActionError,
    _read_json,
    _record_mapping,
    _request,
)

DERIVED_KEY = "sandbox_lifecycle_derived"
GROUP_ROLES = tuple(GROUP_LEVELS)
Contract = list[tuple[str, str, str, int]]


class Journey(Protocol):
    action: PhaseAction
    context: PhaseExecutionContext
    evidence: list[dict[str, object]]
    mappings: list[dict[str, str]]
    on_substep: PhaseSubstep | None

    @property
    def ids(self) -> dict[str, str]: ...

    def request(
        self,
        path: str,
        step: str,
        *,
        method: str = "GET",
        expected: int = 200,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response: ...

    def read(
        self, path: str, step: str, *, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]: ...


def derived_release_contract(derived: Mapping[str, str], department_id: str) -> Contract:
    """The writes between the reclose and the department purge, in order."""
    channel = f"/api/comms/conversations/{derived['channel']}"
    return [
        (
            "preview_blocked_purge_department",
            "POST",
            f"/api/departments/{department_id}/purge/preview",
            200,
        ),
        ("preview_purge_derived_channel", "POST", channel + "/purge/preview", 200),
        ("purge_derived_channel", "POST", channel + "/purge", 200),
        ("detach_derived_category", "PUT", f"/api/comms/categories/{derived['category']}", 200),
        *(
            (f"delete_derived_{role}", "DELETE", f"/api/access/groups/{derived[role]}", 204)
            for role in GROUP_ROLES
        ),
    ]


def _fail(message: str, step: str) -> SamplePhaseActionError:
    return SamplePhaseActionError(message, step=step)


def _items(page: Mapping[str, Any], step: str) -> list[dict[str, Any]]:
    rows, paging = page.get("items"), page.get("pagination")
    if (
        not isinstance(rows, list)
        or not isinstance(paging, Mapping)
        or paging.get("has_more") is not False
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise _fail("Derived item search returned an unexpected page", step)
    return cast(list[dict[str, Any]], rows)


def _one(rows: list[dict[str, Any]], step: str) -> dict[str, Any]:
    if len(rows) != 1 or not isinstance(rows[0].get("id"), str):
        raise _fail("Expected exactly one derived item of the fixture department", step)
    return rows[0]


def _write(
    run: Journey,
    method: str,
    path: str,
    step: str,
    *,
    expected: int = 200,
    body: Mapping[str, Any] | None = None,
    if_match: str | None = None,
) -> httpx.Response:
    return _request(
        run.action,
        run.context,
        run.evidence,
        actor_key=run.action.actor_key,
        method=method,
        path=path,
        step=step,
        expected=expected,
        on_substep=run.on_substep,
        json_body=body,
        headers={"If-Match": if_match} if if_match else None,
    )


def _etag(response: httpx.Response, step: str) -> str:
    etag = response.headers.get("ETag")
    if not isinstance(etag, str) or not etag:
        raise _fail("Derived item readback had no ETag", step)
    return etag


def _require_comms_blocker(response: httpx.Response, department_id: str, step: str) -> None:
    try:
        impact: LifecycleImpactResponse = LifecyclePurgePreviewResponse.model_validate_json(
            response.content
        ).impact
    except ValidationError:
        raise _fail("Lifecycle preview was invalid", step) from None
    if (
        str(impact.target_id) != department_id
        or impact.operation.value != "purge"
        or not impact.blockers
        or {row.code for row in impact.blockers} != {LifecycleBlockerCode.COMMS_DEPARTMENT_CONTENT}
        or impact.external_impacts
        or impact.key_strips
    ):
        raise _fail("Department purge preview did not name its OpenComms content", step)


def release_derived_items(run: Journey, dataset: Any) -> None:
    """Prove the purge blocker, then remove the fixture's derived channel, category and groups."""
    department_id = run.ids["department"]
    name = str(fixture_values(dataset)["department_name"])
    client: SampleClient = run.context.clients[run.action.actor_key]

    def keep(role: str, server_id: str) -> None:
        _record_mapping(run.context, client, DERIVED_KEY, role, server_id, run.mappings)

    step = "preview_blocked_purge_department"
    response = _write(run, "POST", f"/api/departments/{department_id}/purge/preview", step)
    _require_comms_blocker(response, department_id, step)

    step = "find_derived_category"
    search = {"search": name, "limit": 100, "offset": 0}
    page = run.read("/api/comms/categories", step, params=search)
    category = _one(
        [row for row in _items(page, step) if row.get("department_id") == department_id], step
    )
    if category.get("name") != derived_name("category", name):
        raise _fail("Derived category name differed", step)

    step = "find_derived_channel"
    page = run.read("/api/comms/conversations", step, params={**search, "archived": "true"})
    channel = _one(
        [
            row
            for row in _items(page, step)
            if row.get("kind") == "channel"
            and row.get("scope") == "department"
            and row.get("department_id") == department_id
        ],
        step,
    )
    if (
        channel.get("category_id") != category["id"]
        or channel.get("name") != derived_name("channel", name)
        or not channel.get("archived_at")
    ):
        raise _fail("Derived channel is not the archived channel of the derived category", step)
    keep("channel", channel["id"])
    keep("category", category["id"])

    path, step = f"/api/comms/conversations/{channel['id']}", "preview_purge_derived_channel"
    preview = _read_json(_write(run, "POST", path + "/purge/preview", step), step=step)
    # The derived channel holds no message or file; the control never purges content.
    if (
        preview.get("conversation_id") != channel["id"]
        or preview.get("message_count") != 0
        or preview.get("file_count") != 0
        or not isinstance(preview.get("token"), str)
        or preview.get("confirmation_name") != channel["name"]
    ):
        raise _fail("Derived channel purge preview was not an empty channel", step)
    body = {
        "token": preview["token"],
        "confirmation_name": preview["confirmation_name"],
        "password": run.context.admin_password,
    }
    step = "purge_derived_channel"
    result = _read_json(_write(run, "POST", path + "/purge", step, body=body), step=step)
    if result.get("conversation_id") != channel["id"] or result.get("purged_message_count") != 0:
        raise _fail("Derived channel purge result differed", step)

    path, step = f"/api/comms/categories/{category['id']}", "read_derived_category"
    response = run.request(path, step)
    current = _read_json(response, step=step)
    etag = _etag(response, step)
    body = {"name": current.get("name"), "position": current.get("position"), "department_id": None}
    step = "detach_derived_category"
    response = _write(run, "PUT", path, step, body=body, if_match=etag)
    if _read_json(response, step=step).get("department_id") is not None:
        raise _fail("Derived category is still bound to the department", step)

    step = "find_derived_groups"
    groups = _items(run.read("/api/access/groups", step, params=search), step)
    for role, level in GROUP_LEVELS.items():
        group = _one(
            [
                row
                for row in groups
                if row.get("name") == derived_name(role, name)
                and row.get("member_ids") == []
                and [
                    (item.get("department_id"), item.get("module_id"), item.get("level"))
                    for item in row.get("access") or []
                    if isinstance(item, dict)
                ]
                == [(department_id, None, level.value)]
            ],
            step,
        )
        keep(role, group["id"])
        path = f"/api/access/groups/{group['id']}"
        response = run.request(path, f"read_derived_{role}")
        etag = _etag(response, f"read_derived_{role}")
        _write(run, "DELETE", path, f"delete_derived_{role}", expected=204, if_match=etag)


def verify_released(admin: SampleClient, derived: Mapping[str, str]) -> bool:
    """Final readback: the channel is gone, the category is detached, the groups are deleted."""
    try:
        if set(derived) != {"channel", "category", *GROUP_ROLES}:
            return False
        channel = admin.request("GET", f"/api/comms/conversations/{derived['channel']}")
        category = admin.request("GET", f"/api/comms/categories/{derived['category']}")
        if channel.status_code != 404 or category.status_code != 200:
            return False
        if category.json().get("department_id") is not None:
            return False
        for role in GROUP_ROLES:
            response = admin.request("GET", f"/api/access/groups/{derived[role]}")
            group = response.json()
            if (
                response.status_code != 200
                or not isinstance(group, dict)
                or group.get("id") != derived[role]
                or group.get("is_deleted") is not True
                or group.get("member_ids") != []
                or group.get("access") != []
            ):
                return False
    except (ValueError, AttributeError, SampleClientError):
        return False
    return True
