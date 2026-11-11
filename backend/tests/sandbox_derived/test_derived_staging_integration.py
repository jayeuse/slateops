"""The derived-item link table and the no-commit helpers a publish calls (BE-SD1, SD8, SD11).

Each helper test commits its setup first, then rolls back after the helper: a helper that
committed would leave its rows behind the rollback.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.systems.access.policy.models import AccessLevel, Group, GroupAccess, GroupMember
from app.systems.access.policy.staging import stage_group
from app.systems.access.users.models import User
from app.systems.comms.conversations.models import (
    CommsCategory,
    CommsConversation,
    CommsMember,
)
from app.systems.comms.conversations.mutations import stage_category, stage_department_channel
from app.systems.comms.messages.models import CommsConversationCounter
from app.systems.openview.dashboards.models import Dashboard
from app.systems.openview.dashboards.service import stage_dashboard
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.derived.models import SandboxDerivedObject
from tests.conftest import create_member, create_organization

pytestmark = pytest.mark.integration


def _setup(db: Session) -> tuple[UUID, User, Department]:
    organization = create_organization(db)
    admin, _ = create_member(db, organization, role="admin")
    department = Department(org_id=organization.id, department_name="Sales")
    db.add(department)
    db.flush()
    return organization.id, admin, department


def _closed_department(db: Session, org_id: UUID) -> Department:
    closed = Department(
        org_id=org_id, department_name="Closed", is_deleted=True,
        deleted_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    db.add(closed)
    db.flush()
    return closed


def _count(db: Session, model: Any, *where: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        pytest.param({"role": "dashboard", "target": "group"},
                     "ck_sandbox_derived_objects_target", id="target-of-another-role"),
        pytest.param({"role": "managers", "target": "group", "dashboard": True},
                     "ck_sandbox_derived_objects_target", id="two-targets"),
        pytest.param({"role": "owners"}, "ck_sandbox_derived_objects_role", id="unknown-role"),
        pytest.param({"role": "managers", "archived_by_close": True,
                      "close_archived_at": datetime(2026, 11, 1, tzinfo=UTC)},
                     "ck_sandbox_derived_objects_close_archive", id="close-archive-on-a-group"),
        pytest.param({"role": "channel", "archived_by_close": True},
                     "ck_sandbox_derived_objects_close_archive", id="close-archive-without-time"),
        pytest.param({"role": "managers", "duplicate": True},
                     "uq_sandbox_derived_objects_department_role", id="second-link-of-a-role"),
    ],
)
def test_a_link_has_at_most_one_target_and_it_matches_the_role(
    integration_db: Session, values: dict[str, Any], constraint: str,
) -> None:
    """BE-SD1: the CHECKs and the unique key refuse a link the sync could misread."""
    org_id, admin, department = _setup(integration_db)
    group = stage_group(
        integration_db, department_id=department.id, name="Sales managers",
        level=AccessLevel.MANAGE, actor_id=admin.id,
    )
    dashboard = stage_dashboard(
        integration_db, department_id=department.id, name="Sales dashboard",
    )
    if values.pop("duplicate", False):
        integration_db.add(SandboxDerivedObject(
            org_id=org_id, department_id=department.id, role="managers", group_id=group.id,
        ))
        integration_db.flush()
    targets = {
        "group_id": group.id if values.pop("target", None) == "group" else None,
        "dashboard_id": dashboard.id if values.pop("dashboard", False) else None,
    }
    integration_db.add(SandboxDerivedObject(
        org_id=org_id, department_id=department.id, **targets, **values,
    ))
    with pytest.raises(IntegrityError) as refused:
        integration_db.flush()
    assert refused.value.orig.diag.constraint_name == constraint


def test_a_released_link_stays_and_a_linked_target_cannot_be_hard_deleted(
    integration_db: Session,
) -> None:
    """BE-SD1, R5, R7: all targets NULL is valid; a set target restricts its hard delete."""
    org_id, admin, department = _setup(integration_db)
    group = stage_group(
        integration_db, department_id=department.id, name="Sales viewers",
        level=AccessLevel.READ, actor_id=admin.id,
    )
    integration_db.add_all([
        SandboxDerivedObject(org_id=org_id, department_id=department.id, role="channel"),
        SandboxDerivedObject(org_id=org_id, department_id=department.id, role="category"),
        SandboxDerivedObject(
            org_id=org_id, department_id=department.id, role="viewers", group_id=group.id,
        ),
    ])
    integration_db.flush()
    keys = {
        key["name"]: (key["constrained_columns"], key["options"].get("ondelete"))
        for key in inspect(integration_db.connection()).get_foreign_keys(
            "sandbox_derived_objects", "public",
        )
        if key["referred_table"] != "users"
    }
    assert keys == {
        "fk_sandbox_derived_objects_org_id_organizations": (["org_id"], "RESTRICT"),
        "fk_sandbox_derived_objects_department_id_departments":
            (["org_id", "department_id"], "RESTRICT"),
        "fk_sandbox_derived_objects_group_id_groups": (["org_id", "group_id"], "RESTRICT"),
        "fk_sandbox_derived_objects_dashboard_id_dashboards":
            (["org_id", "dashboard_id"], "RESTRICT"),
        "fk_sandbox_derived_objects_category_id_comms_categories":
            (["org_id", "category_id"], "RESTRICT"),
        "fk_sandbox_derived_objects_conversation_id_comms_conversations":
            (["org_id", "conversation_id"], "RESTRICT"),
    }
    access = select(GroupAccess).where(GroupAccess.group_id == group.id)
    for row in integration_db.scalars(access):
        integration_db.delete(row)
    integration_db.flush()
    integration_db.delete(group)
    with pytest.raises(IntegrityError) as refused:
        integration_db.flush()
    assert refused.value.orig.diag.constraint_name == "fk_sandbox_derived_objects_group_id_groups"


def test_stage_group_adds_one_department_access_row_and_no_member_without_commit(
    integration_db: Session,
) -> None:
    """SD11, R2: a group, one whole-department access row at its level, no members."""
    _org_id, admin, department = _setup(integration_db)
    integration_db.commit()
    group = stage_group(
        integration_db, department_id=department.id, name="  Sales members ",
        level=AccessLevel.WRITE, actor_id=admin.id,
    )
    assert (group.name, group.description) == ("Sales members", "")
    access = integration_db.scalars(select(GroupAccess).where(GroupAccess.group_id == group.id))
    assert [(row.department_id, row.module_id, row.level) for row in access] == [
        (department.id, None, "write"),
    ]
    assert _count(integration_db, GroupMember, GroupMember.group_id == group.id) == 0
    with pytest.raises(HTTPException) as missing:
        stage_group(
            integration_db, department_id=admin.id, name="Nowhere managers",
            level=AccessLevel.MANAGE, actor_id=admin.id,
        )
    assert (missing.value.status_code, missing.value.detail) == (
        409, "Department does not exist",
    )
    integration_db.rollback()
    assert _count(integration_db, Group, Group.org_id == department.org_id) == 0
    assert _count(integration_db, GroupAccess, GroupAccess.department_id == department.id) == 0
    assert integration_db.get(Department, department.id) is not None


def test_stage_dashboard_claims_the_home_once_and_refuses_a_closed_department(
    integration_db: Session,
) -> None:
    """SD11, R2: empty, manual, position 0; home only when the department has none."""
    org_id, _admin, department = _setup(integration_db)
    closed = _closed_department(integration_db, org_id)
    integration_db.commit()
    first = stage_dashboard(integration_db, department_id=department.id, name="Sales dashboard")
    second = stage_dashboard(integration_db, department_id=department.id, name="Second")
    stored = integration_db.scalars(
        select(Dashboard).where(Dashboard.department_id == department.id).order_by(Dashboard.name)
    ).all()
    assert [
        (row.name, row.is_home, row.position, row.refresh_cadence, row.widgets) for row in stored
    ] == [
        ("Sales dashboard", True, 0, "manual", []),
        ("Second", False, 0, "manual", []),
    ]
    assert {first.id, second.id} == {row.id for row in stored}
    with pytest.raises(HTTPException) as refused:
        stage_dashboard(integration_db, department_id=closed.id, name="Closed")
    assert (refused.value.status_code, refused.value.detail) == (
        409, {"code": "dashboard_invalid", "message": "The department is unavailable"},
    )
    integration_db.rollback()
    assert _count(integration_db, Dashboard, Dashboard.org_id == org_id) == 0


def test_stage_department_channel_has_a_counter_and_no_member_row(
    integration_db: Session,
) -> None:
    """SD11, R2: the category goes last; the channel's creator is the actor, with no member."""
    org_id, admin, department = _setup(integration_db)
    integration_db.add(CommsCategory(org_id=org_id, name="Existing", position=4))
    other = Department(org_id=org_id, department_name="Other")
    integration_db.add(other)
    integration_db.commit()
    category = stage_category(integration_db, department_id=department.id, name=" Sales ")
    assert (category.name, category.position, category.department_id) == (
        "Sales", 5, department.id,
    )
    channel = stage_department_channel(
        integration_db, admin, department_id=department.id, category_id=category.id, name="Sales",
    )
    assert (
        channel.kind, channel.scope, channel.department_id, channel.category_id,
        channel.name, channel.topic, channel.position, channel.created_by, channel.archived_at,
    ) == ("channel", "department", department.id, category.id, "Sales", "", 0, admin.id, None)
    counters = integration_db.scalars(select(CommsConversationCounter).where(
        CommsConversationCounter.conversation_id == channel.id,
    )).all()
    assert [row.last_seq for row in counters] == [0]
    assert _count(integration_db, CommsMember, CommsMember.conversation_id == channel.id) == 0
    with pytest.raises(HTTPException) as mismatched:
        stage_department_channel(
            integration_db, admin, department_id=other.id, category_id=category.id, name="Other",
        )
    assert (mismatched.value.status_code, mismatched.value.detail["code"]) == (
        422, "comms_invalid",
    )
    integration_db.rollback()
    assert _count(integration_db, CommsConversation, CommsConversation.org_id == org_id) == 0
    assert _count(integration_db, CommsCategory, CommsCategory.org_id == org_id) == 1
