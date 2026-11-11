import os
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.users.models import User, UserStatus
from app.systems.comms.access import conversation_level
from app.systems.comms.conversations.models import CommsConversation
from app.systems.comms.conversations.mutations import stage_department_channel
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.lifecycle.exceptions import (
    LifecycleClosedAncestorError,
    LifecyclePlanDriftError,
    LifecyclePreflightError,
)
from app.systems.sandbox.lifecycle.planner import plan_lifecycle
from app.systems.sandbox.lifecycle.schemas import (
    DerivedChange,
    LifecycleBlockerCode,
    LifecycleTargetType,
)
from app.systems.sandbox.lifecycle.service import close_lifecycle, reopen_lifecycle
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from app.systems.sandbox.relationships.projection import list_relationships
from app.systems.sandbox.relationships.schemas import (
    RelationshipAvailability,
    RelationshipListRequest,
)
from tests.lifecycle_integration.lifecycle_integration_support import LifecycleGraph
from tests.rbac.support import add_user
from tests.sandbox_publications.derived_support import (
    ROLES,
    add_people,
    derived_rows,
    kept_counts,
    link_rows,
    with_sales,
)
from tests.sandbox_publications.support import bound_department

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TEST_DATABASE_URL") is None,
        reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests",
    ),
]


def test_department_close_cascades_only_owned_rows_and_commits_once(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department_x = lifecycle_graph.department_x
    department_y = lifecycle_graph.department_y
    module_x = lifecycle_graph.module_x
    module_y = lifecycle_graph.module_y
    field_y = lifecycle_graph.field_y
    external_edge = lifecycle_graph.external_edge

    with patch.object(integration_db, "commit", wraps=integration_db.commit) as commit:
        result = close_lifecycle(
            integration_db,
            LifecycleTargetType.DEPARTMENT,
            department_x.id,
            None,
        )

    assert commit.call_count == 1
    assert all(row.is_deleted is False for row in result.rows)
    assert department_x.is_deleted is True
    assert module_x.is_deleted is True
    assert module_y.is_deleted is False
    assert field_y.is_deleted is False
    assert external_edge.is_deleted is False
    assert department_y.is_deleted is False


def _external_link_state(db: Session, graph: LifecycleGraph) -> list[tuple[object, str, list[str]]]:
    """List the X -> Y field for an administrator, in hidden and available state."""

    reader = add_user(db, "lifecycle-reader", role="admin", status=UserStatus.ACTIVE)
    field = graph.field_external
    items, _pagination = list_relationships(
        db,
        RelationshipListRequest(field_id=field.id, availability=RelationshipAvailability.ALL),
        reader=reader,
    )
    return [
        (item.id, item.visibility.value, [reason.value for reason in item.hidden_reasons])
        for item in items
    ]


def test_target_department_close_hides_the_cross_department_link_without_writing_it(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department_x = lifecycle_graph.department_x
    department_y = lifecycle_graph.department_y
    module_x = lifecycle_graph.module_x
    field_external = lifecycle_graph.field_external
    source = lifecycle_graph.source
    external_edge = lifecycle_graph.external_edge
    edge_updated_at = external_edge.updated_at

    result = close_lifecycle(
        integration_db,
        LifecycleTargetType.DEPARTMENT,
        department_y.id,
        None,
    )

    assert department_y.is_deleted is True
    assert "relationship_edges" not in {row.entity_type for row in result.rows}
    integration_db.refresh(external_edge)
    assert external_edge.is_deleted is False
    assert external_edge.updated_at == edge_updated_at
    assert (department_x.is_deleted, module_x.is_deleted) == (False, False)
    assert (field_external.is_deleted, source.is_deleted) == (False, False)
    assert [
        (
            impact.edge_id,
            impact.external_record_id,
            impact.external_module_id,
            impact.external_department_id,
        )
        for impact in result.external_impacts
    ] == [(external_edge.id, source.id, module_x.id, department_x.id)]
    assert _external_link_state(integration_db, lifecycle_graph) == [
        (external_edge.id, "hidden", ["target_record_archived", "target_module_archived"])
    ]


def test_target_department_reopen_makes_the_cross_department_link_available_again(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department_y = lifecycle_graph.department_y
    external_edge = lifecycle_graph.external_edge
    close_lifecycle(integration_db, LifecycleTargetType.DEPARTMENT, department_y.id, None)
    assert _external_link_state(integration_db, lifecycle_graph)[0][1] == "hidden"

    reopen_lifecycle(integration_db, LifecycleTargetType.DEPARTMENT, department_y.id, None)

    integration_db.refresh(external_edge)
    assert external_edge.is_deleted is False
    assert _external_link_state(integration_db, lifecycle_graph) == [
        (external_edge.id, "available", [])
    ]


def test_field_close_reports_same_module_records_and_department_label(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    field = lifecycle_graph.field_same
    module = lifecycle_graph.module_x
    source = lifecycle_graph.source
    repeated_target = lifecycle_graph.same_target
    blank_target = lifecycle_graph.deleted_target
    option_id = str(uuid7())
    title_field = Field(
        org_id=module.org_id,
        module_id=module.id,
        name="Work order title",
        type=FieldType.SELECT,
        position=2,
        config={"options": [{"id": option_id, "label": "Pump seal replacement"}]},
    )
    integration_db.add(title_field)
    integration_db.flush()
    module.title_field_id = title_field.id
    source.data = {str(title_field.id): option_id}
    repeated_target.data = {str(title_field.id): str(uuid7())}
    blank_target.data = {str(title_field.id): "   "}
    integration_db.commit()
    result = close_lifecycle(
        integration_db,
        LifecycleTargetType.FIELD,
        field.id,
        None,
    )

    assert [row.entity_type for row in result.rows] == ["fields"]
    assert len(result.external_impacts) == 4
    assert {impact.external_module_id for impact in result.external_impacts} == {module.id}
    assert {impact.external_department_name for impact in result.external_impacts} == {
        lifecycle_graph.department_x.department_name
    }
    assert {
        impact.external_record_id: impact.model_dump().get("external_record_label")
        for impact in result.external_impacts
    } == {
        source.id: "Pump seal replacement",
        repeated_target.id: f"Record {str(repeated_target.id)[:8]}",
        blank_target.id: f"Record {str(blank_target.id)[:8]}",
    }
    assert field.is_deleted is True


def test_reopen_legacy_department_only_restores_explicit_root(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department = lifecycle_graph.department_x
    module = lifecycle_graph.module_x
    field = lifecycle_graph.field_same
    record = lifecycle_graph.source
    for row in (department, module, field, record):
        row.is_deleted = True
        row.deleted_at = utc_now()
    integration_db.flush()

    result = reopen_lifecycle(
        integration_db,
        LifecycleTargetType.DEPARTMENT,
        department.id,
        None,
    )

    assert [row.entity_type for row in result.rows] == ["departments"]
    assert department.is_deleted is False
    assert all(row.is_deleted is True for row in (module, field, record))


def test_ancestor_reopen_preserves_independent_closures_and_deleted_records(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department = lifecycle_graph.department_x
    module = lifecycle_graph.module_x
    source = lifecycle_graph.source
    manually_deleted = lifecycle_graph.deleted_target
    manually_deleted.is_deleted = True
    manually_deleted.deleted_at = utc_now()
    independent = Module(org_id=module.org_id, department_id=module.department_id,
                         module_name="Independent closure")
    independent_field = Field(
        org_id=module.org_id,
        module_id=module.id, name="Independently closed", type=FieldType.TEXT, position=2
    )
    integration_db.add_all([independent, independent_field])
    integration_db.flush()
    nested_record = Record(org_id=independent.org_id, module_id=independent.id, data={})
    integration_db.add(nested_record)
    integration_db.commit()
    close_lifecycle(integration_db, "module", independent.id, None)
    close_lifecycle(integration_db, "field", independent_field.id, None)
    close_lifecycle(integration_db, "department", department.id, None)
    assert source.is_deleted

    reopened = reopen_lifecycle(integration_db, "department", department.id, None)

    assert manually_deleted.is_deleted
    assert independent.is_deleted and independent_field.is_deleted and nested_record.is_deleted
    assert not department.is_deleted and not module.is_deleted and not source.is_deleted
    assert independent.id not in {row.entity_id for row in reopened.rows}
    assert independent_field.id not in {row.entity_id for row in reopened.rows}


@pytest.mark.parametrize(
    "key,table",
    [
        ("department_x", "departments"),
        ("module_x", "modules"),
        ("field_same", "fields"),
        ("source", "records"),
    ],
)
def test_close_provenance_constraint_rejects_a_marker_on_an_active_row(
    integration_db: Session, lifecycle_graph: LifecycleGraph, key: str, table: str
) -> None:
    name = f"ck_{table}_lifecycle_close_provenance"
    actual = integration_db.connection().scalar(
        text(
            "SELECT conname FROM pg_constraint WHERE conname = :name "
            "AND conrelid = CAST(:table AS regclass)"
        ),
        {"name": name, "table": f"public.{table}"},
    )
    assert actual == name
    row = getattr(lifecycle_graph, key)
    assert not row.is_deleted
    savepoint = integration_db.begin_nested()
    row.lifecycle_close_operation_id = uuid7()
    with pytest.raises(IntegrityError) as rejected:
        integration_db.flush()
    savepoint.rollback()
    assert rejected.value.orig.diag.constraint_name == name


def test_plan_drift_rolls_back_without_closing_rows(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department = lifecycle_graph.department_x
    module = lifecycle_graph.module_x
    plan = plan_lifecycle(
        integration_db,
        LifecycleTargetType.DEPARTMENT,
        department.id,
        "close",
        None,
    )
    module.module_name = f"Drifted {uuid7()}"
    integration_db.flush()

    with (
        pytest.raises(LifecyclePlanDriftError),
        patch.object(integration_db, "rollback", wraps=integration_db.rollback) as rollback,
    ):
        close_lifecycle(
            integration_db,
            LifecycleTargetType.DEPARTMENT,
            department.id,
            None,
            plan=plan,
        )

    assert rollback.call_count == 1
    assert department.is_deleted is False


def test_reopen_rejects_closed_nearest_ancestor_and_names_active_conflict(
    integration_db: Session, lifecycle_graph: LifecycleGraph
) -> None:
    department = lifecycle_graph.department_x
    module = lifecycle_graph.module_x
    field = lifecycle_graph.field_same
    module.is_deleted = True
    module.deleted_at = utc_now()
    department.is_deleted = True
    department.deleted_at = utc_now()
    field.is_deleted = True
    field.deleted_at = utc_now()
    integration_db.flush()

    with pytest.raises(LifecycleClosedAncestorError, match="Module X"):
        reopen_lifecycle(integration_db, LifecycleTargetType.FIELD, field.id, None)

    department.is_deleted, department.deleted_at = False, None
    active_conflict = Module(
        org_id=department.org_id,
        department_id=department.id,
        module_name=module.module_name,
    )
    integration_db.add(active_conflict)
    integration_db.commit()
    with pytest.raises(LifecyclePreflightError) as raised:
        reopen_lifecycle(integration_db, LifecycleTargetType.MODULE, module.id, None)

    blockers = raised.value.blockers
    assert any(blocker.code is LifecycleBlockerCode.MODULE_NAME_CONFLICT for blocker in blockers)
    assert any(blocker.conflicting_entity_id == active_conflict.id for blocker in blockers)
    assert module.is_deleted is True


def _change(channel: CommsConversation, action: str) -> DerivedChange:
    return DerivedChange.model_validate(
        {"role": "channel", "target_id": channel.id, "name": channel.name, "action": action}
    )


def test_sd_c11_c12_lifecycle_close_archives_the_channel_and_reopen_reports_it(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, _ = with_sales(db)
    sales = bound_department(db, "dep-sales")
    member, channel = add_people(db, sales, publisher)
    kept = kept_counts(db, sales, channel)

    closed = close_lifecycle(db, "department", sales.id, publisher.id)

    assert closed.derived_changes == [_change(channel, "close")]
    db.refresh(channel)
    assert channel.archived_at is not None
    assert kept_counts(db, sales, channel) == kept
    links = link_rows(db, sales)
    assert all(link.closed_at is not None for link in links.values())
    assert {role: link.archived_by_close for role, link in links.items()} == {
        role: role == "channel" for role in ROLES
    }
    assert links["channel"].close_archived_at == channel.archived_at
    assert conversation_level(db, member, channel) == "none"
    assert conversation_level(db, publisher, channel) != "none"

    reopened = reopen_lifecycle(db, "department", sales.id, publisher.id)

    assert reopened.derived_changes == [_change(channel, "reopen")]
    db.refresh(channel)
    assert channel.archived_at is None
    assert all(
        (link.closed_at, link.archived_by_close, link.close_archived_at) == (None, False, None)
        for link in link_rows(db, sales).values()
    )
    assert conversation_level(db, member, channel) == "post"


def test_sd_c13_lifecycle_reopen_keeps_a_channel_that_a_person_archived(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, _ = with_sales(db)
    sales = bound_department(db, "dep-sales")
    channel = derived_rows(db, sales)["channel"]
    archived_at = utc_now()
    channel.archived_at = archived_at
    db.flush()

    closed = close_lifecycle(db, "department", sales.id, publisher.id)
    reopened = reopen_lifecycle(db, "department", sales.id, publisher.id)

    assert closed.derived_changes == reopened.derived_changes == []
    db.refresh(channel)
    assert channel.archived_at == archived_at


def _second_channel(db: Session, sales: Department, publisher: User) -> CommsConversation:
    rows = derived_rows(db, sales)
    return stage_department_channel(
        db,
        publisher,
        department_id=sales.id,
        category_id=rows["category"].id,
        name="Sales leads",
    )


def test_sd_c32_close_preview_names_the_open_channel_and_the_close_does_exactly_that(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, _ = with_sales(db)
    sales = bound_department(db, "dep-sales")
    derived = derived_rows(db, sales)["channel"]
    other = _second_channel(db, sales, publisher)
    preview = plan_lifecycle(db, "department", sales.id, "close", publisher.id)

    assert preview.response().derived_changes == [
        _change(derived, "close"),
        _change(other, "keep"),
    ]

    closed = close_lifecycle(db, "department", sales.id, publisher.id, plan=preview)

    assert closed.derived_changes == preview.response().derived_changes
    db.refresh(derived)
    db.refresh(other)
    assert derived.archived_at is not None
    assert other.archived_at is None


def test_be_sd7_a_channel_rename_after_the_close_preview_refuses_the_close(
    integration_owner_db: Session,
) -> None:
    db = integration_owner_db
    publisher, _ = with_sales(db)
    sales = bound_department(db, "dep-sales")
    other = _second_channel(db, sales, publisher)
    preview = plan_lifecycle(db, "department", sales.id, "close", publisher.id)
    other.name = "Sales escalations"
    db.flush()

    with pytest.raises(LifecyclePlanDriftError):
        close_lifecycle(db, "department", sales.id, publisher.id, plan=preview)

    assert derived_rows(db, sales)["channel"].archived_at is None
    assert not sales.is_deleted
