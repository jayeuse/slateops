"""One throwaway sheet on an existing record that calls each sheet route once (spec D10).

Sample content for sheets is deferred (REQ-0027). This control only proves the routes on a
real run: the administrator creates a blank sheet on one record, edits its columns and rows,
shares it with one member and takes the share back, reads its history, people and lists,
exports it, reads a one-cell workbook and matches one key, checks a member's sheet impact,
reads Appears in, takes a presence token, deletes and restores the sheet, and finally
deletes it again.
"""

import io
from collections.abc import Mapping
from typing import Any

from xlsxwriter import Workbook

from operations.sample.blueprint import SampleDataset
from operations.sample.packs.phase_types import PhaseAction, PhaseJsonValue
from operations.sample.phases.actions import (
    PhaseExecutionContext,
    PhaseSubstep,
    SamplePhaseActionError,
    _id,
    _mapped_id,
    _read_json,
    _request,
    _result,
)

OPERATION = "worksheet_routes"
S = "/api/worksheets/{worksheet_id}"
SHEET_ROUTES = frozenset(
    {
        ("GET", "/api/worksheets"),
        ("POST", "/api/worksheets"),
        ("GET", S),
        ("PATCH", S),
        ("DELETE", S),
        ("POST", S + "/restore"),
        ("GET", "/api/records/{record_id}/worksheets"),
        ("GET", "/api/modules/{module_id}/worksheets"),
        ("PUT", S + "/structure"),
        ("POST", S + "/rows/query"),
        ("POST", S + "/rows"),
        ("PATCH", S + "/rows/{row_id}"),
        ("DELETE", S + "/rows/{row_id}"),
        ("POST", S + "/rows/batch"),
        ("GET", S + "/people"),
        ("GET", S + "/history"),
        ("GET", S + "/shares"),
        ("POST", S + "/shares"),
        ("PATCH", S + "/shares/{share_id}"),
        ("DELETE", S + "/shares/{share_id}"),
        ("GET", S + "/share-candidates"),
        ("POST", S + "/export"),
        ("GET", "/api/users/{user_id}/worksheet-impact"),
        ("POST", "/api/worksheet-import-files"),
        ("POST", "/api/worksheet-import-matches"),
        ("GET", "/api/records/{record_id}/worksheet-rows"),
        ("POST", S + "/presence-token"),
    }
)


def plan_worksheet_controls(dataset: SampleDataset) -> tuple[PhaseAction, ...]:
    """The first record of a module with a text field, and a member no phase changes."""

    pack = dataset.organization
    if pack.phases is None:
        return ()
    from operations.sample.phases.plan import plan_phases

    modules = {module.key: module for module in pack.catalog.modules}
    record = next(
        row for row in dataset.records
        if any(field.type == "Text" for field in modules[row.module_key].fields)
    )
    field = next(item for item in modules[record.module_key].fields if item.type == "Text")
    changed = {key for row in plan_phases(dataset) for key in (row.actor_key, row.target_key)}
    member = next(
        person.key for person in pack.actors.people
        if person.role == "member" and person.status == "active" and person.key not in changed
    )
    values: dict[str, PhaseJsonValue] = {
        "operation": OPERATION,
        "record_key": record.logical_id,
        "module_key": record.module_key,
        "field_key": f"{record.module_key}:{field.key}",
        "member_key": member,
    }
    return (
        PhaseAction(
            key="control:openview:sheet-routes",
            phase="reorganization",
            kind="openview_controls",
            actor_key="admin",
            target_key=record.logical_id,
            values=values,
            expected_status=200,
            expected_detail=None,
            expected_end_state={"sheet_routes": len(SHEET_ROUTES)},
        ),
    )


def _workbook() -> bytes:
    output = io.BytesIO()
    with Workbook(output, {"in_memory": True}) as book:
        book.add_worksheet("Sheet1").write_row(0, 0, ["Key", "Note"])
    return output.getvalue()


def _etag(response: Any, step: str) -> str:
    etag = response.headers.get("ETag")
    if not isinstance(etag, str) or not etag:
        raise SamplePhaseActionError("The sheet response has no ETag", step=step)
    return etag


def execute_worksheet_control(
    action: PhaseAction,
    dataset: SampleDataset,
    context: PhaseExecutionContext,
    *,
    on_substep: PhaseSubstep | None = None,
) -> dict[str, object]:
    if action not in plan_worksheet_controls(dataset):
        raise SamplePhaseActionError("Unsupported sheet route control", step=action.key)
    values: Mapping[str, Any] = action.values
    record = _mapped_id(context, "record", str(values["record_key"]), step=action.key)
    module = _mapped_id(context, "modules", str(values["module_key"]), step=action.key)
    field = _mapped_id(context, "fields", str(values["field_key"]), step=action.key)
    member = _id(context.user_ids, str(values["member_key"]), label="user", step=action.key)
    evidence: list[dict[str, object]] = []
    routes: set[tuple[str, str]] = set()

    def call(step: str, method: str, path: str, template: str, expected: int,
             **options: Any) -> Any:
        routes.add((method, template))
        return _request(action, context, evidence, actor_key="admin", method=method,
                        path=path, step=step, expected=expected, on_substep=on_substep,
                        **options)

    created = call("create_sheet", "POST", "/api/worksheets", "/api/worksheets", 201,
                   json_body={"record_id": record, "title": "Route check",
                              "source": {"kind": "blank"}})
    sheet = _id(_read_json(created, step="create_sheet"), "id", label="sheet",
                step="create_sheet")
    base = f"/api/worksheets/{sheet}"
    etag = _etag(created, "create_sheet")
    call("read_sheet", "GET", base, S, 200)
    call("list_mine", "GET", "/api/worksheets", "/api/worksheets", 200)
    call("list_record", "GET", f"/api/records/{record}/worksheets",
         "/api/records/{record_id}/worksheets", 200)
    call("list_module", "GET", f"/api/modules/{module}/worksheets",
         "/api/modules/{module_id}/worksheets", 200)
    etag = _etag(call("rename", "PATCH", base, S, 200, json_body={"title": "Route check 2"},
                      headers={"If-Match": etag}), "rename")
    saved = call("save_structure", "PUT", f"{base}/structure", S + "/structure", 200,
                 headers={"If-Match": etag}, json_body={
                     "columns": [{"key": "c1", "name": "Note", "type": "text"}],
                     "groups": [], "totals": {}})
    etag = _etag(saved, "save_structure")
    revision = int(etag.strip('"').rpartition(":")[2])
    row = call("add_row", "POST", f"{base}/rows", S + "/rows", 201,
               json_body={"cells": {"c1": "first"}})
    row_id = _id(_read_json(row, step="add_row"), "id", label="row", step="add_row")
    call("query_rows", "POST", f"{base}/rows/query", S + "/rows/query", 200, json_body={})
    patched = call("patch_row", "PATCH", f"{base}/rows/{row_id}", S + "/rows/{row_id}", 200,
                   json_body={"cells": {"c1": {"value": "second",
                                               "expected": {"value": "first"}}}})
    call("batch_rows", "POST", f"{base}/rows/batch", S + "/rows/batch", 200,
         json_body={"structure_revision": revision, "creates": [{"cells": {"c1": "third"}}]})
    call("delete_row", "DELETE", f"{base}/rows/{row_id}", S + "/rows/{row_id}", 204,
         headers={"If-Match": _etag(patched, "patch_row")})
    shared = call("share", "POST", f"{base}/shares", S + "/shares", 201,
                  json_body={"subject": "user", "user_id": member, "level": "view"})
    share = _id(_read_json(shared, step="share"), "id", label="share", step="share")
    call("list_shares", "GET", f"{base}/shares", S + "/shares", 200)
    call("change_share", "PATCH", f"{base}/shares/{share}", S + "/shares/{share_id}", 200,
         json_body={"level": "edit"})
    call("share_candidates", "GET", f"{base}/share-candidates", S + "/share-candidates", 200,
         params={"q": "a"})
    call("unshare", "DELETE", f"{base}/shares/{share}", S + "/shares/{share_id}", 204)
    call("people", "GET", f"{base}/people", S + "/people", 200)
    call("history", "GET", f"{base}/history", S + "/history", 200)
    call("export", "POST", f"{base}/export", S + "/export", 200, json_body={"format": "csv"})
    call("import_file", "POST", "/api/worksheet-import-files", "/api/worksheet-import-files",
         200, params={"tab": 0}, content=_workbook(),
         headers={"Content-Type": "application/octet-stream"})
    call("import_matches", "POST", "/api/worksheet-import-matches",
         "/api/worksheet-import-matches", 200,
         json_body={"module_id": module, "field_id": field, "keys": ["Route check"]})
    call("impact", "GET", f"/api/users/{member}/worksheet-impact",
         "/api/users/{user_id}/worksheet-impact", 200)
    call("appears_in", "GET", f"/api/records/{record}/worksheet-rows",
         "/api/records/{record_id}/worksheet-rows", 200)
    call("presence_token", "POST", f"{base}/presence-token", S + "/presence-token", 200)
    etag = _etag(call("read_before_delete", "GET", base, S, 200), "read_before_delete")
    call("delete_sheet", "DELETE", base, S, 204, headers={"If-Match": etag})
    restored = call("restore_sheet", "POST", f"{base}/restore", S + "/restore", 200)
    call("remove_sheet", "DELETE", base, S, 204,
         headers={"If-Match": _etag(restored, "restore_sheet")})
    if routes != SHEET_ROUTES:
        raise SamplePhaseActionError("The sheet control missed a sheet route", step=action.key)
    return _result(action, context, evidence, [], extra={"sheet_routes": len(routes)})
