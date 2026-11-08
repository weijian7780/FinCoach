"""Shared research deadlines, measured rewrite admission and outage recovery."""
from dataclasses import replace

import pytest

from app import llm
from app.rag import research_answer as answer, research_answer_budget as budgets, verifier
from app.rag.grounding import GroundingClaim
from app.rag.research_policy import QuestionPlan
from test_writer_round2 import allow, decision, draft


@pytest.fixture
def backup(monkeypatch):
    monkeypatch.setattr(llm, 'COACH_WRITER_FALLBACK_BASE_URL', 'https://openrouter.ai/api/v1')
    monkeypatch.setattr(llm, 'COACH_WRITER_FALLBACK_API_KEY_ENV', 'TEST_BACKUP_CREDENTIAL')
    monkeypatch.setattr(llm, 'COACH_WRITER_FALLBACK_MODEL', 'deepseek/test')
    monkeypatch.setenv('TEST_BACKUP_CREDENTIAL', 'test-value')
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_BASE_URL', 'https://openrouter.ai/api/v1')
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_API_KEY', 'test-value')
    monkeypatch.setattr(verifier, 'LLM_PRIMARY_MODEL', 'nemotron-test')


@pytest.mark.parametrize('elapsed,expected', [(10, 60), (40, 45), (80, 5)])
def test_real_research_checker_gets_remaining_work_time_capped_at_60(monkeypatch, elapsed, expected):
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 90)
    monkeypatch.setattr(budgets, 'COACH_FINALIZATION_RESERVE_SECONDS', 5)
    clock = [100.0]
    monkeypatch.setattr(llm, 'monotonic', lambda: clock[0])
    seen = allow(monkeypatch)
    work = budgets.research_work_budget(llm.CoachRequestBudget(started_at=100.0 - elapsed))
    result = answer.check_research_draft(draft('Investors may visit the office [S1].'),
        public_question='Explain', decision=decision(), budget=work)
    assert result.is_valid
    assert seen[0][1]['timeout_seconds'] == expected


@pytest.mark.parametrize('error,expected_attempts', [
    ('verifier_invalid_json', [False, False, True]),
    ('verifier_output_truncated', [False, False, True]),
    ('verifier_http_error', [False, True]),
    ('verifier_timeout', [False, True]),
])
def test_no_split_and_correct_failure_chain(monkeypatch, backup, error, expected_attempts):
    clock, calls = [0.0], []
    monkeypatch.setattr(verifier, 'monotonic', lambda: clock[0])
    def attempt(*args, timeout_seconds, _fallback=False, **kwargs):
        calls.append((_fallback, timeout_seconds))
        clock[0] += 1
        return verifier.GroundingVerification({1: 'supported'} if _fallback else {},
            model='deepseek/test' if _fallback else 'nemotron-test',
            error_code=None if _fallback else error)
    monkeypatch.setattr(verifier, '_verify_grounding_claims_once', attempt)
    result = verifier.verify_grounding_claims([GroundingClaim(1, 'x', (1,))], ['x'],
        timeout_seconds=60, research_context=verifier.ResearchVerificationContext('q', 'd', ()))
    assert result.all_supported
    assert [x[0] for x in calls] == expected_attempts
    assert calls[0][1] == 60


@pytest.mark.parametrize('error', ['verifier_invalid_json', 'verifier_http_error'])
@pytest.mark.parametrize('left,may_continue', [(4.99, False), (5.0, True), (5.01, True)])
def test_retry_or_backup_needs_five_seconds(monkeypatch, backup, error, left, may_continue):
    clock, calls = [0.0], []
    monkeypatch.setattr(verifier, 'monotonic', lambda: clock[0])
    def attempt(*args, _fallback=False, **kwargs):
        calls.append(_fallback)
        if len(calls) == 1:
            clock[0] = 60 - left
            return verifier.GroundingVerification({}, error_code=error, model='nemotron-test')
        return verifier.GroundingVerification({1: 'supported'}, model='other')
    monkeypatch.setattr(verifier, '_verify_grounding_claims_once', attempt)
    verifier.verify_grounding_claims([GroundingClaim(1, 'x', (1,))], ['x'],
        timeout_seconds=60, research_context=verifier.ResearchVerificationContext('q', 'd', ()))
    assert len(calls) == (2 if may_continue else 1)
    if may_continue:
        assert calls[1] is (error == 'verifier_http_error')


def test_valid_semantic_rejection_never_triggers_backup(monkeypatch, backup):
    calls = []
    def attempt(*args, **kwargs):
        calls.append(kwargs['_fallback'])
        return verifier.GroundingVerification({1: 'unsupported'})
    monkeypatch.setattr(verifier, '_verify_grounding_claims_once', attempt)
    verifier.verify_grounding_claims([GroundingClaim(1, 'x', (1,))], ['x'],
        timeout_seconds=60, research_context=verifier.ResearchVerificationContext('q', 'd', ()))
    assert calls == [False]


def test_skip_rewrite_delivers_only_checked_portion(monkeypatch, caplog):
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 90)
    monkeypatch.setattr(budgets, 'COACH_FINALIZATION_RESERVE_SECONDS', 5)
    monkeypatch.setattr(llm, 'monotonic', lambda: 100.0)
    checked = answer.ResearchDraftCheck(False, ('unsupported_claim',),
        '**Insight**\nVerified [S1].', {'approved_claim_count': 1, 'requested_scope_covered': False})
    monkeypatch.setattr(answer, 'check_research_draft', lambda *a, **kw: checked)
    monkeypatch.setattr(answer, '_generate_research_correction',
        lambda *a, **kw: pytest.fail('Rewrite must not start when time is too short'))
    with caplog.at_level('INFO', logger='uvicorn.error'):
        result = answer.recover_research_answer(plan=QuestionPlan('topic', False, True, 'stable'),
            decision=decision(), draft=llm.LLMResult('original', 'primary'),
            budget=llm.CoachRequestBudget(started_at=25), public_question='question')
    assert 'Verified [S1]' in result.result.content
    assert result.diagnostics['rewrite_skipped_for_time'] is True
    assert 'coach_rewrite_skipped' in caplog.text


def test_measured_rewrite_floor_reserves_writer_and_checker(monkeypatch):
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 90)
    monkeypatch.setattr(llm, 'monotonic', lambda: 100.0)
    # 13 s writer + 7 s checker, rounded up from the previous two runs.
    assert budgets.correction_writer_budget(llm.CoachRequestBudget(29.99)) is None
    assert budgets.correction_writer_budget(llm.CoachRequestBudget(30.0)) is not None


def test_slow_research_checker_cannot_overspend_original_budget(monkeypatch, backup):
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 90)
    monkeypatch.setattr(budgets, 'COACH_FINALIZATION_RESERVE_SECONDS', 5)
    clock, seen = [82.0], []
    monkeypatch.setattr(llm, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(verifier, 'monotonic', lambda: clock[0])
    def slow(*args, timeout_seconds, **kwargs):
        seen.append(timeout_seconds)
        clock[0] += timeout_seconds
        return verifier.GroundingVerification({}, error_code='verifier_timeout')
    monkeypatch.setattr(verifier, '_verify_grounding_claims_once', slow)
    budget = budgets.research_work_budget(llm.CoachRequestBudget(started_at=0))
    result = verifier.verify_grounding_claims([GroundingClaim(1, 'x', (1,))], ['x'],
        timeout_seconds=budget.timeout_for('research_verifier'),
        research_context=verifier.ResearchVerificationContext('q', 'd', ()))
    assert result.error_code == 'verifier_timeout'
    assert seen == [3.0] and clock[0] == 85.0 and clock[0] < 90


def test_mocked_slow_message_includes_repository_time_and_finishes_before_90(monkeypatch):
    from unittest.mock import MagicMock
    from app.rag import service
    from test_research_answer import answer as good_draft, decision as good_decision, supported

    clock = [0.0]
    monkeypatch.setattr(llm, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 90)
    monkeypatch.setattr(budgets, 'COACH_FINALIZATION_RESERVE_SECONDS', 5)
    monkeypatch.setattr(service, 'COACH_RESEARCH_POLICY_ENABLED', True)
    monkeypatch.setattr(service, 'COACH_LLM_INTERPRETATION_ENABLED', False)
    repo = MagicMock(user_id='fixture-user')
    def session(_):
        clock[0] += 2
        return {'id': 's', 'title': 'Existing'}
    repo.require_session.side_effect = session
    repo.find_user_message.return_value = None
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kw: kw['assistant_payload']
    monkeypatch.setattr(service, 'interpret_question', lambda *a, **k:
        QuestionPlan('public programme application', False, True, 'current'))
    monkeypatch.setattr(service, 'retrieve', lambda *a, **k: [])
    def research(*args, **kwargs):
        clock[0] += 28
        return good_decision()
    monkeypatch.setattr(service, 'run_research_policy', research)
    def write(*args, **kwargs):
        assert kwargs['budget'].started_at == 0
        clock[0] += 15
        return llm.AgentLLMResult(good_draft(), 'nemotron')
    monkeypatch.setattr(service, 'generate_result', write)
    def check(claims, *args, **kwargs):
        assert kwargs['timeout_seconds'] == 40
        clock[0] += 39
        return supported(claims, *args, **kwargs)
    monkeypatch.setattr(answer, 'verify_grounding_claims', check)
    monkeypatch.setattr(answer, '_generate_research_correction',
        lambda *a, **k: pytest.fail('Valid checked answer must not be rewritten'))
    reply = service.CoachingService(repo, MagicMock()).send_message('s', 'm',
        'How do I apply for this public programme?')
    assert 'submit your application' in reply['assistant_message']['content']
    assert clock[0] == 84 and clock[0] < 90
