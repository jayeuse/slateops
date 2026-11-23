"""One organization with a sheet, its owner, its share recipients and its non-recipients."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.systems.access.policy.models import AccessLevel, Group, GroupAccess, GroupMember
from app.systems.access.users.models import User, UserRole
from app.systems.openview.worksheets.models import Worksheet, WorksheetShare
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.fields.models import Field
from app.systems.sandbox.modules.models import Module
from app.systems.sandbox.records.models import Record
from tests.rbac.support import add_department, add_module, add_user, make_group_access

STRUCTURE = {"structureVersion": 1, "nextColumnSeq": 1, "columns": [], "groups": [], "totals": {}}
Anchor = Literal["record", "module"]


@dataclass(frozen=True)
class SheetWorld:
    department: Department
    module: Module
    record: Record
    sheet: Worksheet
    share_group: Group
    owner: User
    viewer: User
    editor: User
    group_member: User
    guest: User
    peer: User
    manager: User
    admin: User
    reader_access: GroupAccess
    outsider: User

    def people(self) -> dict[str, User]:
        return {
            "owner": self.owner, "view share": self.viewer, "edit share": self.editor,
            "edit share by group": self.group_member, "guest with edit share": self.guest,
            "peer": self.peer, "module manager": self.manager, "admin": self.admin,
            "member without module access": self.outsider,
        }


def add_sheet(db: Session, owner: User, *, record: Record | None = None,
              module: Module | None = None) -> Worksheet:
    anchor = record if record is not None else module
    assert anchor is not None
    sheet = Worksheet(
        org_id=anchor.org_id,
        record_id=record.id if record is not None else None,
        module_id=module.id if module is not None else None,
        owner_id=owner.id, title="Grades", structure=dict(STRUCTURE),
    )
    db.add(sheet)
    db.flush()
    return sheet


def share(db: Session, sheet: Worksheet, level: str, *, user: User | None = None,
          group: Group | None = None) -> WorksheetShare:
    row = WorksheetShare(
        org_id=sheet.org_id, worksheet_id=sheet.id, level=level, created_by=sheet.owner_id,
        subject="user" if user is not None else "group",
        user_id=user.id if user is not None else None,
        group_id=group.id if group is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def sheet_world(db: Session, anchor: Anchor = "record") -> SheetWorld:
    department = add_department(db)
    module = add_module(db, department)
    record = Record(org_id=module.org_id, module_id=module.id, data={})
    db.add(record)
    db.flush()
    owner, viewer, editor, group_member, peer, manager = (add_user(db) for _ in range(6))
    guest = add_user(db, role=UserRole.GUEST)
    admin = add_user(db, role=UserRole.ADMIN)
    reader_access = make_group_access(
        db, [owner, viewer, editor, group_member, guest, peer], department, module,
        level=AccessLevel.READ,
    )
    make_group_access(db, [manager], department, module, level=AccessLevel.MANAGE)
    share_group = Group(org_id=module.org_id, name=f"Sheet group {record.id.hex}")
    db.add(share_group)
    db.flush()
    db.add(GroupMember(org_id=module.org_id, group_id=share_group.id, user_id=group_member.id))
    sheet = add_sheet(
        db, owner, record=record if anchor == "record" else None,
        module=module if anchor == "module" else None,
    )
    share(db, sheet, "view", user=viewer)
    share(db, sheet, "edit", user=editor)
    share(db, sheet, "edit", group=share_group)
    share(db, sheet, "edit", user=guest)
    return SheetWorld(
        department, module, record, sheet, share_group, owner, viewer, editor, group_member,
        guest, peer, manager, admin, reader_access, add_user(db),
    )


@dataclass(frozen=True)
class Students:
    module: Module
    name: Field
    score: Field
    alice: Record
    bob: Record


def add_students(
    db: Session, world: SheetWorld, readers: list[User], name: str = "Student List",
) -> Students:
    """A Student List module that only ``readers`` can read, with two live records."""

    module = add_module(db, world.department, name)
    make_group_access(db, readers, world.department, module, level=AccessLevel.READ)
    title = Field(org_id=module.org_id, module_id=module.id, name="Name", type="text",
                  position=0, config={})
    score = Field(org_id=module.org_id, module_id=module.id, name="Score", type="int",
                  position=1, config={})
    db.add_all([title, score])
    db.flush()
    module.title_field_id = title.id
    records = []
    for label, points in (("Alice", 90), ("Bob", 70)):
        record = Record(org_id=module.org_id, module_id=module.id,
                        data={str(title.id): label, str(score.id): points})
        db.add(record)
        records.append(record)
    db.flush()
    return Students(module, title, score, records[0], records[1])


def editable_structure(students: Students) -> dict[str, object]:
    """Every editable column kind, a link to Student List and one lookup through it."""

    return {
        "structureVersion": 1, "nextColumnSeq": 10,
        "columns": [
            {"key": "c1", "name": "Student", "type": "link",
             "link": {"moduleId": str(students.module.id)}},
            {"key": "c2", "name": "Name", "type": "lookup",
             "lookup": {"linkKey": "c1", "fieldId": str(students.name.id)}},
            {"key": "c3", "name": "Note", "type": "text"},
            {"key": "c4", "name": "Points", "type": "int"},
            {"key": "c5", "name": "Mark", "type": "decimal",
             "decimal": {"places": 2, "currency": False}},
            {"key": "c6", "name": "Status", "type": "select",
             "select": {"options": [{"id": "o1", "label": "Pass"}, {"id": "o2", "label": "Fail"}]}},
            {"key": "c7", "name": "Teacher", "type": "user"},
            {"key": "c8", "name": "Done", "type": "boolean"},
            {"key": "c9", "name": "Due", "type": "date"},
        ],
        "groups": [], "totals": {},
    }
