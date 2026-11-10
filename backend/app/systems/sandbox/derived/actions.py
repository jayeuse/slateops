"""The one computation of a publish's derived changes (setup spec R15, SD25).

Pure: plain inputs in, ``PublicationChange`` values out. The planner uses it for the review,
and the executor applies the changes of the recomputed plan and checks what it did against them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.systems.access.policy.models import AccessLevel
from app.systems.boards.models import BoardStatus
from app.systems.sandbox.derived.models import DERIVED_ROLES
from app.systems.sandbox.publications.schemas import PublicationChange, PublicationCounts

DerivedKind = Literal["group", "dashboard", "board", "category", "channel"]
DERIVED_KINDS: tuple[DerivedKind, ...] = ("group", "dashboard", "board", "category", "channel")
GROUP_LEVELS: dict[str, AccessLevel] = {
    "managers": AccessLevel.MANAGE,
    "members": AccessLevel.WRITE,
    "viewers": AccessLevel.READ,
}
_COUNT_KEYS = {
    "department": "departments",
    "module": "modules",
    "field": "fields",
    "relationship": "relationships",
    "trigger": "triggers",
    "group": "groups",
    "dashboard": "dashboards",
    "board": "boards",
    "category": "categories",
    "channel": "channels",
}


@dataclass(frozen=True, slots=True)
class BoardState:
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class DepartmentOutcome:
    """A department as the publish leaves it.

    ``key`` is the department's Sandbox id, or its live id when no binding names it.
    ``created`` is true when this publish creates the department row.
    """

    key: str
    name: str
    closed: bool
    created: bool
    board: BoardState | None


_ROLE_KINDS: dict[str, DerivedKind] = {
    "managers": "group",
    "members": "group",
    "viewers": "group",
    "dashboard": "dashboard",
    "category": "category",
    "channel": "channel",
}


def role_kind(role: str) -> DerivedKind:
    return _ROLE_KINDS[role]


def derived_name(role: str, department_name: str) -> str:
    """R2 name patterns (plan D5 a): groups and the dashboard add a word; the rest copy."""
    base = department_name.strip()  # each system's create schema strips the name it stores
    return f"{base} {role}" if role in GROUP_LEVELS or role == "dashboard" else base


def derived_label(role: str, name: str) -> str:
    """The review label: the derived name, and for a group its access level (R2)."""
    return f"{name} · {GROUP_LEVELS[role].value}" if role in GROUP_LEVELS else name


def board_action(board: BoardState | None, name: str, closed: bool) -> str | None:
    """What ``sync_department_board`` does to a department's Board, or None for nothing."""
    if board is None:
        return "create"
    if board.status != (BoardStatus.ARCHIVED if closed else BoardStatus.ACTIVE):
        return "close" if closed else "reopen"
    if board.name != name[:200]:
        return "update"
    return None


def derived_changes(departments: Iterable[DepartmentOutcome]) -> list[PublicationChange]:
    """Every derived change of a publish (SD7, SD9, R1, R2).

    The Board follows every department the Board loop visits. The other items are created
    only for a department that this publish creates and leaves open; existing and reopened
    departments derive nothing.
    """
    changes: list[PublicationChange] = []
    for department in departments:
        action = board_action(department.board, department.name, department.closed)
        if action is not None:
            changes.append(
                _change("board", action, f"{department.key}#board", department.name[:200])
            )
        if not department.created or department.closed:
            continue
        for role in DERIVED_ROLES:
            name = derived_name(role, department.name)
            changes.append(
                _change(
                    role_kind(role), "create", f"{department.key}#{role}", derived_label(role, name)
                )
            )
    return changes


def publication_counts(changes: Iterable[PublicationChange]) -> PublicationCounts:
    """One count per kind; ``category`` counts as ``categories``, not ``categorys``."""
    tally = Counter(_COUNT_KEYS[change.kind] for change in changes)
    return PublicationCounts(**{key: tally[key] for key in _COUNT_KEYS.values()})


def planned_derived(changes: Iterable[PublicationChange]) -> Counter[tuple[str, str, str, str]]:
    return Counter(
        (change.kind, change.sandbox_id, change.action, change.label)
        for change in changes
        if change.kind in DERIVED_KINDS
    )


def _change(kind: str, action: str, sandbox_id: str, label: str) -> PublicationChange:
    return PublicationChange.model_validate(
        {"kind": kind, "action": action, "sandboxId": sandbox_id, "label": label}
    )
