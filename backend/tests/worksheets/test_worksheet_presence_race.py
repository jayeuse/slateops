"""A presence token that races a share removal (PR5, D13; Security review N-2).

The removal holds the sheet row for update until it commits. The token request reads the
person's access only once it holds that row for share, so it sees the share gone, answers
404 and leaves no grant behind.
"""

import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine, select
from uuid6 import uuid7

from app.core.database.organization_scope import scope_session
from app.core.database.session import AuditSession
from app.systems.access.users.models import User
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.openview.worksheets.models import Worksheet, WorksheetRealtimeGrant
from app.systems.openview.worksheets.presence import issue_presence_token
from app.systems.openview.worksheets.shares import remove_share
from tests.conftest import guarded_create_engine
from tests.race_support import backend_pid, join, start, wait_until_blocked_by
from tests.worksheets.committed_support import CommittedSheet
from tests.worksheets.committed_support import committed_sheet as committed_sheet

pytestmark = pytest.mark.integration


@pytest.fixture
def runtime() -> Iterator[Engine]:
    engine = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    yield engine
    engine.dispose()


def _session(engine: Engine, world: CommittedSheet) -> AuditSession:
    db = AuditSession(engine, expire_on_commit=False)
    scope_session(db, world.org_id)
    db.info[AUDIT_CONTEXT_KEY] = AuditContext(
        request_id=uuid7(), request_method="POST", request_path="/api/race",
    )
    return db


def test_a_token_request_waits_for_a_share_removal_and_then_refuses(
    committed_sheet: CommittedSheet, runtime: Engine,
) -> None:
    world = committed_sheet
    removal = _session(runtime, world)
    owner = removal.get(User, world.owner_id)
    remove_share(removal, owner, world.sheet_id, world.share_id)  # holds its locks, open

    def token() -> Any:
        with _session(runtime, world) as db:
            editor = db.get(User, world.editor_id)
            try:
                issue_presence_token(world.sheet_id, editor, db)
            except HTTPException as refused:
                db.rollback()
                return refused.status_code
            return 200

    thread, results = start(token)
    try:
        wait_until_blocked_by(world.owner_engine, backend_pid(removal))
        removal.commit()
    finally:
        removal.close()
    assert join(thread, results) == 404
    with _session(runtime, world) as db:
        assert db.scalars(select(WorksheetRealtimeGrant.id).where(
            WorksheetRealtimeGrant.worksheet_id == world.sheet_id)).all() == []


def test_a_person_who_cannot_see_the_sheet_gets_404_while_a_writer_holds_it(
    committed_sheet: CommittedSheet, runtime: Engine,
) -> None:
    """D14 R5, PR3: a hidden sheet answers the 404 of a missing one at once, even while
    another session holds the sheet row; it never waits for the writer."""

    world = committed_sheet
    holder = _session(runtime, world)
    holder.execute(select(Worksheet.id).where(Worksheet.id == world.sheet_id)
                   .with_for_update())

    def token() -> Any:
        with _session(runtime, world) as db:
            admin = db.get(User, world.admin_id)  # sees no private sheet it is not shared
            try:
                issue_presence_token(world.sheet_id, admin, db)
            except HTTPException as refused:
                db.rollback()
                return refused.status_code
            return 200

    try:
        thread, results = start(token)
        assert join(thread, results) == 404
    finally:
        holder.rollback()
        holder.close()
