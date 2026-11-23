"""A lock wait past its bound answers 503 ``worksheet_busy`` (spec D3.3)."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import psycopg
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from uuid6 import uuid7

from app.systems.openview.worksheets import locking
from app.systems.openview.worksheets.models import Worksheet


def test_a_lock_wait_that_times_out_answers_busy_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(locking, "wait_briefly_for_locks", lambda _db: None)
    db = Mock()
    db.scalar.side_effect = OperationalError(
        "SELECT ... FOR SHARE", {}, psycopg.errors.LockNotAvailable("lock timeout"),
    )
    sheet = SimpleNamespace(id=uuid7(), owner_id=uuid7(), record_id=uuid7(), module_id=None)
    with pytest.raises(HTTPException) as refused:
        locking.lock_worksheet(db, cast(Worksheet, sheet))
    assert (refused.value.status_code, refused.value.detail) == (
        503, {"code": "worksheet_busy", "message": "The sheet is busy; try again"},
    )
    db.rollback.assert_called_once_with()
