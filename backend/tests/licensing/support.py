"""License files signed with a development key made for the test run (never a file)."""

from datetime import date
from functools import cache
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy.orm import Session

from app.systems.manage.licensing.editions import Edition
from app.systems.manage.licensing.license_file import LicenseFile, sign
from app.systems.manage.licensing.models import InstallationLicense
from app.systems.manage.licensing.state import forget_cached_state

LICENSE_ID = UUID("01936f4e-0000-7000-8000-000000000001")


@cache
def development_key() -> Ed25519PrivateKey:
    """A key made for this test run; `conftest.py` makes it the development key."""

    return Ed25519PrivateKey.generate()


def development_public_key() -> str:
    return development_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def license_text(
    edition: Edition = Edition.OFFICE, *, seats: int = 25, starts: date = date(2026, 1, 1),
    ends: date = date(2099, 12, 31), signer: Ed25519PrivateKey | None = None,
) -> str:
    found = LicenseFile(
        id=LICENSE_ID, customer="Acme Ltd", edition=edition, seats=seats, starts=starts,
        ends=ends, issued=starts,
    )
    return sign(found, signer or development_key())


def install(db: Session, text: str, *, seen_through: date = date(2026, 1, 1)) -> None:
    """Store `text` as the installation's license file."""

    from app.core.base_model import utc_now

    db.add(InstallationLicense(license_text=text, imported_at=utc_now(), seen_through=seen_through))
    db.flush()
    forget_cached_state()
