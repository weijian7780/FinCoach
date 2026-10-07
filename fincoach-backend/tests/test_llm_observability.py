from types import SimpleNamespace as NS

from app.llm import AgentLLMResult
from app.llm_observability import completion_metadata
from unittest.mock import patch
import pytest


def response(reason, completion=100, total=200, reasoning=30):
    return NS(choices=[NS(finish_reason=reason)], usage=NS(
        prompt_tokens=100, completion_tokens=completion, total_tokens=total,
        completion_tokens_details=NS(reasoning_tokens=reasoning)))


def test_length_and_native_limit_are_truncated():
    for reason in ('length', 'MAX_TOKENS'):
        assert completion_metadata(response(reason), max_tokens=100, timeout_seconds=12)['truncated']


def test_empty_paid_generation_retains_usage_and_logs_attempt(caplog):
    from app.llm import _Provider, _generate_with_provider
    resp = response('length')
    resp.choices[0].message = NS(content='')
    client = NS(chat=NS(completions=NS(create=lambda **_: resp)))
    with caplog.at_level('INFO', logger='uvicorn.error'), pytest.raises(RuntimeError) as raised:
        _generate_with_provider(lambda **_: client,
            _Provider('primary', 'https://example.test', 'not-a-key', 'test-model'),
            'Public question', reasoning_effort='high', timeout_seconds=20)
    assert raised.value.completion_metadata['completion_tokens'] == 100
    assert raised.value.completion_metadata['truncated']
    assert 'coach_provider_attempt' in caplog.text
    assert 'not-a-key' not in caplog.text


def test_near_cap_is_warning_not_truncation():
    data = completion_metadata(response('stop', 95, 195), max_tokens=100, timeout_seconds=12)
    assert data['near_cap'] and not data['truncated']
    assert data['reasoning_tokens'] == 30
    assert data['accounting_residual_tokens'] == 0


def test_missing_usage_and_unknown_residual():
    data = completion_metadata(NS(choices=[NS(finish_reason=None)]), max_tokens=100, timeout_seconds=12)
    assert data['total_tokens'] is None and not data['near_cap']
    data = completion_metadata(response('stop', total=240), max_tokens=1000, timeout_seconds=12)
    assert data['accounting_residual_tokens'] == 40
    assert data['reasoning_tokens'] == 30  # residual does not invent more thinking


def test_agent_seven_positional_fields_stay_compatible():
    result = AgentLLMResult('text', 'model', 1, 2, {'a': 3}, ('tool',), ({'ok': True},), finish_reason='stop')
    assert result.ui_payload == {'a': 3} and result.tool_results == ({'ok': True},)
    assert result.finish_reason == 'stop'


def test_successful_completion_preserves_requested_cap_and_reasoning_usage():
    from app.llm import _Provider, _generate_with_provider
    resp = response('length')
    resp.choices[0].message = NS(content='A partial explanation.')
    client = NS(chat=NS(completions=NS(create=lambda **_: resp)))
    result = _generate_with_provider(lambda **_: client,
        _Provider('primary', 'https://example.test', 'not-a-key', 'test-model'),
        'Public question', reasoning_effort='high', timeout_seconds=20, max_tokens=100)
    assert result.requested_max_tokens == 100 and result.reasoning_tokens == 30
    assert result.total_tokens == 200


def test_approved_research_writer_can_use_low_reasoning_without_changing_general_policy():
    from app import llm
    provider = llm._Provider('primary', 'https://example.test', 'not-a-key', 'test-model')
    budget = llm.CoachRequestBudget.start().for_stage(max_seconds=20, stage_name='research_writer')
    with patch.object(llm, '_configured', return_value=True), \
         patch.object(llm, '_provider_order', return_value=[provider]), \
         patch.object(llm, '_generate_with_provider', return_value=NS(content='Explanation.')) as generate:
        llm.generate_result('Approved public facts', budget=budget, reasoning_effort='low')
    assert generate.call_args.kwargs['reasoning_effort'] == 'low'


def test_valid_json_with_length_is_rejected_and_usage_retained():
    from app.rag.verifier import verify_grounding_claims
    from app.rag.grounding import GroundingClaim
    resp = response('length')
    resp.choices[0].message = NS(content='{"claims":[{"id":1,"verdict":"supported","source_index":1}]}')
    client = NS(chat=NS(completions=NS(create=lambda **_: resp)))
    with patch('app.rag.verifier._create_verifier_client', return_value=client):
        checked = verify_grounding_claims([GroundingClaim(1, 'A fact.', (1,))], ['A fact.'], timeout_seconds=5)
    assert checked.error_code == 'verifier_output_truncated'
    assert checked.completion_tokens == 100 and checked.finish_reason == 'length'


def test_verifier_json_and_timeout_are_distinct():
    from app.rag.verifier import verify_grounding_claims
    from app.rag.grounding import GroundingClaim
    resp = response('stop')
    resp.choices[0].message = NS(content='{unfinished')
    client = NS(chat=NS(completions=NS(create=lambda **_: resp)))
    with patch('app.rag.verifier._create_verifier_client', return_value=client):
        checked = verify_grounding_claims([GroundingClaim(1, 'A fact.', (1,))], ['A fact.'], timeout_seconds=5)
    assert checked.error_code == 'verifier_invalid_json' and checked.completion_tokens == 100
    with patch('app.rag.verifier._create_verifier_client', side_effect=TimeoutError):
        checked = verify_grounding_claims([GroundingClaim(1, 'A fact.', (1,))], ['A fact.'], timeout_seconds=5)
    assert checked.error_code == 'verifier_timeout'
