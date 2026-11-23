"""The computed-column grammar and its save-time checks (spec D7.1, D7.4, D14 S3; K3, K4).

SH-21 (refusals with a reason), SH-22 (keys are stored, so a rename changes nothing),
SH-72 (the depth limit holds while parsing; the expanded-size budget across columns).
"""

from typing import Any

import pytest
from pydantic import TypeAdapter

from app.systems.openview.worksheets.expression import (
    ExpressionError,
    check_expressions,
    parse_stored,
)
from app.systems.openview.worksheets.structure import Column

BASE: list[dict[str, Any]] = [
    {"key": "c1", "name": "Student", "type": "link", "link": {"moduleId": str(0).zfill(32)}},
    {"key": "c2", "name": "Score", "type": "lookup",
     "lookup": {"linkKey": "c1", "fieldId": "0" * 32}},
    {"key": "c3", "name": "Quiz 1", "type": "decimal", "decimal": {"places": 2}},
    {"key": "c4", "name": "Quiz 2", "type": "int"},
    {"key": "c5", "name": "Note", "type": "text"},
    {"key": "c6", "name": "Name", "type": "lookup",
     "lookup": {"linkKey": "c1", "fieldId": "0" * 32}},
]
NUMERIC_LOOKUPS = {"c2"}  # Score reads a number field; Name reads a text field


def _computed(key: str, name: str, expression: str) -> dict[str, Any]:
    return {"key": key, "name": name, "type": "computed", "computed": {"expression": expression}}


def _columns(*computed: dict[str, Any]) -> list[Column]:
    return TypeAdapter(list[Column]).validate_python([*BASE, *computed])


def _check(*computed: dict[str, Any], decimal_mark: str = ".",
           unchanged: frozenset[str] = frozenset()) -> dict[str, str]:
    return check_expressions(_columns(*computed), numeric_lookups=NUMERIC_LOOKUPS,
                             unchanged=unchanged, decimal_mark=decimal_mark)


def _refused(*computed: dict[str, Any], **options: Any) -> ExpressionError:
    with pytest.raises(ExpressionError) as refused:
        _check(*computed, **options)
    return refused.value


@pytest.mark.parametrize(("expression", "stored"), [
    ("{Quiz 1} + {quiz 2}", "{c3} + {c4}"),
    ("({Quiz 1} + {Quiz 2}) / 2", "({c3} + {c4}) / 2"),
    ("{Quiz 1} - ({Quiz 2} - 1)", "{c3} - ({c4} - 1)"),
    ("-{Score} * 2.5", "-{c2} * 2.5"),
    ("round(average({Quiz 1}, {Quiz 2}, {Score}), 1)", "ROUND(AVERAGE({c3}, {c4}, {c2}), 1)"),
    ("SUM({c3}, {c4})", "SUM({c3}, {c4})"),
    ("MIN({Quiz 1}, 3) + MAX({Quiz 2})", "MIN({c3}, 3) + MAX({c4})"),
])
def test_an_editor_expression_is_stored_with_keys_and_canonical_separators(
    expression: str, stored: str,
) -> None:
    assert _check(_computed("c7", "Total", expression)) == {"c7": stored}


def test_a_comma_decimal_locale_uses_semicolons_between_arguments() -> None:
    saved = _check(_computed("c7", "Total", "ROUND({Quiz 1} * 1,5; 2)"), decimal_mark=",")
    assert saved == {"c7": "ROUND({c3} * 1.5, 2)"}


def test_an_unchanged_stored_expression_is_read_in_its_canonical_form() -> None:
    saved = _check(_computed("c7", "Total", "SUM({c3}, {c4})"), decimal_mark=",",
                   unchanged=frozenset({"c7"}))
    assert saved == {"c7": "SUM({c3}, {c4})"}


def test_a_computed_column_reads_another_and_renames_change_nothing() -> None:
    first = _check(_computed("c7", "Total", "{Quiz 1} + {Quiz 2}"),
                   _computed("c8", "Bonus", "{Total} * 2"))
    assert first == {"c7": "{c3} + {c4}", "c8": "{c7} * 2"}
    renamed = [dict(column) for column in BASE]
    renamed[2] = {**renamed[2], "name": "Quiz A"}
    columns = TypeAdapter(list[Column]).validate_python([
        *renamed, _computed("c7", "Total", "{c3} + {c4}"), _computed("c8", "Bonus", "{c7} * 2"),
    ])
    assert check_expressions(columns, numeric_lookups=NUMERIC_LOOKUPS,
                             unchanged=frozenset({"c7", "c8"}), decimal_mark=".") == first


@pytest.mark.parametrize(("expression", "reason"), [
    ("B2 + 1", "cell_reference"),
    ("{Quiz 1} + total", "bare_name"),
    ("{Nobody}", "unknown_column"),
    ("{Note} + 1", "not_numeric"),
    ("{Name} + 1", "not_numeric"),
    ("{Student} + 1", "not_numeric"),
    ("POWER({Quiz 1}, 2)", "unknown_function"),
    ("{Quiz 1} +", "syntax"),
    ("({Quiz 1}", "syntax"),
    ("{Quiz 1} 2", "syntax"),
    ("SUM()", "arguments"),
    ("SUM(" + ", ".join(["1"] * 51) + ")", "arguments"),
    ("ROUND({Quiz 1})", "arguments"),
    ("ROUND({Quiz 1}, 11)", "round_places"),
    ("ROUND({Quiz 1}, 1.5)", "round_places"),
    ("ROUND({Quiz 1}, {Quiz 2})", "round_places"),
    ("1" * 1001, "too_long"),
    ("+".join(["1"] * 51), "too_many_nodes"),
    ("(" * 21 + "1" + ")" * 21, "too_deep"),
    ("-" * 21 + "1", "too_deep"),
    ("SUM(" * 21 + "1" + ")" * 21, "too_deep"),
], ids=lambda value: value[:24] if isinstance(value, str) else value)
def test_an_expression_breaking_a_rule_is_refused_with_its_reason(
    expression: str, reason: str,
) -> None:
    refused = _refused(_computed("c7", "Total", expression))
    assert (refused.key, refused.reason) == ("c7", reason)
    assert refused.message.startswith("Total: ")


def test_twenty_levels_of_nesting_are_allowed() -> None:
    saved = _check(_computed("c7", "Total", "(" * 20 + "1" + ")" * 20))
    assert saved == {"c7": "1"}


def test_a_thousand_characters_of_brackets_are_refused_without_a_recursion_error() -> None:
    expression = "(" * 499 + "1" + ")" * 499 + " "
    assert len(expression) == 1_000
    assert _refused(_computed("c7", "Total", expression)).reason == "too_deep"


def test_a_name_that_is_also_another_columns_key_is_ambiguous() -> None:
    refused = _refused(_computed("c7", "c3", "1"), _computed("c8", "Bonus", "{c3} + 1"))
    assert (refused.key, refused.reason) == ("c8", "ambiguous_column")


@pytest.mark.parametrize("cycle", [
    [("c7", "Total", "{Bonus} + 1"), ("c8", "Bonus", "{Total} * 2")],
    [("c7", "Total", "{Total} + 1")],
])
def test_a_reference_loop_is_refused_and_names_its_columns(cycle: list[tuple[str, ...]]) -> None:
    refused = _refused(*(_computed(*column) for column in cycle))
    assert refused.reason == "loop"
    for _key, name, _expression in cycle:
        assert name in refused.message


def test_a_chain_of_more_than_ten_computed_columns_is_refused() -> None:
    chain = [_computed("c7", "Step 0", "{Quiz 1} + 1")]
    chain += [_computed(f"c{8 + index}", f"Step {index + 1}", f"{{Step {index}}} + 1")
              for index in range(9)]
    assert len(_check(*chain)) == 10
    longer = [*chain, _computed("cz", "Step 10", "{Step 9} + 1")]
    refused = _refused(*longer)
    assert (refused.key, refused.reason) == ("cz", "chain_too_deep")


def test_a_fan_out_chain_over_the_expanded_budget_is_refused() -> None:
    """D14 S3: each step reads the one before four times; the size grows fourfold."""

    chain = [_computed("c7", "Step 0", "{Quiz 1} + {Quiz 1} + {Quiz 1} + {Quiz 1}")]
    chain += [_computed(f"c{8 + index}", f"Step {index + 1}",
                        " + ".join([f"{{Step {index}}}"] * 4)) for index in range(4)]
    assert len(_check(*chain[:4])) == 4  # 7, 31, 127, 511 expanded nodes
    refused = _refused(*chain)  # the fifth step expands to 2,047 nodes
    assert (refused.key, refused.reason) == ("c11", "too_large")


def test_a_stored_expression_parses_with_keys_only() -> None:
    assert parse_stored("ROUND({c3} * 1.5, 2)").node_count == 5
    with pytest.raises(ExpressionError):
        parse_stored("{Quiz 1} + 1")
