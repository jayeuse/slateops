"""Fixtures for every audit test."""

import pytest

from app.systems.manage.audit import seals


@pytest.fixture(autouse=True)
def fresh_chain_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no failing chain; none leaves one for the next (P4).

    The back-off lives in process memory, and the installation chain (None) is shared by
    every test, so a failure in one test would otherwise make a later one skip it.
    """

    monkeypatch.setattr(seals, "_BACKOFF", seals.ChainBackoff())
