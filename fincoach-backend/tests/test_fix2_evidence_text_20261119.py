"""Fix 2 (2026-11-19): a sentence pointing at a missing list removes only itself.

Independent facts around it are kept as separate literal spans, a conditional
intro still drops the whole piece, and complete short answers / passive
"provided." endings are kept.
"""
import pytest

from app.rag.evidence_text import complete_evidence_passages


def _assert_literal(passages, source):
    for passage in passages:
        assert passage in source


def test_facts_after_a_missing_list_intro_are_kept_as_separate_spans():
    source = ("Borrowers who pay in full get a discount. The schedule is shown below. "
              "The charge is 1% per year.")
    passages = complete_evidence_passages(source)
    assert passages == ("Borrowers who pay in full get a discount.", "The charge is 1% per year.")
    _assert_literal(passages, source)


def test_a_following_intro_without_list_is_removed_but_later_facts_stay():
    source = "Apply online. Use the following steps. Applications close on 30 June."
    passages = complete_evidence_passages(source)
    assert passages == ("Apply online.", "Applications close on 30 June.")
    _assert_literal(passages, source)


@pytest.mark.parametrize("source", [
    "Applicants may apply. The following conditions:\nEligible",
    "Applicants may apply. The following conditions apply.",
    "Applicants may apply. You are eligible if the following are met. Fees are waived.",
])
def test_a_conditional_intro_never_leaves_an_unconditional_rule(source):
    passages = complete_evidence_passages(source)
    assert "Applicants may apply." not in passages
    assert passages == ()


def test_short_malay_answer_to_a_question_is_complete():
    source = "Is the loan interest-free? Tidak."
    assert complete_evidence_passages(source) == (source,)
    assert complete_evidence_passages("Adakah pinjaman ini percuma? J: Bukan.") == (
        "Adakah pinjaman ini percuma? J: Bukan.",)


@pytest.mark.parametrize("source", [
    "Supporting documents must be provided.",
    "A receipt is provided.",
])
def test_passive_provided_sentence_is_complete(source):
    assert complete_evidence_passages(source) == (source,)


@pytest.mark.parametrize("source", [
    "Applicants cannot.",
    "You must.",
    "Apply if",
    "The discount is given provided that",
    "Tidak.",
    "The answer is tidak",
])
def test_unfinished_rules_are_still_dropped(source):
    assert complete_evidence_passages(source) == ()


def test_colon_intro_still_drops_the_unverifiable_content_after_it():
    source = "Fees are RM10. Pay using the following methods: cash and"
    passages = complete_evidence_passages(source)
    assert passages == ("Fees are RM10.",)
