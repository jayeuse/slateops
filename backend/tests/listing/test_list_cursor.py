"""The keyset cursor: an opaque position, and one fixed 422 for every bad value (P7, H3 to H5)."""

import base64
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import strategies as st

from app.common.listing.cursor import decode_cursor, encode_cursor
from tests.property_support import PROPERTY

ROW = UUID("01a1c046-9daf-7a87-8bb5-5e1813b4e6dd")
INVALID = [{"loc": ["query", "cursor"], "msg": "Invalid cursor", "type": "value_error"}]


def _raw(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


@PROPERTY
@given(
    st.datetimes(
        min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
    ),
    st.uuids(),
)
def test_a_cursor_names_the_same_row_after_a_round_trip(moment: datetime, row: UUID) -> None:
    cursor = encode_cursor(moment, row)

    assert decode_cursor(cursor) == (moment, row)
    assert len(cursor) <= 128
    assert set(cursor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_a_time_with_another_offset_is_the_same_instant_in_utc() -> None:
    eastern = datetime(2026, 11, 9, 7, tzinfo=timezone(timedelta(hours=-5)))

    moment, row = decode_cursor(_raw(f"{eastern.isoformat()}|{ROW}"))

    assert (moment, moment.tzinfo, row) == (datetime(2026, 11, 9, 12, tzinfo=UTC), UTC, ROW)


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param("A" * 129, id="longer-than-128"),
        pytest.param(_raw(f"2026-11-09T12:00:00+00:00|{ROW}") + "=", id="padding-sign"),
        pytest.param(_raw(f"2026-11-09T12:00:00+00:00|{ROW}")[:-1] + "+", id="outside-base64url"),
        pytest.param("A", id="impossible-padding"),
        pytest.param("", id="empty"),
        pytest.param(_raw("été|x"), id="not-ascii"),
        pytest.param(_raw(f"2026-11-09T12:00:00+00:00{ROW}"), id="no-separator"),
        pytest.param(_raw(f"2026-11-09T12:00:00+00:00|{ROW}|x"), id="two-separators"),
        pytest.param(_raw(f"2026-11-09T12:00:00|{ROW}"), id="no-offset"),
        pytest.param(_raw(f"yesterday|{ROW}"), id="not-a-time"),
        pytest.param(_raw(f"0001-01-01T00:00:00+01:00|{ROW}"), id="year-1-with-offset"),
        pytest.param(_raw(f"9999-12-31T23:59:59-01:00|{ROW}"), id="year-9999-with-offset"),
        pytest.param(_raw("2026-11-09T12:00:00+00:00|not-a-uuid"), id="bad-uuid"),
    ],
)
def test_every_bad_cursor_gets_one_fixed_422_that_echoes_nothing(cursor: str) -> None:
    with pytest.raises(HTTPException) as refusal:
        decode_cursor(cursor)

    assert refusal.value.status_code == 422
    assert refusal.value.detail == INVALID
