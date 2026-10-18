"""Shared test isolation.

Live network side effects added for production reliability are disabled by
default so unit tests stay hermetic. Tests that exercise them re-enable the
flag explicitly with ``monkeypatch``.

Superseded tests for the rolled-back research engine live in ``tests/archive/``
as reference records only; see the archive README for why each file was
retired and which live tests now cover its safety scenarios.
"""
import pytest

collect_ignore_glob = ["archive/*", "archive/**/*"]


@pytest.fixture(autouse=True)
def _no_live_network_side_effects(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "COACH_SEARCH_RESULT_CACHE_ENABLED", False, raising=False)
    yield
