"""The installation's one imported license file (no row means no license file: Desk)."""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import BaseModel


class InstallationLicense(BaseModel):
    __tablename__ = "installation_licenses"
    __table_args__ = (
        CheckConstraint("singleton_key = true", name="ck_installation_licenses_singleton"),
        CheckConstraint(
            "NOT is_deleted AND deleted_at IS NULL", name="ck_installation_licenses_live"
        ),
        CheckConstraint(
            "length(license_text) BETWEEN 1 AND 4000", name="ck_installation_licenses_text"
        ),
        UniqueConstraint("singleton_key", name="uq_installation_licenses_singleton"),
    )
    singleton_key: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    license_text: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The latest UTC day the installation has seen, so a clock set back cannot
    # extend a license (spec editions.md, States).
    seen_through: Mapped[date] = mapped_column(Date, nullable=False)
