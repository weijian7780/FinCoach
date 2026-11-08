"""Pure offline tests for aggregate reservations; no provider traffic."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HARNESS = Path(__file__).parents[1] / 'experiment' / 'guard.py'
if not HARNESS.exists():
    # The trial spending guard lives with a staged experiment, not in the app.
    pytest.skip('trial harness (experiment/guard.py) is not in this checkout', allow_module_level=True)
spec = importlib.util.spec_from_file_location('trial_guard', HARNESS)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_model_reservations_sum_across_providers_and_stop_before_dollar_cap(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {})
    ident = guard.reserve('gemini', '0.160')
    with pytest.raises(module.BudgetStop):
        guard.reserve('openrouter', '0.141')
    assert guard.state['stopped']
    assert guard.state['reason'] == 'next_call_exceeds_usd_0_30'
    assert guard.state['outstanding'][ident]['maximum'] == '0.160'


def test_coach_guard_blocks_gemini_before_reservation(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {}, forbid_gemini=True)
    with pytest.raises(module.BudgetStop):
        guard._model_reservation('generativelanguage.googleapis.com',
            b'{"model":"gemini-3.5-flash-lite","max_tokens":30}')
    assert guard.state['stopped'] and guard.state['reason'] == 'coach_gemini_forbidden'
    assert guard.state['requests'] == 0 and not guard.state['outstanding']


def test_missing_usage_retains_reservation_and_tavily_settles_in_credits(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {})
    first = guard.reserve('gemini', '0.080')
    second = guard.reserve('tavily', 2)
    guard.settle(first, None)
    guard.settle(second, 1, credits=1)
    assert first in guard.state['outstanding']
    assert second not in guard.state['outstanding']
    assert guard.state['usage']['tavily_credits'] == 1


def test_tavily_credit_limit_is_independent_of_dollar_limit(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {})
    guard.reserve('gemini', '0.295')
    ident = guard.reserve('tavily', 149)
    assert guard.state['outstanding'][ident]['maximum'] == '149'
    with pytest.raises(module.BudgetStop):
        guard.reserve('tavily', 2)
    assert guard.state['reason'] == 'next_call_exceeds_150_tavily_credits'


def test_pending_tavily_credits_are_reserved_across_calls(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {})
    first = guard.reserve('tavily', 149)
    guard.settle(first, None)
    second = guard.reserve('tavily', 1)
    assert second in guard.state['outstanding']
    with pytest.raises(module.BudgetStop):
        guard.reserve('tavily', 1)


def test_parallel_url_reservations_cannot_exceed_credit_cap(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {})
    guard.state['usage']['tavily_credits'] = 149
    def reserve(_):
        try:
            return guard.reserve('tavily', 1)
        except module.BudgetStop:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(reserve, range(4)))
    assert sum(item is not None for item in results) == 1
    assert len(guard.state['outstanding']) == 1 and guard.state['stopped']
    assert guard.state['reason'] == 'next_call_exceeds_150_tavily_credits'


def test_forced_outage_is_local_and_not_a_paid_model_request(tmp_path):
    guard = module.Guard(tmp_path / 'ledger.json', {}, forced=True)
    content = b'{"model":"openai/gpt-6-luna","max_tokens":10}'
    with pytest.raises(ConnectionError, match='Synthetic preferred-writer outage'):
        guard._model_reservation('openrouter.ai', content)
    assert guard.state['requests'] == 0
    assert not guard.state['stopped']
