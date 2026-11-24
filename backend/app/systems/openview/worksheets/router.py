"""Sheet routes (spec D10 routes 1 to 8 and 25).

Every route that names a sheet loads it through the access rule first, so a missing, deleted
or hidden sheet answers the same 404 before any other check (D14 R5).
"""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.common.dependencies import get_current_user
from app.common.listing import (
    DeletedFilter,
    ListQuerySpec,
    StandardListResponse,
    execute_standard_list,
)
from app.core.database import get_db
from app.systems.access.policy.checks import module_level
from app.systems.access.policy.transaction_access import forget_access
from app.systems.access.users.membership import current_membership
from app.systems.access.users.models import User, UserRole
from app.systems.openview.worksheets.access import (
    load_visible_worksheet,
    my_worksheets_clause,
    own_deleted_worksheet_clause,
    visible_worksheet_clause,
    worksheet_states,
)
from app.systems.openview.worksheets.candidates import like, share_candidates, visible_people
from app.systems.openview.worksheets.create_sources import (
    Draft,
    check_copy,
    check_mapping,
    copy_rows,
    finish,
    from_sheet,
    from_template,
)
from app.systems.openview.worksheets.locking import (
    lock_anchor,
    lock_owner,
    lock_source,
    lock_worksheet,
)
from app.systems.openview.worksheets.models import Worksheet
from app.systems.openview.worksheets.presence import revoke_stale_grants
from app.systems.openview.worksheets.query import query_rows, read_row
from app.systems.openview.worksheets.row_writes import authorize_edit
from app.systems.openview.worksheets.schemas import (
    SheetBlankSource,
    SheetCopySource,
    SheetPeople,
    SheetRow,
    SheetRowPage,
    SheetRowsQuery,
    SheetShareCandidates,
    SheetStructureSource,
    SheetStructureUpdate,
    SheetTemplateSource,
    WorksheetCreate,
    WorksheetDetail,
    WorksheetListRequest,
    WorksheetRename,
    WorksheetSort,
    WorksheetSummary,
)
from app.systems.openview.worksheets.serializers import detail, summaries, worksheet_etag
from app.systems.openview.worksheets.structure_save import save_structure
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.access import record_access

BLANK_STRUCTURE = {
    "structureVersion": 1, "nextColumnSeq": 1, "columns": [], "groups": [], "totals": {},
}


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
# The OpenAPI header documentation, as in the access policy routes.
_ETAG: dict[str, dict[str, Any]] = {"ETag": {"schema": {"type": "string"}}}
_CONDITIONAL: dict[int | str, dict[str, Any]] = {
    412: {"description": "If-Match does not match the locked sheet version"},
    428: {"description": "If-Match header is required"},
}
Actor = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]

MY_SHEETS = ListQuerySpec(
    sort_fields={
        WorksheetSort.TITLE: cast(ColumnElement[Any], Worksheet.title),
        WorksheetSort.UPDATED_AT: cast(ColumnElement[Any], Worksheet.updated_at),
        WorksheetSort.CREATED_AT: cast(ColumnElement[Any], Worksheet.created_at),
    },
    default_sort=WorksheetSort.TITLE,
    tie_breaker=cast(ColumnElement[Any], Worksheet.id),
    search_fields=(cast(ColumnElement[str], Worksheet.title),),
    deleted_field=cast(ColumnElement[bool], Worksheet.is_deleted),
)
# The Sheets tab and the module page list live sheets only, with the exact total (D10).
ANCHOR_SHEETS = replace(MY_SHEETS, deleted_field=None, exact_total=True)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message})


def not_found() -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, "worksheet_not_found", "Sheet not found")


def _visible(db: Session, user: User, worksheet_id: UUID) -> Worksheet:
    sheet = load_visible_worksheet(db, user, worksheet_id)
    if sheet is None:
        raise not_found()
    return sheet


def _require_owner(db: Session, user: User, sheet: Worksheet) -> None:
    """Rename, delete and share need the owner of a private sheet (C5, V5, L7)."""

    present, level = worksheet_states(db, user, [sheet])[sheet.id]
    if not present:
        raise _error(
            status.HTTP_409_CONFLICT, "worksheet_open", "The sheet is open and read-only"
        )
    if level != "owner":
        raise _error(
            status.HTTP_403_FORBIDDEN, "worksheet_read_only", "Only the owner can do this"
        )


def _require_if_match(value: str | None) -> str:
    if value is None:
        raise _error(
            status.HTTP_428_PRECONDITION_REQUIRED, "precondition_required",
            "If-Match is required",
        )
    return value


def _owned_under_lock(
    db: Session, user: User, worksheet_id: UUID, if_match: str | None
) -> Worksheet:
    """The 404, the open and owner checks, then the locks, the same checks again, the 412."""

    sheet = _visible(db, user, worksheet_id)
    _require_owner(db, user, sheet)
    expected = _require_if_match(if_match)
    sheet = lock_worksheet(db, sheet)
    forget_access(db, user.id)  # the checks below read the person's authority again
    sheet = _visible(db, user, worksheet_id)
    _require_owner(db, user, sheet)
    if expected != worksheet_etag(sheet):
        raise _error(
            status.HTTP_412_PRECONDITION_FAILED, "worksheet_changed",
            "The sheet changed; reload it",
        )
    return sheet


def _page(
    db: Session, user: User, statement: Select[Worksheet],
    params: WorksheetListRequest, spec: ListQuerySpec[WorksheetSort],
) -> StandardListResponse[WorksheetSummary]:
    result = execute_standard_list(db, statement, params, spec)
    return StandardListResponse(
        items=summaries(db, user, result.items), pagination=result.pagination
    )


@router.get("/worksheets", response_model=StandardListResponse[WorksheetSummary])
def list_my_worksheets(
    user: Actor, db: Database, params: Annotated[WorksheetListRequest, Query()],
) -> StandardListResponse[WorksheetSummary]:
    """My sheets (P4): owned or shared now; ``deleted=only`` lists the person's own (R6)."""

    if params.deleted is DeletedFilter.INCLUDE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{
                "loc": ["query", "deleted"], "msg": "Use exclude or only", "type": "value_error",
            }],
        )
    clause = (
        own_deleted_worksheet_clause(db, user)
        if params.deleted is DeletedFilter.ONLY
        else my_worksheets_clause(db, user)
    )
    return _page(db, user, select(Worksheet).where(clause), params, MY_SHEETS)


@router.get(
    "/records/{record_id}/worksheets", response_model=StandardListResponse[WorksheetSummary]
)
def list_record_worksheets(
    record_id: UUID, user: Actor, db: Database,
    params: Annotated[WorksheetListRequest, Query()],
) -> StandardListResponse[WorksheetSummary]:
    if record_access(db, user, record_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "record_not_found", "Record not found")
    statement = select(Worksheet).where(
        Worksheet.record_id == record_id, visible_worksheet_clause(db, user)
    )
    return _page(db, user, statement, params, ANCHOR_SHEETS)


@router.get(
    "/modules/{module_id}/worksheets", response_model=StandardListResponse[WorksheetSummary]
)
def list_module_worksheets(
    module_id: UUID, user: Actor, db: Database,
    params: Annotated[WorksheetListRequest, Query()],
) -> StandardListResponse[WorksheetSummary]:
    if module_level(db, user, module_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "module_not_found", "Module not found")
    statement = select(Worksheet).where(
        Worksheet.module_id == module_id, visible_worksheet_clause(db, user)
    )
    return _page(db, user, statement, params, ANCHOR_SHEETS)


def _creation_anchor(db: Session, user: User, payload: WorksheetCreate) -> UUID:
    """404 for an unreadable anchor, 403 for a guest, 409 for a deleted anchor (C1, C3, C4)."""

    if payload.record_id is not None:
        found = record_access(db, user, payload.record_id)
        if found is None:
            raise _error(status.HTTP_404_NOT_FOUND, "record_not_found", "Record not found")
        active = not found[0].is_deleted
    else:
        if module_level(db, user, cast(UUID, payload.module_id)) is None:
            raise _error(status.HTTP_404_NOT_FOUND, "module_not_found", "Module not found")
        module = db.get(Module, payload.module_id)
        active = module is not None and not module.is_deleted
    membership = current_membership(db, user)
    if membership is None or membership.role == UserRole.GUEST.value:
        raise _error(
            status.HTTP_403_FORBIDDEN, "worksheet_create_forbidden", "Guests cannot create sheets"
        )
    if not active:
        code, what = (
            ("record_not_active", "record") if payload.record_id is not None
            else ("module_not_active", "module")
        )
        raise _error(status.HTTP_409_CONFLICT, code, f"The {what} is deleted or closed")
    return membership.org_id


def _source_checks(db: Session, user: User, payload: WorksheetCreate) -> Worksheet | None:
    """The 404 loaders of the source first (R5), then the anchor, then the copy rules."""

    source = payload.source
    original = None
    if isinstance(source, SheetStructureSource | SheetCopySource):
        original = _visible(db, user, source.worksheet_id)
    if isinstance(source, SheetTemplateSource):
        check_mapping(db, user, source)
    _creation_anchor(db, user, payload)
    if isinstance(source, SheetCopySource) and original is not None:
        check_copy(db, user, payload, original)
    return original


def _structure(db: Session, user: User, payload: WorksheetCreate,
               original: Worksheet | None) -> tuple[dict[str, Any], Draft | None]:
    source = payload.source
    if isinstance(source, SheetBlankSource):
        return dict(BLANK_STRUCTURE), None
    if isinstance(source, SheetTemplateSource):
        draft = from_template(db, source)
    else:
        assert original is not None  # loaded by `_source_checks`
        draft = from_sheet(db, user, original)
    built = finish(db, draft)
    return built.model_dump(mode="json"), draft


@router.post(
    "/worksheets", response_model=WorksheetDetail, status_code=status.HTTP_201_CREATED,
    responses={201: {"headers": {**_ETAG, "Location": {"schema": {"type": "string"}}}}},
)
def create_worksheet(
    payload: WorksheetCreate, user: Actor, db: Database, response: Response,
) -> WorksheetDetail:
    """Route 3: blank, from a structure (X7), a copy (L6) or a template (X6)."""

    original = _source_checks(db, user, payload)
    lock_owner(db, user.id)
    lock_anchor(db, record_id=payload.record_id, module_id=payload.module_id)
    if isinstance(payload.source, SheetCopySource) and original is not None:
        lock_source(db, original.id)
    forget_access(db, user.id)
    original = _source_checks(db, user, payload)  # again under the locks
    org_id = _creation_anchor(db, user, payload)
    structure, draft = _structure(db, user, payload, original)
    sheet = Worksheet(
        org_id=org_id, record_id=payload.record_id, module_id=payload.module_id,
        owner_id=user.id, title=payload.title, structure=structure,
    )
    db.add(sheet)
    db.flush()
    if isinstance(payload.source, SheetCopySource) and original is not None and draft:
        copy_rows(db, original, sheet, draft)
    db.commit()
    db.refresh(sheet)
    response.headers["Location"] = f"/api/worksheets/{sheet.id}"
    response.headers["ETag"] = worksheet_etag(sheet)
    return detail(db, user, sheet)


@router.get(
    "/worksheets/{worksheet_id}", response_model=WorksheetDetail,
    responses={200: {"headers": _ETAG}},
)
def get_worksheet(
    worksheet_id: UUID, user: Actor, db: Database, response: Response,
) -> WorksheetDetail:
    sheet = _visible(db, user, worksheet_id)
    response.headers["ETag"] = worksheet_etag(sheet)
    return detail(db, user, sheet)


@router.patch(
    "/worksheets/{worksheet_id}", response_model=WorksheetDetail,
    responses={200: {"headers": _ETAG}, **_CONDITIONAL},
)
def rename_worksheet(
    worksheet_id: UUID, payload: WorksheetRename, user: Actor, db: Database,
    response: Response, if_match: IfMatch = None,
) -> WorksheetDetail:
    sheet = _owned_under_lock(db, user, worksheet_id, if_match)
    if sheet.title != payload.title:
        sheet.title = payload.title
        sheet.revision += 1
    db.commit()
    db.refresh(sheet)
    response.headers["ETag"] = worksheet_etag(sheet)
    return detail(db, user, sheet)


@router.delete(
    "/worksheets/{worksheet_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None,
    responses=_CONDITIONAL,
)
def delete_worksheet(
    worksheet_id: UUID, user: Actor, db: Database, if_match: IfMatch = None,
) -> None:
    sheet = _owned_under_lock(db, user, worksheet_id, if_match)
    sheet.is_deleted = True
    sheet.deleted_at = datetime.now(UTC)
    revoke_stale_grants(db, sheet.id)  # a deleted sheet has no presence
    db.commit()


def _restorable(db: Session, user: User, worksheet_id: UUID) -> Worksheet:
    sheet = db.scalars(
        select(Worksheet).where(
            Worksheet.id == worksheet_id,
            or_(visible_worksheet_clause(db, user), own_deleted_worksheet_clause(db, user)),
        )
    ).one_or_none()
    if sheet is None:
        raise not_found()
    if not sheet.is_deleted:
        raise _error(status.HTTP_409_CONFLICT, "worksheet_not_deleted", "The sheet is not deleted")
    present, _level = worksheet_states(db, user, [sheet])[sheet.id]
    if not present:
        raise _error(
            status.HTTP_409_CONFLICT, "worksheet_open", "The sheet is open and read-only"
        )
    return sheet


@router.post(
    "/worksheets/{worksheet_id}/restore", response_model=WorksheetDetail,
    responses={200: {"headers": _ETAG}},
)
def restore_worksheet(
    worksheet_id: UUID, user: Actor, db: Database, response: Response,
) -> WorksheetDetail:
    sheet = _restorable(db, user, worksheet_id)
    lock_worksheet(db, sheet)
    forget_access(db, user.id)
    sheet = _restorable(db, user, worksheet_id)
    sheet.is_deleted = False
    sheet.deleted_at = None
    db.commit()
    db.refresh(sheet)
    response.headers["ETag"] = worksheet_etag(sheet)
    return detail(db, user, sheet)


@router.get("/worksheets/{worksheet_id}/share-candidates", response_model=SheetShareCandidates)
def list_share_candidates(
    worksheet_id: UUID, user: Actor, db: Database,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> SheetShareCandidates:
    sheet = _visible(db, user, worksheet_id)
    _require_owner(db, user, sheet)
    return share_candidates(db, user, (q or "").strip())


@router.get("/worksheets/{worksheet_id}/people", response_model=SheetPeople)
def list_sheet_people(
    worksheet_id: UUID, user: Actor, db: Database,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> SheetPeople:
    """People an owner or Edit recipient can put in a person cell, themselves included."""

    authorize_edit(db, user, worksheet_id)  # 404 first, then 403 for read-only (R5)
    return SheetPeople(people=visible_people(db, user, like((q or "").strip()),
                                             include_self=True))


@router.post("/worksheets/{worksheet_id}/rows/query", response_model=SheetRowPage)
def query_worksheet_rows(
    worksheet_id: UUID, payload: SheetRowsQuery, user: Actor, db: Database,
) -> SheetRowPage:
    """Route 9: one page of rows as this person may see them, with totals over all rows."""

    return query_rows(db, user, _visible(db, user, worksheet_id), payload)


@router.get(
    "/worksheets/{worksheet_id}/rows/{row_id}", response_model=SheetRow,
    responses={200: {"headers": _ETAG}},
)
def get_worksheet_row(
    worksheet_id: UUID, row_id: UUID, user: Actor, db: Database, response: Response,
) -> SheetRow:
    row = read_row(db, user, _visible(db, user, worksheet_id), row_id)
    if row is None:
        raise _error(status.HTTP_404_NOT_FOUND, "worksheet_row_not_found", "Row not found")
    response.headers["ETag"] = row.etag
    return row


@router.put(
    "/worksheets/{worksheet_id}/structure", response_model=WorksheetDetail,
    responses={200: {"headers": _ETAG}, **_CONDITIONAL},
)
def save_worksheet_structure(
    worksheet_id: UUID, payload: SheetStructureUpdate, user: Actor, db: Database,
    response: Response, if_match: IfMatch = None,
) -> WorksheetDetail:
    """Route 6: owner or Edit; ``If-Match`` names the sheet revision the person saw."""

    sheet = save_structure(db, user, worksheet_id, payload, if_match)
    db.commit()
    db.refresh(sheet)
    response.headers["ETag"] = worksheet_etag(sheet)
    return detail(db, user, sheet)
