"""File search (BE-UF1, UF-C4.2): readable library documents on real PostgreSQL."""

from hashlib import sha256

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.base_model import utc_now
from app.systems.access.policy.checks import department_level_filter
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User, UserRole
from app.systems.boards.models import Board
from app.systems.platform.files.models import File
from app.systems.sandbox.departments.models import Department
from tests.boards.support import project_board
from tests.conftest import create_member, create_organization
from tests.files.test_library_routes import library_file
from tests.rbac.support import add_department, add_module, add_user, make_group_access
from tests.search.support import client as _client
from tests.search.support import ids as _ids
from tests.search.support import search as _search
from tests.search.support import titled_module
from tests.search.test_search_routes import _event, _post

pytestmark = pytest.mark.integration


def _board_file(db: Session, creator: User, board: Board, name: str) -> File:
    content = b"board attachment"
    file = File(
        org_id=board.org_id,
        purpose="board_attachment",
        board_id=board.id,
        creator_id=creator.id,
        filename=name,
        expected_size=len(content),
        actual_size=len(content),
        object_key=uuid7().hex,
        state="ready",
        media_type="application/pdf",
        digest=sha256(content).hexdigest(),
    )
    db.add(file)
    db.commit()
    return file


def test_file_kind_finds_readable_library_documents_by_file_name_words(
    integration_owner_db: Session,
) -> None:
    """UF-C4.2, BE-UF1-1, BE-UF1-4: a Sales reader and a Sales guest find only Sales files."""

    db = integration_owner_db
    reader = add_user(db)
    guest = add_user(db, role=UserRole.GUEST)
    sales, finance = add_department(db), add_department(db)
    make_group_access(db, [reader, guest], sales, level=AccessLevel.READ)
    invoice = library_file(db, reader, sales, name="invoice-2026.pdf")
    report = library_file(db, reader, sales, name="quarterly_report.v2.xlsx")
    library_file(db, reader, finance, name="invoice-finance.pdf")
    for actor in (reader, guest):
        api = _client(db, actor)
        result = _search(api, "file", "invoice", limit=5)
        assert result["pagination"]["total"] == 1
        assert result["items"] == [
            {
                "kind": "file",
                "id": str(invoice.id),
                "title": "invoice-2026.pdf",
                "context_label": sales.department_name,
                "module_id": None,
                "board_id": None,
                "department_id": str(sales.id),
                "can_open": True,
            }
        ]
        # Separators read as spaces, and the name as written still matches.
        for text, expected in (
            ("2026", invoice),
            ("invoice-2026.pdf", invoice),
            ("quarterly report", report),
            ("v2", report),
            ("quarterly_report.v2.xlsx", report),
        ):
            assert _ids(_search(api, "file", text)) == {str(expected.id)}, text
        assert _ids(_search(api, "file", "finance")) == set()


def test_file_total_counts_only_direct_department_readers_before_paging(
    integration_owner_db: Session,
) -> None:
    """BE-UF1-2, BE-UF1-3 (N-1): module-only grants and no level find and count nothing."""

    db = integration_owner_db
    reader, module_only, no_level = add_user(db), add_user(db), add_user(db)
    sales, finance = add_department(db), add_department(db)
    make_group_access(db, [reader], sales, level=AccessLevel.WRITE)
    make_group_access(db, [reader, module_only], finance, add_module(db, finance))
    make_group_access(db, [no_level], add_department(db), level=AccessLevel.MANAGE)
    first = library_file(db, reader, sales, name="ledger summary.pdf")
    second = library_file(db, reader, sales, name="ledger detail.pdf")
    library_file(db, reader, finance, name="ledger finance.pdf")
    api = _client(db, reader)
    pages = [_search(api, "file", "ledger", limit=1, offset=offset) for offset in (0, 1)]
    assert [page["pagination"] for page in pages] == [
        {
            "limit": 1,
            "offset": offset,
            "count": 1,
            "total": 2,
            "total_is_capped": False,
            "has_more": offset == 0,
        }
        for offset in (0, 1)
    ]
    assert {page["items"][0]["id"] for page in pages} == {str(first.id), str(second.id)}
    for actor in (module_only, no_level):
        assert _search(_client(db, actor), "file", "ledger")["pagination"]["total"] == 0


def test_file_kind_lists_only_ready_live_library_documents_of_live_departments(
    integration_owner_db: Session,
) -> None:
    """BE-UF1-1 (N-2): not ready, archived, deleted-department and board files are hidden."""

    db = integration_owner_db
    admin = add_user(db, role=UserRole.ADMIN)
    department, closed = add_department(db), add_department(db)
    live = library_file(db, admin, department, name="harbor plan.pdf")
    library_file(db, admin, department, state="uploading", name="harbor pending.pdf")
    library_file(db, admin, department, archived=True, name="harbor archived.pdf")
    library_file(db, admin, closed, name="harbor closed.pdf")
    _board_file(db, admin, project_board(db), "harbor board.pdf")
    closed.is_deleted = True
    closed.deleted_at = utc_now()
    db.commit()
    result = _search(_client(db, admin), "file", "harbor")
    assert _ids(result) == {str(live.id)}
    assert result["pagination"]["total"] == 1


def test_file_kind_keeps_an_administrator_inside_the_bound_organization(
    integration_owner_db: Session,
) -> None:
    """BE-UF1-3 (N-2): an administrator of A does not find a library file of B."""

    db = integration_owner_db
    admin_a = add_user(db, role=UserRole.ADMIN)
    own = library_file(db, admin_a, add_department(db), name="charter home.pdf")
    other = create_organization(db)
    admin_b, _ = create_member(db, other, UserRole.ADMIN.value)
    department_b = Department(org_id=other.id, department_name="Sales")
    db.add(department_b)
    db.flush()
    foreign = library_file(db, admin_b, department_b, name="charter away.pdf")
    assert _ids(_search(_client(db, admin_a), "file", "charter")) == {str(own.id)}
    assert _ids(_search(_client(db, admin_b), "file", "charter")) == {str(foreign.id)}


def test_every_other_kind_carries_a_null_department_id(integration_owner_db: Session) -> None:
    """BE-UF1-4: record, person, post and event items have department_id null."""

    db = integration_owner_db
    admin = add_user(db, role=UserRole.ADMIN)
    admin.display_name = "Saffron person"
    titled_module(db, ["Saffron record"])
    board = project_board(db)
    _post(db, board, admin, "Saffron post")
    _event(db, board, admin, "Saffron event")
    db.commit()
    api = _client(db, admin)
    for kind in ("record", "person", "post", "event"):
        items = _search(api, kind, "saffron")["items"]
        assert len(items) == 1, kind
        assert items[0]["kind"] == kind and items[0]["department_id"] is None, kind


def test_department_level_filter_keeps_only_departments_whose_row_includes_the_level(
    integration_owner_db: Session,
) -> None:
    """BE-UF1-9: READ on A and WRITE on B give A and B for read, B for write, none for manage."""

    db = integration_owner_db
    person = add_user(db)
    read_only, writable, unrelated = add_department(db), add_department(db), add_department(db)
    make_group_access(db, [person], read_only, level=AccessLevel.READ)
    make_group_access(db, [person], writable, level=AccessLevel.WRITE)
    candidates = (read_only.id, writable.id, unrelated.id)

    def departments(level: AccessLevel) -> set[object]:
        return set(
            db.scalars(
                select(Department.id).where(
                    Department.id.in_(candidates),
                    department_level_filter(db, person, Department.id, level),
                )
            )
        )

    assert departments(AccessLevel.READ) == {read_only.id, writable.id}
    assert departments(AccessLevel.WRITE) == {writable.id}
    assert departments(AccessLevel.MANAGE) == set()
