from unittest.mock import patch
from app.llm import LLMResult, CoachRequestBudget
from app.rag.research_answer import check_research_draft, safe_draft_units, recover_research_answer
from app.rag.verifier import GroundingVerification
from app.rag.research_policy import QuestionPlan
from tests.test_research_answer import decision


def approved(claims, *_a, **_kw):
    return GroundingVerification({c.id: 'supported' for c in claims}, {c.id: 1 for c in claims})


def test_truncated_prefix_retains_verified_sentence_not_fragment():
    text = '**Insight**\nApply through the portal [S1]. You need a copy of your spouse’s'
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=approved):
        result = check_research_draft(text, public_question='Apply?', decision=decision(),
            budget=CoachRequestBudget.start(), completion=LLMResult(text, 'primary', finish_reason='length'))
    assert not result.is_valid and 'Apply through the portal' in result.approved_text
    assert 'spouse' not in result.approved_text
    assert result.diagnostics['requested_scope_covered'] is False


def test_qualified_list_is_dropped_as_one_block_when_last_item_unfinished():
    text = '**Insight**\nApply online [S1].\n\n**Recommended action**\nFor foreign spouses:\n- Passport copy [S1]\n- Copy of spouse’s'
    units = safe_draft_units(text, finish_reason='length')
    assert any('Apply online' in unit[1] for unit in units)
    assert not any('Passport' in unit[1] or 'foreign' in unit[1] for unit in units)


def test_fallback_timeout_retains_independently_verified_partial():
    text = '**Insight**\nApply through the portal [S1]. and'
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=approved), patch(
        'app.rag.research_answer.generate_fallback_result', side_effect=TimeoutError):
        result = recover_research_answer(plan=QuestionPlan('application', False, True, 'stable'),
            decision=decision(), draft=LLMResult(text, 'primary', finish_reason='length'),
            budget=CoachRequestBudget.start(), public_question='Apply?')
    assert 'Apply through the portal' in result.result.content
    assert not result.diagnostics['complete']


def test_every_prefix_never_displays_an_incomplete_unit():
    text = '**Insight**\nApply through the portal [S1].\n\n**Recommended action**\nFor adopted children:\n- Provide an adoption certificate [S1].\n- Provide a MyKid copy [S1].\n\n**Educational guidance**\nThis is educational guidance, not licensed financial advice.'
    for end in range(len(text)+1):
        with patch('app.rag.research_answer.verify_grounding_claims', side_effect=approved):
            result = check_research_draft(text[:end], public_question='Apply?', decision=decision(),
                budget=CoachRequestBudget.start(), completion=LLMResult(text[:end], 'primary', finish_reason='length'))
        assert not result.is_valid
        if result.approved_text:
            assert result.diagnostics['requested_scope_covered'] is False
            for _, unit, _ in safe_draft_units(text[:end], finish_reason='length'):
                if not unit.endswith(':'):
                    assert '[S1]' in unit


def test_added_period_does_not_complete_dangling_phrase():
    assert not safe_draft_units('**Insight**\nYou need a copy of your spouse’s [S1].', finish_reason='length')


def test_expected_incompleteness_does_not_erase_verified_prefix():
    text = '**Insight**\nApply through the portal [S1]. You need a copy of your spouse’s'
    def verdict(claims, *_a, **_kw):
        return GroundingVerification({c.id: 'supported' for c in claims}, {c.id: 1 for c in claims},
            quality_errors=('incomplete_supported_answer',), requested_scope_covered=False,
            unanswered_requested_parts=('documents',))
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=verdict):
        result = check_research_draft(text, public_question='Apply?', decision=decision(),
            budget=CoachRequestBudget.start(), completion=LLMResult(text, 'primary', finish_reason='length'))
    assert 'Apply through the portal' in (result.approved_text or '')
    assert not result.is_valid
