"""Coach-only model selection, privacy skips and draft-bound product verdicts."""
import io
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app import config, llm
from app.rag import research_policy, service, verifier, web_research
from app.rag.search_privacy import make_search_guard
from tests.test_category_interpretation_contract import StoredClient, USER_ID, stored_rows
from tests.test_deepseek_writer_gap import configure_roles
from tests.test_search_gap_followup import SOURCE, assessment_reply, make_plan
from test_product_policy import _check, _context, _draft, _reply, _verified, OTHER, STEERING


def roles(monkeypatch):
    configure_roles(monkeypatch)
    monkeypatch.setattr(llm, 'COACH_STRUCTURED_PROVIDER_ORDER', 'writer_first')


def test_all_coach_structured_stages_use_deepseek_then_nemotron_without_gemini(monkeypatch):
    roles(monkeypatch)
    assert [p.model for p in llm._structured_providers()] == [
        'deepseek/deepseek-v4.1-flash-1017', 'nvidia/nemotron-3.5-super-vl:free']
    seen = []
    def attempt(_client, provider, _prompt, **kwargs):
        seen.append((provider.model, kwargs['stage_name']))
        if provider.role == 'writer_fallback':
            raise ConnectionError('synthetic outage')
        return llm.LLMResult('{}', provider.model)
    monkeypatch.setattr(llm, '_generate_with_provider', attempt)
    assert llm.generate_structured_result('q').model == 'nvidia/nemotron-3.5-super-vl:free'
    assert llm.generate_validated_interpretation('q', response_schema={}, validate=lambda text: text,
        budget=llm.CoachRequestBudget.start()) == '{}'
    assert [model for model, _ in seen] == [
        'deepseek/deepseek-v4.1-flash-1017', 'nvidia/nemotron-3.5-super-vl:free'] * 2
    assert {stage for _, stage in seen} == {'evidence_assessment', 'request_interpretation'}


def test_receipt_vision_still_uses_its_gemini_model(monkeypatch):
    roles(monkeypatch)
    monkeypatch.setattr(config, 'GEMINI_API_KEY', 'synthetic-receipt-only')
    monkeypatch.setattr(config, 'GEMINI_RECEIPT_MODEL', 'gemini-receipt-test')
    from app.receipt_vision import verify_receipt_image
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, format='PNG')
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason='STOP')],
        text=json.dumps({'decisions': [], 'missingLines': []}), usage_metadata=None)
    with patch('google.genai.Client') as factory:
        factory.return_value.__enter__.return_value = client
        verify_receipt_image(image.getvalue(), [])
    assert client.models.generate_content.call_args.kwargs['model'] == 'gemini-receipt-test'
    assert [p.model for p in llm._structured_providers()][0].startswith('deepseek/')


def test_both_structured_providers_down_reaches_existing_rule_router(monkeypatch):
    from test_semantic_first_order import _send
    roles(monkeypatch)
    seen = []
    def unavailable(_client, provider, _prompt, **kwargs):
        seen.append(provider.model)
        raise ConnectionError('synthetic outage')
    monkeypatch.setattr(llm, '_generate_with_provider', unavailable)
    monkeypatch.setattr(service, 'COACH_LLM_INTERPRETATION_ENABLED', True)
    message, _ = _send('what about that one thing')
    assert seen == ['deepseek/deepseek-v4.1-flash-1017', 'nvidia/nemotron-3.5-super-vl:free']
    assert message['model'] == 'fincoach-interpretation-policy'


@pytest.mark.parametrize(('goal', 'language'), [('advise', 'ms'), ('plan', 'ms-MY'), ('advise', 'en')])
def test_records_advice_and_plan_forward_validated_reply_language(monkeypatch, goal, language):
    prompts = []
    monkeypatch.setattr(service, '_format_fast_verified_read', lambda *a: 'verified facts')
    monkeypatch.setattr(service, 'generate_result', lambda prompt, **kwargs: (
        prompts.append(prompt) or SimpleNamespace(content='A neutral observation.', model='synthetic',
                                                   finish_reason='stop')))
    result, mode, origin, _ = service._records_answer(
        goal=goal, tool_name='get_savings_goals', tool_result={'status': 'ok'},
        question='question', prompt='base prompt', language=language, check_paragraph=False,
        reasoning_effort='low', budget=llm.CoachRequestBudget.start())
    assert prompts and f'Language: {language}.' in prompts[0]
    assert mode == 'two_phase_advice' and origin == 'mixed'
    assert result.content.startswith('verified facts')


def test_records_rule_router_advice_remains_unchanged_when_language_unknown(monkeypatch):
    prompts = []
    monkeypatch.setattr(service, '_format_fast_verified_read', lambda *a: 'verified facts')
    monkeypatch.setattr(service, 'generate_result', lambda prompt, **kwargs: (
        prompts.append(prompt) or SimpleNamespace(content='A neutral observation.', model='synthetic',
                                                   finish_reason='stop')))
    service._records_answer(goal='advise', tool_name='get_savings_goals', tool_result={'status': 'ok'},
        question='question', prompt='base prompt', language=None, check_paragraph=False,
        reasoning_effort='low', budget=llm.CoachRequestBudget.start())
    assert 'Language:' not in prompts[0]


def test_accepted_interpreter_language_reaches_records_advice_writer(monkeypatch):
    from test_semantic_reads import _interpreted, _send
    prompts = []
    _interpreted(monkeypatch, {'route': 'personal_finance', 'goal': 'advise',
        'response_language': 'ms', 'requested_output': 'advice', 'read': {
            'operation': 'get_spending_summary', 'category': {'decision': 'none'},
            'period': {'kind': 'month', 'month': '2026-09'}}})
    monkeypatch.setattr(service, 'COACH_RESEARCH_POLICY_ENABLED', False)
    monkeypatch.setattr(service, 'COACH_WRITE_ACTIONS_ENABLED', False)
    monkeypatch.setattr(service, 'generate_result', lambda prompt, **kwargs: (
        prompts.append(prompt) or SimpleNamespace(content='A neutral observation.', model='synthetic',
                                                   finish_reason='stop')))
    message = _send('Bagaimanakah saya boleh mengurus perbelanjaan saya?')
    assert message['content'] and any('Language: ms.' in prompt for prompt in prompts)


@pytest.mark.parametrize('owned_kind', ['goal', 'category', 'merchant'])
@pytest.mark.parametrize('proposed_present', [True, False])
def test_unsafe_legacy_query_is_not_sent_even_when_no_proposal(owned_kind, proposed_present, monkeypatch, caplog):
    rows = stored_rows(['Food'])
    if owned_kind == 'goal':
        rows['savings_goals'] = [{'id': 'g1', 'user_id': USER_ID, 'name': 'Private Laptop'}]
    elif owned_kind == 'category':
        rows['categories'].append({'id': 1001, 'user_id': USER_ID, 'name': 'Private Laptop'})
    else:
        rows['transactions'].append({'id': 't1', 'user_id': USER_ID, 'source': 'Private Laptop'})
    guard = make_search_guard(StoredClient(rows), USER_ID)
    cache = web_research.WebResearchCache()
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    with caplog.at_level('INFO', logger='app.rag.search_privacy'):
        result = web_research.research_evidence('my Private Laptop savings goal Malaysia',
            web_query='Private Laptop savings practices' if proposed_present else '',
            web_query_guard=guard, api_key='synthetic', cache=cache, timeout=3)
    assert sent == [] and not result.web_ran and result.reason == 'privacy_skip_owned_name'
    assert cache.privacy_skips == [{'privacy_guard_skip': True}]
    assert 'private laptop' not in caplog.text.casefold()


def test_blocked_proposal_is_generalized_instead_of_using_clean_legacy(monkeypatch):
    rows = stored_rows(['Food'])
    rows['savings_goals'] = [{'id': 'g1', 'user_id': USER_ID, 'name': 'Private Laptop'}]
    rewritten = {'search_query': 'saving habits Malaysia', 'general_public': True,
                 'same_financial_subject': True, 'contains_personal_context': False}
    generate = MagicMock(return_value=SimpleNamespace(content=json.dumps(rewritten)))
    guard = make_search_guard(StoredClient(rows), USER_ID, generate=generate, budget=llm.CoachRequestBudget.start())
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('saving practices Malaysia', web_query='Private Laptop savings',
        web_query_guard=guard, api_key='synthetic', cache=web_research.WebResearchCache(), timeout=8)
    assert sent == ['saving habits Malaysia'] and generate.call_count == 1


def test_clean_proposal_can_be_sent_when_legacy_contains_an_owned_name(monkeypatch):
    rows = stored_rows(['Food'])
    rows['savings_goals'] = [{'id': 'g1', 'user_id': USER_ID, 'name': 'Private Laptop'}]
    sent = []
    monkeypatch.setattr(web_research, 'search_web', lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence('my Private Laptop goal Malaysia', web_query='saving habits Malaysia',
        web_query_guard=make_search_guard(StoredClient(rows), USER_ID), api_key='synthetic', timeout=3)
    assert sent == ['saving habits Malaysia']


def test_followup_gap_skips_unsafe_legacy_and_records_boolean_only(monkeypatch):
    rows = stored_rows(['Food'])
    rows['savings_goals'] = [{'id': 'g1', 'user_id': USER_ID, 'name': 'Private Laptop'}]
    plan = replace(make_plan(), topic='Private Laptop savings goal',
        required_facts=('Private Laptop saving practice',), search_query='general saving methods',
        part_search_queries=('general saving methods',))
    sent = []
    def search(query, **kwargs):
        sent.append(query)
        kwargs['cache'].search_calls += 1
        return [web_research.WebResult(SOURCE.title, SOURCE.url, SOURCE.content, .9)]
    monkeypatch.setattr(config, 'COACH_PUBLIC_SOURCE_CACHE_ENABLED', False)
    monkeypatch.setattr(web_research, 'search_web', search)
    monkeypatch.setattr(web_research, 'extract_passages', lambda *a, **k: {})
    monkeypatch.setattr(research_policy, 'extract_passages', lambda *a, **k: {})
    decision = research_policy.run_research_policy(plan, [],
        generate=MagicMock(return_value=assessment_reply('Private Laptop saving practices')),
        budget=llm.CoachRequestBudget.start(), api_key='synthetic', web_enabled=True,
        max_results=4, timeout=4, web_query_guard=make_search_guard(StoredClient(rows), USER_ID))
    assert sent and all('private laptop' not in query.casefold() for query in sent)
    assert decision.diagnostics['privacy_skips']
    assert all(event == {'privacy_guard_skip': True} for event in decision.diagnostics['privacy_skips'])


def test_absent_product_or_empty_claims_are_uncertain_and_do_not_refuse(monkeypatch):
    for ids, entity in (((), 'Versa Save'), ((1,), 'Versa Save')):
        checked, _ = _check(monkeypatch, _draft(OTHER), _verified(1, 'recommendation', ids, entity))
        assert checked.is_valid and checked.diagnostics['product_policy']['first_verdict'] == 'uncertain'


def test_q9_malay_inflation_draft_is_not_refused_for_an_absent_product(monkeypatch):
    text = 'Inflasi mengurangkan kuasa beli wang simpanan apabila harga barang naik [S1].'
    checked, _ = _check(monkeypatch, _draft(text), _verified(1, 'recommendation', (), 'Versa Save'))
    assert checked.is_valid and checked.diagnostics['product_policy']['first_verdict'] == 'uncertain'


def test_product_verdict_parser_binds_name_case_insensitively_and_requires_claim(monkeypatch):
    absent, _ = _reply(monkeypatch, {'verdict': 'recommendation', 'claim_ids': [1], 'named_entity': 'Versa Save'})
    empty, _ = _reply(monkeypatch, {'verdict': 'recommendation', 'claim_ids': [], 'named_entity': 'Acme'},
                      context=replace(_context(), draft=_draft(STEERING)))
    valid, _ = _reply(monkeypatch, {'verdict': 'recommendation', 'claim_ids': [1], 'named_entity': 'acme securities'},
                      context=replace(_context(), draft=_draft(STEERING)))
    assert absent.product_verdict == empty.product_verdict == 'uncertain'
    assert (valid.product_verdict, valid.product_claim_ids) == ('recommendation', (1,))


@pytest.mark.parametrize('bad_claims', [[999], '1', None, [True]])
def test_recommendation_without_a_valid_claim_is_uncertain(bad_claims):
    result = verifier._read_product_policy({'product_policy': {'verdict': 'recommendation',
        'claim_ids': bad_claims, 'named_entity': 'Acme'}}, {1}, 'Open an Acme account')
    assert result == ('uncertain', (), None)
