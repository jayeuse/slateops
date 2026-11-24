"""A row save that races a leave or a share removal (L3, D3.3; SH-57).

Two real PostgreSQL sessions run the real functions. One is held at a statement after it has
taken its locks; the test waits until the other is blocked behind it, then lets it go. Each
order ends with either the save committed first, or the save refused once the change is
visible: no save commits after the sheet reads as open or after the share is gone.
"""

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine, text
from uuid6 import uuid7

import app.systems.access.users.account_operations as account_operations
from app.core.database.organization_scope import scope_session
from app.core.database.session import AuditSession
from app.systems.access.users.models import User
from app.systems.access.users.schemas import UserUpdate
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.openview.worksheets.row_writes import write_rows
from app.systems.openview.worksheets.schemas import (
    SheetCellChange,
    SheetRowBatchUpdate,
    SheetValueCell,
)
from app.systems.openview.worksheets.shares import remove_share
from tests.conftest import guarded_create_engine
from tests.race_support import WAIT, StatementPause, join, start, wait_until_blocked_by
from tests.worksheets.committed_support import CommittedSheet
from tests.worksheets.committed_support import committed_sheet as committed_sheet

pytestmark = pytest.mark.integration


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Engine]]:
    monkeypatch.setattr(account_operations, "_record_outcome", lambda *_a, **_k: None)
    first = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    second = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    yield first, second
    first.dispose()
    second.dispose()


def _in_session(engine: Engine, world: CommittedSheet, act: Callable[[Any], Any]) -> Any:
    with AuditSession(engine, expire_on_commit=False) as db:
        scope_session(db, world.org_id)
        db.info[AUDIT_CONTEXT_KEY] = AuditContext(
            request_id=uuid7(), request_method="POST", request_path="/api/race",
        )
        try:
            return act(db)
        except HTTPException as error:
            db.rollback()
            return error.status_code, error.detail["code"]


def _disable(engine: Engine, world: CommittedSheet) -> Any:
    def act(db: Any) -> str:
        admin = db.get(User, world.admin_id)
        account_operations.update_user(world.owner_id, UserUpdate(status="disabled"), admin, db)
        return "disabled"

    return _in_session(engine, world, act)


def _save(engine: Engine, world: CommittedSheet) -> Any:
    def act(db: Any) -> str:
        editor = db.get(User, world.editor_id)
        change = SheetCellChange(value="y", expected=SheetValueCell(value="x"))
        write_rows(db, editor, world.sheet_id, [],
                   [SheetRowBatchUpdate(row_id=world.row_id, cells={"c3": change})],
                   conflict="cell_changed")
        db.commit()
        return "saved"

    return _in_session(engine, world, act)


def _remove(engine: Engine, world: CommittedSheet) -> Any:
    def act(db: Any) -> str:
        remove_share(db, db.get(User, world.owner_id), world.sheet_id, world.share_id)
        db.commit()
        return "removed"

    return _in_session(engine, world, act)


def _race(world: CommittedSheet, first: tuple[Engine, Callable[..., Any], str],
          second: tuple[Engine, Callable[..., Any]]) -> tuple[Any, Any]:
    """Hold ``first`` at its statement, block ``second`` behind it, then release both."""

    engine, action, held_at = first
    pause = StatementPause(engine, held_at)
    try:
        held = start(lambda: action(engine, world))
        assert pause.paused.wait(WAIT), "the first session never reached its held statement"
        other = start(lambda: second[1](second[0], world))
        wait_until_blocked_by(world.owner_engine, pause.holder_pid)
        pause.release.set()
        return join(*held), join(*other)
    finally:
        pause.remove()


def _cell(world: CommittedSheet) -> str:
    with world.owner_engine.connect() as connection:
        return str(connection.scalar(
            text("SELECT data ->> 'c3' FROM public.worksheet_rows WHERE id = :id"),
            {"id": world.row_id},
        ))


def test_a_save_behind_a_disable_is_refused_once_the_sheet_is_open(
    committed_sheet: CommittedSheet, engines: tuple[Engine, Engine],
) -> None:
    leave, save = engines
    outcomes = _race(committed_sheet, (leave, _disable, "UPDATE users"), (save, _save))
    assert outcomes == ("disabled", (403, "worksheet_read_only"))
    assert _cell(committed_sheet) == "x"


def test_a_save_ahead_of_a_disable_commits_first(
    committed_sheet: CommittedSheet, engines: tuple[Engine, Engine],
) -> None:
    save, leave = engines
    outcomes = _race(committed_sheet, (save, _save, "UPDATE worksheet_rows"), (leave, _disable))
    assert outcomes == ("saved", "disabled")
    assert _cell(committed_sheet) == "y"


def test_a_share_removal_waits_for_a_save_in_progress(
    committed_sheet: CommittedSheet, engines: tuple[Engine, Engine],
) -> None:
    save, removal = engines
    outcomes = _race(committed_sheet, (save, _save, "UPDATE worksheet_rows"), (removal, _remove))
    assert outcomes == ("saved", "removed")
    assert _cell(committed_sheet) == "y"


def test_a_save_behind_a_share_removal_finds_the_sheet_gone(
    committed_sheet: CommittedSheet, engines: tuple[Engine, Engine],
) -> None:
    removal, save = engines
    outcomes = _race(committed_sheet, (removal, _remove, "UPDATE worksheet_shares"),
                     (save, _save))
    assert outcomes == ("removed", (404, "worksheet_not_found"))
    assert _cell(committed_sheet) == "x"
