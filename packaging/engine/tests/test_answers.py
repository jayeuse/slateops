"""The install answers (TASK-0086 AC-I1; plan 6.1) and the copies of the W2 and W5a rules.

The engine cannot import ``backend/`` (standard library only), so it keeps copies of
``local_ca._validate_host`` and ``create_organization.validate_identity``; the drift tests
compare each copy with its source on one table.
"""

from __future__ import annotations

from typing import Any

import pytest

from engine import answers
from operations import local_ca
from operations.create_organization import validate_identity

VALID: dict[str, Any] = {
    "business_name": "Front Desk Dental",
    "slug": "front-desk",
    "admin_email": "owner" + "@frontdesk.test",
    "admin_username": "owner77",
    "public_host": "frontdesk-pc.local",
    "backup_target": "E:\\SlateOps\\Backups",
    "data_vhd_max_gb": 256,
    "time_zone": "Asia/Manila",
}

HOSTS = [
    "frontdesk-pc.local",
    "a.b.local",
    "FRONTDESK.local",
    "frontdesk.lan",
    "local",
    ".local",
    "-a.local",
    "a-.local",
    "a..local",
    "a_b.local",
    "a b.local",
    "a.local.",
    "10.0.0.1",
    "1.2.3.local",
    "x" * 64 + ".local",
    ("a" * 62 + ".") * 4 + "local",
    "",
]
IDENTITIES = [
    ("Front Desk", "front-desk"),
    ("  ", "front"),
    ("x" * 201, "front"),
    (" " + "x" * 200 + " ", "front"),
    ("Front", "Front"),
    ("Front", "front--desk"),
    ("Front", "-front"),
    ("Front", "front_desk"),
    ("Front", "a" * 201),
    ("Front", ""),
]


def _w2_accepts(host: str) -> bool:
    try:
        local_ca._validate_host(host)
    except local_ca.LocalCAError:
        return False
    return True


def _w5a_accepts(name: str, slug: str) -> bool:
    try:
        validate_identity(name, slug)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize("host", HOSTS)
def test_ac_i1_the_public_host_rule_equals_the_local_ca_rule(host: str) -> None:
    assert answers.valid_host(host) is _w2_accepts(host)


@pytest.mark.parametrize(("name", "slug"), IDENTITIES)
def test_ac_i1_the_name_and_slug_rule_equals_the_bootstrap_rule(name: str, slug: str) -> None:
    assert answers.valid_identity(name, slug) is _w5a_accepts(name, slug)


def test_ac_i1_valid_answers_pass_unchanged() -> None:
    assert answers.parse(dict(VALID)) == VALID


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("public_host", "frontdesk.lan"),
        ("public_host", "192.168.1.10"),
        ("slug", "Front Desk"),
        ("business_name", " "),
        ("business_name", "Front\nDesk"),
        ("business_name", "Front\u2028Desk"),
        ("admin_email", "no-at-sign"),
        ("admin_email", "a@b@c.test"),
        ("admin_email", "a b@c.test"),
        ("admin_email", "owner@frontdesk.test\r\nBcc: x@y.test"),
        ("admin_username", ""),
        ("admin_username", "has space"),
        ("admin_username", "x" * 101),
        ("time_zone", "Mars/Olympus"),
        ("time_zone", "../../etc/passwd"),
        ("time_zone", ""),
        ("backup_target", "/mnt/e/backups"),
        ("backup_target", "E:"),
        ("backup_target", "E:\\Back\tups"),
        ("data_vhd_max_gb", 0),
        ("data_vhd_max_gb", 24),
        ("data_vhd_max_gb", 65537),
        ("data_vhd_max_gb", True),
        ("data_vhd_max_gb", "256"),
    ],
)
def test_ac_i1_each_invalid_value_is_refused(key: str, value: Any) -> None:
    assert answers.parse({**VALID, key: value}) is None


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_ac_i1_the_key_set_is_exact(change: str) -> None:
    given = dict(VALID)
    if change == "missing":
        del given["time_zone"]
    else:
        given["provider_user_id"] = "x"

    assert answers.parse(given) is None
