import os
from enum import StrEnum

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.common.dependencies import get_current_user
from app.common.listing import (
    ListQueryResult,
    ListQuerySpec,
    StandardListRequest,
    execute_standard_list,
)
from app.core.base_model import utc_now
from app.core.database.session import get_db
from app.main import create_app
from app.systems.access.users.models import UserRole
from app.systems.sandbox.departments.models import Department
from tests.conftest import create_organization
from tests.organization_scope_support import scoped_override
from tests.rbac.support import add_department, add_module, add_user

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        TEST_DATABASE_URL is None,
        reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests",
    ),
]


class DepartmentSortField(StrEnum):
    NAME = "department_name"


def test_standard_list_executes_against_postgresql(integration_db: Session) -> None:
    token = str(uuid7())
    organization = create_organization(integration_db)
    integration_db.add_all(
        [
            Department(org_id=organization.id, department_name=f"{token} Alpha"),
            Department(org_id=organization.id, department_name=f"{token} Beta"),
            Department(
                org_id=organization.id, department_name=f"{token} Deleted",
                is_deleted=True, deleted_at=utc_now(),
            ),
        ]
    )
    integration_db.flush()

    spec = ListQuerySpec(
        sort_fields={DepartmentSortField.NAME: Department.department_name},
        default_sort=DepartmentSortField.NAME,
        tie_breaker=Department.id,
        search_fields=(Department.department_name,),
        deleted_field=Department.is_deleted,
    )
    result = execute_standard_list(
        integration_db,
        select(Department),
        StandardListRequest[DepartmentSortField](search=token, limit=1),
        spec,
    )

    assert [department.department_name for department in result.items] == [f"{token} Alpha"]
    assert result.pagination.total == 2
    assert result.pagination.has_more is True


class SeriesSortField(StrEnum):
    VALUE = "value"


def _series_list(
    db: Session, rows: int, *, limit: int = 25, offset: int = 0
) -> ListQueryResult[int]:
    series = func.generate_series(1, rows).table_valued("value").render_derived()
    spec = ListQuerySpec(
        sort_fields={SeriesSortField.VALUE: series.c.value},
        default_sort=SeriesSortField.VALUE,
        tie_breaker=series.c.value,
    )
    return execute_standard_list(
        db,
        select(series.c.value),
        StandardListRequest[SeriesSortField](limit=limit, offset=offset),
        spec,
    )


@pytest.mark.parametrize(
    ("rows", "total", "capped"),
    [
        pytest.param(50, 50, False, id="small-list-is-exact"),
        pytest.param(10_000, 10_000, False, id="exactly-the-cap-is-exact"),
        pytest.param(10_001, 10_000, True, id="one-above-the-cap-is-capped"),
        pytest.param(12_000, 10_000, True, id="far-above-the-cap-is-capped"),
    ],
)
def test_the_total_stops_at_ten_thousand_and_says_so(
    integration_db: Session, rows: int, total: int, capped: bool
) -> None:
    result = _series_list(integration_db, rows)

    assert result.pagination.total == total
    assert result.pagination.total_is_capped is capped
    assert result.pagination.has_more is (rows > 25)
    assert result.items == list(range(1, min(rows, 25) + 1))


@pytest.mark.parametrize(
    ("offset", "values", "has_more"),
    [
        pytest.param(9_990, list(range(9_991, 10_016)), True, id="across-the-cap"),
        pytest.param(11_990, list(range(11_991, 12_001)), False, id="last-page-past-the-cap"),
    ],
)
def test_a_capped_list_knows_whether_more_rows_follow_from_the_page_alone(
    integration_db: Session, offset: int, values: list[int], has_more: bool
) -> None:
    result = _series_list(integration_db, 12_000, offset=offset)

    assert result.items == values
    assert result.pagination.total == 10_000
    assert result.pagination.has_more is has_more
    assert result.pagination.count == len(values)
    assert result.pagination.limit == 25


def test_the_record_list_keeps_its_exact_total_above_the_cap(integration_db: Session) -> None:
    # D1: Records lists keep their exact count, and the sample tool reads them by it (K61).
    db = integration_db
    admin = add_user(db, role=UserRole.ADMIN)
    module = add_module(db, add_department(db))
    db.connection().execute(
        text(
            "INSERT INTO public.records (id, org_id, module_id, data) "
            "SELECT gen_random_uuid(), :org, :module, '{}'::jsonb "
            "FROM generate_series(1, 10001)"
        ),
        {"org": module.org_id, "module": module.id},
    )
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_current_user] = scoped_override(lambda: admin)

    with TestClient(application) as client:
        listed = client.get("/api/records", params={"module_id": str(module.id), "limit": 1})

    assert listed.status_code == 200, listed.text
    assert listed.json()["pagination"]["total"] == 10_001
    assert listed.json()["pagination"]["total_is_capped"] is False
    assert listed.json()["pagination"]["has_more"] is True
