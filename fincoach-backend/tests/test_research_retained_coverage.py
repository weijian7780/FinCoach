"""Displayed coverage must depend only on retained, owned supported claims."""
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from app.rag.grounding import GroundingClaim
from app.rag.research_coverage import RequestedPart, PartCoverage
from app.rag.verifier import ResearchVerificationContext, verify_grounding_claims


@pytest.mark.parametrize('dependencies', [[99], [], ['1'], [1, 1]])
def test_invalid_part_claim_dependencies_fail_closed(dependencies):
    result = _check(dependencies)
    assert result.error_code == 'invalid_verifier_response'
    assert not result.answered_part_claims


def test_valid_part_claim_dependencies_are_preserved():
    result = _check([1])
    assert result.error_code is None
    assert result.answered_part_claims == (('p1', (1,)),)


def test_compound_explanation_has_room_for_conditional_document_lists():
    from app.rag.research_answer import research_answer_word_limit
    from app.rag.research_policy import QuestionPlan
    plan = QuestionPlan('Public programme', False, True, 'current',
                        required_facts=('application steps', 'required documents'), part_tracking=True)
    assert research_answer_word_limit(plan) == 360
    assert research_answer_word_limit(NS()) <= 360


def test_oversized_draft_preserves_only_bounded_verified_blocks():
    from app.llm import CoachRequestBudget
    from app.rag.research_answer import check_research_draft
    from app.rag.verifier import GroundingVerification
    from tests.test_research_answer import decision, answer
    draft = answer(' '.join(['Apply through the official portal using your own account and complete the requested personal details before submitting the application [S1].'] * 10))
    def supported(claims, *_a, **_kw):
        return GroundingVerification({c.id: 'supported' for c in claims},
                                     {c.id: 1 for c in claims}, requested_scope_covered=True)
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=supported):
        checked = check_research_draft(draft, public_question='How do I apply?',
            decision=decision(), budget=CoachRequestBudget.start(), max_words=180)
    assert not checked.is_valid and 'answer_too_long' in checked.error_codes
    assert checked.approved_text and 'Apply through' in checked.approved_text
    assert len(checked.approved_text.split()) <= 210  # includes fixed headings/disclaimer
    assert checked.diagnostics['requested_scope_covered'] is False


def _check(dependencies):
    payload = dict(claims=[dict(id=1, verdict='supported', source_index=1,
                               scope_relation='preserved')], quality_errors=[],
                   requested_scope_covered=True, unanswered_requested_parts=[],
                   answered_part_ids=['p1'], answered_part_claims={'p1': dependencies})
    response = NS(choices=[NS(message=NS(content=json.dumps(payload)), finish_reason='stop')], usage=None)
    client = NS(chat=NS(completions=NS(create=lambda **_: response)))
    text = 'The programme provides financial education.'
    context = ResearchVerificationContext('What does it provide?', text, (),
        requested_parts=(RequestedPart('p1', 'purpose'),),
        coverage=(PartCoverage('p1', 'confirmed', (1,), complete=True),))
    with patch('app.rag.verifier._create_verifier_client', return_value=client):
        return verify_grounding_claims([GroundingClaim(1, text, (1,))], [text],
                                      timeout_seconds=5, research_context=context)
