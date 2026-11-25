from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.systems.manage.licensing.editions import Edition, Feature, Limit
from app.systems.manage.licensing.state import Phase


class LicenseImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4_000)


class LimitUse(BaseModel):
    limit: Limit
    allowed: int | None  # None: no limit
    used: int | None  # None: not counted for this reader or this limit


class EditionPrice(BaseModel):
    edition: Edition
    name: str
    monthly_usd: int
    yearly_usd: int
    seats: int | None


class LicenseStatus(BaseModel):
    edition: Edition
    edition_name: str
    phase: Phase
    read_only: bool
    customer: str | None
    starts: date | None
    ends: date | None
    grace_ends: date | None
    warning_ends: date | None
    features: list[Feature]
    limits: list[LimitUse]
    editions: list[EditionPrice]
    can_import: bool
