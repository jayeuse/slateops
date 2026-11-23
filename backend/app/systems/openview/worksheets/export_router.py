"""Route 20 (export) and route 15 (history) of a sheet (spec D10, D9.1, D5.3).

Both load the sheet through the access rule first: a missing, deleted or hidden sheet
answers the same 404 before any other check (D14 R5).
"""

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.dependencies import CurrentIdentity, get_current_identity, get_current_user
from app.common.listing import ListQuerySpec, StandardListResponse, execute_standard_list
from app.core.database import get_db
from app.core.database.organization_scope import session_organization
from app.systems.access.policy.checks import (
    forbidden,
    module_level,
    require_fresh_module_access,
)
from app.systems.access.policy.models import AccessLevel
from app.systems.access.users.models import User
from app.systems.openview.worksheets import export as sheet_export
from app.systems.openview.worksheets.access import load_visible_worksheet
from app.systems.openview.worksheets.export import MEDIA_TYPES, commit_export_event
from app.systems.openview.worksheets.history import history_items
from app.systems.openview.worksheets.locking import lock_actor_shares
from app.systems.openview.worksheets.models import Worksheet, WorksheetRowRevision
from app.systems.openview.worksheets.router import not_found
from app.systems.openview.worksheets.schemas import (
    SheetExportRequest,
    SheetHistoryRequest,
    SheetHistorySort,
    SheetRowRevision,
)
from app.systems.sandbox.records.models import Record


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
Actor = Annotated[User, Depends(get_current_user)]
Identity = Annotated[CurrentIdentity, Depends(get_current_identity)]
Database = Annotated[Session, Depends(get_db)]

HISTORY = ListQuerySpec(
    sort_fields={
        SheetHistorySort.CREATED_AT: cast(ColumnElement[Any], WorksheetRowRevision.created_at),
    },
    default_sort=SheetHistorySort.CREATED_AT,
    tie_breaker=cast(ColumnElement[Any], WorksheetRowRevision.id),
)


def _anchor_module(db: Session, sheet: Worksheet) -> UUID:
    if sheet.module_id is not None:
        return sheet.module_id
    record = db.get(Record, sheet.record_id)
    if record is None:
        raise not_found()
    return record.module_id


@router.post(
    "/worksheets/{worksheet_id}/export",
    response_class=Response,
    responses={
        200: {"content": {
            media_type: {"schema": {"type": "string", "format": "binary"}}
            for media_type in MEDIA_TYPES.values()
        }},
        403: {"description": "Current module access or session ended"},
        404: {"description": "Sheet is absent or hidden"},
        422: {"description": "Export exceeds 10,000 rows or 8 MiB"},
        503: {"description": "Export generation or authorization persistence is unavailable"},
    },
)
def export_worksheet(
    worksheet_id: UUID, payload: SheetExportRequest, actor: Actor, identity: Identity,
    db: Database,
) -> Response:
    """Route 20: anyone who can see the sheet exports what they see (X2-X5)."""

    actor_id = actor.id
    sheet = load_visible_worksheet(db, actor, worksheet_id)
    if sheet is None:
        raise not_found()
    module_id, sheet_org = _anchor_module(db, sheet), sheet.org_id
    bind = db.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    org_id = session_organization(db)
    db.rollback()  # release the request's read transaction before the snapshot
    try:
        exported = sheet_export.export_snapshot(
            engine, reader_id=actor_id, worksheet_id=worksheet_id, format=payload.format,
            org_id=org_id,
        )
    except (SQLAlchemyError, OSError) as error:
        db.rollback()
        raise HTTPException(503, detail="Unable to create export") from error
    # The authority again, held until the event commits: the module, the session, the
    # exporter's shares, the sheet through the access rule, then each linked module the
    # file reads (D9.1).
    fresh = require_fresh_module_access(
        db, actor_id=actor_id, session_id=identity.session_id, module_id=module_id,
        level=AccessLevel.READ,
    )
    lock_actor_shares(db, sheet_org, worksheet_id, actor_id)
    if load_visible_worksheet(db, fresh, worksheet_id) is None:
        db.rollback()
        raise not_found()
    if any(module_level(db, fresh, module) is None for module in exported.link_modules):
        db.rollback()  # a linked module read during the build is no longer readable
        raise forbidden()
    commit_export_event(db, actor_id, worksheet_id, payload.format, exported)
    return Response(
        exported.content,
        media_type=MEDIA_TYPES[payload.format],
        headers={
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/worksheets/{worksheet_id}/history",
    response_model=StandardListResponse[SheetRowRevision],
)
def list_worksheet_history(
    worksheet_id: UUID, user: Actor, db: Database,
    params: Annotated[SheetHistoryRequest, Query()],
) -> StandardListResponse[SheetRowRevision]:
    """Route 15: every row change of a sheet the person can see, newest first (H3)."""

    sheet = load_visible_worksheet(db, user, worksheet_id)
    if sheet is None:
        raise not_found()
    statement = select(WorksheetRowRevision).where(
        WorksheetRowRevision.org_id == sheet.org_id,
        WorksheetRowRevision.worksheet_id == sheet.id,
    )
    if params.row_id is not None:
        statement = statement.where(WorksheetRowRevision.row_id == params.row_id)
    result = execute_standard_list(db, statement, params, HISTORY)
    return StandardListResponse(
        items=history_items(db, user, sheet, result.items), pagination=result.pagination,
    )
