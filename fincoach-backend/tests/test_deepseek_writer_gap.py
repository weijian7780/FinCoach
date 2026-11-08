"""Staged regressions for separated model roles and duplicate discovery."""
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import llm
from app import config
from app.rag import research_policy, verifier, web_research
from app.rag.grounding import GroundingClaim
from tests.test_search_gap_followup import GAP, SOURCE, assessment_reply, make_plan, run_gap


def configure_roles(monkeypatch):
    monkeypatch.setattr(llm, 'LLM_PRIMARY_BASE_URL', 'https://openrouter.ai/api/v1')
    monkeypatch.setattr(llm, 'LLM_PRIMARY_API_KEY', 'synthetic-primary')
    monkeypatch.setattr(llm, 'LLM_PRIMARY_MODEL', 'nvidia/nemotron-3.5-super-vl:free')
    monkeypatch.setattr(llm, 'LLM_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
    monkeypatch.setattr(llm, 'LLM_API_KEY', 'synthetic-gemini')
    monkeypatch.setattr(llm, 'LLM_MODEL', 'gemini-3.5-flash-lite')
    monkeypatch.setattr(llm, 'COACH_WRITER_FALLBACK_BASE_URL', 'https://openrouter.ai/api/v1')
    monkeypatch.setattr(llm, 'COACH_WRITER_FALLBACK_API_KEY_ENV', 'SYNTHETIC_WRITER_KEY')
    monkeypatch.setattr(llm, 'COACH_WRITER_FALLBACK_MODEL', 'deepseek/deepseek-v4.1-flash-1017')
    monkeypatch.setenv('SYNTHETIC_WRITER_KEY', 'synthetic-writer')
    monkeypatch.setattr(llm, 'COACH_STRUCTURED_PROVIDER_ORDER', 'fallback_first')
    monkeypatch.setattr(llm, 'COACH_WRITER_PROVIDER_ORDER', 'fallback_first', raising=False)
    monkeypatch.setattr(llm, 'COACH_PRIMARY_REASONING', 'off', raising=False)


def test_writer_order_does_not_change_structured_provider_order(monkeypatch):
    configure_roles(monkeypatch)
    assert [p.model for p in llm._writing_providers()] == [
        'deepseek/deepseek-v4.1-flash-1017', 'nvidia/nemotron-3.5-super-vl:free']
    assert [p.model for p in llm._structured_providers()] == [
        'gemini-3.5-flash-lite', 'nvidia/nemotron-3.5-super-vl:free']


def test_writer_requests_and_backup_have_required_wire_policy(monkeypatch):
    configure_roles(monkeypatch)
    deepseek, nemotron = llm._writing_providers()
    captured = []
    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'), finish_reason='stop')],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    factory = lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm._generate_with_provider(factory, deepseek, 'test', reasoning_effort='high', timeout_seconds=5)
    assert captured[0]['model'] == 'deepseek/deepseek-v4.1-flash-1017'
    assert captured[0]['extra_body']['reasoning'] == {'enabled': False}
    assert captured[0]['extra_body']['provider'] == {'data_collection': 'deny', 'require_parameters': True}
    llm._generate_with_provider(factory, deepseek, 'test', reasoning_effort='low', timeout_seconds=5, structured=True)
    assert captured[1]['extra_body']['reasoning'] == {'enabled': False}
    assert captured[1]['extra_body']['provider']['data_collection'] == 'deny'
    assert llm._provider_request_policy(deepseek, tool_request=True).extra_body['provider']['data_collection'] == 'deny'
    llm._generate_with_provider(factory, nemotron, 'test', reasoning_effort='high', timeout_seconds=5)
    assert captured[2]['extra_body']['reasoning'] == {'enabled': False}


def test_unset_writer_order_retains_previous_provider_order(monkeypatch):
    configure_roles(monkeypatch)
    monkeypatch.setattr(llm, 'COACH_WRITER_PROVIDER_ORDER', 'primary_first')
    assert [p.model for p in llm._writing_providers()] == [
        'nvidia/nemotron-3.5-super-vl:free', 'deepseek/deepseek-v4.1-flash-1017']


def test_first_draft_correction_and_failover_use_the_requested_order(monkeypatch):
    configure_roles(monkeypatch)
    seen = []
    def generate(_factory, provider, *args, **kwargs):
        seen.append(provider.model)
        if len(seen) == 3:
            raise ConnectionError('synthetic failure')
        return SimpleNamespace(content='ok')
    monkeypatch.setattr(llm, '_generate_with_provider', generate)
    llm.generate_result('first draft')
    llm.generate_fallback_result('correction')
    llm.generate_result('failover')
    assert seen == ['deepseek/deepseek-v4.1-flash-1017', 'deepseek/deepseek-v4.1-flash-1017',
                    'deepseek/deepseek-v4.1-flash-1017', 'nvidia/nemotron-3.5-super-vl:free']


def test_separate_checker_override_uses_env_name_and_existing_deepseek_backup(monkeypatch):
    configure_roles(monkeypatch)
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_BASE_URL', 'https://openrouter.ai/api/v1', raising=False)
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_API_KEY_ENV', 'SYNTHETIC_CHECKER_KEY', raising=False)
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_MODEL', 'nvidia/nemotron-3.5-super-vl:free', raising=False)
    monkeypatch.setenv('SYNTHETIC_CHECKER_KEY', 'synthetic-checker')
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_MODEL', 'unrelated-writer-model')
    url, key, model, extra = verifier._verifier_settings()
    assert (url, key, model) == ('https://openrouter.ai/api/v1', 'synthetic-checker', 'nvidia/nemotron-3.5-super-vl:free')
    assert extra == {'extra_body': {'reasoning': {'enabled': False}}}
    fallback = verifier._verifier_settings(fallback=True)
    assert fallback[2] == 'deepseek/deepseek-v4.1-flash-1017'
    assert fallback[3]['extra_body']['provider']['data_collection'] == 'deny'


def test_unset_checker_override_keeps_existing_primary_behavior(monkeypatch):
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_MODEL', '', raising=False)
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_BASE_URL', 'https://gemini.example/')
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_API_KEY', 'synthetic-primary')
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_MODEL', 'old-primary')
    assert verifier._verifier_settings() == ('https://gemini.example/', 'synthetic-primary', 'old-primary', {})


def test_checker_retries_and_then_uses_deepseek_backup(monkeypatch):
    configure_roles(monkeypatch)
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_BASE_URL', 'https://openrouter.ai/api/v1', raising=False)
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_API_KEY_ENV', 'SYNTHETIC_CHECKER_KEY', raising=False)
    monkeypatch.setattr(verifier, 'COACH_VERIFIER_MODEL', 'nvidia/nemotron-3.5-super-vl:free', raising=False)
    monkeypatch.setenv('SYNTHETIC_CHECKER_KEY', 'synthetic-checker')
    seen = []
    def once(*args, **kwargs):
        seen.append(kwargs['_fallback'])
        if len(seen) < 3:
            return verifier.GroundingVerification({}, error_code='verifier_invalid_json')
        return verifier.GroundingVerification({1: 'supported'}, model=verifier._verifier_settings(fallback=True)[2])
    monkeypatch.setattr(verifier, '_verify_grounding_claims_once', once)
    result = verifier.verify_grounding_claims([GroundingClaim(1, 'A fact.', (1,))], ['A fact.'],
        timeout_seconds=20, research_context=verifier.ResearchVerificationContext('q', 'd', ()))
    assert seen == [False, False, True]
    assert result.model == 'deepseek/deepseek-v4.1-flash-1017'


def test_gap_scope_does_not_append_existing_country_or_period():
    plan = replace(make_plan(), period='2026')
    sent = run_gap('CDS account requirements in malaysia during 2026', plan)
    assert len(sent) >= 2
    assert sent[1].casefold().count('malaysia') == 1
    assert sent[1].count('2026') == 1


def test_normalized_duplicate_is_skipped_after_privacy_guard(monkeypatch):
    client = MagicMock()
    client.search.return_value = {'results': [{'title': 'Bursa', 'url': SOURCE.url,
                                                'content': SOURCE.content, 'score': .9}]}
    cache = web_research.WebResearchCache()
    with (patch.dict(sys.modules, {'tavily': SimpleNamespace(TavilyClient=lambda **kw: client)}),
          patch.object(web_research, 'extract_passages', return_value={})):
        for phrase, mode in [('CDS  ACCOUNT Malaysia', 'institution'), ('cds account malaysia', 'broader')]:
            web_research.research_evidence('legacy Malaysia', api_key='test', cache=cache, timeout=4,
                public_policy=True, single_search=True, discovery_mode=mode,
                web_query=phrase, web_query_guard=lambda proposed, legacy: proposed)
    assert client.search.call_count == 1
    assert len(cache.skipped_searches) == 1
    assert cache.skipped_searches[0]['reason'] == 'duplicate_search'


def test_duplicate_privacy_fallback_is_not_sent_twice(monkeypatch):
    client = MagicMock()
    client.search.return_value = {'results': [{'title': 'Bursa', 'url': SOURCE.url,
                                                'content': SOURCE.content, 'score': .9}]}
    cache = web_research.WebResearchCache()
    with (patch.dict(sys.modules, {'tavily': SimpleNamespace(TavilyClient=lambda **kw: client)}),
          patch.object(web_research, 'extract_passages', return_value={})):
        for phrase, mode in [('legacy Malaysia', 'institution'), ('unsafe proposed', 'broader')]:
            web_research.research_evidence('legacy Malaysia', api_key='test', cache=cache, timeout=4,
                public_policy=True, single_search=True, discovery_mode=mode,
                web_query=phrase, web_query_guard=lambda proposed, legacy: legacy)
    assert client.search.call_count == 1
    assert len(cache.skipped_searches) == 1


def test_duplicate_is_recorded_in_policy_diagnostics(monkeypatch):
    client = MagicMock()
    client.search.return_value = {'results': [{'title': 'Bursa', 'url': SOURCE.url,
                                                'content': SOURCE.content, 'score': .9}]}
    plan = replace(make_plan(), search_query='CDS account requirements',
                   part_search_queries=('CDS account requirements',))
    with (patch.dict(sys.modules, {'tavily': SimpleNamespace(TavilyClient=lambda **kw: client)}),
          patch.object(config, 'COACH_PUBLIC_SOURCE_CACHE_ENABLED', False),
          patch.object(web_research, 'extract_passages', return_value={}),
          patch.object(research_policy, 'extract_passages', return_value={})):
        decision = research_policy.run_research_policy(plan, [],
            generate=MagicMock(return_value=assessment_reply('CDS account requirements')),
            budget=llm.CoachRequestBudget.start(), api_key='test', web_enabled=True, max_results=4, timeout=4,
            web_query_guard=lambda proposed, legacy: proposed or legacy)
    assert client.search.call_count == 1
    assert decision.diagnostics['skipped_searches']
    assert all(set(x) == {'reason', 'query_hash'} for x in decision.diagnostics['skipped_searches'])


def test_duplicate_is_skipped_even_between_search_modes():
    client = MagicMock()
    client.search.return_value = {'results': [{'title': 'Bursa', 'url': SOURCE.url,
                                                'content': SOURCE.content, 'score': .9}]}
    cache = web_research.WebResearchCache()
    with patch.dict(sys.modules, {'tavily': SimpleNamespace(TavilyClient=lambda **kw: client)}):
        web_research.search_web('CDS account Malaysia', api_key='test', cache=cache)
    assert client.search.call_count == 1
    assert len(cache.skipped_searches) == 1


def test_skipped_empty_duplicate_is_not_a_new_web_attempt():
    client = MagicMock()
    client.search.return_value = {'results': []}
    cache = web_research.WebResearchCache()
    with patch.dict(sys.modules, {'tavily': SimpleNamespace(TavilyClient=lambda **kw: client)}):
        first = web_research.research_evidence('CDS Malaysia', api_key='test', cache=cache,
                                               single_search=True, public_policy=True)
        second = web_research.research_evidence('CDS Malaysia', api_key='test', cache=cache,
                                                single_search=True, public_policy=True)
    assert first.web_ran and not second.web_ran
    assert second.reason == 'duplicate_search'
    assert client.search.call_count == 1


def test_nonduplicate_search_failure_keeps_prior_web_attempt_semantics():
    cache = web_research.WebResearchCache()
    with patch.object(web_research, 'search_web', return_value=[]):
        outcome = web_research.research_evidence('CDS Malaysia', api_key='test', cache=cache)
    assert outcome.web_ran and outcome.reason == 'no_results'


_HARNESS = Path(__file__).parents[1] / 'experiment' / 'guard.py'
# The trial spending guard lives with a staged experiment, not in the app.
_requires_harness = pytest.mark.skipif(not _HARNESS.exists(),
                                       reason='trial harness (experiment/guard.py) is not in this checkout')


@_requires_harness
def test_openrouter_guard_settles_reported_cost_not_max_price(tmp_path):
    path = Path(__file__).parents[1] / 'experiment' / 'guard.py'
    spec = importlib.util.spec_from_file_location('deepseek_gap_guard', path)
    guard_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard_mod)
    guard = guard_mod.Guard(tmp_path / 'ledger.json', {})
    ident = guard.reserve('openrouter', '.10', input_bound=100, output_bound=100,
                          input_price='.001', output_price='.002', request_price='0', model='deepseek/test')
    guard._settle_model(ident, {'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'cost': .005}})
    assert guard.state['settled']['openrouter'] == '0.005'


@_requires_harness
def test_openrouter_guard_falls_back_to_max_pricing_without_reported_cost(tmp_path):
    path = Path(__file__).parents[1] / 'experiment' / 'guard.py'
    spec = importlib.util.spec_from_file_location('deepseek_gap_guard_no_cost', path)
    guard_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard_mod)
    guard = guard_mod.Guard(tmp_path / 'ledger.json', {})
    ident = guard.reserve('openrouter', '.10', input_bound=100, output_bound=100,
                          input_price='.001', output_price='.002', request_price='0', model='deepseek/test')
    guard._settle_model(ident, {'usage': {'prompt_tokens': 10, 'completion_tokens': 10}})
    assert guard.state['settled']['openrouter'] == '0.030'


@_requires_harness
def test_guard_uses_reported_cost_without_token_counts_and_keeps_malformed_reservations(tmp_path):
    spec = importlib.util.spec_from_file_location('deepseek_gap_guard_usage', Path(__file__).parents[1] / 'experiment' / 'guard.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    guard = mod.Guard(tmp_path / 'ledger.json', {})
    def reserve():
        return guard.reserve('openrouter', '.10', input_bound=100, output_bound=100,
                             input_price='.001', output_price='.002', request_price='0', model='deepseek/test')
    first = reserve()
    guard._settle_model(first, {'usage': {'cost': '.004'}})
    assert guard.state['settled']['openrouter'] == '0.004'
    second = reserve()
    guard._settle_model(second, {'usage': {'cost': 'invalid'}})
    assert second in guard.state['outstanding']
