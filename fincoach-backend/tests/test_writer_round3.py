"""Research-only total deadlines, useful retries and stage reservations."""
from threading import Event
from time import monotonic
from types import SimpleNamespace as NS

import pytest

from app import llm
from app.rag import verifier, research_answer as answer, research_answer_budget as budgets
from app.rag.grounding import GroundingClaim
from test_writer_fixes import setup, response, verdict, check

CONTEXT = verifier.ResearchVerificationContext('q', 'd', ())


@pytest.mark.parametrize('elapsed,retry', [(9.9, True), (10, True), (10.1, False)])
def test_full_first_limit_and_five_second_retry_floor(monkeypatch, elapsed, retry):
    payload = {**verdict('unsupported'), 'quality_errors': []}
    calls, timeouts = setup(monkeypatch, [response('{'), response(payload)], elapsed=elapsed)
    result = check(timeout=15, context=CONTEXT)
    assert timeouts[0] == 15
    assert len(calls) == (2 if retry else 1)
    assert result.error_code == (None if retry else 'verifier_invalid_json')
    if retry:
        assert timeouts[1] == pytest.approx(15 - elapsed)


def test_research_checker_stays_on_nemotron_after_two_bad_replies(monkeypatch):
    calls, _ = setup(monkeypatch, [response('{'), response('{'), response(verdict())])
    result = check(timeout=15, context=CONTEXT)
    assert result.error_code == 'verifier_invalid_json'
    assert [c['model'] for c in calls] == ['nemotron-test', 'nemotron-test']


def test_slow_sdk_is_abandoned_and_late_reply_cannot_approve(monkeypatch):
    release, finished, entered = Event(), Event(), Event()
    def create(**kwargs):
        entered.set()
        release.wait(2)
        return response({**verdict(), 'quality_errors': []})
    def close():
        finished.set()
    monkeypatch.setattr(verifier, '_create_verifier_client', lambda **kw:
        NS(chat=NS(completions=NS(create=create)), close=close))
    started = monotonic()
    try:
        result = check(timeout=.08, context=CONTEXT)
        elapsed = monotonic() - started
        assert entered.is_set() and .06 <= elapsed < .4
        assert result.error_code == 'verifier_timeout' and not result.verdicts
    finally:
        release.set()
        assert finished.wait(1)
    assert result.error_code == 'verifier_timeout' and not result.verdicts


def test_slow_client_setup_is_also_bounded(monkeypatch):
    release, finished = Event(), Event()
    def factory(**kw):
        release.wait(2)
        finished.set()
        raise TimeoutError
    monkeypatch.setattr(verifier, '_create_verifier_client', factory)
    started = monotonic()
    try:
        assert check(timeout=.08, context=CONTEXT).error_code == 'verifier_timeout'
        assert monotonic() - started < .4
    finally:
        release.set()
        assert finished.wait(1)


def test_research_cap_does_not_change_records_cap(monkeypatch):
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 120)
    monkeypatch.setitem(llm._EVIDENCE_ROLE_CAPS, 'research_verifier', 15)
    monkeypatch.setitem(llm._EVIDENCE_ROLE_CAPS, 'verifier', 5)
    budget = llm.CoachRequestBudget.start()
    assert budget.timeout_for('research_verifier') == 15
    assert budget.timeout_for('verifier') == 5
    child = budget.for_stage(max_seconds=2)
    assert 0 < child.timeout_for('research_verifier') <= 2


def test_research_call_site_uses_own_role(monkeypatch):
    from test_writer_round2 import draft, decision, allow
    seen = allow(monkeypatch)
    roles = []
    class Budget:
        def timeout_for(self, role):
            roles.append(role)
            return 15
    answer.check_research_draft(draft('Investors may visit the office [S1].'),
        public_question='Explain', decision=decision(), budget=Budget())
    assert roles == ['research_verifier']
    assert seen[0][1]['timeout_seconds'] == 15


def test_correction_leaves_full_research_check_slot(monkeypatch):
    monkeypatch.setattr(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 120)
    assert budgets.correction_writer_budget(llm.CoachRequestBudget.start().for_stage(max_seconds=19)) is None
    work = llm.CoachRequestBudget.start().for_stage(max_seconds=40)
    child = budgets.correction_writer_budget(work)
    assert child is not None and child.remaining_seconds() <= budgets.COACH_RESEARCH_CORRECTION_SECONDS
    assert child.stage_deadline_at <= work.stage_deadline_at - budgets.RESEARCH_CHECKER_ESTIMATE_SECONDS


def test_default_research_limit_follows_existing_limit(monkeypatch):
    import runpy
    from app import config
    monkeypatch.delenv('COACH_RESEARCH_VERIFIER_TIMEOUT_SECONDS', raising=False)
    monkeypatch.setenv('GROUNDING_VERIFIER_TIMEOUT_SECONDS', '5')
    assert runpy.run_path(config.__file__)['COACH_RESEARCH_VERIFIER_TIMEOUT_SECONDS'] == 5
    monkeypatch.setenv('COACH_RESEARCH_VERIFIER_TIMEOUT_SECONDS', '15')
    assert runpy.run_path(config.__file__)['COACH_RESEARCH_VERIFIER_TIMEOUT_SECONDS'] == 15


def test_abandoned_workers_have_bounded_capacity(monkeypatch):
    from threading import BoundedSemaphore
    from app.rag import research_checker_deadline as hard
    monkeypatch.setattr(hard, '_slots', BoundedSemaphore(1))
    release, finished = Event(), Event()
    def blocked():
        try:
            release.wait(2)
        finally:
            finished.set()
    try:
        with pytest.raises(TimeoutError):
            hard.within_deadline(blocked, .03)
        entered = []
        with pytest.raises(TimeoutError):
            hard.within_deadline(lambda: entered.append(True), .1)
        assert not entered
    finally:
        release.set()
        assert finished.wait(1)
