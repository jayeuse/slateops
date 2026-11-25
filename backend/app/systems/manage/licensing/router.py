"""The edition in effect and the license file import (spec editions.md ED-1, ED-2, ED-10)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.dependencies.auth import (
    get_current_user,
    require_fresh_exact_admin,
    require_platform_operator,
)
from app.core.base_model import utc_now
from app.core.config.settings import get_settings
from app.core.database import get_db
from app.systems.access.users.membership import current_membership, is_platform_operator
from app.systems.access.users.models import Membership, User, UserRole
from app.systems.manage.licensing import usage
from app.systems.manage.licensing.editions import PAID_SEATS, SELLABLE, Limit
from app.systems.manage.licensing.license_file import LicenseInvalid, accepted_keys, verify
from app.systems.manage.licensing.models import InstallationLicense
from app.systems.manage.licensing.schemas import (
    EditionPrice,
    LicenseImport,
    LicenseStatus,
    LimitUse,
)
from app.systems.manage.licensing.state import (
    LicenseState,
    Phase,
    current_state,
    evaluate,
    forget_cached_state,
    is_read_only,
    stored_license,
)

router = APIRouter(prefix="/license", tags=["license"])
Database = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_user)]


def _membership(db: Session, user: User) -> Membership:
    membership = current_membership(db, user)
    if membership is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    return membership


def _status(db: Session, state: LicenseState, membership: Membership) -> LicenseStatus:
    admin = membership.role == UserRole.ADMIN.value
    # Count what has a limit, plus the people; a no-limit count can be slow on large data.
    shown = {limit for limit, allowed in state.terms.limits.items() if allowed is not None}
    counted = usage.all_usage(db, shown | {Limit.SEATS, Limit.GUESTS}) if admin else {}
    found = state.license
    return LicenseStatus(
        edition=state.terms.edition,
        edition_name=state.terms.name,
        phase=state.phase,
        read_only=is_read_only(db),
        customer=found.customer if found else None,
        starts=found.starts if found else None,
        ends=found.ends if found else None,
        grace_ends=state.grace_ends,
        warning_ends=state.warning_ends,
        features=sorted(state.terms.features),
        limits=[
            LimitUse(limit=limit, allowed=allowed, used=counted.get(limit))
            for limit, allowed in state.terms.limits.items()
        ],
        editions=[
            EditionPrice(
                edition=terms.edition, name=terms.name, monthly_usd=terms.monthly_usd,
                yearly_usd=terms.yearly_usd,
                seats=PAID_SEATS.get(terms.edition, terms.limits[Limit.SEATS]),
            )
            for terms in SELLABLE
        ],
        can_import=admin and is_platform_operator(db, membership.user_id),
    )


@router.get("", response_model=LicenseStatus)
def get_license(db: Database, user: Actor, response: Response) -> LicenseStatus:
    membership = _membership(db, user)
    row = stored_license(db)
    today = utc_now().date()
    if row is not None and today > row.seen_through:
        row.seen_through = today  # the latest day seen; a clock set back cannot extend it
        db.commit()
    response.headers["Cache-Control"] = "no-store"
    return _status(db, current_state(db), membership)


@router.put("", response_model=LicenseStatus)
def import_license(
    payload: LicenseImport, db: Database, user: Actor, response: Response
) -> LicenseStatus:
    membership = _membership(db, user)
    require_fresh_exact_admin(db, membership.user_id)
    require_platform_operator(db, membership.user_id)
    environment = get_settings().environment
    row = stored_license(db)
    today = max(utc_now().date(), row.seen_through if row else utc_now().date())
    try:
        found = verify(payload.text, accepted_keys(environment))
        if found.starts > today:
            raise LicenseInvalid("This license file starts later; import it on its start date")
        if evaluate(found, today, environment).phase is Phase.ENDED:
            raise LicenseInvalid("This license file has ended")
    except LicenseInvalid as error:  # nothing written yet
        raise HTTPException(
            status_code=422, detail={"code": "license_invalid", "message": str(error)}
        ) from error
    try:
        if row is None:
            row = InstallationLicense(seen_through=today)
            db.add(row)
        row.license_text = payload.text.strip()
        row.imported_at = utc_now()
        row.seen_through = today
        row.performed_by = membership.user_id
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"code": "license_unavailable", "message": "The license could not be saved"},
        ) from error
    forget_cached_state()
    response.headers["Cache-Control"] = "no-store"
    return _status(db, current_state(db), membership)
