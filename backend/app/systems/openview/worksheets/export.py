"""Route 20: sheet export as CSV, Excel or template (spec X2-X5, D9.1, D9.2, D5.4).

The file is built in an independent snapshot transaction from the per-viewer projection,
so it holds exactly what the exporter may see. After the build, the route checks the
exporter's module access and session again and loads the sheet through the access rule
with the exporter's shares held, then commits ``worksheets.export.authorized``; only then
are the bytes released.
"""

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from uuid6 import uuid7

from app.core.database.organization_scope import apply_connection_scope
from app.systems.access.policy.checks import module_level
from app.systems.access.users.membership import bound_organization
from app.systems.access.users.models import User
from app.systems.access.users.person_visibility import visible_person_ids
from app.systems.manage.audit.models import SecurityEventOutcome
from app.systems.manage.audit.schemas import SecurityEventIngestRequest
from app.systems.manage.audit.security_events import append_security_event
from app.systems.manage.workspace.models import WorkspaceProfile
from app.systems.openview.worksheets.access import load_visible_worksheet
from app.systems.openview.worksheets.export_files import (
    CellFormat,
    ExportColumn,
    encode_csv,
    encode_xlsx,
)
from app.systems.openview.worksheets.models import Worksheet as SheetModel
from app.systems.openview.worksheets.models import WorksheetRow
from app.systems.openview.worksheets.projection import project_rows
from app.systems.openview.worksheets.query import projected_cell, projected_rows
from app.systems.openview.worksheets.schemas import Cell, SheetValueCell
from app.systems.openview.worksheets.serializers import person_refs
from app.systems.openview.worksheets.structure import (
    Column,
    SheetLinkColumn,
    SheetLookupColumn,
    SheetSelectColumn,
    WorksheetStructure,
)
from app.systems.openview.worksheets.template import build_template, template_bytes
from app.systems.sandbox.fields.models import Field, FieldType
from app.systems.sandbox.records import export as record_export

ExportFormat = Literal["csv", "xlsx", "template"]
EXPORT_EVENT = "worksheets.export.authorized"
MEDIA_TYPES: dict[ExportFormat, str] = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "template": "application/json",
}


@dataclass(frozen=True)
class ExportFile:
    content: bytes
    filename: str
    row_count: int
    column_count: int
    # The modules of link columns the snapshot let the exporter read; rechecked (D9.1).
    link_modules: frozenset[UUID] = frozenset()


def sheet_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={"code": "worksheet_not_found", "message": "Sheet not found"},
    )


def _slug(title: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:80] or "sheet"


def _export_column(db: Session, column: Column) -> ExportColumn:
    """The field kind each column's values are written as; lookups as their source field."""

    if isinstance(column, SheetSelectColumn):
        options = {option.id: option.label for option in column.select.options}
        return ExportColumn(column.name, FieldType.SELECT, options)
    if isinstance(column, SheetLookupColumn):
        source = db.get(Field, column.lookup.fieldId)
        kind = FieldType(source.type) if source is not None else FieldType.TEXT
        # A choice lookup is projected as its label already; a person stays a person.
        if kind in {FieldType.SELECT, FieldType.RELATIONSHIP}:
            kind = FieldType.TEXT
        return ExportColumn(column.name, kind)
    if column.type == "computed":
        return ExportColumn(column.name, FieldType.DECIMAL)
    if isinstance(column, SheetLinkColumn) or column.type == "sheet_lookup":
        return ExportColumn(column.name, FieldType.TEXT)
    return ExportColumn(column.name, FieldType(column.type))


def _people(db: Session, reader: User, columns: list[ExportColumn],
            rows: list[list[Cell]]) -> dict[str, str]:
    """Names of the people in person cells whom the exporter can see; others stay unnamed."""

    ids: set[UUID] = set()
    for cells in rows:
        for cell, column in zip(cells, columns, strict=True):
            if column.kind is FieldType.USER and isinstance(cell, SheetValueCell):
                try:
                    ids.add(UUID(str(cell.value)))
                except ValueError:
                    continue
    visible = visible_person_ids(db, reader, ids)
    return {str(key): ref.display_name for key, ref in person_refs(db, visible).items()}


def _data_file(db: Session, reader: User, sheet: SheetModel, format: ExportFormat,
               profile: WorkspaceProfile) -> ExportFile:
    structure = WorksheetStructure.model_validate(sheet.structure)
    keys = [column.key for column in structure.columns]
    columns = [_export_column(db, column) for column in structure.columns]
    statement = (
        projected_rows(project_rows(db, reader, structure), sheet)
        .order_by(WorksheetRow.position, WorksheetRow.id)
        .limit(record_export.MAX_ROWS + 1)
    )
    rows = [[projected_cell(row, key) for key in keys] for row in db.execute(statement).mappings()]
    if len(rows) > record_export.MAX_ROWS:
        raise record_export.limit_exceeded()
    rules = CellFormat(
        timezone=profile.timezone, locale=profile.locale or "en-US",
        people=_people(db, reader, columns, rows),
    )
    if format == "xlsx":
        author = reader.display_name or reader.username
        content, count = encode_xlsx(columns, rows, rules, author)
    else:
        content, count = encode_csv(columns, rows, rules)
    local_date = datetime.now(UTC).astimezone(ZoneInfo(profile.timezone)).date()
    filename = f"{_slug(sheet.title)}-{local_date.isoformat()}.{format}"
    return ExportFile(content, filename, count, len(columns))


def build_export(db: Session, *, reader_id: UUID, worksheet_id: UUID,
                 format: ExportFormat) -> ExportFile:
    """The file as ``reader_id`` may see the sheet in ``db``'s snapshot."""

    reader = db.get(User, reader_id)
    sheet = None if reader is None else load_visible_worksheet(db, reader, worksheet_id)
    if reader is None or sheet is None:
        raise sheet_not_found()
    structure = WorksheetStructure.model_validate(sheet.structure)
    readable = frozenset(
        column.link.moduleId for column in structure.columns
        if isinstance(column, SheetLinkColumn)
        and module_level(db, reader, column.link.moduleId) is not None
    )
    if format == "template":
        template = build_template(db, reader, sheet)
        content = template_bytes(template)
        if len(content) > record_export.MAX_BYTES:
            raise record_export.limit_exceeded()
        return ExportFile(content, f"{_slug(sheet.title)}-template.json", 0,
                          len(template.columns), readable)
    profile = db.get(WorkspaceProfile, sheet.org_id)
    if profile is None:
        raise HTTPException(503, detail="Workspace configuration is unavailable")
    built = _data_file(db, reader, sheet, format, profile)
    return replace(built, link_modules=readable)


def export_snapshot(engine: Engine, *, reader_id: UUID, worksheet_id: UUID,
                    format: ExportFormat, org_id: UUID | None) -> ExportFile:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        if org_id is not None:
            apply_connection_scope(connection, org_id)
        with Session(bind=connection) as snapshot:
            return build_export(snapshot, reader_id=reader_id, worksheet_id=worksheet_id,
                                format=format)


def commit_export_event(db: Session, actor_id: UUID, worksheet_id: UUID,
                        format: ExportFormat, exported: ExportFile) -> None:
    """One event per released file, with no title, value or column name (D5.4)."""

    try:
        append_security_event(
            db,
            SecurityEventIngestRequest(
                event_type=EXPORT_EVENT,
                source="worksheets",
                operation_id=uuid7(),
                actor_id=actor_id,
                subject_id=worksheet_id,
                outcome=SecurityEventOutcome.SUCCESS,
                metadata={
                    "format": format,
                    "row_count": exported.row_count,
                    "column_count": exported.column_count,
                },
            ),
            org_id=bound_organization(db),
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(503, detail="Unable to record export authorization") from error
