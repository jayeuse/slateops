"""The lifecycle fixture's derived set on the wire (setup spec R2, SD20, OQ2 a, R7).

A publish that creates the fixture department also creates its derived category, channel and
three empty groups. While the department has a category or channel, its purge preview names
``comms_department_content`` and the purge is refused, as the server does.
"""

from __future__ import annotations

import json
import re
from uuid import uuid4

import httpx

ORG_ID = "0e8f6a64-2d0c-4a59-9a43-8f1f2b4c6d71"
STAMP = "2026-10-03T00:00:00Z"
LEVELS = {"managers": "manage", "members": "write", "viewers": "read"}


def _page(items):
    count = len(items)
    pagination = {"limit": 100, "offset": 0, "count": count, "total": count, "has_more": False}
    return httpx.Response(200, json={"items": items, "pagination": pagination})


class DerivedSetWire:
    """State of the fixture's derived items; the lifecycle wire's ``fault`` applies here too."""

    def __init__(self, lifecycle):
        self.lifecycle, self._state, self.challenges = lifecycle, None, {}

    @property
    def fault(self):
        return self.lifecycle.fault

    @property
    def state(self):
        board = self.lifecycle.board
        if self._state is None and board is not None:
            department_id, name = board["department_id"], board["name"]
            category = {"id": str(uuid4()), "org_id": ORG_ID, "name": name, "position": 7,
                        "department_id": department_id, "created_at": STAMP, "updated_at": STAMP,
                        "revision": 1}  # fmt: skip
            groups = {
                role: {"id": str(uuid4()), "name": f"{name} {role}", "level": level,
                       "is_deleted": False, "revision": 1}  # fmt: skip
                for role, level in LEVELS.items()
            }
            channel = {"id": str(uuid4()), "name": name, "purged": False}
            self._state = {"department_id": department_id, "name": name, "category": category,
                           "channel": channel, "groups": groups}  # fmt: skip
        return self._state

    def blockers(self, department_id):
        state = self.state
        if state is None or state["department_id"] != department_id:
            return []
        if self.fault == "derived_missing_blocker":
            return []
        if state["category"]["department_id"] is None and state["channel"]["purged"]:
            return []
        return [
            {
                "code": "comms_department_content",
                "entity_type": "departments",
                "entity_id": department_id,
                "detail": "Move or remove the department's OpenComms category and channels",
            }
        ]

    def _closed(self):
        row = self.lifecycle.live.get(self.state["department_id"])
        return row is None or row["is_deleted"]

    def _channel(self):
        state, channel = self.state, self.state["channel"]
        return {"id": channel["id"], "org_id": ORG_ID, "created_at": STAMP, "updated_at": STAMP,
                "archived_at": STAMP if self._closed() else None, "level": "manage",
                "member_count": 0, "member_role": None, "kind": "channel", "name": channel["name"],
                "topic": "", "category_id": state["category"]["id"], "position": 0,
                "thread_branches": "all", "scope": "department",
                "department_id": state["department_id"]}  # fmt: skip

    def _group(self, role):
        group, department_id = self.state["groups"][role], self.state["department_id"]
        access = [] if group["is_deleted"] else [
            {"department_id": department_id, "module_id": None, "level": group["level"]}
        ]  # fmt: skip
        members = [str(uuid4())] if self.fault == "derived_group_member" else []
        return {"id": group["id"], "name": group["name"], "description": "",
                "revision": group["revision"], "member_ids": members, "access": access,
                "created_at": STAMP, "updated_at": STAMP, "deleted_at": STAMP if group["is_deleted"]
                else None, "is_deleted": group["is_deleted"], "performed_by": None}  # fmt: skip

    def handle(self, request):
        path, method = request.url.path, request.method
        if not path.startswith(("/api/comms/", "/api/access/groups")) or self.state is None:
            return None
        state, headers = self.state, {"X-Request-ID": str(uuid4())}
        category, channel = state["category"], state["channel"]
        category_path = f"/api/comms/categories/{category['id']}"
        channel_path = f"/api/comms/conversations/{channel['id']}"
        if (method, path) == ("GET", "/api/comms/categories"):
            assert request.url.params["search"] == state["name"]
            decoy = {**category, "id": str(uuid4()), "department_id": None}
            return _page([decoy, dict(category)])
        if path == category_path:
            etag = f'W/"category-{category["revision"]}"'
            if method == "PUT":
                body = json.loads(request.content)
                assert request.headers["If-Match"] == etag and channel["purged"]
                assert body == {"name": category["name"], "position": category["position"],
                                "department_id": None}  # fmt: skip
                category.update(department_id=None, revision=category["revision"] + 1)
                return httpx.Response(200, headers=headers, json=category)
            if self.lifecycle.final_mode and self.fault == "final_derived":
                bound = {**category, "department_id": state["department_id"]}
                return httpx.Response(200, json=bound)
            return httpx.Response(200, headers={"ETag": etag}, json=category)
        if (method, path) == ("GET", "/api/comms/conversations"):
            assert request.url.params["archived"] == "true"
            listed = not channel["purged"] and self._closed()
            return _page([self._channel()] if listed else [])
        if path == channel_path:
            return httpx.Response(404 if channel["purged"] else 200, json=self._channel())
        if path == channel_path + "/purge/preview":
            assert self._closed() and not channel["purged"]
            token = str(uuid4())
            self.challenges[token] = channel["id"]
            messages = 1 if self.fault == "derived_channel_messages" else 0
            return httpx.Response(200, headers=headers, json={
                "org_id": ORG_ID, "conversation_id": channel["id"], "message_count": messages,
                "file_count": 0, "max_seq": messages, "impact_digest": "d" * 64, "token": token,
                "expires_at": "2099-01-01T00:00:00Z", "confirmation_name": channel["name"],
                "last_successful_backup_at": None,
            })  # fmt: skip
        if path == channel_path + "/purge":
            body = json.loads(request.content)
            assert self.challenges.pop(body["token"]) == channel["id"]
            assert body["confirmation_name"] == channel["name"]
            assert body["password"] == "fixture-admin-password"
            channel["purged"] = True
            return httpx.Response(200, headers=headers, json={
                "org_id": ORG_ID, "conversation_id": channel["id"], "operation_id": str(uuid4()),
                "purged_message_count": 0, "purged_file_count": 0,
            })  # fmt: skip
        if (method, path) == ("GET", "/api/access/groups"):
            assert request.url.params["search"] == state["name"]
            live = [role for role, group in state["groups"].items() if not group["is_deleted"]]
            return _page([self._group(role) for role in live])
        match = re.fullmatch(r"/api/access/groups/([0-9a-f-]{36})", path)
        role = next(
            (role for role, group in state["groups"].items() if match and group["id"] == match[1]),
            None,
        )
        if role is None:
            return None
        group, etag = state["groups"][role], f'"group-{state["groups"][role]["revision"]}"'
        if method == "DELETE":
            assert request.headers["If-Match"] == etag and not group["is_deleted"]
            group.update(is_deleted=True, revision=group["revision"] + 1)
            return httpx.Response(204, headers=headers)
        return httpx.Response(200, headers={"ETag": etag}, json=self._group(role))
