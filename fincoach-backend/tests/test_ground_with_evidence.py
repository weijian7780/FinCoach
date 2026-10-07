"""Task 5 — bounded evidence-mode recovery orchestrator (_ground_with_evidence).

`assess_answer` and `generate_fallback_result` are patched (no network / no LLM).
Covers: a fully-supported answer ships unchanged; an unsupported factual
statement is dropped and the answer reassembled; a repair runs at most once; when
nothing survives it routes to the safe insufficient-evidence fallback; and the
verifier is invoked at most twice (≤2 batches) across the whole recovery.
"""

from unittest import mock

from app.llm import CoachRequestBudget, LLMResult
from app.rag import service
from app.rag.answer_assessment import AnswerAssessment
from app.rag.answer_statements import (
    StatementAssessment,
    format_coach_answer,
    split_answer_statements,
)
from app.rag.grounding import DISCLAIMER
from app.rag.retrieval import RetrievedChunk


def _chunk(cid: int, content: str, confidence: str = "established") -> RetrievedChunk:
    return RetrievedChunk(
        id=cid, title="t", source="src", page_number=None, chunk_index=None,
        content=content, similarity=0.6, url="https://x.example",
        source_type="web", tier=1, confidence=confidence,
    )


def _answer(insight: str, action: str = "Track your spending each week.") -> str:
    return (
        f"**Insight**\n{insight}\n"
        f"**Recommended action**\n{action}\n"
        f"**Educational guidance**\n{DISCLAIMER}"
    )


def _assessment_for(content: str, verdicts: dict[int, str], confidence: str):
    statements = split_answer_statements(content)
    return AnswerAssessment(
        statements=tuple(
            StatementAssessment(
                statement_id=s.id,
                verdict=verdicts.get(s.id, "needs_source"),
                entailed_by=1 if verdicts.get(s.id) == "supported" else None,
            )
            for s in statements
        ),
        confidence=confidence,
        supported_count=sum(1 for v in verdicts.values() if v == "supported"),
        unsupported_count=sum(1 for v in verdicts.values() if v != "supported"),
    )


def _call(result_content: str, chunks, *, assess_side_effect, repair=None):
    kwargs = dict(
        chunks=chunks,
        prompt="PROMPT",
        verified_context="",
        allow_uncited_numbers=False,
        require_source_for_facts=True,
        budget=CoachRequestBudget.start(),
    )
    result = LLMResult(result_content, "test-model")
    with (
        mock.patch.object(service, "assess_answer", side_effect=assess_side_effect) as assess,
        mock.patch.object(
            service, "generate_fallback_result",
            return_value=repair if repair is not None else LLMResult("", "repair-model"),
        ) as gen,
    ):
        out = service._ground_with_evidence(result, **kwargs)
    return out, assess, gen


def test_fully_supported_answer_ships_unchanged():
    content = _answer("An emergency fund covers essentials [S1].")
    chunks = [_chunk(1, "An emergency fund covers essential living costs.")]

    def assess(statements, ch, **kw):
        # Every statement supported / advice kept.
        return _assessment_for(content, {1: "supported", 2: "needs_source"}, "established")

    (result, retry, fallback), assess_mock, gen_mock = _call(
        content, chunks, assess_side_effect=assess
    )
    assert fallback is False
    assert retry is False  # nothing dropped
    gen_mock.assert_not_called()  # no repair needed
    assert result.content.endswith(DISCLAIMER)
    assert "emergency fund" in result.content


def test_unsupported_statement_is_dropped_and_answer_rebuilt():
    # Two Insight sentences: the second is unsupported and must be dropped, the
    # first (supported) survives; no repair needed because a valid answer remains.
    content = _answer("A supported fact [S1]. An unsupported claim [S1].")
    chunks = [_chunk(1, "A supported fact holds here.")]
    statements = split_answer_statements(content)
    # ids: 1 supported, 2 unsupported (both Insight), 3 advice (Recommended action)
    verdicts = {statements[0].id: "supported", statements[1].id: "unsupported"}

    def assess(s, ch, **kw):
        return _assessment_for(content, {**verdicts, statements[2].id: "needs_source"}, "established")

    (result, retry, fallback), assess_mock, gen_mock = _call(
        content, chunks, assess_side_effect=assess
    )
    assert fallback is False
    assert retry is True  # a statement was dropped
    gen_mock.assert_not_called()  # reassembly succeeded without a repair
    assert "unsupported claim" not in result.content
    assert "supported fact" in result.content


def test_repair_runs_once_then_succeeds():
    bad = _answer("Fabricated rate is 99% [S1].")
    good = _answer("A verifiable fact [S1].")
    chunks = [_chunk(1, "A verifiable fact is stated in the source.")]
    bad_ids = split_answer_statements(bad)
    good_ids = split_answer_statements(good)

    calls = {"n": 0}

    def assess(statements, ch, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            # initial: the only Insight fact is unsupported -> nothing checkable survives
            return _assessment_for(bad, {bad_ids[0].id: "unsupported"}, "insufficient")
        # repair: supported
        return _assessment_for(good, {good_ids[0].id: "supported"}, "established")

    (result, retry, fallback), assess_mock, gen_mock = _call(
        bad, chunks, assess_side_effect=assess, repair=LLMResult(good, "repair-model")
    )
    assert fallback is False
    assert retry is True
    gen_mock.assert_called_once()  # exactly one repair
    assert assess_mock.call_count == 2  # ≤2 verifier batches (initial + repair)
    assert "verifiable fact" in result.content
    assert result.model == "repair-model"


def test_nothing_survives_routes_to_insufficient_fallback():
    bad = _answer("Fabricated fact [S1].")
    chunks = [_chunk(1, "Unrelated source text.")]
    bad_ids = split_answer_statements(bad)

    def assess(statements, ch, **kw):
        # Both initial and repair leave the Insight fact unsupported.
        target = split_answer_statements(statements[0].text) if False else None
        first_id = statements[0].id
        return _assessment_for_from(statements, {first_id: "unsupported"})

    def _assessment_for_from(statements, verdicts):
        return AnswerAssessment(
            statements=tuple(
                StatementAssessment(
                    statement_id=s.id,
                    verdict=verdicts.get(s.id, "needs_source"),
                    entailed_by=None,
                )
                for s in statements
            ),
            confidence="insufficient",
            supported_count=0,
            unsupported_count=len(statements),
        )

    (result, retry, fallback), assess_mock, gen_mock = _call(
        bad, chunks, assess_side_effect=assess, repair=LLMResult(bad, "repair-model")
    )
    assert fallback is True
    assert retry is True
    assert result.model == "fincoach-grounding-policy"
    # The safe fallback still emits the locked format + disclaimer.
    assert result.content.endswith(DISCLAIMER)
    assert assess_mock.call_count <= 2  # never more than two verifier batches
