"""The edition in effect: the license file, its dates and the environment (spec editions.md)."""

import time
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.base_model import utc_now
from app.core.config.settings import get_settings
from app.systems.manage.licensing import usage
from app.systems.manage.licensing.editions import (
    DESK,
    DEVELOPMENT,
    Edition,
    EditionTerms,
    Limit,
    paid_terms,
)
from app.systems.manage.licensing.license_file import (
    LicenseFile,
    LicenseInvalid,
    accepted_keys,
    verify,
)
from app.systems.manage.licensing.models import InstallationLicense

GRACE_DAYS = 14
WARNING_DAYS = 30


class Phase(StrEnum):
    NONE = "none"  # no license file
    ACTIVE = "active"
    GRACE = "grace"
    WARNING = "warning"
    ENDED = "ended"


@dataclass(frozen=True)
class LicenseState:
    phase: Phase
    terms: EditionTerms
    license: LicenseFile | None
    today: date

    @property
    def grace_ends(self) -> date | None:
        return self.license.ends + timedelta(days=GRACE_DAYS) if self.license else None

    @property
    def warning_ends(self) -> date | None:
        ends = self.grace_ends
        return ends + timedelta(days=WARNING_DAYS) if ends else None


def evaluate(found: LicenseFile | None, today: date, environment: str) -> LicenseState:
    """Pure rule: which terms apply on `today` for this file and environment."""

    unlicensed = DEVELOPMENT if environment in {"development", "test"} else DESK
    if found is None:
        return LicenseState(Phase.NONE, unlicensed, None, today)
    if found.edition is Edition.DESK:
        return LicenseState(Phase.ACTIVE, DESK, found, today)
    terms = paid_terms(found.edition, found.seats)
    state = LicenseState(Phase.ACTIVE, terms, found, today)
    if today <= found.ends:
        return state
    if today <= state.grace_ends:  # type: ignore[operator]
        return LicenseState(Phase.GRACE, terms, found, today)
    if today <= state.warning_ends:  # type: ignore[operator]
        return LicenseState(Phase.WARNING, terms, found, today)
    return LicenseState(Phase.ENDED, DESK, found, today)


def stored_license(db: Session) -> InstallationLicense | None:
    return db.scalar(select(InstallationLicense))


def current_state(db: Session) -> LicenseState:
    environment = get_settings().environment
    row = stored_license(db)
    today = utc_now().date()
    found = None
    if row is not None:
        today = max(today, row.seen_through)
        try:
            found = verify(row.license_text, accepted_keys(environment))
        except LicenseInvalid:
            found = None  # for example a development file after a move to production
    return evaluate(found, today, environment)


def over_limits(db: Session, terms: EditionTerms) -> list[Limit]:
    """The limits of `terms` that the installation's use is above."""

    used = usage.all_usage(db, {key for key, cap in terms.limits.items() if cap is not None})
    return [
        limit for limit, allowed in terms.limits.items()
        if allowed is not None and used[limit] > allowed
    ]


_read_only_cache: dict[str, tuple[float, bool]] = {}
_read_only_lock = Lock()
_READ_ONLY_TTL_SECONDS = 60.0


def is_read_only(db: Session) -> bool:
    """Ended license and above a Desk limit: only administrators may write (DEC-0029 item 11)."""

    state = current_state(db)
    if state.phase is not Phase.ENDED:
        return False
    key = str(state.license.id) if state.license else ""
    now = time.monotonic()
    with _read_only_lock:
        cached = _read_only_cache.get(key)
        if cached is not None and now - cached[0] < _READ_ONLY_TTL_SECONDS:
            return cached[1]
    result = bool(over_limits(db, DESK))
    with _read_only_lock:
        _read_only_cache[key] = (now, result)
    return result


def forget_cached_state() -> None:
    with _read_only_lock:
        _read_only_cache.clear()
