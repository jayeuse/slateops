"""Shared setup for the derived-item tests: a published department "Sales" and its items."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.systems.access.policy.models import Group, GroupAccess, GroupMember
from app.systems.access.users.models import User
from app.systems.comms.conversations.models import (
    CommsCategory,
    CommsChannelAccess,
    CommsConversation,
)
from app.systems.comms.messages.models import CommsMessage
from app.systems.manage.audit.context import set_audit_actor
from app.systems.openview.dashboards.models import Dashboard
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.models import SandboxDerivedObject
from app.systems.sandbox.designs.schemas import DepartmentDocument, SandboxDocument
from app.systems.sandbox.designs.service import read_document, replace_document
from app.systems.sandbox.publications.planner import PublicationPlan, publication_plan
from tests.rbac.support import add_user
from tests.sandbox_publications.support import publish_saved, publish_structure

ROLES = ("managers", "members", "viewers", "dashboard", "category", "channel")


def draft(document: SandboxDocument, **departments: tuple[str, bool]) -> SandboxDocument:
    """A copy of ``document`` with each named department added, renamed or closed."""

    changed = document.model_copy(deep=True)
    current = {item.id: item for item in changed.design.departments}
    for key, (name, closed) in departments.items():
        sandbox_id = key.replace("_", "-")
        if sandbox_id in current:
            current[sandbox_id].name, current[sandbox_id].closed = name, closed
            continue
        changed.design.departments.append(DepartmentDocument(id=sandbox_id, name=name))
        changed.design.layout[sandbox_id] = changed.design.layout["sample-operations"].model_copy(
            deep=True
        )
    return changed


def review_draft(
    db: Session, publisher: User, document: SandboxDocument
) -> tuple[Any, PublicationPlan]:
    current = read_document(db)
    saved = replace_document(
        db, actor_id=publisher.id, expected_revision=current.revision, document=document
    )
    return saved, publication_plan(db, saved.document)


def publish_draft(
    db: Session, publisher: User, document: SandboxDocument
) -> tuple[SandboxDocument, PublicationPlan]:
    saved, review = review_draft(db, publisher, document)
    apply_review(db, publisher, saved, review)
    return document, review


def apply_review(db: Session, publisher: User, saved: Any, review: PublicationPlan) -> None:
    assert not review.blockers
    key = uuid7().hex
    publish_saved(
        db,
        publisher.id,
        saved,
        review,
        token_digest=sha256(key.encode()).hexdigest(),
        idempotency_key=f"follow-{key}",
    )


def with_sales(db: Session) -> tuple[User, SandboxDocument]:
    publisher, document = publish_structure(db)
    set_audit_actor(db, publisher.id)
    document, _ = publish_draft(db, publisher, draft(document, dep_sales=("Sales", False)))
    return publisher, document


def link_rows(db: Session, department: Department) -> dict[str, SandboxDerivedObject]:
    return {
        link.role: link
        for link in db.scalars(
            select(SandboxDerivedObject).where(SandboxDerivedObject.department_id == department.id)
        )
    }


def derived_rows(db: Session, department: Department) -> dict[str, Any]:
    links = link_rows(db, department)
    rows: dict[str, Any] = {}
    for role in ROLES:
        link = links[role]
        rows[role] = (
            db.get(Group, link.group_id)
            if link.group_id
            else db.get(Dashboard, link.dashboard_id)
            if link.dashboard_id
            else db.get(CommsCategory, link.category_id)
            if link.category_id
            else db.get(CommsConversation, link.conversation_id)
        )
    return rows


def add_people(
    db: Session, sales: Department, publisher: User
) -> tuple[User, CommsConversation]:
    """A Sales member with a message and a D45 grant on the derived channel."""

    rows = derived_rows(db, sales)
    member = add_user(db, f"sales-member-{uuid7().hex[-8:]}")
    channel = rows["channel"]
    db.add_all(
        [
            GroupMember(org_id=sales.org_id, group_id=rows["members"].id, user_id=member.id),
            CommsChannelAccess(
                org_id=sales.org_id,
                conversation_id=channel.id,
                subject="user",
                user_id=publisher.id,
                level="read",
                created_by=publisher.id,
            ),
            CommsMessage(
                id=uuid7(),
                org_id=sales.org_id,
                conversation_id=channel.id,
                author_id=publisher.id,
                client_key=uuid7(),
                seq=1,
                body="Kept through close",
                send_fingerprint=uuid7().hex * 2,
            ),
        ]
    )
    db.flush()
    return member, channel


def kept_counts(db: Session, sales: Department, channel: CommsConversation) -> tuple[int, ...]:
    def count(model: Any, *where: Any) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    groups = [link.group_id for link in link_rows(db, sales).values() if link.group_id]
    return (
        count(CommsMessage, CommsMessage.conversation_id == channel.id),
        count(GroupMember, GroupMember.group_id.in_(groups)),
        count(CommsChannelAccess, CommsChannelAccess.conversation_id == channel.id),
        count(GroupAccess, GroupAccess.department_id == sales.id),
    )
