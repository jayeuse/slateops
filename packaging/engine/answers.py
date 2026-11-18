"""The install answers (plan 6.1, TASK-0086 AC-I1) and their stored copy.

The wizard sends them once, on the first ``install`` run, through the secret channel. The
engine keeps them in ``/var/lib/slateops/install-answers.json`` (0600) for a resume and for
``resend-invitation`` (TASK-0080 N-3: the Windows side keeps no answers). They hold personal
data (the administrator email and user name): ``held.load_held`` masks both in every log.

The engine cannot import ``backend/``, so two rules are copies, each with a drift test:
``valid_host`` is ``backend/operations/local_ca.py`` ``_validate_host`` (W2; checked first,
TASK-0083 carry) and ``valid_identity`` is ``create_organization.validate_identity`` (W5a).
Bootstrap stays the authority for the email, the user name and the time zone; the engine
refuses here what would fail there, so the install stops at step 1, not at step 11.
"""

from __future__ import annotations

import ipaddress
import json
import re
import unicodedata
import zoneinfo
from typing import Any

from engine.core import Paths, private_dir, write_private
from engine.drive import valid_target

KEYS = (
    "business_name",
    "slug",
    "admin_email",
    "admin_username",
    "public_host",
    "backup_target",
    "data_vhd_max_gb",
    "time_zone",
)
# local_ca._LABEL and _validate_host (W2).
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
# UserCreate.username (backend/app/systems/access/users/schemas.py:259).
_USERNAME = re.compile(r"[a-zA-Z0-9_-]{3,100}\Z")
# A shape check only; Auth and bootstrap validate the address. Like bootstrap's
# normalize_email, the domain has at least one dot and does not start or end with one.
_LABEL_TEXT = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL = re.compile(
    r"[^@\s]{1,64}@(?=[^@]{1,253}\Z)" + _LABEL_TEXT + r"(?:\." + _LABEL_TEXT + r")+\Z"
)
_TIME_ZONE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{0,30}(?:/[A-Za-z0-9_+-]{1,30}){0,2}\Z")
# Planning values (Proposed): at least the plan 10.2 free-space minimum (25 GB), at most the
# VHDX limit (64 TiB). The Windows side sizes the disk; the engine only records the value.
VHD_MIN_GB, VHD_MAX_GB = 25, 65536


def valid_host(host: str) -> bool:
    labels = host.split(".")
    if (
        len(host) > 253
        or len(labels) < 2
        or labels[-1] != "local"
        or not all(_LABEL.match(label) for label in labels)
    ):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def valid_identity(name: str, slug: str) -> bool:
    return not (
        not name.strip()
        or len(name.strip()) > 200
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
        or len(slug) > 200
    )


def _text(value: Any) -> bool:
    """Customer text: no line boundary and no control character (the W2 rule)."""
    return (
        isinstance(value, str)
        and "".join(value.splitlines()) == value
        and not any(unicodedata.category(character) == "Cc" for character in value)
    )


def _time_zone(value: Any) -> bool:
    if not isinstance(value, str) or not _TIME_ZONE.match(value) or len(value) > 64:
        return False
    try:
        zoneinfo.ZoneInfo(value)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return False
    return True


def parse(given: Any) -> dict[str, Any] | None:
    """The answers when every key is present and valid, else None."""
    if not isinstance(given, dict) or set(given) != set(KEYS):
        return None
    name, slug = given["business_name"], given["slug"]
    size = given["data_vhd_max_gb"]
    checks = (
        isinstance(given["public_host"], str) and valid_host(given["public_host"]),
        _text(name) and isinstance(slug, str) and valid_identity(name, slug),
        _text(given["admin_email"]) and _EMAIL.match(given["admin_email"]) is not None,
        isinstance(given["admin_username"], str)
        and _USERNAME.match(given["admin_username"]) is not None,
        valid_target(given["backup_target"]),  # the set-backup-target rule (TASK-0093)
        isinstance(size, int) and not isinstance(size, bool) and VHD_MIN_GB <= size <= VHD_MAX_GB,
        _time_zone(given["time_zone"]),
    )
    return dict(given) if all(checks) else None


def load(paths: Paths) -> dict[str, Any] | None:
    try:
        stored = json.loads(paths.answers.read_text())
    except (OSError, ValueError):
        return None
    return parse(stored)


def store(paths: Paths, values: dict[str, Any]) -> None:
    private_dir(paths.state)
    data = json.dumps(values, indent=2, sort_keys=True) + "\n"
    write_private(paths.answers, data.encode())
