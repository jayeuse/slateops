"""The keyset cursor of the three growth lists (D1): the position after the last row seen.

A cursor is base64url, with no padding, of ``<created_at ISO 8601 with offset>|<id>``. It is
not signed: it only moves the start inside rows the reader can already read, because its
condition is added to the scoped statement with AND. The decoder checks the length before
anything else and turns every failure into one fixed 422 that echoes nothing (H3 to H5).
"""

import base64
import binascii
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status

# A valid cursor is at most 92 characters: 32 of time, 1 separator and 36 of UUID, encoded.
CURSOR_MAX_LENGTH = 128
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


def invalid_cursor() -> HTTPException:
    """The one answer to a bad cursor, in the shape of a query validation error."""

    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"loc": ["query", "cursor"], "msg": "Invalid cursor", "type": "value_error"}],
    )


def cursor_with_offset() -> HTTPException:
    """A cursor replaces the offset; both together are refused."""

    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{
            "loc": ["query", "cursor"],
            "msg": "A cursor cannot be combined with an offset",
            "type": "value_error",
        }],
    )


def encode_cursor(at: datetime, identity: UUID) -> str:
    text = f"{at.isoformat()}|{identity}"
    return base64.urlsafe_b64encode(text.encode("ascii")).rstrip(b"=").decode("ascii")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    """The aware UTC time and the id that a cursor names, or the fixed 422."""

    if len(value) > CURSOR_MAX_LENGTH or not _BASE64URL.fullmatch(value):
        raise invalid_cursor()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        parts = raw.decode("ascii").split("|")
        if len(parts) != 2:
            raise ValueError("A cursor has one separator")
        at = datetime.fromisoformat(parts[0])
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("A cursor time has an offset")
        return at.astimezone(UTC), UUID(parts[1])
    except (ValueError, binascii.Error, UnicodeDecodeError, OverflowError):
        raise invalid_cursor() from None
