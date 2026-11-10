"""A linked department's derived items follow its name and state on the publish path.

Setup spec slice 2: SD-C9 to SD-C13, SD-C27, SD-C29 to SD-C31, and the rename half of R12.
The lifecycle path of SD-C11 to SD-C13 and SD-C32 is in ``lifecycle_integration``; the
branch rules of R7, R9 and R16 are owned by the ``follow_steps`` table in ``test_planner``.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.systems.access.policy.models import Group
from app.systems.comms.access import conversation_level
from app.systems.comms.realtime.models import CommsRealtimeGrant
from app.systems.manage.audit.models import AuditLog
from app.systems.sandbox.publications.planner import PublicationPlan
from tests.sandbox_publications.derived_support import (
    ROLES,
    add_people,
    apply_review,
    derived_rows,
    draft,
    kept_counts,
    link_rows,
    publish_draft,
    review_draft,
    with_sales,
)
from tests.sandbox_publications.support import bound_department

pytestmark = pytest.mark.integration


def _follow(review: PublicationPlan) -> list[tuple[str, str, str, str]]:
    return [
        (change.kind, change.sandbox_id, change.action, change.label)
        for change in review.changes
        if change.kind in ("group", "dashboard", "category", "channel")
    ]


def test_sd_c9_c10_only_a_department_rename_writes_the_derived_names(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    sales = bound_department(db, "dep-sales")
    derived_rows(db, sales)["channel"].name = "sales-chat"
    db.flush()

    # SD-C10: a publish that does not rename Sales keeps the person's channel name.
    document, review = publish_draft(db, publisher, draft(document, dep_other=("Other", False)))
    assert not [change for change in _follow(review) if change[1].startswith("dep-sales#")]
    assert derived_rows(db, sales)["channel"].name == "sales-chat"

    # SD-C9: the rename reviews and writes every derived name, the channel's included.
    _, review = publish_draft(db, publisher, draft(document, dep_sales=("Revenue", False)))

    assert _follow(review) == [
        ("category", "dep-sales#category", "update", "Revenue"),
        ("channel", "dep-sales#channel", "update", "Revenue"),
        ("dashboard", "dep-sales#dashboard", "update", "Revenue dashboard"),
        ("group", "dep-sales#managers", "update", "Revenue managers · manage"),
        ("group", "dep-sales#members", "update", "Revenue members · write"),
        ("group", "dep-sales#viewers", "update", "Revenue viewers · read"),
    ]
    assert {role: row.name for role, row in derived_rows(db, sales).items()} == {
        "managers": "Revenue managers",
        "members": "Revenue members",
        "viewers": "Revenue viewers",
        "dashboard": "Revenue dashboard",
        "category": "Revenue",
        "channel": "Revenue",
    }


def test_sd_c11_c12_publish_close_archives_the_channel_and_reopen_restores_it(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    sales = bound_department(db, "dep-sales")
    member, channel = add_people(db, sales, publisher)
    kept = kept_counts(db, sales, channel)
    assert conversation_level(db, member, channel) == "post"

    document, review = publish_draft(db, publisher, draft(document, dep_sales=("Sales", True)))

    assert _follow(review) == [("channel", "dep-sales#channel", "close", "Sales")]
    db.refresh(channel)
    assert channel.archived_at is not None
    assert kept_counts(db, sales, channel) == kept
    links = link_rows(db, sales)
    assert all(link.closed_at is not None for link in links.values())
    assert {role: link.archived_by_close for role, link in links.items()} == {
        role: role == "channel" for role in ROLES
    }
    assert links["channel"].close_archived_at == channel.archived_at
    assert {
        entity_id
        for entity_id in db.scalars(
            select(AuditLog.entity_id).where(
                AuditLog.entity_type == "sandbox_derived_objects",
                AuditLog.action == "update",
            )
        )
    } >= {link.id for link in links.values()}
    assert conversation_level(db, member, channel) == "none"
    assert conversation_level(db, publisher, channel) != "none"

    _, review = publish_draft(db, publisher, draft(document, dep_sales=("Sales", False)))

    assert _follow(review) == [("channel", "dep-sales#channel", "reopen", "Sales")]
    db.refresh(channel)
    assert channel.archived_at is None
    assert all(
        (link.closed_at, link.archived_by_close, link.close_archived_at) == (None, False, None)
        for link in link_rows(db, sales).values()
    )
    assert conversation_level(db, member, channel) == "post"


def test_sd_c13_a_person_archive_and_a_deleted_group_outlive_close_and_reopen(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    sales = bound_department(db, "dep-sales")
    rows = derived_rows(db, sales)
    archived_at = utc_now()
    rows["channel"].archived_at = archived_at
    rows["viewers"].is_deleted, rows["viewers"].deleted_at = True, utc_now()
    db.flush()
    groups = db.scalar(select(func.count()).select_from(Group))

    document, close = publish_draft(db, publisher, draft(document, dep_sales=("Sales", True)))
    _, reopen = publish_draft(db, publisher, draft(document, dep_sales=("Sales", False)))

    assert _follow(close) == _follow(reopen) == []
    db.refresh(rows["channel"])
    assert rows["channel"].archived_at == archived_at
    assert db.scalar(select(func.count()).select_from(Group)) == groups
    assert link_rows(db, sales)["viewers"].group_id == rows["viewers"].id


def test_sd_c27_a_swap_of_two_department_names_publishes(integration_owner_db: Session) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    document, _ = publish_draft(db, publisher, draft(document, dep_support=("Support", False)))

    publish_draft(
        db,
        publisher,
        draft(document, dep_sales=("Support", False), dep_support=("Sales", False)),
    )

    for key, name in (("dep-sales", "Support"), ("dep-support", "Sales")):
        rows = derived_rows(db, bound_department(db, key))
        assert [rows[role].name for role in ("managers", "members", "viewers")] == [
            f"{name} managers",
            f"{name} members",
            f"{name} viewers",
        ]


def test_sd_c29_c30_a_moved_category_stays_and_a_restored_dashboard_follows(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    sales = bound_department(db, "dep-sales")
    elsewhere = bound_department(db, "sample-operations")
    rows = derived_rows(db, sales)
    rows["category"].department_id = elsewhere.id
    rows["dashboard"].is_deleted, rows["dashboard"].deleted_at = True, utc_now()
    db.flush()
    rows["dashboard"].is_deleted, rows["dashboard"].deleted_at = False, None
    db.flush()

    _, review = publish_draft(db, publisher, draft(document, dep_sales=("Revenue", False)))

    assert ("category", "dep-sales#category", "update", "Revenue") not in _follow(review)
    db.refresh(rows["category"])
    assert (rows["category"].name, rows["category"].department_id) == ("Sales", elsewhere.id)
    assert rows["dashboard"].name == "Revenue dashboard"
    assert rows["channel"].name == "Revenue"


def test_r12_a_renamed_derived_group_name_in_use_blocks_the_review(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    db.add(Group(org_id=bound_department(db, "dep-sales").org_id, name="revenue MANAGERS"))
    db.flush()

    _, review = review_draft(db, publisher, draft(document, dep_sales=("Revenue", False)))

    assert [(item.code, item.target_id, item.message) for item in review.blockers] == [
        (
            "derived_name_unavailable",
            "dep-sales",
            'Revenue needs the group name "Revenue managers", which "revenue MANAGERS" '
            "already uses",
        )
    ]


def test_sd_c31_a_publish_close_revokes_live_grants_before_its_commit(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, document = with_sales(db)
    sales = bound_department(db, "dep-sales")
    member, channel = add_people(db, sales, publisher)
    grant = CommsRealtimeGrant(
        org_id=sales.org_id,
        user_id=member.id,
        conversation_id=channel.id,
        expires_at=utc_now().replace(year=utc_now().year + 1),
    )
    db.add(grant)
    db.flush()
    grant_id: UUID = grant.id
    at_commit: list[bool] = []
    real_commit = db.commit

    def commit() -> None:
        at_commit.append(
            db.scalar(select(CommsRealtimeGrant.id).where(CommsRealtimeGrant.id == grant_id))
            is not None
        )
        real_commit()

    saved, review = review_draft(db, publisher, draft(document, dep_sales=("Sales", True)))
    with patch.object(db, "commit", side_effect=commit):
        apply_review(db, publisher, saved, review)

    assert at_commit == [False]
