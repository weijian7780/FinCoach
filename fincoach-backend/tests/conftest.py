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
def _legacy_search_transport(request, monkeypatch):
    """Existing SDK mocks explicitly exercise the retained Tavily adapter."""
    if request.module.__name__.split('.')[-1] in {
        'test_admin_link_import', 'test_deepseek_writer_gap', 'test_general_search_privacy',
        'test_open_question_reliability', 'test_public_fetch', 'test_research_recovery',
        'test_search_gap_followup', 'test_web_research',
    }:
        from app import config
        monkeypatch.setattr(config, 'WEB_SEARCH_PROVIDER', 'tavily')


@pytest.fixture(autouse=True)
def _legacy_provider_contract(request, monkeypatch):
    """These tests assert the pre-slot two-provider protocol explicitly.

    Keep that contract testable under deployment environments enabling the new
    slot; test_writer_fallback_slot exercises the enabled three-slot contract.
    """
    module = request.module.__name__.split('.')[-1]
    if module in {
        "test_rag_pipeline", "test_research_applicability", "test_research_notice_regression",
        "test_verifier_provider", "test_writer_fixes", "test_writer_round2", "test_writer_round3",
        "test_structured_provider_order",
    }:
        from app import llm
        for name in ("BASE_URL", "API_KEY_ENV", "MODEL"):
            monkeypatch.setattr(llm, "COACH_WRITER_FALLBACK_" + name, "")
        monkeypatch.setattr(llm, "COACH_WRITER_PROVIDER_ORDER", "primary_first")
        monkeypatch.setattr(llm, "COACH_PRIMARY_REASONING", "default")
    if module in {
        "test_rag_pipeline", "test_research_applicability", "test_research_notice_regression",
        "test_verifier_provider", "test_writer_fixes", "test_writer_round2", "test_writer_round3",
        "test_structured_provider_order", "test_writer_fallback_slot", "test_time_budget_plan",
    }:
        from app.rag import verifier
        for name in ("BASE_URL", "API_KEY_ENV", "MODEL"):
            monkeypatch.setattr(verifier, "COACH_VERIFIER_" + name, "")
    if module == "test_writer_fallback_slot":
        from app import llm
        monkeypatch.setattr(llm, "COACH_WRITER_PROVIDER_ORDER", "primary_first")
        monkeypatch.setattr(llm, "COACH_PRIMARY_REASONING", "default")


@pytest.fixture(autouse=True)
def _no_live_network_side_effects(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "COACH_SEARCH_RESULT_CACHE_ENABLED", False, raising=False)
    # Published-title lookup reads Supabase; title tests supply their own list.
    monkeypatch.setattr("app.rag.service.published_document_titles", lambda: ())
    yield
