"""The email rule of record, sheet and design values: one linear scan with exactly the
answers of the earlier pattern ``[^\\s@]+@[^\\s@]+\\.[^\\s@]+`` (full match)."""

import re
import time
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.systems.sandbox.fields.validation import valid_email
from tests.property_support import PROPERTY

EARLIER = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
# Characters that decide the answer: the separators, Unicode whitespace and ordinary text.
DECIDING = st.text(
    alphabet=st.sampled_from(["a", "b", ".", "@", " ", "\t", "\n", "\x1c", "\x85", "\xa0",
                              " ", "　", "é", "-"]),
    max_size=12,
)


def _earlier(value: str) -> bool:
    return EARLIER.fullmatch(value) is not None


@PROPERTY
@given(st.one_of(DECIDING, st.text(max_size=40)))
def test_the_rule_answers_as_the_earlier_pattern(value: str) -> None:
    assert valid_email(value) == _earlier(value)


def test_the_rule_answers_as_the_earlier_pattern_on_long_and_edge_shapes() -> None:
    shapes = [
        "a@" + "." * 3997 + "@", "a@" + "." * 3997 + " ", "a@a" + "." * 3996 + "@",
        "a@" + "." * 3998, "a@a" + "." * 3996 + "a", "someone@example.org", "a@b.c",
        "a@.b", "a@b.", "a@..", "a@b..c", "@b.c", "a@b.c@d", "a b@c.d", "a@b.c　",
        "", "@", "a@", ".@.", "a@.b.", "a@b .c",
    ]
    for shape in shapes:
        assert valid_email(shape) == _earlier(shape), shape[:20]
    for code in range(0x110000):  # every character, as text and as whitespace candidate
        shape = f"a{chr(code)}@b.c"
        assert valid_email(shape) == _earlier(shape), hex(code)


def test_a_one_mebibyte_value_is_checked_in_linear_time() -> None:
    hostile = "a@" + "." * (1024 * 1024) + "@"
    started = time.perf_counter()
    assert valid_email(hostile) is False
    assert valid_email(hostile[:-1] + "a") is True
    assert time.perf_counter() - started < 0.5


HOSTILE = "a@" + "." * (64 * 1024) + "@"
LONGEST = "a@" + "." * 997 + "@"  # a design default holds at most 1,000 characters


def test_a_design_email_default_is_checked_by_the_rule_in_linear_time() -> None:
    from pydantic import ValidationError

    from app.systems.sandbox.designs.field_schemas import DesignField

    started = time.perf_counter()
    with pytest.raises(ValidationError, match="defaultValue does not match its field"):
        DesignField.model_validate({"id": "contact", "name": "Contact", "type": "Email",
                                    "config": {"kind": "email", "defaultValue": LONGEST}})
    assert time.perf_counter() - started < 0.5


def test_a_sandbox_test_run_value_is_checked_by_the_rule_in_linear_time() -> None:
    from app.systems.sandbox.designs.schemas import SandboxDocument
    from app.systems.sandbox.test_runs.evaluator import _value_is_valid, evaluate_test
    from tests.sandbox_documents import field_payload
    from tests.sandbox_test_runs.fixtures import document_payload

    payload: Any = document_payload()
    module = payload["design"]["modules"][0]
    module["fields"].append(field_payload("contact", "Contact", "Email",
                                          config={"kind": "email"}))
    document = SandboxDocument.model_validate(payload)
    started = time.perf_counter()
    result = evaluate_test(document=document, module_id="requests",
                           values={"contact": HOSTILE}, event={"kind": "record-created"},
                           trigger_ids=None)
    assert [issue.code for issue in result.issues
            if issue.target_id == "contact"] == ["value_invalid"]
    assert not _value_is_valid(HOSTILE, {"config": {"kind": "email"}})
    assert time.perf_counter() - started < 0.5
