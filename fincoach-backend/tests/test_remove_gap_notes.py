"""Display policy must not promote partial evidence or weaken claim removal."""
from unittest.mock import patch
import pytest
from app.llm import AgentLLMResult, CoachRequestBudget
from app.rag import research_answer as answer
from app.rag.research_policy import QuestionPlan
from test_research_notice_regression import evidence, draft, verdict


@pytest.mark.parametrize('language', ['en', 'ms', 'zh', 'ta'])
def test_partial_delivery_has_no_code_note_but_keeps_diagnostics(language):
    with (patch.object(answer, 'verify_grounding_claims', return_value=verdict(mappings=())),
          patch.object(answer, '_generate_research_correction', side_effect=TimeoutError)):
        result = answer.recover_research_answer(
            plan=QuestionPlan('reserve fund', False, True, 'stable', response_language=language),
            decision=evidence(), draft=AgentLLMResult(draft(), 'primary'),
            budget=CoachRequestBudget.start(),
            public_question='What is a reserve fund?\nResponse language: ' + language + '.')
    assert result.diagnostics['complete'] is False
    assert result.diagnostics['reply_reason'] == 'partial'
    assert result.diagnostics['requested_scope_covered'] is False
    assert result.diagnostics['unanswered_requested_parts']
    assert 'money held for future needs' in result.result.content
    assert 'separate container' not in result.result.content
    for note in answer._DETAIL_LEFT_OUT.values():
        assert note not in result.result.content
    assert 'fully confirm' not in result.result.content


@pytest.mark.parametrize('language', ['en', 'ms', 'zh', 'ta'])
def test_no_approved_evidence_keeps_fixed_reply(language):
    from dataclasses import replace
    decision = evidence()
    decision = replace(decision, chunks=[], assessment=replace(
        decision.assessment, status='insufficient', supported_sources=(), supported_quotes=()))
    result = answer.recover_research_answer(
        plan=QuestionPlan('reserve fund', False, True, 'stable', response_language=language), decision=decision,
        draft=None, budget=CoachRequestBudget.start(),
        public_question='What is a reserve fund?\nResponse language: ' + language + '.')
    assert result.result.content == answer._INSUFFICIENT_EVIDENCE_MESSAGES[language]
    assert result.diagnostics['complete'] is False
