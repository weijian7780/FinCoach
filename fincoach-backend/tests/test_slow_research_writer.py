"""A slow SDK response must not keep a checked answer past its deadline."""
from threading import BoundedSemaphore, Event
from time import monotonic

import pytest

from app import llm
from app.rag import research_answer as answer, service
from app.rag.research_policy import QuestionPlan
from test_writer_round2 import decision


def test_slow_corrective_writer_returns_checked_answer_before_stage_deadline(monkeypatch):
    entered, release, finished = Event(), Event(), Event()
    checked = answer.ResearchDraftCheck(False, ('misapplied_claim',),
        '**Insight**\nA supported sentence [S1].',
        {'approved_claim_count': 1, 'requested_scope_covered': False})
    monkeypatch.setattr(answer, 'check_research_draft', lambda *a, **kw: checked)
    monkeypatch.setattr(answer, 'correction_writer_budget',
        lambda budget: budget.for_stage(max_seconds=.08))
    def slow_writer(*args, **kwargs):
        entered.set()
        try:
            release.wait(1)
            return llm.LLMResult('late unverified response', 'nemotron')
        finally:
            finished.set()
    monkeypatch.setattr(answer, '_generate_research_correction', slow_writer)
    started = monotonic()
    try:
        outcome = answer.recover_research_answer(plan=QuestionPlan('topic', False, True, 'stable'),
            decision=decision(), draft=llm.LLMResult('original draft', 'nemotron'),
            budget=llm.CoachRequestBudget.start(), public_question='question')
        elapsed = monotonic() - started
        assert entered.is_set() and elapsed < .4
        assert 'A supported sentence' in outcome.result.content
        assert 'late unverified response' not in outcome.result.content
        assert outcome.recovery_used
    finally:
        release.set()
        assert finished.wait(1)


def test_slow_initial_writer_is_bounded_before_recovery(monkeypatch):
    entered, release, finished = Event(), Event(), Event()
    monkeypatch.setattr(service, 'initial_writer_budget',
        lambda budget: budget.for_stage(max_seconds=.08))
    def slow_writer(*args, **kwargs):
        entered.set()
        try:
            release.wait(1)
            return llm.LLMResult('late unverified response', 'nemotron')
        finally:
            finished.set()
    monkeypatch.setattr(service, 'generate_result', slow_writer)
    observed = {}
    def recover(**kwargs):
        observed.update(kwargs)
        return 'bounded result'
    monkeypatch.setattr(service, 'recover_research_answer', recover)
    started = monotonic()
    try:
        result = service._research_explanation_result(
            plan=QuestionPlan('topic', False, True, 'stable'), decision=decision(),
            budget=llm.CoachRequestBudget.start(), question='question')
        assert entered.is_set() and monotonic() - started < .4
        assert result == 'bounded result'
        assert observed['draft'] is None and observed['initial_failure'] == 'answer_generation_unavailable'
    finally:
        release.set()
        assert finished.wait(1)


def test_stalled_writer_capacity_is_bounded_and_separate_from_checker(monkeypatch):
    from app.rag import research_checker_deadline as hard
    monkeypatch.setattr(hard, '_writer_slots', BoundedSemaphore(1))
    monkeypatch.setattr(hard, '_slots', BoundedSemaphore(1))
    release, finished = Event(), Event()
    def blocked():
        try:
            release.wait(1)
        finally:
            finished.set()
    try:
        with pytest.raises(TimeoutError):
            hard.within_writer_deadline(blocked, .03)
        assert hard.within_deadline(lambda: 'checker available', .1) == 'checker available'
        with pytest.raises(TimeoutError):
            hard.within_writer_deadline(lambda: 'must not run', .1)
    finally:
        release.set()
        assert finished.wait(1)


def test_slow_rewrite_does_not_hold_full_message_past_deadline(monkeypatch):
    from unittest.mock import MagicMock
    from app.rag import research_answer_budget as budgets
    from test_research_answer import decision as good_decision

    clock, entered, release, finished = [0.0], Event(), Event(), Event()
    monkeypatch.setattr(llm, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 90)
    monkeypatch.setattr(budgets, 'COACH_FINALIZATION_RESERVE_SECONDS', 5)
    monkeypatch.setattr(service, 'COACH_RESEARCH_POLICY_ENABLED', True)
    monkeypatch.setattr(service, 'COACH_LLM_INTERPRETATION_ENABLED', False)
    repo = MagicMock(user_id='fixture-user')
    repo.require_session.return_value = {'id': 's', 'title': 'Existing'}
    repo.find_user_message.return_value = None
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kw: kw['assistant_payload']
    monkeypatch.setattr(service, 'interpret_question', lambda *a, **k:
        QuestionPlan('public programme application', False, True, 'current'))
    monkeypatch.setattr(service, 'retrieve', lambda *a, **k: [])
    def research(*args, **kwargs):
        clock[0] += 30
        return good_decision()
    monkeypatch.setattr(service, 'run_research_policy', research)
    def write(*args, **kwargs):
        clock[0] += 15
        return llm.AgentLLMResult('original', 'nemotron')
    monkeypatch.setattr(service, 'generate_result', write)
    def check(*args, **kwargs):
        clock[0] += 8
        return answer.ResearchDraftCheck(False, ('misapplied_claim',),
            '**Insight**\nA supported sentence [S1].',
            {'approved_claim_count': 1, 'requested_scope_covered': False})
    monkeypatch.setattr(answer, 'check_research_draft', check)
    monkeypatch.setattr(answer, 'correction_writer_budget',
        lambda budget: budget.for_stage(max_seconds=.08))
    def slow(*args, **kwargs):
        entered.set()
        try:
            release.wait(1)
            return llm.LLMResult('late unverified response', 'nemotron')
        finally:
            finished.set()
    monkeypatch.setattr(answer, '_generate_research_correction', slow)
    started = monotonic()
    try:
        reply = service.CoachingService(repo, MagicMock()).send_message(
            's', 'm', 'How do I apply for this public programme?')
        assert entered.is_set() and monotonic() - started < .4
        assert clock[0] < 90
        assert 'A supported sentence' in reply['assistant_message']['content']
        assert 'late unverified response' not in reply['assistant_message']['content']
    finally:
        release.set()
        assert finished.wait(1)
