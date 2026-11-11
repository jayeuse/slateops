"""A new department's draft ``setup`` clears derived items before its first publish.

Setup spec slice 4: SD-C18, SD-C19, SD14 both ways, and cleared groups with R12 (BE-SD5, SD13).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.systems.access.policy.models import Group, GroupAccess
from app.systems.comms.conversations.models import CommsCategory, CommsConversation
from app.systems.manage.audit.context import set_audit_actor
from app.systems.sandbox.designs.schemas import DepartmentSetup, SandboxDocument
from tests.sandbox_publications.derived_support import apply_review, draft, link_rows, review_draft
from tests.sandbox_publications.support import bound_department, publish_structure

pytestmark = pytest.mark.integration


def _with_setup(document: SandboxDocument, sandbox_id: str, **items: bool) -> SandboxDocument:
    changed = document.model_copy(deep=True)
    for department in changed.design.departments:
        if department.id == sandbox_id:
            department.setup = DepartmentSetup.model_validate(items)
    return changed


def _count(db: Session, model: Any, *where: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _kinds(review: Any, sandbox_id: str) -> list[tuple[str, str]]:
    return [
        (change.kind, change.action)
        for change in review.changes
        if change.sandbox_id.startswith(f"{sandbox_id}#")
    ]


def test_sd_c18_c19_a_cleared_channel_is_never_created_and_its_category_stays_empty(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = publish_structure(db)
    set_audit_actor(db, publisher.id)
    plain = draft(document, dep_sales=("Sales", False))
    uncleared_saved, uncleared = review_draft(db, publisher, plain)

    cleared = _with_setup(plain, "dep-sales", channel=False)
    saved, review = review_draft(db, publisher, cleared)

    assert _kinds(review, "dep-sales") == [
        ("board", "create"),
        ("category", "create"),
        ("dashboard", "create"),
        ("group", "create"),
        ("group", "create"),
        ("group", "create"),
    ]
    assert (review.counts.channels, review.counts.categories) == (0, 1)
    assert review.impact_digest != uncleared.impact_digest
    assert saved.content_hash != uncleared_saved.content_hash
    apply_review(db, publisher, saved, review)

    sales = bound_department(db, "dep-sales")
    links = link_rows(db, sales)
    assert set(links) == {"managers", "members", "viewers", "dashboard", "category"}
    assert _count(db, CommsConversation, CommsConversation.department_id == sales.id) == 0
    category = db.get(CommsCategory, links["category"].category_id)
    assert category is not None and category.name == "Sales"
    assert _count(db, CommsConversation, CommsConversation.category_id == category.id) == 0

    # SD-C19: a later publish ignores the setup of a bound department, even one turned back on.
    later = _with_setup(draft(cleared, dep_sales=("Sales East", False)), "dep-sales")
    later_saved, later_review = review_draft(db, publisher, later)
    assert ("channel", "create") not in _kinds(later_review, "dep-sales")
    apply_review(db, publisher, later_saved, later_review)

    assert bound_department(db, "dep-sales").department_name == "Sales East"
    assert "channel" not in link_rows(db, sales)
    assert _count(db, CommsConversation, CommsConversation.department_id == sales.id) == 0


def test_sd14_a_cleared_category_puts_the_derived_channel_in_no_category(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = publish_structure(db)
    set_audit_actor(db, publisher.id)

    saved, review = review_draft(
        db, publisher, _with_setup(draft(document, dep_sales=("Sales", False)), "dep-sales",
                                   category=False)
    )
    assert ("category", "create") not in _kinds(review, "dep-sales")
    assert (review.counts.channels, review.counts.categories) == (1, 0)
    apply_review(db, publisher, saved, review)

    sales = bound_department(db, "dep-sales")
    links = link_rows(db, sales)
    assert set(links) == {"managers", "members", "viewers", "dashboard", "channel"}
    channel = db.get(CommsConversation, links["channel"].conversation_id)
    assert channel is not None
    assert (channel.name, channel.department_id, channel.category_id) == ("Sales", sales.id, None)
    assert _count(db, CommsCategory, CommsCategory.department_id == sales.id) == 0


def test_cleared_groups_create_no_group_and_raise_no_derived_name_blocker(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = publish_structure(db)
    set_audit_actor(db, publisher.id)
    taken = Group(org_id=bound_department(db, "sample-operations").org_id, name="sales MANAGERS")
    db.add(taken)
    db.flush()

    saved, review = review_draft(
        db, publisher, _with_setup(draft(document, dep_sales=("Sales", False)), "dep-sales",
                                   groups=False)
    )
    assert list(review.blockers) == []
    assert _kinds(review, "dep-sales") == [
        ("board", "create"),
        ("category", "create"),
        ("channel", "create"),
        ("dashboard", "create"),
    ]
    assert review.counts.groups == 0
    apply_review(db, publisher, saved, review)

    sales = bound_department(db, "dep-sales")
    assert set(link_rows(db, sales)) == {"dashboard", "category", "channel"}
    assert _count(db, GroupAccess, GroupAccess.department_id == sales.id) == 0
    assert _count(db, Group, func.lower(Group.name).like("sales %")) == 1
