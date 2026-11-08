"""Display keeps partial diagnostics but never appends a code gap note."""
from dataclasses import replace
from unittest.mock import patch
import pytest
from app.llm import CoachRequestBudget
from app.rag import research_answer as answer
from app.rag.grounding import DISCLAIMER
from app.rag.verifier import GroundingVerification
from test_research_notice_regression import check, evidence, verdict, draft, FACT, EXTRA


def test_q5_purpose_still_has_a_sentence_after_another_is_removed():
    result = check(verdict(mappings=(("p1", (1, 2)),)))
    assert not result.is_valid
    assert result.diagnostics['requested_scope_covered'] is False
    assert result.diagnostics['addressed_part_ids'] == ['p1']
    assert not result.diagnostics['gap_note_added']
    assert answer._DETAIL_LEFT_OUT['en'] not in result.approved_text
    assert 'separate container' not in result.approved_text


def test_q2_all_approved_broad_coverage_failure_is_not_a_gap():
    result = check(GroundingVerification({1:'supported',2:'supported'}, {1:1,2:1},
        requested_scope_covered=False, answered_part_claims=(("p1", (1,2)),)))
    assert not result.is_valid  # Existing recovery/completeness gate remains.
    assert not result.diagnostics['gap_note_added']
    assert answer._DETAIL_LEFT_OUT['en'] not in result.approved_text


def test_single_requested_part_with_zero_surviving_sentences_gets_no_note():
    result = check(verdict(mappings=(("p1", (2,)),)))
    assert result.diagnostics['gap_note_parts'] == ['What is a reserve fund?']
    assert not result.diagnostics['gap_note_added']
    assert answer._DETAIL_LEFT_OUT['en'] not in result.approved_text


def test_multiple_parts_name_the_one_without_a_sentence_only_in_diagnostics():
    result = check(verdict(mappings=(("p1", (1,)), ("p2", (2,))),
                           answered=("p1", "p2")), evidence(second_part=True))
    assert result.diagnostics['gap_note_parts'] == ['Where is it kept?']
    assert '“Where is it kept?”' not in result.approved_text
    assert '“What is a reserve fund?”' not in result.approved_text
    assert answer._DETAIL_LEFT_OUT['en'] not in result.approved_text


def test_q10_surviving_assessment_note_prevents_duplicate():
    text = f'**Insight**\n{FACT[:-1]} [S1].\n\nI have not confirmed where it is kept.\n\n**Educational guidance**\n{DISCLAIMER}'
    decision = evidence(second_part=True)
    decision = replace(decision, assessment=replace(decision.assessment,
        status='partial', missing=('Where is it kept?',), parts=(decision.assessment.parts[0],
        replace(decision.assessment.parts[1], status='missing', complete=False))))
    result = GroundingVerification({1:'supported',2:'supported'}, {1:1},
        requested_scope_covered=False, assessment_supported_ids=(2,),
        answered_part_claims=(("p1", (1,)), ("p2", ())))
    with patch.object(answer,'verify_grounding_claims',return_value=result):
        checked=answer.check_research_draft(text, public_question='What is a reserve fund and where is it kept?',
            decision=decision,budget=CoachRequestBudget.start())
    assert checked.approved_text
    assert 'I have not confirmed where it is kept.' in checked.approved_text
    assert 'fully confirm and explain' not in checked.approved_text
    assert not checked.diagnostics['gap_note_added']


@pytest.mark.parametrize('body', ['Ini panduan pendidikan, bukan nasihat kewangan berlesen.',
    'This is educational information.', DISCLAIMER])
def test_exact_disclaimer_repair_reused(body):
    prefix='**Insight**\nA supported fact [S1].\n\n**Educational guidance**\n'
    assert answer.normalize_research_layout(prefix+body)==prefix+DISCLAIMER


def test_disclaimer_preserves_following_duplicate_heading():
    text='**Insight**\nA fact [S1].\n\n**Educational guidance**\nTerjemahan.\n\n**Insight**\nAnother fact [S1].'
    fixed=answer.normalize_research_layout(text)
    assert fixed.count('**Insight**')==2 and 'Another fact [S1].' in fixed
    assert DISCLAIMER in fixed and 'Terjemahan.' not in fixed
