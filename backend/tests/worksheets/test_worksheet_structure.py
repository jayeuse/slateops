"""The stored sheet structure (spec D1.7) and its column limit (D8)."""

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from app.systems.openview.worksheets.structure import WorksheetStructure

MODULE = "01900000-0000-7000-8000-000000000001"
FIELD = "01900000-0000-7000-8000-000000000002"
SOURCE_SHEET = "01900000-0000-7000-8000-000000000003"


def _example() -> dict[str, Any]:
    """The D1.7 example, plus one From another sheet column and one plain text column."""
    return {
        "structureVersion": 1,
        "nextColumnSeq": 9,
        "columns": [
            {"key": "c1", "name": "Student", "type": "link", "link": {"moduleId": MODULE}},
            {
                "key": "c2", "name": "Student no.", "type": "lookup",
                "lookup": {"linkKey": "c1", "fieldId": FIELD},
            },
            {
                "key": "c3", "name": "Quiz 1", "type": "decimal",
                "decimal": {"places": 2, "currency": False},
            },
            {
                "key": "c4", "name": "Quiz 2", "type": "decimal",
                "decimal": {"places": 2, "currency": False},
            },
            {
                "key": "c5", "name": "Total", "type": "computed",
                "computed": {"expression": "{c3} + {c4}", "places": 2},
            },
            {
                "key": "c6", "name": "Grade", "type": "select",
                "select": {"options": [{"id": "o1", "label": "Pass"}]},
            },
            {
                "key": "c7", "name": "Final grade", "type": "sheet_lookup",
                "sheet_lookup": {
                    "sourceWorksheetId": SOURCE_SHEET, "sourceColumnKey": "c9",
                    "linkKey": "c1", "sourceLinkKey": "c2",
                },
            },
            {"key": "c8", "name": "Remarks", "type": "text"},
        ],
        "groups": [{"name": "Period 1", "keys": ["c3", "c4", "c5"]}],
        "totals": {"c5": "average", "c1": "count"},
    }


def _plain(count: int) -> dict[str, Any]:
    return {
        "structureVersion": 1,
        "nextColumnSeq": count + 1,
        "columns": [
            {"key": f"c{index}", "name": f"Column {index}", "type": "int"}
            for index in range(1, count + 1)
        ],
        "groups": [],
        "totals": {},
    }


def test_the_spec_example_is_accepted_and_stored_unchanged() -> None:
    example = _example()
    assert WorksheetStructure.model_validate(example).model_dump(mode="json") == example


@pytest.mark.parametrize(
    "column_type",
    ["text", "long_text", "email", "url", "number", "int", "boolean", "date", "datetime", "user"],
)
def test_every_plain_field_type_is_a_column_type(column_type: str) -> None:
    structure = _plain(1)
    structure["columns"][0]["type"] = column_type
    assert WorksheetStructure.model_validate(structure).model_dump(mode="json") == structure


def test_a_sheet_holds_one_hundred_columns_and_refuses_the_one_hundred_and_first() -> None:
    assert len(WorksheetStructure.model_validate(_plain(100)).columns) == 100
    with pytest.raises(ValidationError, match="at most 100 items"):
        WorksheetStructure.model_validate(_plain(101))


def _column(structure: dict[str, Any], key: str) -> dict[str, Any]:
    return next(column for column in structure["columns"] if column["key"] == key)


def _set(path: str, value: Any):
    """Change one value of the example; ``c5.computed.expression`` names column c5."""

    def change(structure: dict[str, Any]) -> None:
        head, *rest = path.split(".")
        target = _column(structure, head) if head.startswith("c") else structure
        keys = rest if head.startswith("c") else [head, *rest]
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return change


def _add_column(column: dict[str, Any]):
    def change(structure: dict[str, Any]) -> None:
        structure["columns"].append(column)

    return change


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_set("structureVersion", 2), "Input should be 1"),
        (_set("layout", {}), "Extra inputs are not permitted"),
        (_set("c8.key", "C8"), "String should match pattern"),
        (_set("c8.key", "c123456789"), "String should match pattern"),
        (_set("c8.key", "c1"), "Column keys must be unique"),
        (_set("c8.name", " quiz 1 "), "Column names must be unique"),
        (_set("c8.name", "   "), "Column names cannot be blank"),
        (_set("c8.name", "x" * 151), "at most 150 characters"),
        (_set("c8.type", "relationship"), "relationship is not a column type"),
        (_set("c8.type", "formula"), "Input tag 'formula' found using 'type' does not match"),
        (_set("c2.lookup.linkKey", "c3"), "must name a link column"),
        (_set("c2.lookup.linkKey", "c99"), "must name a link column"),
        (_set("c7.sheet_lookup.linkKey", "c8"), "must name a link column"),
        (_set("c6.select.options", []), "at least 1 item"),
        (
            _set("c6.select.options", [{"id": "o1", "label": "A"}, {"id": "o2", "label": "A"}]),
            "Option IDs and labels must be unique",
        ),
        (_set("c5.computed.expression", "1" * 1001), "at most 1000 characters"),
        (_set("groups", [{"name": "P", "keys": ["c3", "c99"]}]), "Group keys must name columns"),
        (_set("groups", [{"name": "P", "keys": ["c3", "c5"]}]), "adjacent columns in order"),
        (_set("groups", [{"name": "P", "keys": ["c4", "c3"]}]), "adjacent columns in order"),
        (_set("groups", [{"name": "P", "keys": []}]), "at least 1 item"),
        (
            _set("groups", [{"name": "A", "keys": ["c3", "c4"]}, {"name": "B", "keys": ["c4"]}]),
            "Groups cannot overlap",
        ),
        (_set("totals", {"c99": "count"}), "Totals must name columns"),
        (_set("totals", {"c8": "sum"}), "only count works on a text column"),
        (_set("totals", {"c5": "median"}), "Input should be 'sum', 'average', 'min', 'max'"),
        (_add_column({"key": "c9", "name": "Spare", "type": "decimal"}), "Field required"),
    ],
    ids=[
        "unknown-version", "extra-top-level-key", "key-uppercase", "key-too-long",
        "duplicate-key", "duplicate-name-ignoring-case-and-spaces", "blank-name", "long-name",
        "relationship-type", "unknown-type", "lookup-of-a-non-link", "lookup-of-a-missing-key",
        "sheet-lookup-of-a-non-link", "choice-list-without-options", "duplicate-option-label",
        "long-expression", "group-of-a-missing-key", "group-with-a-gap", "group-out-of-order",
        "empty-group", "overlapping-groups", "totals-of-a-missing-key", "sum-of-text",
        "unknown-total", "decimal-without-its-options",
    ],
)
def test_an_invalid_structure_is_refused(change, message: str) -> None:
    structure = copy.deepcopy(_example())
    change(structure)
    with pytest.raises(ValidationError, match=message):
        WorksheetStructure.model_validate(structure)


@pytest.mark.parametrize(
    ("key", "function"),
    [("c8", "count"), ("c3", "sum"), ("c5", "max"), ("c2", "average"), ("c7", "min")],
    ids=["count-of-text", "sum-of-decimal", "max-of-computed", "average-of-lookup",
         "min-of-another-sheet"],
)
def test_totals_accept_count_anywhere_and_numbers_where_the_value_can_be_numeric(
    key: str, function: str,
) -> None:
    structure = _example()
    structure["totals"] = {key: function}
    assert WorksheetStructure.model_validate(structure).totals == {key: function}
