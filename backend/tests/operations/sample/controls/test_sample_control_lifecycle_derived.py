"""The department purge request contract with and without the fixture's derived set."""

from __future__ import annotations

from operations.sample.controls.lifecycle import lifecycle_request_contract

IDS = {"department": "d1", "module": "m1", "title_field": "t1", "field": "f1", "board": "b1"}
DERIVED = {
    "channel": "c1",
    "category": "k1",
    "managers": "g1",
    "members": "g2",
    "viewers": "g3",
}


def test_department_purge_contract_removes_the_derived_set_first_and_keeps_legacy_runs() -> None:
    """SD20, OQ2 (a): a run with a derived set proves the blocker and removes the set first.

    A run populated before derived setup (SD5) has no derived mappings and keeps its contract.
    """
    reclose = [
        ("preview_reclose_department", "POST", "/api/departments/d1/close/preview", 200),
        ("reclose_department", "POST", "/api/departments/d1/close", 200),
    ]
    purge = [
        ("preview_purge_department", "POST", "/api/departments/d1/purge/preview", 200),
        ("purge_department", "POST", "/api/departments/d1/purge", 200),
    ]
    assert lifecycle_request_contract("purge_department", IDS) == reclose + purge
    assert lifecycle_request_contract("purge_department", IDS, DERIVED) == [
        *reclose,
        ("preview_blocked_purge_department", "POST", "/api/departments/d1/purge/preview", 200),
        (
            "preview_purge_derived_channel",
            "POST",
            "/api/comms/conversations/c1/purge/preview",
            200,
        ),
        ("purge_derived_channel", "POST", "/api/comms/conversations/c1/purge", 200),
        ("detach_derived_category", "PUT", "/api/comms/categories/k1", 200),
        ("delete_derived_managers", "DELETE", "/api/access/groups/g1", 204),
        ("delete_derived_members", "DELETE", "/api/access/groups/g2", 204),
        ("delete_derived_viewers", "DELETE", "/api/access/groups/g3", 204),
        *purge,
    ]
    # A module purge never carries derived steps.
    assert len(lifecycle_request_contract("purge_module", IDS, DERIVED)) == 4
