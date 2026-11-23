"""Turning a cell value from a request into the stored value (K1, O4, X11, F6).

Field-type rules come from the Sandbox validators (`sandbox/fields/validation.py`), run on a
transient field that carries the column's type. Numbers arrive as JSON numbers, or as text
in the organization's locale (O4). Whole and plain numbers are stored as JSON numbers, and
decimals as canonical decimal strings, as the Sandbox stores them. Text that looks like a
formula stays text: nothing in a cell is ever evaluated (X11).
"""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any
from uuid import UUID, uuid4

from babel import Locale
from babel.numbers import NumberFormatError, parse_decimal
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.systems.access.users.models import User
from app.systems.access.users.person_visibility import visible_person_ids
from app.systems.openview.worksheets.structure import (
    MAX_ROW_BYTES,
    MAX_TEXT_CELL_CHARACTERS,
    Column,
    SheetDecimalColumn,
    SheetLinkColumn,
    SheetSelectColumn,
)
from app.systems.sandbox.fields.models import Field
from app.systems.sandbox.fields.validation import validate_field_value

READ_ONLY_TYPES = frozenset({"lookup", "computed", "sheet_lookup"})
_TEXT_TYPES = frozenset({"text", "long_text", "email", "url"})
# A JSON number keeps a decimal exactly when it has at most 15 significant digits.
_DECIMAL_DIGITS = 15


@dataclass(frozen=True)
class LinkValue:
    record_id: UUID


@dataclass(frozen=True)
class UnlinkedValue:
    text: str


def worksheet_limit(limit: str, maximum: int, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "worksheet_limit", "message": message, "limit": limit,
                "maximum": maximum},
    )


def cell_error(code: str, key: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, "message": message, "key": key},
    )


def row_bytes(data: dict[str, Any]) -> int:
    """The stored size of a row's cells: compact UTF-8 JSON (D8 row and sheet sizes)."""

    return len(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode())


def check_row_size(data: dict[str, Any]) -> int:
    size = row_bytes(data)
    if size > MAX_ROW_BYTES:
        raise worksheet_limit("row_size", MAX_ROW_BYTES, "A row holds at most 32 KiB of data")
    return size


def _text(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise cell_error("cell_invalid", key, "Enter text")
    if len(value) > MAX_TEXT_CELL_CHARACTERS:
        raise worksheet_limit(
            "cell", MAX_TEXT_CELL_CHARACTERS, "A text cell holds at most 4,000 characters"
        )
    return value


def _number(key: str, value: Any, locale: str) -> Decimal:
    if isinstance(value, bool):
        raise cell_error("cell_invalid", key, "Enter a number")
    if isinstance(value, int | float):
        if not isfinite(value):
            raise cell_error("cell_invalid", key, "Enter a number")
        return Decimal(str(value))
    if isinstance(value, str) and value.strip():
        try:
            return parse_decimal(value.strip(), locale=Locale.parse(locale, sep="-"))
        except (NumberFormatError, InvalidOperation, ValueError) as error:
            raise cell_error("cell_invalid", key, "Enter a number") from error
    raise cell_error("cell_invalid", key, "Enter a number")


def _json_number(key: str, number: Decimal) -> int | float:
    if number == number.to_integral_value():
        return int(number)
    if len(number.normalize().as_tuple().digits) > _DECIMAL_DIGITS:
        raise cell_error("cell_invalid", key, "Use at most 15 significant digits")
    return float(number)


def _field_rules(key: str, column: Column, value: Any) -> Any:
    field = Field(id=uuid4(), type=column.type, config={}, required=False)
    try:
        return validate_field_value(field, value)
    except ValueError as error:
        raise cell_error("cell_invalid", key, f"Not a valid {column.name} value") from error


def convert_cell(
    db: Session, actor: User, key: str, column: Column, value: Any, locale: str,
) -> Any:
    """The stored JSON value, a :class:`LinkValue`, an :class:`UnlinkedValue` or None."""

    if column.type in READ_ONLY_TYPES:
        raise cell_error("column_read_only", key, f"{column.name} cannot be edited")
    if value is None:
        return None
    if isinstance(column, SheetLinkColumn):
        if isinstance(value, dict) and set(value) == {"record_id"}:
            try:
                return LinkValue(UUID(str(value["record_id"])))
            except ValueError as error:
                raise cell_error("link_target_invalid", key, "Choose a record") from error
        if isinstance(value, dict) and set(value) == {"unlinked"}:
            return UnlinkedValue(_text(key, value["unlinked"]))
        raise cell_error("cell_invalid", key, "Choose a record")
    if column.type in _TEXT_TYPES:
        return _field_rules(key, column, _text(key, value))
    if isinstance(column, SheetDecimalColumn):
        # Stored as the Sandbox stores decimals: a canonical decimal string (D1.7).
        return _field_rules(key, column, format(_number(key, value, locale), "f"))
    if column.type in {"int", "number"}:
        number = _number(key, value, locale)
        if column.type == "int" and number != number.to_integral_value():
            raise cell_error("cell_invalid", key, "Enter a whole number")
        return _json_number(key, number)
    if isinstance(column, SheetSelectColumn):
        for option in column.select.options:
            if value in (option.id, option.label):
                return option.id
        raise cell_error("cell_invalid", key, f"Choose one of the {column.name} options")
    if column.type == "user":
        try:
            person = UUID(str(value))
        except ValueError as error:
            raise cell_error("cell_invalid", key, "Choose a person") from error
        if person not in visible_person_ids(db, actor, [person]):
            raise cell_error("cell_invalid", key, "Choose a person")
        return str(person)
    return _field_rules(key, column, value)  # boolean, date, datetime
