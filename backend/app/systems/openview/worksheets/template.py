"""The template file of a sheet: its structure only, per exporter (spec X5, D9.2, D14 S1).

The template starts from :func:`structure_view`, the one per-viewer structure serializer.
It holds no rows, no shares and no organization, module, record, field, person or sheet
IDs. A link column names its module and department, and a lookup names its field, only
when the exporter can read that module now; otherwise the column becomes ``text``, and so
does every lookup through it. A From another sheet column is always ``text``. A total that
only a number column can have is dropped from a column that became ``text``.
"""

import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.systems.access.policy.checks import module_level
from app.systems.access.users.models import User
from app.systems.openview.worksheets.models import Worksheet
from app.systems.openview.worksheets.serializers import structure_view
from app.systems.openview.worksheets.structure import (
    SheetComputedColumn,
    SheetDecimalColumn,
    SheetLinkColumn,
    SheetLookupColumn,
    SheetPlainColumn,
    SheetSelectColumn,
)
from app.systems.openview.worksheets.template_schema import (
    TEMPLATE_KIND,
    SheetTemplate,
    SheetTemplateLink,
    SheetTemplateLinkColumn,
    SheetTemplateLookup,
    SheetTemplateLookupColumn,
    TemplateColumn,
)
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.fields.models import Field as RecordField
from app.systems.sandbox.fields.models import FieldType
from app.systems.sandbox.modules.models import Module


def _readable_module(db: Session, user: User, module_id: UUID) -> SheetTemplateLink | None:
    module = db.get(Module, module_id)
    if module is None or module.is_deleted or module_level(db, user, module_id) is None:
        return None
    department = db.get(Department, module.department_id)
    if department is None or department.is_deleted:
        return None
    return SheetTemplateLink(
        moduleName=module.module_name, departmentName=department.department_name,
    )


def _field_name(db: Session, field_id: UUID, module_id: UUID) -> str | None:
    found = db.get(RecordField, field_id)
    if (found is None or found.is_deleted or found.module_id != module_id
            or FieldType(found.type) is FieldType.RELATIONSHIP):
        return None
    return found.name


def build_template(db: Session, user: User, sheet: Worksheet) -> SheetTemplate:
    view = structure_view(db, user, sheet)
    linked: dict[str, UUID] = {}
    columns: list[TemplateColumn] = []
    for column in view.columns:
        text = SheetPlainColumn(key=column.key, name=column.name, type="text")
        if isinstance(column, SheetLinkColumn):
            link = _readable_module(db, user, column.link.moduleId)
            if link is None:
                columns.append(text)
                continue
            linked[column.key] = column.link.moduleId
            columns.append(SheetTemplateLinkColumn(
                key=column.key, name=column.name, type="link", link=link,
            ))
        elif isinstance(column, SheetLookupColumn):
            module_id = linked.get(column.lookup.linkKey)
            name = (
                None if module_id is None
                else _field_name(db, column.lookup.fieldId, module_id)
            )
            columns.append(text if name is None else SheetTemplateLookupColumn(
                key=column.key, name=column.name, type="lookup",
                lookup=SheetTemplateLookup(linkKey=column.lookup.linkKey, fieldName=name),
            ))
        elif isinstance(
            column, SheetPlainColumn | SheetDecimalColumn | SheetSelectColumn
            | SheetComputedColumn,
        ):
            columns.append(column)
        else:  # From another sheet, visible or not: never in a template (S1)
            columns.append(text)
    as_text = {column.key for column in columns if column.type == "text"}
    totals = {
        key: function for key, function in view.totals.items()
        if function == "count" or key not in as_text
    }
    return SheetTemplate(
        kind=TEMPLATE_KIND, schemaVersion=1, title=sheet.title, columns=columns,
        groups=view.groups, totals=totals,
    )


def template_bytes(template: SheetTemplate) -> bytes:
    document = template.model_dump(mode="json")
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
