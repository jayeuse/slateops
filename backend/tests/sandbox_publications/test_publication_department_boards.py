"""A Sandbox publish gives every department its Board and keeps it in step."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.systems.boards.models import Board, BoardScope
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.designs.service import read_document, replace_document
from app.systems.sandbox.publications.planner import publication_plan
from tests.rbac.support import add_department
from tests.sandbox_publications.support import (
    binding,
    bound_department,
    publish_revision,
    publish_saved,
    publish_structure,
    publishable_document,
)

pytestmark = pytest.mark.integration


def _department_boards(db: Session) -> dict[object, Board]:
    return {
        board.department_id: board
        for board in db.scalars(
            select(Board).where(
                Board.scope == BoardScope.DEPARTMENT.value, Board.is_deleted.is_(False)
            )
        )
    }


def test_a_published_department_gets_its_board(integration_owner_db: Session) -> None:
    db = integration_owner_db
    publisher, document = publish_structure(db, publishable_document())

    boards = _department_boards(db)
    for department_document in document.design.departments:
        department = db.get(
            Department, binding(db, "department", department_document.id).department_id
        )
        assert department is not None
        board = boards[department.id]
        assert board.name == department_document.name
        assert board.status == "active"

    renamed = document.model_copy(deep=True)
    commercial = next(item for item in renamed.design.departments if item.id == "sample-commercial")
    commercial.name = "Sales"
    commercial.closed = True
    for module in renamed.design.modules:
        if module.department_id == "sample-commercial":
            module.closed = True
            for field in module.fields:
                field.closed = True
    for relationship in list(renamed.design.relationships):
        renamed.design.relationships.remove(relationship)
    publish_revision(db, publisher, renamed, "close-commercial")

    department_id = binding(db, "department", "sample-commercial").department_id
    board = _department_boards(db)[department_id]
    db.refresh(board)
    assert board.name == "Sales"
    assert board.status == "archived"
    assert len([item for item in _department_boards(db) if item == department_id]) == 1


def test_sd_c23_the_review_lists_each_board_change_and_the_publish_does_exactly_those(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = publish_structure(db, publishable_document())
    operations = bound_department(db, "sample-operations")
    commercial = bound_department(db, "sample-commercial")
    boards = _department_boards(db)
    boards[operations.id].name = "Old operations"
    boards[commercial.id].is_deleted = True
    boards[commercial.id].deleted_at = datetime.now(UTC)
    unbound = add_department(db, "Legacy")
    db.flush()

    changed = document.model_copy(deep=True)
    changed.design.modules[0].name = "Requests renamed"
    current = read_document(db)
    saved = replace_document(
        db, actor_id=publisher.id, expected_revision=current.revision, document=changed
    )
    review = publication_plan(db, saved.document)

    assert [
        (change.sandbox_id, change.action, change.label)
        for change in review.changes
        if change.kind == "board"
    ] == sorted(
        [
            (f"{unbound.id}#board", "create", "Legacy"),
            ("sample-commercial#board", "create", "Commercial"),
            ("sample-operations#board", "update", "Operations"),
        ]
    )
    assert review.counts.boards == 3
    publish_saved(
        db,
        publisher.id,
        saved,
        review,
        token_digest="b" * 64,
        idempotency_key=f"boards-{publisher.id}",
    )
    boards = _department_boards(db)
    assert {
        department_id: boards[department_id].name
        for department_id in (operations.id, commercial.id, unbound.id)
    } == {operations.id: "Operations", commercial.id: "Commercial", unbound.id: "Legacy"}
