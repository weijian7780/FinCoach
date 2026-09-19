"""Task 2 — decomposition/reassembly of coach answers.

Covers: split preserves section + `[Sn]` markers; `format_coach_answer` output
passes `validate_coach_answer`; the reassembly is an idempotent normal form; the
≤120-word cap is enforced by dropping whole statements (never mid-statement); and
the new StrictModel contracts forbid extra fields.
"""

import pytest
from pydantic import ValidationError

from app.rag.answer_statements import (
    AnswerAssessment,
    AnswerStatement,
    StatementAssessment,
    count_answer_words,
    format_coach_answer,
    split_answer_statements,
)
from app.rag.grounding import DISCLAIMER, validate_coach_answer


def _valid_answer() -> str:
    return format_coach_answer(
        [
            AnswerStatement(id=1, section="Insight", text="An emergency fund covers essentials [S1]."),
            AnswerStatement(id=2, section="Insight", text="It reduces reliance on debt [S1]."),
            AnswerStatement(id=3, section="Recommended action", text="Set aside a small amount each week."),
        ]
    )


# Source text lexically supports BOTH cited Insight sentences. The formatter joins
# same-section sentences onto one line, so `validate_coach_answer` attributes the
# line's `[S1]` to each sentence on it and checks each against this source.
_SUPPORTING_REFERENCE = (
    "An emergency fund covers essential living costs and reduces reliance on debt."
)


def test_split_preserves_section_and_markers():
    answer = (
        "**Insight**\n"
        "An emergency fund covers essentials [S1]. It reduces debt reliance.\n"
        "**Recommended action**\n"
        "Save a little weekly.\n"
        "**Educational guidance**\n"
        f"{DISCLAIMER}"
    )
    statements = split_answer_statements(answer)

    # The disclaimer is boilerplate, not a checkable statement.
    assert [s.section for s in statements] == [
        "Insight",
        "Insight",
        "Recommended action",
    ]
    # Sentence 1 carries its own marker; sentence 2 shares the line, so it
    # inherits the line's citation — exactly how validate_coach_answer attributes it.
    assert statements[0].cited_indices == (1,)
    assert statements[1].cited_indices == (1,)
    assert "[S1]" in statements[0].text
    # ids are assigned in reading order and unique.
    assert [s.id for s in statements] == [1, 2, 3]


def test_format_output_passes_validate_coach_answer():
    answer = _valid_answer()
    result = validate_coach_answer(answer, [_SUPPORTING_REFERENCE], "")
    assert result.is_valid, result.errors
    assert answer.endswith(DISCLAIMER)


def test_format_is_an_idempotent_normal_form():
    answer = _valid_answer()
    once = format_coach_answer(split_answer_statements(answer))
    twice = format_coach_answer(split_answer_statements(once))
    assert once == twice == answer


def test_word_cap_drops_recommended_action_before_insight():
    # "save"/"track" carry no _EXTERNAL_FACT_CUE and no numbers, so the trimmed
    # answer needs no citation to stay valid.
    long_action = " ".join(["save"] * 200)
    statements = [
        AnswerStatement(id=1, section="Insight", text="Track your spending each week."),
        AnswerStatement(id=2, section="Recommended action", text=long_action),
    ]
    formatted = format_coach_answer(statements)
    reparsed = split_answer_statements(formatted)

    # The over-long Recommended action is dropped; the Insight answer survives.
    assert count_answer_words(reparsed) <= 120
    assert any(s.section == "Insight" for s in reparsed)
    assert not any(s.section == "Recommended action" for s in reparsed)
    # Still a valid, disclaimer-terminated answer after trimming.
    assert validate_coach_answer(formatted, [], "").is_valid


def test_word_cap_keeps_first_insight_even_if_over_budget():
    # A single oversized Insight statement is kept (never truncated mid-statement).
    huge = " ".join(["money"] * 200)
    statements = [AnswerStatement(id=1, section="Insight", text=huge)]
    formatted = format_coach_answer(statements)
    reparsed = split_answer_statements(formatted)
    assert len(reparsed) == 1
    assert reparsed[0].section == "Insight"


def test_count_answer_words_ignores_markers_headings_disclaimer():
    statements = [
        AnswerStatement(id=1, section="Insight", text="**Bold** fact here [S1]."),
    ]
    # "Bold fact here ." -> markers/asterisks stripped, 4 tokens counted.
    assert count_answer_words(statements) == 4


def test_strict_models_forbid_extra_fields():
    with pytest.raises(ValidationError):
        AnswerStatement(id=1, section="Insight", text="x", bogus=True)
    with pytest.raises(ValidationError):
        StatementAssessment(statement_id=1, verdict="supported", extra="no")
    with pytest.raises(ValidationError):
        AnswerAssessment(confidence="established", junk=1)


def test_statement_assessment_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        StatementAssessment(statement_id=1, verdict="maybe")
