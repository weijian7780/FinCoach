"""Private-query rewrite and wall-clock extraction regressions."""
import json
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import config, llm
from app.rag import research_policy, web_research
from app.rag.search_privacy import make_search_guard
from tests.test_category_interpretation_contract import StoredClient, USER_ID, stored_rows


def client_with_owned(kind='goal'):
    rows = stored_rows(['Food'])
    if kind == 'goal':
        rows['savings_goals'] = [{'id': 'g1', 'user_id': USER_ID, 'name': 'Private Laptop'}]
    elif kind == 'category':
        rows['categories'].append({'id': 1001, 'user_id': USER_ID, 'name': 'Private Laptop'})
    else:
        rows['transactions'].append({'id': 't1', 'user_id': USER_ID, 'source': 'Private Laptop'})
    return StoredClient(rows)


def answer(text):
    return SimpleNamespace(content=json.dumps({'search_query': text, 'general_public': True,
        'same_financial_subject': True, 'contains_personal_context': False}))


@pytest.mark.parametrize('kind', ['goal', 'category', 'merchant'])
@pytest.mark.parametrize('proposed', ['', 'my Private Laptop saving routine'])
def test_owned_query_is_rewritten_once_and_only_general_query_is_sent(kind, proposed, monkeypatch, caplog):
    generate = Mock(return_value=answer('saving habits Malaysia'))
    guard = make_search_guard(client_with_owned(kind), USER_ID, generate=generate,
                              budget=llm.CoachRequestBudget.start())
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    with caplog.at_level('INFO'):
        web_research.research_evidence('my Private Laptop saving routine Malaysia',
            web_query=proposed, web_query_guard=guard, api_key='synthetic',
            cache=web_research.WebResearchCache(), timeout=8)
    assert sent == ['saving habits Malaysia']
    assert generate.call_count == 1
    assert 'private laptop' not in generate.call_args.args[0].casefold()
    assert 'private laptop' not in caplog.text.casefold()
    assert generate.call_args.kwargs['stage_name'] == 'search_privacy_rewrite'


def test_rewrite_still_containing_owned_name_is_never_sent(monkeypatch):
    generate = Mock(return_value=answer('Private Laptop saving Malaysia'))
    guard = make_search_guard(client_with_owned(), USER_ID, generate=generate,
                              budget=llm.CoachRequestBudget.start())
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    result = web_research.research_evidence('my Private Laptop savings Malaysia',
        web_query_guard=guard, api_key='synthetic', cache=web_research.WebResearchCache(), timeout=8)
    assert generate.call_count == 1 and not sent and not result.web_ran


@pytest.mark.parametrize('bad', ['', 'saving RM3000 Malaysia', 'word ' * 13, None])
def test_invalid_rewrite_is_never_sent(monkeypatch, bad):
    generate = Mock(return_value=answer(bad))
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('Private Laptop savings Malaysia', api_key='synthetic', timeout=8,
        web_query_guard=make_search_guard(client_with_owned(), USER_ID, generate=generate,
                                         budget=llm.CoachRequestBudget.start()))
    assert generate.call_count == 1 and sent == []


def test_rewrite_self_reported_personal_context_is_never_sent(monkeypatch):
    generate = Mock(return_value=SimpleNamespace(content=json.dumps({'search_query': 'saving habits Malaysia',
        'general_public': False, 'same_financial_subject': True, 'contains_personal_context': True})))
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('Private Laptop savings Malaysia', api_key='synthetic', timeout=8,
        web_query_guard=make_search_guard(client_with_owned(), USER_ID, generate=generate,
                                         budget=llm.CoachRequestBudget.start()))
    assert generate.call_count == 1 and not sent


def test_lookup_failure_never_sends_raw_query_or_unknown_names_to_model(monkeypatch):
    generate = Mock(return_value=answer('saving habits Malaysia'))
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('my Private Laptop savings Malaysia', api_key='synthetic', timeout=8,
        web_query_guard=make_search_guard(object(), USER_ID, generate=generate,
                                         budget=llm.CoachRequestBudget.start()))
    assert not sent
    assert all('private laptop' not in str(call).casefold() for call in generate.call_args_list)


def test_clean_query_is_sent_without_rewrite(monkeypatch):
    generate = Mock(return_value=answer('unused'))
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('legacy Private Laptop goal', web_query='saving habits Malaysia',
        api_key='synthetic', timeout=8, web_query_guard=make_search_guard(
            client_with_owned(), USER_ID, generate=generate, budget=llm.CoachRequestBudget.start()))
    assert sent == ['saving habits Malaysia'] and generate.call_count == 0


def test_guard_exception_does_not_fall_back_to_raw_query(monkeypatch):
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    def broken(*args, **kwargs):
        raise RuntimeError('lookup unavailable')
    result = web_research.research_evidence('my Private Laptop savings Malaysia', api_key='synthetic',
        timeout=8, web_query_guard=broken, cache=web_research.WebResearchCache())
    assert not sent and not result.web_ran


def test_followup_gap_is_rewritten_before_actual_search(monkeypatch):
    from tests.test_search_gap_followup import SOURCE, assessment_reply, make_plan
    generate = Mock(return_value=answer('share trading account Malaysia'))
    sent = []
    def search(query, **kwargs):
        sent.append(query)
        kwargs['cache'].search_calls += 1
        return [web_research.WebResult(SOURCE.title, SOURCE.url, SOURCE.content, .9)]
    monkeypatch.setattr(config, 'COACH_PUBLIC_SOURCE_CACHE_ENABLED', False)
    monkeypatch.setattr(web_research, 'search_web', search)
    monkeypatch.setattr(web_research, 'extract_passages', lambda *a, **k: {})
    monkeypatch.setattr(research_policy, 'extract_passages', lambda *a, **k: {})
    budget = llm.CoachRequestBudget.start()
    research_policy.run_research_policy(make_plan(), [],
        generate=Mock(return_value=assessment_reply('Private Laptop CDS rules')),
        budget=budget, api_key='synthetic', web_enabled=True, max_results=4, timeout=8,
        web_query_guard=make_search_guard(client_with_owned(), USER_ID, generate=generate, budget=budget))
    assert generate.call_count >= 1 and 'share trading account Malaysia' in sent
    assert all('private laptop' not in query.casefold() for query in sent)


def test_privacy_rewrite_only_attempts_the_first_structured_provider(monkeypatch):
    from tests.test_deepseek_writer_gap import configure_roles
    configure_roles(monkeypatch)
    monkeypatch.setattr(llm, 'COACH_STRUCTURED_PROVIDER_ORDER', 'writer_first')
    calls = []
    def failed(_client, provider, _prompt, **kwargs):
        calls.append(provider.model)
        raise ConnectionError('synthetic')
    monkeypatch.setattr(llm, '_generate_with_provider', failed)
    with pytest.raises(ConnectionError):
        llm.generate_structured_result('q', budget=llm.CoachRequestBudget.start(),
            reserve_after_seconds=0, stage_name='search_privacy_rewrite', max_provider_attempts=1, max_tokens=256)
    assert calls == ['deepseek/deepseek-v4.1-flash-1017']


def test_rewrite_is_skipped_when_stage_budget_is_exhausted(monkeypatch):
    generate = Mock(return_value=answer('saving habits Malaysia'))
    budget = llm.CoachRequestBudget.start().for_stage(max_seconds=0)
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('Private Laptop savings Malaysia', api_key='synthetic', timeout=8,
        web_query_guard=make_search_guard(client_with_owned(), USER_ID, generate=generate, budget=budget))
    assert not sent and generate.call_count == 0


def test_slow_url_cannot_block_other_tavily_passages(monkeypatch):
    good = 'https://example.com/quick'
    slow = 'https://example.com/stalled'
    release = threading.Event()
    class Client:
        def __init__(self, **kwargs):
            pass
        def extract(self, **kwargs):
            urls = kwargs['urls']
            if slow in urls:
                release.wait(3)
            return {'results': [{'url': u, 'raw_content': 'genuine passage'} for u in urls],
                    'failed_results': [], 'usage': {'credits': 1}}
    monkeypatch.setitem(sys.modules, 'tavily', SimpleNamespace(TavilyClient=Client))
    monkeypatch.setattr(config, 'COACH_DIRECT_FETCH_ENABLED', False)
    cache = web_research.WebResearchCache()
    start = time.monotonic()
    try:
        passages = web_research.extract_passages([good, slow], api_key='synthetic', timeout=1.25,
                                                 cache=cache, complete_context=True)
        elapsed = time.monotonic() - start
        assert elapsed < 1.8 and good in passages and slow not in passages
        events = {event['url']: event for event in cache.extraction_events}
        assert events[slow]['error_type'] == 'deadline' and events[good]['success']
        assert all(isinstance(event['elapsed_ms'], (int, float)) for event in events.values())
    finally:
        release.set()


def test_direct_fetch_keeps_fast_url_and_records_stalled_url_deadline(monkeypatch):
    good = 'https://www.bursamalaysia.com/quick'
    slow = 'https://www.bursamalaysia.com/stalled'
    release = threading.Event()
    completed = threading.Event()
    def fetch(url, *, timeout):
        if url == slow:
            release.wait(3)
            completed.set()
        return 'genuine public passage' * 30
    monkeypatch.setattr(config, 'COACH_DIRECT_FETCH_ENABLED', True)
    monkeypatch.setattr('app.rag.public_fetch.fetch_official_page', fetch)
    cache = web_research.WebResearchCache()
    pages = {}
    start = time.monotonic()
    try:
        web_research._direct_fetch_fallback([good, slow], pages, cache=cache, remaining=1.6)
        assert time.monotonic() - start < 2.2 and good in pages and slow not in pages
        events = {event['url']: event for event in cache.extraction_events}
        assert events[good]['success'] and events[slow]['error_type'] == 'deadline'
        assert all(isinstance(event['elapsed_ms'], (int, float)) for event in events.values())
        saved_events = list(cache.extraction_events)
        release.set()
        assert completed.wait(1)
        assert slow not in pages and cache.extraction_events == saved_events
    finally:
        release.set()
