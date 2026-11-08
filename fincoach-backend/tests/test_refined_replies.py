from app.rag.grounding import safe_product_redirect
from app.rag.research_answer import _partial_notice, _DETAIL_LEFT_OUT, _failure_reply


def test_refusal_uses_interpreted_locale_or_english_for_outage():
    assert safe_product_redirect() == safe_product_redirect("en")
    assert "FinCoach menerangkan" in safe_product_redirect("ms-MY")
    assert len({safe_product_redirect(lang) for lang in ("en", "ms", "zh", "ta")}) == 4


def test_resolved_whole_question_is_not_a_missing_detail():
    question = "Terangkan perkara ini.\nResponse language: ms"
    assert _partial_notice(question, ("Describe this",), "Describe this?") == _DETAIL_LEFT_OUT["ms"]
    assert "fees" in _partial_notice(question, ("fees",), part_count=2)


def test_unknown_and_exhausted_time_get_distinct_messages():
    assert _failure_reply("en", (), ("research_time_exhausted",))[0] == "technical"
    assert _failure_reply("en", (), ("unrecognised_code",))[0] == "unknown"
