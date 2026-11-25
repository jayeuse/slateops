"""The license file and the edition in effect (spec editions.md ED-1, ED-2, States)."""

from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.systems.manage.licensing.editions import Edition, Limit
from app.systems.manage.licensing.license_file import (
    LicenseInvalid,
    accepted_keys,
    sign,
    verify,
)
from app.systems.manage.licensing.state import Phase, evaluate
from tests.licensing.support import development_key, license_text


def test_a_development_file_is_accepted_in_test_and_refused_in_production() -> None:
    text = license_text(Edition.HEADQUARTERS, seats=40)
    found = verify(text, accepted_keys("test"))
    assert (found.edition, found.seats, found.customer) == (Edition.HEADQUARTERS, 40, "Acme Ltd")
    with pytest.raises(LicenseInvalid, match="signature is not valid"):
        verify(text, accepted_keys("production"))


def test_a_changed_or_foreign_file_is_refused() -> None:
    text = license_text()
    payload, signature = text.split(".")
    other = license_text(seats=250)  # same key, other payload
    stranger = license_text(signer=Ed25519PrivateKey.generate())
    for refused in (f"{other.split('.')[0]}.{signature}", stranger, payload, "", "a.b.c"):
        with pytest.raises(LicenseInvalid):
            verify(refused, accepted_keys("test"))


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"seats": 0}, "no seats"),
        ({"ends": date(2025, 12, 31)}, "ends before it starts"),
        ({"customer": "  "}, "no customer"),
        ({"edition": Edition.DEVELOPMENT}, "the development edition is never in a file"),
    ],
)
def test_a_signed_file_with_bad_content_is_refused(change: dict[str, Any], reason: str) -> None:
    found = verify(license_text(), accepted_keys("test"))
    with pytest.raises(LicenseInvalid, match="content is not valid"):
        verify(sign(replace(found, **change), development_key()), accepted_keys("test"))


def test_no_license_is_desk_in_production_and_unlimited_in_development() -> None:
    desk = evaluate(None, date(2026, 6, 1), "production")
    assert (desk.phase, desk.terms.edition, desk.terms.limits[Limit.SEATS]) == (
        Phase.NONE, Edition.DESK, 2
    )
    development = evaluate(None, date(2026, 6, 1), "development")
    assert (development.terms.edition, development.terms.limits[Limit.SEATS]) == (
        Edition.DEVELOPMENT, None
    )


@pytest.mark.parametrize(
    ("today", "phase", "edition"),
    [
        (date(2026, 12, 31), Phase.ACTIVE, Edition.OFFICE),  # the end date itself
        (date(2027, 1, 14), Phase.GRACE, Edition.OFFICE),  # 14 days of grace
        (date(2027, 1, 15), Phase.WARNING, Edition.OFFICE),
        (date(2027, 2, 13), Phase.WARNING, Edition.OFFICE),  # 30 days of warning
        (date(2027, 2, 14), Phase.ENDED, Edition.DESK),
    ],
)
def test_a_paid_license_runs_through_grace_and_warning_then_ends_as_desk(
    today: date, phase: Phase, edition: Edition,
) -> None:
    found = verify(license_text(seats=30, ends=date(2026, 12, 31)), accepted_keys("test"))
    state = evaluate(found, today, "production")
    assert (state.phase, state.terms.edition) == (phase, edition)


def test_a_paid_file_sets_the_seats_and_twice_as_many_guests() -> None:
    found = verify(license_text(seats=30), accepted_keys("test"))
    terms = evaluate(found, date(2026, 6, 1), "production").terms
    assert (terms.limits[Limit.SEATS], terms.limits[Limit.GUESTS], terms.limits[Limit.RECORDS]) == (
        30, 60, None
    )
