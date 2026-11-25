"""The signed license file: `<payload>.<signature>`, Ed25519 over the payload bytes."""

import base64
import json
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.systems.manage.licensing.editions import PAID_SEATS, Edition

# Public halves only. Both private keys stay with the owner in
# `~/.config/slateops-license/`, outside every repository. The development key
# is accepted only in development and test; tests make their own key.
PRODUCTION_PUBLIC_KEY = "6761c668062e95ccdfb7c6589764459c3134556ff45214e734da90693efb3bc7"
DEVELOPMENT_PUBLIC_KEY = "289cf86818e8bc7d14c335db660e114c6f48effabfcf425d7d81451e735ae117"
MAX_FILE_CHARACTERS = 4_000
_FILE_EDITIONS = {Edition.DESK, Edition.OFFICE, Edition.HEADQUARTERS}


class LicenseInvalid(ValueError):
    """The text is not a license file this installation accepts."""


@dataclass(frozen=True)
class LicenseFile:
    id: UUID
    customer: str
    edition: Edition
    seats: int
    starts: date
    ends: date
    issued: date


def accepted_keys(environment: str) -> tuple[str, ...]:
    if environment in {"development", "test"}:
        return (PRODUCTION_PUBLIC_KEY, DEVELOPMENT_PUBLIC_KEY)
    return (PRODUCTION_PUBLIC_KEY,)


def _decode(part: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    except ValueError as error:
        raise LicenseInvalid("The file is not a Slate Operations license file") from error


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def verify(text: str, keys: tuple[str, ...]) -> LicenseFile:
    """Check the signature against `keys` and read the payload; raise LicenseInvalid."""

    text = text.strip()
    if not text or len(text) > MAX_FILE_CHARACTERS or text.count(".") != 1:
        raise LicenseInvalid("The file is not a Slate Operations license file")
    payload_part, signature_part = text.split(".")
    payload, signature = _decode(payload_part), _decode(signature_part)
    if not any(_signed_by(key, payload, signature) for key in keys):
        raise LicenseInvalid("The license file signature is not valid for this installation")
    return _read(payload)


def _signed_by(key: str, payload: bytes, signature: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(signature, payload)
    except InvalidSignature:
        return False
    return True


def _read(payload: bytes) -> LicenseFile:
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("v") != 1:
            raise LicenseInvalid("This license file version is not supported")
        edition = Edition(data["edition"])
        seats = data["seats"]
        found = LicenseFile(
            id=UUID(data["id"]), customer=str(data["customer"]).strip(), edition=edition,
            seats=seats, starts=date.fromisoformat(data["starts"]),
            ends=date.fromisoformat(data["ends"]), issued=date.fromisoformat(data["issued"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, LicenseInvalid):
            raise
        raise LicenseInvalid("The license file content is not valid") from error
    if edition not in _FILE_EDITIONS or type(seats) is not int or seats < 1:
        raise LicenseInvalid("The license file content is not valid")
    if edition in PAID_SEATS and seats > 10_000:
        raise LicenseInvalid("The license file content is not valid")
    if not found.customer or len(found.customer) > 200 or found.ends < found.starts:
        raise LicenseInvalid("The license file content is not valid")
    return found


def sign(found: LicenseFile, private_key: Ed25519PrivateKey) -> str:
    """Write the file text for `found` (used by operations/issue_license.py and tests)."""

    payload = json.dumps(
        {
            "v": 1, "id": str(found.id), "customer": found.customer,
            "edition": found.edition.value, "seats": found.seats,
            "starts": found.starts.isoformat(), "ends": found.ends.isoformat(),
            "issued": found.issued.isoformat(),
        },
        separators=(",", ":"),
    ).encode()
    return f"{_encode(payload)}.{_encode(private_key.sign(payload))}"
