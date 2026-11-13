"""Library documents as global search candidates."""

from typing import Any

from sqlalchemy import and_, func, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.core.database.organization_scope import bound_organization_column
from app.systems.access.policy.checks import department_level_filter
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User
from app.systems.platform.files.models import File
from app.systems.sandbox.departments.models import Department


def separators_as_spaces(text: ColumnElement[str] | Any) -> ColumnElement[str]:
    """Read ``.``, ``-`` and ``_`` as spaces, in the stored name and in the typed text alike."""

    return func.translate(text, "._-", "   ")


def library_files(db: Session, actor: User) -> Subquery:
    """Ready library documents of live departments that the actor reads by a department level.

    The rule is the library list's (``level_for`` on the department), applied in SQL
    before paging so ``total`` counts readable files only. Board, record and Comms
    attachments, logos and avatars are never candidates. The organization predicate
    keeps an administrator, whose access filter is ``true()``, inside the bound
    organization; row-level security stays the backstop.
    """

    words = separators_as_spaces(File.filename)
    return (
        select(
            File.id.label("id"),
            File.filename.label("title"),
            Department.department_name.label("context_label"),
            literal(None).label("module_id"),
            literal(None).label("board_id"),
            File.department_id.label("department_id"),
            literal(True).label("can_open"),
            func.concat_ws(" ", words, File.filename).label("search_text"),
        )
        .join(
            Department,
            and_(Department.org_id == File.org_id, Department.id == File.department_id),
        )
        .where(
            File.org_id == bound_organization_column(),
            File.purpose == "library_document",
            File.state == "ready",
            File.is_deleted.is_(False),
            Department.is_deleted.is_(False),
            Department.deleted_at.is_(None),
            department_level_filter(db, actor, File.department_id, AccessLevel.READ),
        )
        .subquery()
    )
