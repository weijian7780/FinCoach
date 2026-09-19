"""Task 4 — per-statement entailment assessment.

The verifier is patched (no network). Covers: a fabricated claim with no entailing
source is rejected; a claim entailed by its source passes; the verifier runs AT
MOST once (one batch for all cited statements); an uncited statement is
`needs_source`; a verifier error fails closed; and the overall confidence is the
weakest confidence among the relied-upon sources.
"""

from unittest import mock

from app.llm import CoachRequestBudget
from app.rag.answer_assessment import assess_answer
from app.rag.answer_statements import AnswerStatement
from app.rag.retrieval import RetrievedChunk
from app.rag.verifier import GroundingVerification


def _web_chunk(cid: int, confidence: str, content: str = "web passage text") -> RetrievedChunk:
    return RetrievedChunk(
        id=cid, title="t", source="src", page_number=None, chunk_index=None,
        content=content, similarity=0.5, url="https://x.example",
        source_type="web", tier=1, confidence=confidence,
    )


def _corpus_chunk(cid: int, content: str = "corpus passage") -> RetrievedChunk:
    return RetrievedChunk(
        id=cid, title="t", source="corpus.md", page_number=None,
        chunk_index=0, content=content, similarity=0.8,
    )


def _budget() -> CoachRequestBudget:
    return CoachRequestBudget.start()


def test_supported_statement_passes_and_carries_entailing_source():
    statements = [AnswerStatement(id=1, section="Insight", text="A fact [S1].", cited_indices=(1,))]
    chunks = [_web_chunk(1, "established")]
    with mock.patch(
        "app.rag.answer_assessment.verify_grounding_claims",
        return_value=GroundingVerification({1: "supported"}, {1: 1}),
    ):
        assessment = assess_answer(
            statements, chunks, budget=_budget(), verifier_timeout_seconds=5.0
        )
    assert assessment.statements[0].verdict == "supported"
    assert assessment.statements[0].entailed_by == 1
    assert assessment.supported_count == 1
    assert assessment.confidence == "established"


def test_fabricated_claim_with_no_entailing_source_is_unsupported():
    statements = [AnswerStatement(id=1, section="Insight", text="Invented [S1].", cited_indices=(1,))]
    chunks = [_web_chunk(1, "established")]
    with mock.patch(
        "app.rag.answer_assessment.verify_grounding_claims",
        return_value=GroundingVerification({1: "unsupported"}, {}),
    ):
        assessment = assess_answer(
            statements, chunks, budget=_budget(), verifier_timeout_seconds=5.0
        )
    assert assessment.statements[0].verdict == "unsupported"
    assert assessment.confidence == "insufficient"
    assert assessment.unsupported_count == 1


def test_verifier_error_fails_closed():
    statements = [AnswerStatement(id=1, section="Insight", text="A fact [S1].", cited_indices=(1,))]
    chunks = [_web_chunk(1, "established")]
    with mock.patch(
        "app.rag.answer_assessment.verify_grounding_claims",
        return_value=GroundingVerification({}, error_code="verifier_unavailable"),
    ):
        assessment = assess_answer(
            statements, chunks, budget=_budget(), verifier_timeout_seconds=5.0
        )
    assert assessment.statements[0].verdict == "unsupported"


def test_uncited_statement_is_needs_source_and_not_sent_to_verifier():
    statements = [AnswerStatement(id=1, section="Insight", text="No citation here.")]
    with mock.patch(
        "app.rag.answer_assessment.verify_grounding_claims"
    ) as verify:
        assessment = assess_answer(
            statements, [], budget=_budget(), verifier_timeout_seconds=5.0
        )
    verify.assert_not_called()  # nothing cited -> no verifier call at all
    assert assessment.statements[0].verdict == "needs_source"
    assert assessment.confidence == "insufficient"


def test_verifier_runs_at_most_once_for_multiple_cited_statements():
    statements = [
        AnswerStatement(id=1, section="Insight", text="One [S1].", cited_indices=(1,)),
        AnswerStatement(id=2, section="Insight", text="Two [S1].", cited_indices=(1,)),
        AnswerStatement(id=3, section="Recommended action", text="Do a thing."),
    ]
    chunks = [_web_chunk(1, "reported")]
    with mock.patch(
        "app.rag.answer_assessment.verify_grounding_claims",
        return_value=GroundingVerification({1: "supported", 2: "supported"}, {1: 1, 2: 1}),
    ) as verify:
        assessment = assess_answer(
            statements, chunks, budget=_budget(), verifier_timeout_seconds=5.0
        )
    verify.assert_called_once()  # single batch for both cited statements
    # The two cited statements were passed together in that one call.
    passed_claims = verify.call_args.args[0]
    assert {c.id for c in passed_claims} == {1, 2}
    assert assessment.statements[2].verdict == "needs_source"
    assert assessment.supported_count == 2


def test_confidence_is_weakest_source_relied_upon():
    # Supported statements cite an established corpus source and an anecdotal web
    # source; the roll-up must report the weakest (anecdotal), never established.
    statements = [
        AnswerStatement(id=1, section="Insight", text="Corpus fact [S1].", cited_indices=(1,)),
        AnswerStatement(id=2, section="Insight", text="Forum claim [S2].", cited_indices=(2,)),
    ]
    chunks = [_corpus_chunk(1), _web_chunk(2, "anecdotal")]
    with mock.patch(
        "app.rag.answer_assessment.verify_grounding_claims",
        return_value=GroundingVerification({1: "supported", 2: "supported"}, {1: 1, 2: 2}),
    ):
        assessment = assess_answer(
            statements, chunks, budget=_budget(), verifier_timeout_seconds=5.0
        )
    assert assessment.confidence == "anecdotal"
