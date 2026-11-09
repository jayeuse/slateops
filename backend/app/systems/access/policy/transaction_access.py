"""One resolution of a person's access for each transaction (plan step 3.4).

:func:`app.systems.access.policy.scope.effective_levels` keeps its result here, keyed by
the transaction's organization and the person, and tagged with the root transaction.
Nothing outlives that transaction:

- Commit, rollback (a savepoint's too) and the root transaction's end clear every entry;
  ``Session.close()`` fires only the end event. Releasing a savepoint does not clear.
- A lookup under another root transaction misses and clears the entries.
- A flush that writes a row the resolution reads (groups, their members and access rows,
  memberships, users, modules, departments) clears every entry.
- A lock or a fresh read of a person's authority is a change too: :func:`forget_access`
  drops that person's entry and stored membership, so the next check reads both again.
  A check that must see the state after a lock calls it, or passes a fresh membership.
  Every load or reload of a ``User`` or ``Membership`` row drops it too. That is the only
  drop for callers that reload the person with ``populate_existing`` and do not call
  :func:`forget_access` (the notification query, the scheduled post's author check).

This module never imports the membership or scope modules, so both can call it.
"""

from itertools import chain
from typing import Any
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

from app.systems.access.policy.models import Group, GroupAccess, GroupMember
from app.systems.access.users.models import Membership, User
from app.systems.sandbox.departments.models import Department
from app.systems.sandbox.modules.models import Module

STORE_KEY = "slateops.effective_access"
# The request's membership reads (``membership.organization_membership``) live here too.
MEMBERSHIP_CACHE_KEY = "slateops.memberships"
_INPUTS = (GroupAccess, GroupMember, Group, Membership, User, Module, Department)
Key = tuple[UUID, UUID]


def _info(db: Session) -> dict[str, Any] | None:
    # A test double of a session has no transactions to tag; it never stores.
    info = getattr(db, "info", None) if isinstance(db, Session) else None
    return info if isinstance(info, dict) else None


def recall_access(db: Session, org_id: UUID, user_id: UUID) -> Any | None:
    """The resolution this root transaction stored for the person, if any."""

    info = _info(db)
    store = info.get(STORE_KEY) if info is not None else None
    if store is None or info is None:
        return None
    root = db.get_transaction()
    if root is None or store["root"] is not root:
        info.pop(STORE_KEY, None)
        return None
    return store["entries"].get((org_id, user_id))


def remember_access(db: Session, org_id: UUID, user_id: UUID, access: Any) -> None:
    """Keep (or overwrite) the person's resolution for the rest of the root transaction."""

    info = _info(db)
    root = db.get_transaction() if info is not None else None
    if info is None or root is None:
        return
    store = info.get(STORE_KEY)
    if store is None or store["root"] is not root:
        store = {"root": root, "entries": {}}
        info[STORE_KEY] = store
    store["entries"][(org_id, user_id)] = access


def forget_access(db: Session, user_id: UUID) -> None:
    """Drop the person's stored resolution and membership in every organization."""

    info = _info(db)
    if info is None:
        return
    store = info.get(STORE_KEY)
    if store is not None:
        for key in [key for key in store["entries"] if key[1] == user_id]:
            del store["entries"][key]
    memberships = info.get(MEMBERSHIP_CACHE_KEY)
    if isinstance(memberships, dict):
        for key in [key for key in memberships if key[1] == user_id]:
            del memberships[key]


def clear_access(db: Session) -> None:
    info = _info(db)
    if info is not None:
        info.pop(STORE_KEY, None)


@event.listens_for(Session, "after_commit")
def _clear_after_commit(session: Session) -> None:
    # SQLAlchemy also sends this event when a savepoint is released, which changes
    # nothing that a resolution reads; a batch keeps its resolution across its items.
    if not session.in_nested_transaction():
        clear_access(session)


@event.listens_for(Session, "after_rollback")
def _clear_after_rollback(session: Session) -> None:
    clear_access(session)


@event.listens_for(Session, "after_transaction_end")
def _clear_at_root_end(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        clear_access(session)


@event.listens_for(Session, "before_flush")
def _clear_on_input_write(session: Session, _context: Any, _instances: Any) -> None:
    if any(
        isinstance(instance, _INPUTS)
        for instance in chain(session.new, session.dirty, session.deleted)
    ):
        clear_access(session)


def _forget_reloaded(target: User | Membership, context: Any, *_attributes: Any) -> None:
    session = getattr(context, "session", None)
    user_id = target.__dict__.get("id" if isinstance(target, User) else "user_id")
    if isinstance(session, Session) and isinstance(user_id, UUID):
        forget_access(session, user_id)


for _model in (User, Membership):
    event.listen(_model, "load", _forget_reloaded)
    event.listen(_model, "refresh", _forget_reloaded)
