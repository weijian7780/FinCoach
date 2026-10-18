"""Fetch diagnostics and deliberate extraction refresh (Task 4).

These cover the two defects the plan's reverification found: per-URL failures
collapsing into one guessed cause, and an advanced extraction being served from
the basic full-page cache so no API call happened at all.
"""
import hashlib
import sys
import types
from unittest.mock import patch

import pytest

from app.rag import web_research
from app.rag.web_research import FetchDiagnostic, WebResearchCache, extract_passages


class _FakeTavily:
    """Fake Tavily SDK whose response and raise behaviour are set per test."""

    response: dict = {"results": []}
    raises: Exception | None = None
    calls: list[dict] = []

    def __init__(self, api_key):
        pass

    def extract(self, **kwargs):
        type(self).calls.append(kwargs)
        if type(self).raises is not None:
            raise type(self).raises
        return type(self).response


@pytest.fixture(autouse=True)
def no_direct_network(monkeypatch):
    """Keep every test in this module hermetic.

    ``COACH_DIRECT_FETCH_ENABLED`` defaults on, so without this the failed/clipped
    cases would really fetch the live official host. The direct-fetch path has its
    own coverage in ``test_public_fetch.py``.
    """
    from app import config
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", False)


@pytest.fixture
def tavily(monkeypatch):
    _FakeTavily.response = {"results": []}
    _FakeTavily.raises = None
    _FakeTavily.calls = []
    module = types.SimpleNamespace(TavilyClient=_FakeTavily)
    monkeypatch.setitem(sys.modules, "tavily", module)
    return _FakeTavily


def _diagnostics(cache: WebResearchCache, url: str) -> list[FetchDiagnostic]:
    return [d for d in cache.fetch_diagnostics if d.url == url]


def _tavily_row(cache: WebResearchCache, url: str) -> FetchDiagnostic:
    rows = [d for d in _diagnostics(cache, url) if d.method == "tavily_extract"]
    assert rows, "the Tavily attempt must be recorded"
    return rows[-1]


def test_mixed_results_and_failed_results_preserve_successes(tavily):
    """HTTP 200 with one success and one failure keeps the success as evidence."""
    good = "https://www.ptptn.gov.my/en/korporat/"
    bad = "https://www.ptptn.gov.my/en/missing/"
    tavily.response = {
        "results": [{"url": good, "title": "PTPTN", "raw_content": "PTPTN corporate information. " * 40}],
        "failed_results": [{"url": bad, "error": "Failed to retrieve content"}],
    }
    cache = WebResearchCache()
    passages = extract_passages([good, bad], api_key="k", query="PTPTN",
                                timeout=8, cache=cache, complete_context=True)
    assert good in passages and bad not in passages, "a successful passage was discarded"
    outcomes = {d.url: d.outcome for d in cache.fetch_diagnostics}
    assert outcomes[good] == "ok"
    assert outcomes[bad] in {"unknown", "provider_failure"}


def test_generic_provider_error_never_becomes_an_invented_target_403(tavily):
    """A generic provider error must not be reported as a target access denial.

    The plan forbids inferring a target 403 or a JavaScript-only page from
    "Failed to retrieve content"; the observed target status stays unknown.
    """
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    tavily.response = {"results": [], "failed_results": [{"url": url, "error": "Failed to retrieve content"}]}
    cache = WebResearchCache()
    extract_passages([url], api_key="k", query="ICU", timeout=8, cache=cache, complete_context=True)
    rows = _diagnostics(cache, url)
    assert rows, "every requested URL must get a diagnostic row"
    row = rows[-1]
    assert row.outcome != "access_denied", "the target's status was not observed"
    assert row.observed_status is None, "an unobserved target status must stay unknown"
    assert row.method == "tavily_extract"


def test_provider_exception_records_provider_failure_not_target_status(tavily):
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    tavily.raises = RuntimeError("connection reset")
    cache = WebResearchCache()
    extract_passages([url], api_key="k", query="ICU", timeout=8, cache=cache, complete_context=True)
    row = _tavily_row(cache, url)
    assert row.outcome == "provider_failure"
    assert row.observed_status is None
    assert cache.last_error, "the technical failure must stay visible to the caller"


def test_cache_hit_is_ok_and_does_not_claim_a_network_fetch(tavily):
    url = "https://akpk.org.my/dmp"
    cache = WebResearchCache()
    cache.full_pages[url] = "Official AKPK DMP guidance content with documents."
    extract_passages([url], api_key="k", query="documents", timeout=8,
                     cache=cache, complete_context=True)
    rows = _diagnostics(cache, url)
    assert rows and rows[-1].method == "cache" and rows[-1].outcome == "ok"
    assert cache.extract_calls == 0


def test_diagnostics_record_content_hash_and_truncation(tavily):
    """The hash describes the text kept for the URL, so a refresh is comparable."""
    url = "https://www.ptptn.gov.my/en/korporat/"
    short = "PTPTN corporate information."
    tavily.response = {"results": [{"url": url, "title": "PTPTN", "raw_content": short}]}
    cache = WebResearchCache()
    passages = extract_passages([url], api_key="k", query="PTPTN", timeout=8,
                                cache=cache, complete_context=True)
    row = _tavily_row(cache, url)
    assert row.outcome == "ok" and row.truncated is False
    assert row.content_hash == hashlib.sha256(passages[url].encode()).hexdigest()

    # A page longer than the support-quote bound is reported as clipped, and the
    # hash still describes exactly the text kept for this URL.
    long_raw = "word " * (web_research._MAX_PASSAGE_CHARS // 4)
    tavily.response = {"results": [{"url": url, "title": "PTPTN corporate", "raw_content": long_raw}]}
    cache = WebResearchCache()
    passages = extract_passages([url], api_key="k", query="PTPTN", timeout=8,
                                cache=cache, complete_context=True)
    row = _tavily_row(cache, url)
    assert row.outcome == "partial" and row.truncated is True
    assert row.content_hash == hashlib.sha256(passages[url].encode()).hexdigest()


def test_advanced_refresh_bypasses_basic_full_page_cache(tavily):
    """A deliberate escalation must reach the provider, not serve cached basics.

    Before the fix, ``extract_passages(..., extract_depth="advanced")`` returned
    the basic text already in ``cache.full_pages`` and made no API call, so the
    escalation silently did nothing while looking successful.
    """
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    cache = WebResearchCache()
    cache.full_pages[url] = "Basic excerpt that omits the documents section."
    before = len(tavily.calls)
    tavily.response = {"results": [{"url": url, "title": "ICU",
                                    "raw_content": "Advanced full content including the documents list."}]}
    passages = extract_passages([url], api_key="k", query="documents", timeout=8,
                                cache=cache, complete_context=True,
                                extract_depth="advanced", force_refresh=True)
    assert len(tavily.calls) == before + 1, "the advanced extraction never called the provider"
    assert "documents list" in passages[url], "the refreshed text was not used"
    assert tavily.calls[-1]["extract_depth"] == "advanced"


def test_force_refresh_does_not_consume_cache_hit_credit(tavily):
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    cache = WebResearchCache()
    cache.full_pages[url] = "Basic excerpt."
    tavily.response = {"results": [{"url": url, "title": "ICU", "raw_content": "Refreshed content."}]}
    extract_passages([url], api_key="k", query="q", timeout=8, cache=cache,
                     complete_context=True, force_refresh=True)
    assert cache.cache_hits == 0
    assert cache.extract_calls == 1


def test_policy_escalates_once_to_advanced_and_does_not_repeat_a_failed_mode(
        tavily, monkeypatch):
    """A missing section triggers at most one advanced refresh, never a repeat.

    This drives the real ``run_research_policy`` round loop. The basic pass returns
    nothing for the cached official page; the deliberate escalation must bypass the
    cache, reach the provider, and be capped so a mode that already failed for a
    URL is not purchased again.
    """
    from app.llm import CoachRequestBudget
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    from app.rag.retrieval import RetrievedChunk
    from app.rag.web_research import ResearchOutcome

    url = "https://akpk.org.my/dmp"
    source = RetrievedChunk(1, "AKPK DMP", "akpk.org.my", None, 0,
                            "AKPK DMP guidance.", 0.9, url=url,
                            source_type="web", tier=1, confidence="sufficient")
    partial = policy.EvidenceAssessment(
        "partial", ("required documents",), supported_sources=(1,),
        supported_quotes=((1, source.content),),
        parts=(PartCoverage("p1", "missing"),))
    plan = policy.QuestionPlan(
        topic="AKPK DMP", needs_personal=False, needs_external=True, time_scope="current",
        entities=("AKPK",), required_facts=("required documents",),
        interpreted=True, part_tracking=True, original_question="AKPK DMP documents")

    seen: list[dict] = []

    def fake_extract(urls, **kwargs):
        seen.append({"urls": list(urls), **kwargs})
        # Basic passes find nothing usable; the deliberate advanced pass also
        # fails, so the same URL must not be escalated twice.
        return {}

    monkeypatch.setattr(policy, "extract_passages", fake_extract)
    monkeypatch.setattr(policy, "assess_evidence", lambda *a, **k: partial)
    monkeypatch.setattr(policy, "research_evidence",
                        lambda *a, **k: ResearchOutcome([], True, "no_results"))

    cache_holder = {}
    real_cache_cls = policy.WebResearchCache

    def cache_factory(*args, **kwargs):
        cache = real_cache_cls(*args, **kwargs)
        cache.full_pages[url] = "Basic cached excerpt without the documents section."
        cache.max_extract_calls = 6
        cache_holder["cache"] = cache
        return cache

    monkeypatch.setattr(policy, "WebResearchCache", cache_factory)
    policy.run_research_policy(plan, [source], generate=lambda *a, **k: None,
                               budget=CoachRequestBudget.start(), api_key="k",
                               web_enabled=True, max_results=4, timeout=8)

    advanced = [call for call in seen if call.get("extract_depth") == "advanced"]
    assert advanced, "the missing section never triggered an advanced refresh"
    assert all(call.get("force_refresh") is True for call in advanced), (
        "an escalation must bypass the basic cache to reach the provider")
    assert len(advanced) <= 2, "advanced retries must stay within the request cap"
    refreshed_urls = [u for call in advanced for u in call["urls"]]
    assert refreshed_urls.count(url) <= 1, "a failed refresh was repeated for the same URL"


def test_failed_refresh_preserves_previous_verified_page(tavily):
    """A failed refresh must not destroy usable cached content."""
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    cache = WebResearchCache()
    cache.full_pages[url] = "Previously verified page content about the documents section."
    cache.fetched_pages  # touched for clarity
    tavily.response = {"results": [], "failed_results": [{"url": url, "error": "Failed to retrieve content"}]}
    passages = extract_passages([url], api_key="k", query="documents", timeout=8,
                                cache=cache, complete_context=True,
                                extract_depth="advanced", force_refresh=True)
    assert cache.full_pages[url] == "Previously verified page content about the documents section."
    # The refresh returned nothing, so the caller keeps the earlier page available
    # through the normal cache path rather than losing it.
    reused = extract_passages([url], api_key="k", query="documents", timeout=8,
                              cache=cache, complete_context=True)
    assert "Previously verified" in reused[url]
