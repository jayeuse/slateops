from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import Mock

import pytest
from uuid6 import uuid7

from app.systems.sandbox.derived.actions import (
    BoardState,
    DepartmentOutcome,
    LinkedItem,
    board_action,
    derived_changes,
    follow_steps,
    publication_counts,
)
from app.systems.sandbox.designs.schemas import DesignField, TriggerDocument
from app.systems.sandbox.fields.models import FieldType
from app.systems.sandbox.fields.validation import field_config
from app.systems.sandbox.publications.close_rules import _module_has_unmanaged_fields
from app.systems.sandbox.publications.models import SandboxBinding
from app.systems.sandbox.publications.preflight import (
    module_schema_blockers,
    structure_name_blockers,
)
from app.systems.sandbox.publications.rules import (
    _field_key,
    _trigger_blockers,
    operational_config,
    relationship_metadata,
)
from app.systems.sandbox.publications.trigger_comparison import (
    desired_trigger_signature,
    record_trigger_signature,
)
from app.systems.sandbox.record_triggers.models import (
    RecordTrigger,
    RecordTriggerAction,
    RecordTriggerCondition,
)
from tests.sandbox_designs.fixtures import sample_document
from tests.sandbox_test_runs.fixtures import option_id, sandbox_document

SELECT_OPTION_ID = str(uuid7())


def test_field_binding_key_is_module_scoped() -> None:
    assert _field_key("orders", "status") != _field_key("invoices", "status")
    assert _field_key("orders:current", "status") != _field_key("orders", "current:status")
    assert len(_field_key("m" * 1_000, "f" * 1_000)) <= 1_000
    digest = sha256(b"a:b\x00c").hexdigest()
    assert _field_key("a:b", "c") != _field_key("field", digest)


def test_relationship_cardinality_maps_to_live_edge_constraints() -> None:
    class Relationship:
        cardinality = "one-to-many"

    assert relationship_metadata(Relationship()) == (True, False)


@pytest.mark.parametrize(
    ("field_type", "config", "expected"),
    [
        (
            "Text",
            {"kind": "text", "defaultValue": "new", "maxLength": 90},
            {"defaultValue": "new", "maxLength": 90},
        ),
        (
            "Number",
            {"kind": "number", "defaultValue": 3, "min": 1, "max": 9, "step": 2},
            {"defaultValue": 3, "minimum": 1, "maximum": 9, "step": 2},
        ),
        (
            "Integer",
            {"kind": "integer", "defaultValue": 4.0, "min": 0.0, "max": 10.0, "step": 2.0},
            {"defaultValue": 4, "minimum": 0, "maximum": 10, "step": 2},
        ),
        ("Checkbox", {"kind": "checkbox", "defaultValue": False}, {"defaultValue": False}),
        (
            "Select",
            {
                "kind": "select",
                "defaultValue": SELECT_OPTION_ID,
                "options": [{"id": SELECT_OPTION_ID, "label": "Open"}],
            },
            {
                "defaultValue": SELECT_OPTION_ID,
                "options": [{"id": SELECT_OPTION_ID, "label": "Open"}],
            },
        ),
    ],
)
def test_operational_config_uses_live_validation_keys(field_type, config, expected) -> None:
    field = DesignField.model_validate(
        {
            **sample_document().design.modules[0].fields[0].model_dump(by_alias=True),
            "type": field_type,
            "config": config,
        }
    )

    converted = operational_config(field)
    assert converted == expected
    assert (
        field_config(
            FieldType(
                {
                    "Text": "text",
                    "Number": "number",
                    "Integer": "int",
                    "Checkbox": "boolean",
                    "Select": "select",
                }[field_type]
            ),
            converted,
        )
        == converted
    )


def test_text_default_is_not_mistaken_for_a_numeric_length() -> None:
    assert field_config(FieldType.TEXT, {"defaultValue": "draft", "maxLength": 20}) == {
        "defaultValue": "draft",
        "maxLength": 20,
    }


def test_trigger_semantic_signature_detects_trigger_condition_and_action_edits() -> None:
    desired = sandbox_document().triggers[0]
    module_id = uuid7()
    priority_id = uuid7()
    status_id = uuid7()
    score_id = uuid7()
    module_bindings = {
        "requests": SandboxBinding(kind="module", sandbox_id="requests", module_id=module_id)
    }
    field_bindings = {
        _field_key("requests", "priority"): SandboxBinding(
            kind="field",
            sandbox_id=_field_key("requests", "priority"),
            field_id=priority_id,
        ),
        _field_key("requests", "status"): SandboxBinding(
            kind="field",
            sandbox_id=_field_key("requests", "status"),
            field_id=status_id,
        ),
        _field_key("requests", "score"): SandboxBinding(
            kind="field",
            sandbox_id=_field_key("requests", "score"),
            field_id=score_id,
        ),
    }
    live = RecordTrigger(
        module_id=module_id,
        name=desired.name,
        enabled=True,
        priority=10,
        event_kind="record-created",
        condition_operator="all",
    )
    conditions = [
        RecordTriggerCondition(
            field_id=priority_id,
            position=0,
            operator="=",
            value_kind="literal",
            literal_value={"value": option_id("priority", "High")},
        )
    ]
    actions = [
        RecordTriggerAction(
            target_field_id=status_id,
            position=0,
            kind="set-field",
            value_kind="literal",
            literal_value={"value": "Triaged"},
        )
    ]

    live_signature = record_trigger_signature(live, conditions, actions)
    assert desired_trigger_signature(desired, module_bindings, field_bindings) == live_signature

    variants: list[TriggerDocument] = []
    trigger_changed = desired.model_dump(by_alias=True, mode="json")
    trigger_changed["trigger"] = {
        "kind": "field-changed",
        "moduleId": "requests",
        "fieldId": "priority",
    }
    variants.append(TriggerDocument.model_validate(trigger_changed))
    condition_changed = desired.model_dump(by_alias=True, mode="json")
    condition_changed["conditionGroup"]["conditions"][0]["value"]["value"] = "Low"
    variants.append(TriggerDocument.model_validate(condition_changed))
    action_changed = desired.model_dump(by_alias=True, mode="json")
    action_changed["actions"][0]["value"]["value"] = "Done"
    variants.append(TriggerDocument.model_validate(action_changed))

    assert all(
        desired_trigger_signature(variant, module_bindings, field_bindings) != live_signature
        for variant in variants
    )


def test_relationship_scoped_trigger_references_block_publication() -> None:
    document = sandbox_document()
    base = document.triggers[0].model_dump(by_alias=True, mode="json")
    variants: list[TriggerDocument] = []

    condition_field = TriggerDocument.model_validate(base)
    condition_field.condition_group.conditions[0].field.relationship_id = "request-equipment"
    variants.append(condition_field)

    condition_value_payload = TriggerDocument.model_validate(base).model_dump(
        by_alias=True, mode="json"
    )
    condition_value_payload["conditionGroup"]["conditions"][0]["value"] = {
        "kind": "field-reference",
        "moduleId": "requests",
        "fieldId": "priority",
        "relationshipId": "request-equipment",
    }
    variants.append(TriggerDocument.model_validate(condition_value_payload))

    action_target = TriggerDocument.model_validate(base)
    action_target.actions[0].target.relationship_id = "request-equipment"
    variants.append(action_target)

    trigger_value_payload = TriggerDocument.model_validate(base).model_dump(
        by_alias=True, mode="json"
    )
    trigger_value_payload["trigger"] = {
        "kind": "threshold-crossed",
        "moduleId": "requests",
        "fieldId": "score",
        "operator": ">",
        "value": {
            "kind": "field-reference",
            "moduleId": "requests",
            "fieldId": "priority",
            "relationshipId": "request-equipment",
        },
    }
    variants.append(TriggerDocument.model_validate(trigger_value_payload))

    assert all(
        "trigger_relationship_reference_unsupported"
        in {blocker.code for blocker in _trigger_blockers(document, record_trigger)}
        for record_trigger in variants
    )


def test_invalid_select_configuration_returns_a_schema_blocker() -> None:
    document = sample_document().model_copy(deep=True)
    select_field = document.design.modules[0].fields[2]
    select_field.config.options = []

    blockers = module_schema_blockers(document)

    assert ("module_schema_invalid", "sample-requests") in {
        (blocker.code, blocker.target_id) for blocker in blockers
    }


def test_relationship_to_a_closed_module_does_not_make_an_empty_schema_valid() -> None:
    document = sample_document().model_copy(deep=True)
    source = document.design.modules[0]
    target = document.design.modules[1]
    for field in source.fields:
        field.closed = True
    target.closed = True

    blockers = module_schema_blockers(document)

    assert ("module_schema_invalid", "sample-requests") in {
        (blocker.code, blocker.target_id) for blocker in blockers
    }


def test_bound_fields_do_not_block_their_parent_module_from_closing() -> None:
    module_id = uuid7()
    field_id = uuid7()
    field = SimpleNamespace(id=field_id, type=FieldType.TEXT)
    database = Mock()
    database.scalars.return_value = [field]
    binding = SandboxBinding(
        kind="field",
        sandbox_id="sample-requests:sample-title",
        field_id=field_id,
    )

    assert not _module_has_unmanaged_fields(
        database,
        module_id,
        {binding.sandbox_id: binding},
        {},
    )


def test_closed_structure_names_do_not_block_later_active_names() -> None:
    document = sample_document().model_copy(deep=True)
    document.design.departments[0].closed = True
    document.design.departments[1].name = "Operations"
    document.design.modules[0].closed = True
    document.design.modules[1].name = "Service requests"

    assert not structure_name_blockers(document)


def _outcome(name: str, *, closed: bool = False, created: bool = False, board=None):
    return DepartmentOutcome("dep-a", name, closed, created, board)


def test_sd_c1_c8_derived_changes_create_the_set_only_for_a_new_open_department() -> None:

    created = [
        (c.kind, c.sandbox_id, c.action, c.label)
        for c in derived_changes([_outcome("Sales", created=True)])
    ]
    assert created == [
        ("board", "dep-a#board", "create", "Sales"),
        ("group", "dep-a#managers", "create", "Sales managers · manage"),
        ("group", "dep-a#members", "create", "Sales members · write"),
        ("group", "dep-a#viewers", "create", "Sales viewers · read"),
        ("dashboard", "dep-a#dashboard", "create", "Sales dashboard"),
        ("category", "dep-a#category", "create", "Sales"),
        ("channel", "dep-a#channel", "create", "Sales"),
    ]
    closed = derived_changes([_outcome("Sales", created=True, closed=True)])
    assert [(c.kind, c.action) for c in closed] == [("board", "create")]
    existing = derived_changes([_outcome("Sales", board=BoardState("Sales", "active"))])
    assert existing == []


@pytest.mark.parametrize(
    ("board", "closed", "expected"),
    [
        pytest.param(None, False, "create", id="no-board"),
        pytest.param(("Sales", "active"), True, "close", id="department-closes"),
        pytest.param(("Old", "archived"), False, "reopen", id="reopen-wins-over-rename"),
        pytest.param(("Old", "active"), False, "update", id="rename"),
        pytest.param(("Sales", "active"), False, None, id="unchanged"),
    ],
)
def test_sd_c23_board_action_mirrors_the_board_sync(board, closed, expected) -> None:

    state = BoardState(*board) if board is not None else None
    assert board_action(state, "Sales", closed) == expected


def test_sd_c1_counts_name_categories_and_every_derived_kind() -> None:

    counts = publication_counts(derived_changes([_outcome("Sales", created=True)]))
    assert counts.model_dump() == {
        "departments": 0,
        "modules": 0,
        "fields": 0,
        "relationships": 0,
        "triggers": 0,
        "groups": 3,
        "dashboards": 1,
        "boards": 1,
        "categories": 1,
        "channels": 1,
    }


def test_sd_c22_a_150_character_department_name_gives_labels_the_review_accepts() -> None:

    name = "D" * 150
    labels = {c.sandbox_id: c.label for c in derived_changes([_outcome(name, created=True)])}
    assert labels["dep-a#managers"] == f"{name} managers · manage"
    assert len(labels["dep-a#managers"]) == 168


_CLOSE_STAMP = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)
_LATER_STAMP = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)
_ROLE_NAMES = {
    "managers": "Sales managers",
    "members": "Sales members",
    "viewers": "Sales viewers",
    "dashboard": "Sales dashboard",
    "category": "Sales",
    "channel": "Sales",
}
_IDS = {role: uuid7() for role in _ROLE_NAMES}


def _linked(**changes: dict[str, Any]) -> list[LinkedItem]:
    """One department's six links with live, open targets; ``changes`` edits one role."""
    items = []
    for role, name in _ROLE_NAMES.items():
        item = LinkedItem(role, _IDS[role], name, removed=False, moved=False)
        items.append(replace(item, **changes.get(role, {})))
    return items


_RENAMED = [
    ("managers", "update", "Revenue managers"),
    ("members", "update", "Revenue members"),
    ("viewers", "update", "Revenue viewers"),
    ("dashboard", "update", "Revenue dashboard"),
    ("category", "update", "Revenue"),
    ("channel", "update", "Revenue"),
]
_BY_CLOSE = {
    "archived_at": _CLOSE_STAMP,
    "archived_by_close": True,
    "close_archived_at": _CLOSE_STAMP,
}


@pytest.mark.parametrize(
    ("items", "renamed_to", "transition", "expected"),
    [
        # SD-C9, SD18: a rename gives every item its derived name, a person's name included.
        (_linked(channel={"name": "sales-chat"}), "Revenue", None, _RENAMED),
        # SD-C10: no rename and no state change leaves every name as it is.
        (_linked(channel={"name": "sales-chat"}), None, None, []),
        # R7, R5: a deleted group, an archived dashboard, and a released link are left alone.
        (
            _linked(
                viewers={"removed": True},
                dashboard={"removed": True},
                category={"target_id": None, "name": ""},
            ),
            "Revenue",
            None,
            [_RENAMED[0], _RENAMED[1], _RENAMED[5]],
        ),
        # R16, SD-C29: a category a person moved to another department is not followed.
        (_linked(category={"moved": True}), "Revenue", None, [*_RENAMED[:4], _RENAMED[5]]),
        # R7: a channel a person archived keeps its name.
        (_linked(channel={"archived_at": _LATER_STAMP}), "Revenue", None, _RENAMED[:5]),
        # R8: a close archives the open derived channel and nothing else.
        (_linked(), None, "close", [("channel", "close", "Sales")]),
        # SD-C13: a channel a person archived before the close stays theirs.
        (_linked(channel={"archived_at": _LATER_STAMP}), None, "close", []),
        # A publish that renames and closes: the channel is archived under its new name.
        (_linked(), "Revenue", "close", [*_RENAMED, ("channel", "close", "Revenue")]),
        # A rename while closed follows the channel that the close archived.
        (_linked(channel=_BY_CLOSE), "Revenue", None, _RENAMED),
        # R9, SD-C12: the reopen unarchives what the close archived, at the same instant.
        (_linked(channel=_BY_CLOSE), None, "reopen", [("channel", "reopen", "Sales")]),
        # R9: archived again after the close, or restored by a person: the person's state stays.
        (
            _linked(channel={**_BY_CLOSE, "archived_at": _LATER_STAMP}),
            None,
            "reopen",
            [],
        ),
        (_linked(channel={**_BY_CLOSE, "archived_at": None}), None, "reopen", []),
    ],
)
def test_follow_steps_change_only_linked_items_that_people_left_in_place(
    items: list[LinkedItem],
    renamed_to: str | None,
    transition: Literal["close", "reopen"] | None,
    expected: list[tuple[str, str, str]],
) -> None:
    steps = follow_steps(items, renamed_to=renamed_to, transition=transition)

    assert [(step.role, step.action, step.name) for step in steps] == expected
    assert all(step.target_id == _IDS[step.role] for step in steps)
