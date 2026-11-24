"""Routes 21 and 22: read an Excel file and preview the key matching (spec D9.3; X8-X10, H6).

Route 21 holds one shared file-processing slot while the child parses the bytes the
middleware admitted (10 MiB, 413 above it; 503 ``files_busy`` when the slots are full),
and writes one ``worksheets.import.file_parsed`` event per parse, with no file content.
Route 22 matches up to 2,000 keys against the live records of a module the person can
read, in one statement; a key matched twice or more is ambiguous.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased
from uuid6 import uuid7

from app.common.dependencies import get_current_user
from app.core.database import get_db
from app.systems.access.policy.checks import module_level
from app.systems.access.users.membership import bound_organization, current_membership
from app.systems.access.users.models import User, UserRole
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.audit.security_events import append_committed_security_event
from app.systems.openview.worksheets.import_worker import ImportRefused, parse_import
from app.systems.openview.worksheets.link_projection import TITLE_TYPES, record_label
from app.systems.platform.files.providers import hold_file_worker
from app.systems.sandbox.fields.models import Field as RecordField
from app.systems.sandbox.fields.models import FieldType
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record

PARSED_EVENT = "worksheets.import.file_parsed"
MAX_TABS = 255


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["worksheets"], dependencies=[Depends(_no_store)])
Actor = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db)]


class SheetImportTab(BaseModel):
    index: int
    name: str


class SheetImportFile(BaseModel):
    """One parsed tab: cells are text, numbers, booleans, ISO dates or null."""

    tabs: list[SheetImportTab]
    tab_index: int
    rows: list[list[str | int | float | bool | None]]
    formula_without_value_count: int
    row_count: int
    column_count: int


Key = Annotated[str, StringConstraints(max_length=200)]


class SheetImportMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: UUID
    field_id: UUID
    keys: list[Key] = Field(max_length=2_000)


class SheetImportRecord(BaseModel):
    record_id: UUID
    label: str


class SheetImportMatch(BaseModel):
    key: str
    state: Literal["matched", "unmatched", "ambiguous"]
    record: SheetImportRecord | None


class SheetImportMatchCounts(BaseModel):
    matched: int
    unmatched: int
    ambiguous: int


class SheetImportMatches(BaseModel):
    results: list[SheetImportMatch]
    counts: SheetImportMatchCounts


def _record_parse(actor_id: UUID, org_id: UUID, size: int, reason: str | None,
                  rows: int) -> None:
    append_committed_security_event(
        SecurityEventIngestRequest(
            event_type=PARSED_EVENT, source="worksheets", operation_id=uuid7(),
            actor_id=actor_id,
            outcome=SecurityEventOutcome.SUCCESS if reason is None
            else SecurityEventOutcome.FAILURE,
            reason=reason,
            metadata={"outcome": "accepted" if reason is None else "refused",
                      "reason": reason, "bytes": size, "row_count": rows},
        ),
        org_id=org_id,
    )


@router.post(
    "/worksheet-import-files", response_model=SheetImportFile,
    responses={
        200: {"description": "The chosen tab, cell values only"},
        403: {"description": "Guests cannot import"},
        413: {"description": "The file is above 10 MiB"},
        422: {"description": "The file, the tab or a sheet limit is refused"},
        503: {"description": "The file slots are full, or the file took too long"},
    },
)
def read_import_file(
    request: Request, user: Actor, db: Database,
    content: Annotated[bytes, Body(media_type="application/octet-stream")],
    tab: Annotated[int, Query(ge=0, le=MAX_TABS)] = 0,
) -> SheetImportFile:
    """Route 21: one tab of an ``.xlsx`` file, read in an isolated child (D14 E1-E5)."""

    membership = current_membership(db, user)
    if membership is None or membership.role == UserRole.GUEST.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={
            "code": "import_forbidden", "message": "Guests cannot import",
        })
    actor_id, org_id = user.id, membership.org_id
    db.rollback()  # no transaction stays open while the child runs
    with hold_file_worker(request):
        try:
            parsed = parse_import(content, tab)
        except ImportRefused as refused:
            _record_parse(actor_id, org_id, len(content), refused.reason, 0)
            raise HTTPException(refused.status_code, detail=refused.detail,
                                headers=refused.headers) from refused
    _record_parse(actor_id, org_id, len(content), None, int(parsed.get("row_count", 0)))
    return SheetImportFile.model_validate(parsed)


def _module_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail={
        "code": "module_not_found", "message": "Module not found",
    })


@router.post("/worksheet-import-matches", response_model=SheetImportMatches)
def match_import_keys(
    payload: SheetImportMatchRequest, user: Actor, db: Database,
) -> SheetImportMatches:
    """Route 22: each key against the live records of a readable module (X8)."""

    module = db.get(Module, payload.module_id)
    field = db.get(RecordField, payload.field_id)
    if (module is None or module.is_deleted or module.org_id != bound_organization(db)
            or module_level(db, user, payload.module_id) is None
            or field is None or field.is_deleted or field.module_id != module.id
            or FieldType(field.type) is FieldType.RELATIONSHIP):
        # Missing, of another organization, unreadable, or a field of another module.
        raise _module_not_found()
    keys = list(dict.fromkeys(payload.keys))
    title = aliased(RecordField, name="title")
    text = Record.data.op("->>")(str(field.id))
    ranked = (
        select(
            text.label("key"), Record.id.label("record_id"),
            record_label(Record, title).label("label"),
            func.row_number().over(partition_by=text, order_by=Record.id).label("rank"),
        )
        .join(Module, Module.id == Record.module_id)
        .outerjoin(title, and_(
            title.id == Module.title_field_id, title.module_id == Module.id,
            title.is_deleted.is_(False), title.type.in_(TITLE_TYPES),
        ))
        .where(Record.module_id == module.id, Record.is_deleted.is_(False), text.in_(keys))
        .subquery()
    )
    found: dict[str, list[Any]] = {}
    for row in db.execute(select(ranked).where(ranked.c.rank <= 2)).mappings():
        found.setdefault(row["key"], []).append(row)
    results = []
    for key in payload.keys:
        rows = found.get(key, [])
        state: Literal["matched", "unmatched", "ambiguous"] = (
            "matched" if len(rows) == 1 else "ambiguous" if rows else "unmatched"
        )
        record = (SheetImportRecord(record_id=rows[0]["record_id"], label=rows[0]["label"])
                  if state == "matched" else None)
        results.append(SheetImportMatch(key=key, state=state, record=record))
    counts = SheetImportMatchCounts(
        matched=sum(item.state == "matched" for item in results),
        unmatched=sum(item.state == "unmatched" for item in results),
        ambiguous=sum(item.state == "ambiguous" for item in results),
    )
    return SheetImportMatches(results=results, counts=counts)
