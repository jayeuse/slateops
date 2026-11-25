"""Write a signed license file for one customer (spec docs/specs/editions.md).

Run from `backend/`:

    uv run python -m operations.issue_license --customer "Acme Ltd" --edition office \
        --starts 2026-12-01 --ends 2026-12-31 --output acme-2026-12.slatelicense

The seats come from the edition: Office 25, Headquarters 100, Desk 2.

The private key is read from `--key-file` (default: the owner's production key in
`~/.config/slateops-license/`). The key is never printed. The output file must not exist.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app.systems.manage.licensing import license_file
from app.systems.manage.licensing.editions import DESK, PAID_SEATS, Edition, Limit
from app.systems.manage.licensing.license_file import LicenseFile, LicenseInvalid, sign, verify

DEFAULT_KEY_FILE = Path.home() / ".config" / "slateops-license" / "production-signing-key.pem"
FILE_EDITIONS = (Edition.DESK.value, Edition.OFFICE.value, Edition.HEADQUARTERS.value)
# The edition sets the seats (DEC-0029); guests are twice the seats.
EDITION_SEATS = {**PAID_SEATS, Edition.DESK: DESK.limits[Limit.SEATS] or 2}


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--customer", required=True)
    parser.add_argument("--edition", required=True, choices=FILE_EDITIONS)
    parser.add_argument("--starts", required=True, type=date.fromisoformat)
    parser.add_argument("--ends", required=True, type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    key = load_pem_private_key(args.key_file.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        print("The key file is not an Ed25519 private key.", file=sys.stderr)
        return 2
    found = LicenseFile(
        id=uuid4(), customer=args.customer.strip(), edition=Edition(args.edition),
        seats=EDITION_SEATS[Edition(args.edition)], starts=args.starts, ends=args.ends,
        issued=date.today(),
    )
    text = sign(found, key)
    try:  # the file must pass the same check as the application's import
        verify(text, license_file.accepted_keys("development"))
    except LicenseInvalid as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    try:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"Refused: {args.output} already exists.", file=sys.stderr)
        return 2
    with os.fdopen(descriptor, "w") as output:
        output.write(text + "\n")
    kind = "production" if _production(text) else "development (development and test only)"
    print(f"Wrote {args.output}: {found.edition.value}, {found.seats} seats, "
          f"{found.starts} to {found.ends}, {kind} key.")
    return 0


def _production(text: str) -> bool:
    try:
        verify(text, license_file.accepted_keys("production"))
    except LicenseInvalid:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
