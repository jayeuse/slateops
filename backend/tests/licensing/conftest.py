import pytest

from app.systems.manage.licensing import license_file
from tests.licensing.support import development_public_key


@pytest.fixture(autouse=True)
def _test_run_development_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development and test accept this run's key in place of the owner's development key."""

    monkeypatch.setattr(license_file, "DEVELOPMENT_PUBLIC_KEY", development_public_key())
