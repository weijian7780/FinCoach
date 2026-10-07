"""Shared test isolation.

Live network side effects added for production reliability are disabled by
default so unit tests stay hermetic. Tests that exercise them re-enable the
flag explicitly with ``monkeypatch``.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_live_network_side_effects(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "COACH_SEARCH_RESULT_CACHE_ENABLED", False, raising=False)
    yield
