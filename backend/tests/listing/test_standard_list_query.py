from datetime import UTC, datetime
from enum import StrEnum

import pytest
from fastapi import HTTPException
from hypothesis import assume, given
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from uuid6 import uuid7

from app.common.listing.cursor import encode_cursor
from app.common.listing.query import ListQuerySpec, build_standard_list_statements
from app.common.listing.schemas import KeysetListRequest, StandardListRequest
from app.systems.sandbox.departments.models import Department
from tests.property_support import PROPERTY


class DepartmentSortField(StrEnum):
    NAME = "department_name"


def test_list_query_escapes_search_and_counts_before_pagination() -> None:
    spec = ListQuerySpec(
        sort_fields={DepartmentSortField.NAME: Department.department_name},
        default_sort=DepartmentSortField.NAME,
        tie_breaker=Department.id,
        search_fields=(Department.department_name,),
        deleted_field=Department.is_deleted,
    )
    items, count = build_standard_list_statements(
        select(Department),
        StandardListRequest[DepartmentSortField](
            search="50%_done",
            deleted="only",
            sort_order="desc",
            limit=10,
            offset=20,
        ),
        spec,
    )
    compiled = items.compile(dialect=postgresql.dialect())
    assert "%50\\%\\_done%" in compiled.params.values()
    assert "is_deleted IS true" in str(compiled)
    # A NOT NULL column keeps the default null order, which an index scan gives (contract 2.4).
    assert "departments.id DESC" in str(compiled)
    assert "NULLS LAST" not in str(compiled)
    assert "LIMIT" in str(compiled) and "OFFSET" in str(compiled)
    count_compiled = count.compile(dialect=postgresql.dialect())
    # The count stops one row above the cap (D1); it never sorts or skips.
    assert all(keyword not in str(count_compiled) for keyword in ("ORDER BY", "OFFSET"))
    assert 10_001 in count_compiled.params.values()


@pytest.mark.parametrize(
    ("params", "parameter", "message"),
    [
        ({"search": "alpha"}, "search", "This endpoint does not support search"),
        (
            {"deleted": "only"},
            "deleted",
            "This endpoint does not support deleted record filtering",
        ),
    ],
)
def test_unsupported_list_filters_return_422(
    params: dict[str, str], parameter: str, message: str
) -> None:
    spec = ListQuerySpec(
        sort_fields={DepartmentSortField.NAME: Department.department_name},
        default_sort=DepartmentSortField.NAME,
        tie_breaker=Department.id,
    )
    with pytest.raises(HTTPException) as error:
        build_standard_list_statements(
            select(Department),
            StandardListRequest[DepartmentSortField](**params),
            spec,
        )
    assert error.value.status_code == 422
    # The same shape as a FastAPI request validation error.
    assert error.value.detail == [
        {"loc": ["query", parameter], "msg": message, "type": "value_error"}
    ]


def _department_spec() -> ListQuerySpec[DepartmentSortField]:
    return ListQuerySpec(
        sort_fields={DepartmentSortField.NAME: Department.department_name},
        default_sort=DepartmentSortField.NAME,
        tie_breaker=Department.id,
        deleted_field=Department.is_deleted,
    )


def test_default_list_hides_deleted_rows_sorts_ascending_and_counts_every_match() -> None:
    items, count = build_standard_list_statements(
        select(Department),
        StandardListRequest[DepartmentSortField](limit=10, offset=20),
        _department_spec(),
    )

    item_sql = str(
        items.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "WHERE departments.is_deleted IS false" in item_sql
    assert "ORDER BY departments.department_name ASC, departments.id ASC" in item_sql
    # One row more than the page says whether more follow.
    assert item_sql.endswith("LIMIT 11 OFFSET 20")
    count_sql = str(count.compile(dialect=postgresql.dialect()))
    assert count_sql.startswith("SELECT count(*) AS count_1")


class NullableSortField(StrEnum):
    DELETED_AT = "deleted_at"
    NAME_LENGTH = "name_length"


@pytest.mark.parametrize(
    ("sort_by", "order_by"),
    [
        pytest.param(
            NullableSortField.DELETED_AT,
            "ORDER BY departments.deleted_at DESC NULLS LAST, departments.id DESC",
            id="nullable-column-keeps-nulls-last",
        ),
        pytest.param(
            NullableSortField.NAME_LENGTH,
            "ORDER BY length(departments.department_name) DESC NULLS LAST, departments.id DESC",
            id="expression-keeps-nulls-last",
        ),
    ],
)
def test_only_a_column_that_can_hold_a_null_sorts_nulls_last(
    sort_by: NullableSortField, order_by: str
) -> None:
    spec = ListQuerySpec(
        sort_fields={
            NullableSortField.DELETED_AT: Department.deleted_at,
            NullableSortField.NAME_LENGTH: func.length(Department.department_name),
        },
        default_sort=NullableSortField.DELETED_AT,
        tie_breaker=Department.id,
    )
    items, _count = build_standard_list_statements(
        select(Department),
        StandardListRequest[NullableSortField](sort_by=sort_by, sort_order="desc"),
        spec,
    )

    assert order_by in str(items.compile(dialect=postgresql.dialect()))


def test_a_cursor_that_reaches_a_list_without_keyset_gets_the_fixed_422() -> None:
    # Only the D1 lists page by cursor; a request model that carries one elsewhere is refused
    # before any condition is built, even when the cursor itself is valid.
    cursor = encode_cursor(datetime(2026, 11, 9, 12, tzinfo=UTC), uuid7())

    with pytest.raises(HTTPException) as refusal:
        build_standard_list_statements(
            select(Department),
            KeysetListRequest[DepartmentSortField](cursor=cursor),
            _department_spec(),
        )

    assert refusal.value.status_code == 422
    assert refusal.value.detail == [
        {"loc": ["query", "cursor"], "msg": "Invalid cursor", "type": "value_error"}
    ]


def test_an_empty_list_reports_a_total_of_zero() -> None:
    from app.common.listing.query import execute_standard_list
    from app.common.listing.schemas import PaginationMetadata

    class EmptyResultSession:
        def scalar(self, _statement: object) -> int:
            return 0

        def scalars(self, _statement: object) -> "EmptyResultSession":
            return self

        def all(self) -> list[Department]:
            return []

    result = execute_standard_list(
        EmptyResultSession(),
        select(Department),
        StandardListRequest[DepartmentSortField](),
        _department_spec(),
    )

    assert result.items == []
    assert result.pagination == PaginationMetadata(
        limit=25, offset=0, count=0, total=0, has_more=False
    )


def _like_pattern(search: str) -> str:
    spec = ListQuerySpec(
        sort_fields={DepartmentSortField.NAME: Department.department_name},
        default_sort=DepartmentSortField.NAME,
        tie_breaker=Department.id,
        search_fields=(Department.department_name,),
    )
    items, _ = build_standard_list_statements(
        select(Department), StandardListRequest[DepartmentSortField](search=search), spec
    )
    (pattern,) = (
        value
        for value in items.compile(dialect=postgresql.dialect()).params.values()
        if isinstance(value, str)
    )
    return pattern


def _like_tokens(pattern: str) -> list[tuple[str, str]]:
    """Read a LIKE pattern with the backslash escape: ("wild", "%"|"_") or ("text", char)."""

    tokens = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            assert index + 1 < len(pattern), "a trailing escape matches nothing"
            tokens.append(("text", pattern[index + 1]))
            index += 2
            continue
        tokens.append(("wild" if character in "%_" else "text", character))
        index += 1
    return tokens


@PROPERTY
@given(
    st.text(alphabet=st.sampled_from("ab %_\\\t"), min_size=1, max_size=30) | st.text(max_size=100)
)
def test_list_search_matches_its_text_literally_inside_any_value(search: str) -> None:
    normalized = search.strip()
    assume(normalized)

    tokens = _like_tokens(_like_pattern(search))

    assert tokens[0] == ("wild", "%") and tokens[-1] == ("wild", "%")
    assert all(kind == "text" for kind, _ in tokens[1:-1])
    assert "".join(character for _, character in tokens[1:-1]) == normalized
