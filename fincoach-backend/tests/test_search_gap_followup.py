"""Real research-policy regressions for evidence-directed follow-up searches."""
import json
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import config
from app.llm import CoachRequestBudget
from app.rag import research_policy as policy
from app.rag.research_policy import QuestionPlan
from app.rag.retrieval import RetrievedChunk
from app.rag.search_privacy import SKIP_UNSAFE_SEARCH, make_search_guard
from app.rag.web_research import ResearchOutcome
from app.rag import web_research
from tests.test_category_interpretation_contract import StoredClient, USER_ID, stored_rows

GAP = "CDS account opening requirements with Bursa Malaysia"
SOURCE = RetrievedChunk(-1, "Bursa CDS", "bursamalaysia.com", None, 0,
    "A CDS account is opened through an authorised depositor.", .9,
    url="https://www.bursamalaysia.com/cds", source_type="web", tier=1, confidence="established")


def make_plan():
    return QuestionPlan("share trading account", False, True, "stable", part_tracking=True,
        required_facts=("how to open a share trading account",), part_domains=("finance",),
        part_entities=((),), part_ids=("p1",), search_query="open share trading account Malaysia",
        part_search_queries=("open share trading account Malaysia",))


def assessment_reply(gap):
    return SimpleNamespace(content=json.dumps({"status": "partial", "missing": [gap] if gap else [],
        "conflicting": False, "jurisdiction_matches": True, "period_matches": True,
        "support": [{"source_id": 1, "quote": SOURCE.content}],
        "coverage": [{"part_id": "p1", "status": "reported", "support_indices": [1],
                      "resolution": "direct", "complete": False, "evidence_requirement": "explanatory"}]}))


def run_gap(gap, plan=None):
    sent = []
    rows = stored_rows(["Food"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Private Laptop"}]
    guard = make_search_guard(StoredClient(rows), USER_ID)

    def search(query, **kwargs):
        proposed = kwargs.get("web_query") or ""
        selected = kwargs["web_query_guard"](proposed, query)
        if selected is SKIP_UNSAFE_SEARCH:
            return ResearchOutcome([], False, "privacy_skip_owned_name")
        sent.append(selected)
        kwargs["cache"].search_calls += 1
        return ResearchOutcome([SOURCE], True, "ok")

    with (patch.object(config, "COACH_PUBLIC_SOURCE_CACHE_ENABLED", False),
          patch.object(policy, "research_evidence", side_effect=search),
          patch.object(policy, "extract_passages", return_value={})):  # no real network
        policy.run_research_policy(plan or make_plan(), [], generate=MagicMock(return_value=assessment_reply(gap)),
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4,
            timeout=4, web_query_guard=guard)
    return sent


def test_second_actual_search_uses_checker_missing_fact():
    sent = run_gap(GAP)
    assert len(sent) >= 2
    assert sent[0] == "open share trading account Malaysia"
    assert sent[1] != sent[0]
    assert GAP in sent[1]


def test_followup_gap_includes_jurisdiction_and_public_period():
    sent = run_gap(GAP, replace(make_plan(), period='2026'))
    assert len(sent) >= 2
    assert GAP in sent[1] and 'Malaysia' in sent[1] and '2026' in sent[1]


def test_followup_retains_scope_when_gap_hits_existing_signoff_scrubber():
    sent = run_gap('account opening best verification', replace(make_plan(), period='2026'))
    assert len(sent) >= 2
    assert 'account opening' in sent[1]
    assert 'Malaysia' in sent[1] and '2026' in sent[1]


def test_missing_fact_containing_owned_name_is_not_sent():
    sent = run_gap("Private Laptop CDS rules")
    assert sent
    assert all("private laptop" not in query.casefold() for query in sent)


def test_checker_gap_survives_part_coverage_mapping():
    plan = make_plan()
    result = policy.assess_evidence(plan, [SOURCE], generate=MagicMock(return_value=assessment_reply(GAP)))
    assert result.missing == ("how to open a share trading account",)
    assert result.search_missing == (GAP,)


def test_checker_is_asked_for_english_gaps_and_exact_source_quotes():
    generate = MagicMock(return_value=assessment_reply(GAP))
    policy.assess_evidence(make_plan(), [SOURCE], generate=generate)
    prompt = generate.call_args.args[0]
    assert 'Write each missing fact in English' in prompt
    assert 'Copy each quote exactly from the supplied text' in prompt


def test_empty_checker_missing_preserves_previous_stage_search_wording():
    sent = run_gap("")
    # The starting stage made these same three searches with this fixture.
    assert sent == ["open share trading account Malaysia"] * 3


def test_each_new_part_gets_its_own_first_phrase_then_its_gap():
    plan = replace(make_plan(), required_facts=('opening account', 'account fees'),
        part_domains=('finance', 'finance'), part_entities=((), ()), part_ids=('p1', 'p2'),
        part_search_queries=('open share trading account', 'share trading account fees'))
    sent = []
    def search(query, **kwargs):
        sent.append(kwargs.get('web_query') or query)
        kwargs['cache'].search_calls += 1
        return ResearchOutcome([SOURCE], True, 'ok')
    with (patch.object(config, 'COACH_PUBLIC_SOURCE_CACHE_ENABLED', False),
          patch.object(policy, 'research_evidence', side_effect=search),
          patch.object(policy, 'extract_passages', return_value={}),
          patch.object(policy, 'select_unresolved_part', side_effect=['p1', 'p2', 'p1', 'p1'])):
        policy.run_research_policy(plan, [], generate=MagicMock(return_value=assessment_reply(GAP)),
            budget=CoachRequestBudget.start(), api_key='test', web_enabled=True, max_results=4, timeout=4,
            web_query_guard=lambda proposed, legacy: proposed or legacy)
    assert sent[0] == 'open share trading account Malaysia'
    assert sent[1] == 'share trading account fees Malaysia'
    assert len(sent) >= 3 and GAP in sent[2]


def test_extraction_diagnostics_record_each_url_without_page_or_error_text():
    good = "https://www.bursamalaysia.com/good"
    failed = "https://www.bursamalaysia.com/fail"
    client = MagicMock()
    client.extract.return_value = {"results": [{"url": good, "raw_content": "private page text"}],
        "failed_results": [{"url": failed, "error": "HTTP 403 arbitrary provider text"}],
        "usage": {"credits": 1}}
    cache = web_research.WebResearchCache()
    with (patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **kwargs: client)}),
          patch.object(config, "COACH_DIRECT_FETCH_ENABLED", False)):
        passages = web_research.extract_passages([good, failed], api_key="test", cache=cache,
                                                  complete_context=True)
    assert good in passages and failed not in passages
    assert [{k: v for k, v in event.items() if k != 'elapsed_ms'} for event in cache.extraction_events] == [
        {"url": good, "method": "tavily", "attempted": True, "success": True, "error_type": None},
         {"url": failed, "method": "tavily", "attempted": True, "success": False, "error_type": "http_403"}]
    assert all(isinstance(event['elapsed_ms'], (int, float)) for event in cache.extraction_events)
    recorded = json.dumps(cache.extraction_events)
    assert "private page text" not in recorded and "arbitrary provider text" not in recorded


def test_extraction_exception_records_type_for_each_requested_url():
    urls = ["https://www.bursamalaysia.com/a", "https://www.bursamalaysia.com/b"]
    client = MagicMock()
    client.extract.side_effect = TimeoutError("untrusted details")
    cache = web_research.WebResearchCache()
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **kwargs: client)}):
        assert web_research.extract_passages(urls, api_key="test", cache=cache) == {}
    assert [event["url"] for event in cache.extraction_events] == urls
    assert all(event["error_type"] == "TimeoutError" and not event["success"] for event in cache.extraction_events)
    assert "untrusted details" not in json.dumps(cache.extraction_events)


def test_arbitrary_provider_error_identifier_is_not_written_to_diagnostics():
    assert web_research._provider_extract_error("untrustedOpaqueValue") == "provider_reported_failure"
    assert web_research._provider_extract_error("request timed out") == "timeout"


def test_direct_fetch_failure_is_recorded_without_guessing_its_cause():
    url = 'https://www.bursamalaysia.com/fail'
    cache = web_research.WebResearchCache()
    with (patch.object(config, 'COACH_DIRECT_FETCH_ENABLED', True),
          patch('app.rag.public_fetch.fetch_official_page', return_value=None)):
        web_research._direct_fetch_fallback([url], {}, cache=cache, remaining=5)
    assert [{k: v for k, v in event.items() if k != 'elapsed_ms'} for event in cache.extraction_events] == [
        {'url': url, 'method': 'direct', 'attempted': True,
         'success': False, 'error_type': 'unavailable_or_rejected'}]
    assert isinstance(cache.extraction_events[0]['elapsed_ms'], (int, float))


def test_policy_decision_includes_extraction_diagnostics():
    def search(query, **kwargs):
        cache = kwargs['cache']
        cache.search_calls += 1
        cache.extraction_events.append({'url': SOURCE.url, 'method': 'tavily', 'attempted': True,
                                        'success': False, 'error_type': 'http_403'})
        return ResearchOutcome([SOURCE], True, 'ok')
    with (patch.object(config, 'COACH_PUBLIC_SOURCE_CACHE_ENABLED', False),
          patch.object(policy, 'research_evidence', side_effect=search),
          patch.object(policy, 'extract_passages', return_value={})):
        decision = policy.run_research_policy(make_plan(), [], generate=MagicMock(return_value=assessment_reply(GAP)),
            budget=CoachRequestBudget.start(), api_key='test', web_enabled=True, max_results=4, timeout=4)
    assert decision.diagnostics['extractions']
    assert decision.diagnostics['extractions'][0]['url'] == SOURCE.url
    assert decision.diagnostics['extractions'][0]['error_type'] == 'http_403'
