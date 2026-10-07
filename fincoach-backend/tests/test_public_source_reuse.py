from dataclasses import replace
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from unittest.mock import Mock
from time import monotonic

from app.llm import CoachRequestBudget
from app.rag.public_source_store import PublicSourcePage, PublicSourceSpec, PublicSourceStore
from app.rag.research_policy import QuestionPlan
from app.rag.research_windows import bootstrap_public_sources
from app.rag.web_research import WebResearchCache

URL = "https://example.gov.my/guidance.pdf"
PLAN = QuestionPlan("Example assistance", False, True, "current", required_facts=("application", "documents"), part_tracking=True)
SPEC = PublicSourceSpec("example", ("Example assistance",), "Malaysia", "2026", (URL,))


def page():
    text = "Example assistance 2026. Apply through the official portal. Married applicants supply a marriage certificate."
    return PublicSourcePage(URL, "Example assistance 2026", text, datetime.now(timezone.utc), sha256(text.encode()).hexdigest(), declared_period="2026")


def bootstrap(plan, store, cache):
    return bootstrap_public_sources(plan, store=store, catalog=(SPEC,), cache=cache,
        budget=CoachRequestBudget(started_at=monotonic()), api_key="test", timeout=10, reserve_after_seconds=20)


def test_cold_fetch_and_warm_reassessment_windows(tmp_path, monkeypatch):
    def fetch(urls, **kw):
        kw["cache"].extract_calls += 1
        kw["cache"].fetched_pages[URL] = page()
        return {URL: page().content}
    extract = Mock(side_effect=fetch)
    monkeypatch.setattr("app.rag.web_research.extract_passages", extract)
    store = PublicSourceStore(tmp_path)
    cold = WebResearchCache()
    assert bootstrap(PLAN, store, cold)
    assert cold.extract_calls == 1
    warm = WebResearchCache()
    assert bootstrap(PLAN, store, warm)
    assert extract.call_count == 1 and warm.extract_calls == 0
    assert warm.public_source_diagnostics["cache_pages_used"] == 1


def test_expired_wrong_period_and_explicit_search_do_not_reuse(tmp_path, monkeypatch):
    extract = Mock(return_value={})
    monkeypatch.setattr("app.rag.web_research.extract_passages", extract)
    store = PublicSourceStore(tmp_path)
    store.put(replace(page(), fetched_at=datetime.now(timezone.utc)-timedelta(days=2)))
    assert not bootstrap(PLAN, store, WebResearchCache())
    store.put(page())
    assert not bootstrap(replace(PLAN, time_scope="historical", period="2023"), store, WebResearchCache())
    assert not bootstrap(replace(PLAN, explicit_search=True), store, WebResearchCache())
    assert extract.call_count == 2


def test_source_cards_deduplicate_after_used_rank_filter():
    from app.rag.service import unique_source_rows
    rows = [{"url": URL, "source_type": "web", "rank": 1},
            {"url": URL + "#documents", "source_type": "web", "rank": 2},
            {"url": "https://example.gov.my/other", "source_type": "web", "rank": 3}]
    assert [r["rank"] for r in unique_source_rows(rows)] == [1, 3]
    assert [r["rank"] for r in unique_source_rows(rows[1:])] == [2, 3]


def test_unknown_programme_and_extraction_cap_preserve_discovery(tmp_path, monkeypatch):
    extract = Mock(return_value={})
    monkeypatch.setattr("app.rag.web_research.extract_passages", extract)
    store = PublicSourceStore(tmp_path)
    assert not bootstrap(replace(PLAN, topic="Other programme"), store, WebResearchCache())
    cache = WebResearchCache()
    # Sit exactly on the request-local extract ceiling. The cap is configurable
    # (the public research envelope allows more than the old hardcoded 4), so read
    # it from the cache rather than pinning a magic number that silently stops
    # testing the cap once the default moves.
    cache.extract_calls = cache.max_extract_calls
    assert not bootstrap(PLAN, store, cache)
    extract.assert_not_called()


def test_policy_reassesses_stored_pages_without_preliminary_or_search(tmp_path, monkeypatch):
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    store = PublicSourceStore(tmp_path)
    store.put(page())
    monkeypatch.setattr("app.rag.public_source_store.load_catalog", lambda path: (SPEC,))
    checks = []
    def assess(plan, chunks, **kwargs):
        checks.append(chunks)
        return policy.EvidenceAssessment("sufficient", supported_sources=(1,),
            supported_quotes=((1, chunks[0].content),),
            parts=(PartCoverage("p1", "confirmed", (1,), complete=True),
                   PartCoverage("p2", "confirmed", (1,), complete=True)))
    monkeypatch.setattr(policy, "assess_evidence", assess)
    search = Mock(side_effect=AssertionError("No blind search for complete fresh evidence"))
    monkeypatch.setattr(policy, "research_evidence", search)
    result = policy.run_research_policy(PLAN, [], generate=Mock(), budget=CoachRequestBudget(started_at=monotonic()),
        api_key="test", web_enabled=True, max_results=4, timeout=10, source_store=store)
    assert len(checks) == 1 and checks[0]
    assert result.assessment.status == "sufficient"
    assert all(part.complete and part.support_indices == (1,) for part in result.assessment.parts)
    assert result.diagnostics["search_calls"] == result.diagnostics["extract_calls"] == 0
    search.assert_not_called()


def test_cache_failure_never_prevents_returning_fetched_windows(tmp_path, monkeypatch):
    def fetch(urls, **kw):
        kw["cache"].fetched_pages[URL] = page()
        kw["cache"].extract_calls += 1
        return {URL: page().content}
    monkeypatch.setattr("app.rag.web_research.extract_passages", fetch)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    assert bootstrap(PLAN, PublicSourceStore(blocked), WebResearchCache())


def test_model_cannot_invent_explicit_search_intent():
    import json
    from types import SimpleNamespace
    from app.rag.research_policy import interpret_question
    def generate(*args, **kwargs):
        return SimpleNamespace(content=json.dumps({"topic": "STR application", "needs_personal": False,
            "needs_external": True, "time_scope": "current", "entities": ["STR"],
            "required_facts": ["application", "documents"], "explicit_search": True}))
    plan = interpret_question("how do i apply STR, what document do i need", [], base_personal=False,
        base_external=True, generate=generate, budget=CoachRequestBudget.start())
    assert not plan.explicit_search


def test_latest_request_refreshes_known_pages_instead_of_cache(tmp_path, monkeypatch):
    store = PublicSourceStore(tmp_path)
    store.put(page())
    extract = Mock(return_value={})
    monkeypatch.setattr("app.rag.web_research.extract_passages", extract)
    p = replace(PLAN, original_question="What are the latest Example assistance application requirements?")
    assert not bootstrap(p, store, WebResearchCache())
    extract.assert_called_once()
