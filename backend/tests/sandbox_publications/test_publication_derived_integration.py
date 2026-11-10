"""A department that a publish creates open gets its derived set in the same publish.

Setup spec slice 1: SD-C1 to SD-C6, SD-C8, SD-C21, SD-C26 (SD-C7, SD-C25 are in the race
file; SD-C23 is in the Board file; SD-C22 is in the router and planner files).
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.systems.sandbox.derived.planning as derived_planning
import app.systems.sandbox.publications.executor as publication_executor
from app.systems.access.policy.models import Group, GroupAccess, GroupMember
from app.systems.access.users.models import User, UserRole
from app.systems.comms.access import conversation_level
from app.systems.comms.conversations.models import CommsCategory, CommsConversation, CommsMember
from app.systems.comms.messages.models import CommsConversationCounter
from app.systems.manage.audit.context import set_audit_actor
from app.systems.openview.dashboards.models import Dashboard, DashboardWidget
from app.systems.openview.dashboards.service import stage_dashboard
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.models import SandboxDerivedObject
from app.systems.sandbox.designs.schemas import DepartmentDocument, SandboxDocument
from app.systems.sandbox.designs.service import read_document, replace_document
from app.systems.sandbox.publications.executor import PublicationError
from app.systems.sandbox.publications.planner import PublicationPlan, publication_plan
from app.systems.sandbox.publications.schemas import PublicationChange, PublicationCounts
from tests.rbac.support import add_user, organization
from tests.sandbox_publications.support import (
    bound_department,
    publish_saved,
    publish_structure,
)

pytestmark = pytest.mark.integration


def _with_department(
    document: SandboxDocument, sandbox_id: str, name: str, *, closed: bool = False
) -> SandboxDocument:
    changed = document.model_copy(deep=True)
    changed.design.departments.append(DepartmentDocument(id=sandbox_id, name=name, closed=closed))
    changed.design.layout[sandbox_id] = changed.design.layout["sample-operations"].model_copy(
        deep=True
    )
    return changed


def _review(db: Session, publisher: User, document: SandboxDocument) -> tuple[Any, PublicationPlan]:
    current = read_document(db)
    saved = replace_document(
        db, actor_id=publisher.id, expected_revision=current.revision, document=document
    )
    return saved, publication_plan(db, saved.document)


def _publish(db: Session, publisher: User, saved: Any, review: PublicationPlan, key: str) -> None:
    publish_saved(
        db,
        publisher.id,
        saved,
        review,
        token_digest=sha256(f"{key}-{publisher.id}".encode()).hexdigest(),
        idempotency_key=f"{key}-{publisher.id}",
    )


def _published(db: Session) -> tuple[User, SandboxDocument]:
    publisher, document = publish_structure(db)
    set_audit_actor(db, publisher.id)
    return publisher, document


def _count(db: Session, model: Any) -> int:
    org = organization(db).id
    return int(db.scalar(select(func.count()).select_from(model).where(model.org_id == org)) or 0)


def _derived_counts(db: Session) -> dict[str, int]:
    return {
        "groups": _count(db, Group),
        "dashboards": _count(db, Dashboard),
        "categories": _count(db, CommsCategory),
        "channels": _count(db, CommsConversation),
        "links": _count(db, SandboxDerivedObject),
    }


def _change(kind: str, sandbox_id: str, label: str, action: str = "create") -> PublicationChange:
    return PublicationChange.model_validate(
        {"kind": kind, "action": action, "sandboxId": sandbox_id, "label": label}
    )


def test_sd_c1_review_lists_the_derived_set_under_a_new_department(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = _published(db)

    _saved, review = _review(db, publisher, _with_department(document, "dep-sales", "Sales"))

    assert not review.blockers
    assert list(review.changes) == [
        _change("board", "dep-sales#board", "Sales"),
        _change("category", "dep-sales#category", "Sales"),
        _change("channel", "dep-sales#channel", "Sales"),
        _change("dashboard", "dep-sales#dashboard", "Sales dashboard"),
        _change("department", "dep-sales", "Sales"),
        _change("group", "dep-sales#managers", "Sales managers · manage"),
        _change("group", "dep-sales#members", "Sales members · write"),
        _change("group", "dep-sales#viewers", "Sales viewers · read"),
    ]
    assert review.counts == PublicationCounts(
        departments=1, groups=3, dashboards=1, boards=1, categories=1, channels=1
    )


def test_sd_c2_c3_publish_creates_the_set_with_its_links_and_comms_events(
    integration_owner_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = integration_owner_db
    publisher, document = _published(db)
    events: list[str] = []
    real_event = derived_planning.organization_event

    def record_event(session: Session, kind: Any) -> None:
        events.append(kind)
        real_event(session, kind)

    monkeypatch.setattr(derived_planning, "organization_event", record_event)
    saved, review = _review(db, publisher, _with_department(document, "dep-sales", "Sales"))
    _publish(db, publisher, saved, review, "sales")

    sales = bound_department(db, "dep-sales")
    links = {
        link.role: link
        for link in db.scalars(
            select(SandboxDerivedObject).where(SandboxDerivedObject.department_id == sales.id)
        )
    }
    assert set(links) == {"managers", "members", "viewers", "dashboard", "category", "channel"}
    groups = {
        role: db.get(Group, links[role].group_id) for role in ("managers", "members", "viewers")
    }
    assert {role: group.name for role, group in groups.items() if group is not None} == {
        "managers": "Sales managers",
        "members": "Sales members",
        "viewers": "Sales viewers",
    }
    for role, level in (("managers", "manage"), ("members", "write"), ("viewers", "read")):
        group = groups[role]
        assert group is not None
        access = db.scalars(select(GroupAccess).where(GroupAccess.group_id == group.id)).all()
        assert [(row.department_id, row.module_id, row.level) for row in access] == [
            (sales.id, None, level)
        ]
        assert (
            db.scalar(
                select(func.count())
                .select_from(GroupMember)
                .where(GroupMember.group_id == group.id)
            )
            == 0
        )
    dashboard = db.get(Dashboard, links["dashboard"].dashboard_id)
    assert dashboard is not None
    assert (dashboard.name, dashboard.department_id, dashboard.is_home) == (
        "Sales dashboard",
        sales.id,
        True,
    )
    assert (dashboard.refresh_cadence, dashboard.position) == ("manual", 0)
    assert (
        db.scalar(
            select(func.count())
            .select_from(DashboardWidget)
            .where(DashboardWidget.dashboard_id == dashboard.id)
        )
        == 0
    )
    category = db.get(CommsCategory, links["category"].category_id)
    channel = db.get(CommsConversation, links["channel"].conversation_id)
    assert category is not None and channel is not None
    assert (category.name, category.department_id) == ("Sales", sales.id)
    assert (channel.name, channel.kind, channel.scope) == ("Sales", "channel", "department")
    assert (channel.department_id, channel.category_id) == (sales.id, category.id)
    # SD-C3: the publishing administrator creates it; no member row; its counter exists.
    assert channel.created_by == publisher.id
    assert (
        db.scalar(
            select(func.count())
            .select_from(CommsMember)
            .where(CommsMember.conversation_id == channel.id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(CommsConversationCounter.last_seq).where(
                CommsConversationCounter.conversation_id == channel.id
            )
        )
        == 0
    )
    assert events == ["structure", "grants"]

    writer = add_user(db, "sales-writer")
    reader = add_user(db, "sales-reader")
    guest = add_user(db, "sales-guest", role=UserRole.GUEST)
    for user, role in ((writer, "members"), (reader, "viewers"), (guest, "members")):
        group = groups[role]
        assert group is not None
        db.add(GroupMember(org_id=sales.org_id, group_id=group.id, user_id=user.id))
    db.flush()
    assert [conversation_level(db, user, channel) for user in (writer, reader, guest)] == [
        "post",
        "read",
        "read",
    ]


def test_sd_c4_existing_departments_without_links_get_nothing(
    integration_owner_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = integration_owner_db
    real = derived_planning.derived_changes
    # The organization as it was before this change: published departments, no link rows.
    monkeypatch.setattr(
        derived_planning,
        "derived_changes",
        lambda outcomes: [change for change in real(outcomes) if change.kind == "board"],
    )
    publisher, document = _published(db)
    monkeypatch.undo()
    before = _derived_counts(db)
    assert before["links"] == 0

    changed = _with_department(document, "dep-sales", "Sales")
    changed.design.modules[0].name = "Requests renamed"
    saved, review = _review(db, publisher, changed)
    # SD5: the review itself derives nothing for departments this publish does not create.
    assert {
        change.sandbox_id.split("#")[0]
        for change in review.changes
        if change.kind in ("group", "dashboard", "board", "category", "channel")
    } == {"dep-sales"}
    _publish(db, publisher, saved, review, "module-and-sales")

    sales = bound_department(db, "dep-sales")
    after = _derived_counts(db)
    assert {key: after[key] - before[key] for key in after} == {
        "groups": 3,
        "dashboards": 1,
        "categories": 1,
        "channels": 1,
        "links": 6,
    }
    for column in (
        SandboxDerivedObject.department_id,
        Dashboard.department_id,
        CommsConversation.department_id,
        CommsCategory.department_id,
    ):
        assert set(db.scalars(select(column).where(column.class_.org_id == sales.org_id))) == {
            sales.id
        }


def test_sd_c5_a_failed_derived_step_rolls_back_the_whole_publish(
    integration_owner_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = integration_owner_db
    publisher, document = _published(db)
    before = _derived_counts(db)
    saved, review = _review(db, publisher, _with_department(document, "dep-sales", "Sales"))

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("category helper failed")

    monkeypatch.setattr(derived_planning, "stage_category", fail)
    with pytest.raises(RuntimeError, match="category helper failed"):
        _publish(db, publisher, saved, review, "sales-fails")
    db.rollback()

    assert _derived_counts(db) == before
    assert db.scalar(select(Department.id).where(Department.department_name == "Sales")) is None


def test_sd_c6_an_active_group_name_blocks_the_review(integration_owner_db: Session) -> None:
    db = integration_owner_db
    publisher, document = _published(db)
    taken = Group(org_id=bound_department(db, "sample-operations").org_id, name="sales MANAGERS")
    db.add(taken)
    db.flush()

    _saved, review = _review(db, publisher, _with_department(document, "dep-sales", "Sales"))

    assert [(b.code, b.target_id, b.message) for b in review.blockers] == [
        (
            "derived_name_unavailable",
            "dep-sales",
            'Sales needs the group name "Sales managers", which "sales MANAGERS" already uses',
        )
    ]


def test_sd_c8_a_new_closed_department_derives_only_its_board(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = _published(db)
    before = _derived_counts(db)
    changed = _with_department(document, "dep-sales", "Sales", closed=True)

    saved, review = _review(db, publisher, changed)
    assert [(c.kind, c.sandbox_id, c.action) for c in review.changes] == [
        ("board", "dep-sales#board", "create"),
        ("department", "dep-sales", "create"),
    ]
    _publish(db, publisher, saved, review, "sales-closed")

    assert _derived_counts(db) == before


def test_sd_c21_two_new_departments_with_one_group_name_block_the_review(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = _published(db)
    changed = _with_department(
        _with_department(document, "dep-sales", "Sales"), "dep-sales-lower", "sales"
    )

    _saved, review = _review(db, publisher, changed)

    assert [(b.code, b.target_id, b.message) for b in review.blockers] == [
        (
            "derived_name_unavailable",
            "dep-sales-lower",
            f'Sales and sales need the same group name "Sales {role}"',
        )
        for role in ("managers", "members", "viewers")
    ]


def test_sd_c26_the_publish_refuses_a_sync_that_made_more_than_its_review(
    integration_owner_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = integration_owner_db
    publisher, document = _published(db)
    before = _derived_counts(db)
    saved, review = _review(db, publisher, _with_department(document, "dep-sales", "Sales"))
    real = derived_planning.create_derived_items

    def one_more(session: Session, changes: Any, departments: Any, actor_id: Any) -> Any:
        made = real(session, changes, departments, actor_id)
        extra = stage_dashboard(session, department_id=departments["dep-sales"].id, name="Extra")
        return [*made, derived_planning.made_change("dep-sales", "dashboard", extra)]

    monkeypatch.setattr(publication_executor, "create_derived_items", one_more)
    with pytest.raises(PublicationError) as refused:
        _publish(db, publisher, saved, review, "sales-extra")
    db.rollback()

    assert (refused.value.code, refused.value.status_code) == ("publication_unavailable", 500)
    assert _derived_counts(db) == before
    assert db.scalar(select(Department.id).where(Department.department_name == "Sales")) is None
