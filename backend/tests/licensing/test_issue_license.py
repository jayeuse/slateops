"""operations/issue_license.py takes the seats from the edition (DEC-0029)."""

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from app.systems.manage.licensing.editions import Edition
from app.systems.manage.licensing.license_file import accepted_keys, verify
from operations import issue_license
from tests.licensing.support import development_key


@pytest.mark.parametrize(
    ("edition", "seats"), [("office", 25), ("headquarters", 100), ("desk", 2)]
)
def test_the_edition_sets_the_seats_of_the_issued_file(
    tmp_path: Path, edition: str, seats: int
) -> None:
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(development_key().private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ))
    output = tmp_path / "acme.slatelicense"
    status = issue_license.main([
        "--customer", "Acme Ltd", "--edition", edition, "--starts", "2026-12-01",
        "--ends", "2026-12-31", "--output", str(output), "--key-file", str(key_file),
    ])
    found = verify(output.read_text(), accepted_keys("test"))
    assert (status, found.edition, found.seats) == (0, Edition(edition), seats)
