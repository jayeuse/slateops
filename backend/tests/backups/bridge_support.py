"""The backup bridge's database session in tests: runtime role, no bound organization."""

import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import select

from app.core.database.session import AuditSession
from app.systems.access.users.membership import transaction_organization
from app.systems.manage.audit.context import AUDIT_CONTEXT_KEY, AuditContext
from app.systems.manage.backups.models import BackupPolicy
from tests.conftest import guarded_create_engine


@contextmanager
def bridge_session() -> Iterator[AuditSession]:
    """As ``backup_state.coordinated_session`` opens it, without any policy row; rolled back."""
    engine = guarded_create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        with AuditSession(engine) as db:
            db.info[AUDIT_CONTEXT_KEY] = AuditContext(
                request_method="OPERATOR", request_path="/operations/backup_state",
                actor_label="Installation backup runner",
            )
            try:
                assert transaction_organization(db) is None
                for stale in db.scalars(select(BackupPolicy)).all():
                    db.delete(stale)
                db.flush()
                yield db
            finally:
                db.rollback()
    finally:
        engine.dispose()


def on_fresh_thread[Result](function: Callable[[], Result]) -> Result:
    """Run as a new bridge process would: a thread with no test organization binding."""
    outcome: list[Result] = []
    failure: list[BaseException] = []

    def run() -> None:
        try:
            outcome.append(function())
        except BaseException as error:
            failure.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(60)
    assert not thread.is_alive(), "the bridge call hung"
    if failure:
        raise failure[0]
    return outcome[0]
