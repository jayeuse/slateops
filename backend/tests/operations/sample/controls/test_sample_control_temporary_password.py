"""Temporary-password control faults use a closed wire; live runs own provider proof."""

import json

import pytest

from operations.sample.client import SampleWriteOutcomeUnknown
from operations.sample.controls.actions import execute_control_action, plan_controls
from operations.sample.controls.request_verification import verify_request_evidence
from operations.sample.controls.temporary_password import CONTROL_ROUTES
from operations.sample.phases.actions import SamplePhaseActionError
from operations.sample.verification.route_coverage import read_route_evidence
from tests.operations.sample.controls.sample_temporary_password_wire import (
    OPERATION,
    PASSWORD,
    dataset,
    journey,
    planned,
)

ROUTE = ("POST", "/api/users/{user_id}/temporary-password")


@pytest.mark.parametrize("pack", ("harbor", "school"))
def test_plan_gives_the_people_target_one_temporary_password_journey(pack):
    source = dataset(pack)
    action = planned(source)
    operations = [row.values["operation"] for row in plan_controls(source)]
    people = next(
        row for row in plan_controls(source) if row.values["operation"] == "review_people_security"
    )
    assert action.kind == "access_controls"
    assert action.actor_key == action.target_key == people.target_key
    assert action.values == {"operation": OPERATION, "admin_steps": ["set_temporary_password"]}
    assert operations.index(OPERATION) == operations.index("review_people_security") + 1


@pytest.mark.parametrize("pack", ("harbor", "school"))
def test_temporary_password_journey_ends_with_the_original_password_and_no_mark(tmp_path, pack):
    with journey(tmp_path, pack) as (source, action, context, server):
        result = execute_control_action(action, source, context)
        assert result["outcome"] == "completed"
        assert CONTROL_ROUTES == frozenset({ROUTE})
        assert result["original_password_restored"] is True
        assert result["password_change_required"] is False
        assert server.writes == ["temporary", "change"] and len(server.chosen) == 1
        assert server.password == PASSWORD and server.marked is False
        primary = context.clients[action.target_key]
        me = primary.request("GET", "/api/auth/me").json()
        assert me["id"] == server.target and me["password_change_required"] is False
        assert [row["step"] for row in result["request_evidence"]] == [
            "set_temporary_password",
            "login_temporary_password",
            "change_temporary_password",
            "logout_temporary_session",
            "login_original_password",
        ]
        issues, observed = [], {"control_requests_verified": 0}
        verify_request_evidence(
            source,
            {"actor_ids": {action.target_key: server.target}},
            action,
            result,
            {action.target_key: server.target},
            server.admin,
            set(),
            observed,
            issues,
        )
        assert issues == [] and observed["control_requests_verified"] == 5
    journal = (tmp_path / "requests.jsonl").read_text()
    for secret in (server.chosen[0], PASSWORD):
        assert secret not in journal and secret not in json.dumps(result)
    covered = read_route_evidence(tmp_path / "requests.jsonl")["covered"]
    assert [row["requests"] for row in covered if (row["method"], row["path"]) == ROUTE] == [1]


def test_temporary_password_stops_before_the_write_for_a_person_with_a_verified_factor(tmp_path):
    with journey(tmp_path, fault="verified_factor") as (source, action, context, server):
        with pytest.raises(SamplePhaseActionError):
            execute_control_action(action, source, context)
        assert "verified_factor" in server.fault_hits
        assert server.writes == [] and server.password == PASSWORD and not server.marked


@pytest.mark.parametrize(
    "fault",
    (
        "receipt_password",
        "receipt_revocation",
        "mark_missing",
        "gate_open",
        "gate_code",
        "change_refused",
        "mark_kept",
    ),
)
def test_temporary_password_fault_fails_and_restores_the_original_password(tmp_path, fault):
    with journey(tmp_path, fault=fault) as (source, action, context, server):
        with pytest.raises(SamplePhaseActionError) as error:
            execute_control_action(action, source, context)
        assert fault in server.fault_hits, "The intended response boundary was not reached"
        assert server.chosen[0] not in str(error.value)
        assert server.writes.count("temporary") == 1, "The administrator write is never replayed"
        assert server.password == PASSWORD and server.marked is False
        primary = context.clients[action.target_key]
        assert primary.request("GET", "/api/auth/me").json()["id"] == server.target


def test_lost_temporary_password_response_is_not_replayed_and_is_restored(tmp_path):
    with journey(tmp_path, fault="unknown_write") as (source, action, context, server):
        with pytest.raises(SampleWriteOutcomeUnknown):
            execute_control_action(action, source, context)
        assert "unknown_write" in server.fault_hits
        assert server.writes.count("temporary") == 1
        assert server.password == PASSWORD and server.marked is False


def test_a_mark_left_without_the_temporary_password_is_reported_not_hidden(tmp_path):
    with journey(tmp_path, fault="provider_failed") as (source, action, context, server):
        with pytest.raises(SamplePhaseActionError) as error:
            execute_control_action(action, source, context)
        assert "provider_failed" in server.fault_hits
        assert error.value.step == "read_original_identity"
        assert server.writes.count("temporary") == 1 and server.password == PASSWORD
