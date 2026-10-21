from app.rag.grounding import _citation_supports_claim
from app.rag.answer_eval import AnswerCase, score_answer_counts, WEB_ANSWERABLE


def test_unrelated_passages_cannot_pool_claim_support():
    assert not _citation_supports_claim('Education loans cover tuition fees and living expenses.',
        ['Education loans cover tuition fees.', 'A separate allowance covers living expenses.'])


def test_conditional_category_cannot_disappear_or_swap():
    source = 'For foreign spouses, provide a passport copy and visa copy with the application.'
    assert not _citation_supports_claim('Provide a passport copy and visa copy with the application.', [source])
    assert not _citation_supports_claim('For citizen spouses, provide a passport copy and visa copy with the application.', [source])
    assert _citation_supports_claim(source, [source])


def test_misapplied_counts_as_answered_and_in_precision_denominator():
    cases = [AnswerCase('a', WEB_ANSWERABLE, 'q'), AnswerCase('b', WEB_ANSWERABLE, 'q')]
    result = score_answer_counts(cases, {'a': 'supported', 'b': 'misapplied'})
    assert result['schema_version'] == 2
    assert result['overall']['grounding_precision'] == .5
    assert result['overall']['misapplied_rate'] == .5
