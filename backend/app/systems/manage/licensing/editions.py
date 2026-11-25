"""The self-hosted editions: limits, Office features and prices (DEC-0029, spec editions.md)."""

from dataclasses import dataclass
from enum import StrEnum


class Edition(StrEnum):
    DESK = "desk"
    OFFICE = "office"
    HEADQUARTERS = "headquarters"
    # Development and test installations without a license file (never production).
    DEVELOPMENT = "development"


class Feature(StrEnum):
    OPENCOMMS = "opencomms"
    DASHBOARDS = "dashboards"
    REPORTS = "reports"
    AUTOMATIONS = "automations"
    GANTT = "gantt"
    AUDIT_VIEWER = "audit_viewer"


class Limit(StrEnum):
    SEATS = "seats"
    GUESTS = "guests"
    DEPARTMENTS = "departments"
    MODULES = "modules"
    RECORDS = "records"
    SHEETS = "sheets"
    SHEET_ROWS = "sheet_rows"


@dataclass(frozen=True)
class EditionTerms:
    edition: Edition
    name: str
    monthly_usd: int
    yearly_usd: int
    features: frozenset[Feature]
    # None is "no limit". Seats and guests come from the license file for paid editions.
    limits: dict[Limit, int | None]


ALL_FEATURES = frozenset(Feature)
_NO_LIMITS: dict[Limit, int | None] = dict.fromkeys(Limit)

DESK = EditionTerms(
    Edition.DESK, "Desk", 0, 0, frozenset(),
    {
        Limit.SEATS: 2, Limit.GUESTS: 0, Limit.DEPARTMENTS: 2, Limit.MODULES: 3,
        Limit.RECORDS: 1_000, Limit.SHEETS: 10, Limit.SHEET_ROWS: 1_000,
    },
)
OFFICE = EditionTerms(Edition.OFFICE, "Office", 39, 390, ALL_FEATURES, _NO_LIMITS)
HEADQUARTERS = EditionTerms(
    Edition.HEADQUARTERS, "Headquarters", 89, 890, ALL_FEATURES, _NO_LIMITS
)
DEVELOPMENT = EditionTerms(
    Edition.DEVELOPMENT, "Development", 0, 0, ALL_FEATURES, _NO_LIMITS
)
PAID_SEATS = {Edition.OFFICE: 25, Edition.HEADQUARTERS: 100}
SELLABLE = (DESK, OFFICE, HEADQUARTERS)
TERMS = {terms.edition: terms for terms in (*SELLABLE, DEVELOPMENT)}


def paid_terms(edition: Edition, seats: int) -> EditionTerms:
    """Office or Headquarters with the seats of its license file; guests are 2 per seat."""

    base = TERMS[edition]
    return EditionTerms(
        base.edition, base.name, base.monthly_usd, base.yearly_usd, base.features,
        {**base.limits, Limit.SEATS: seats, Limit.GUESTS: seats * 2},
    )
