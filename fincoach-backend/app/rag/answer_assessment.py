"""Task 4 — verify each answer statement against its cited source, once.

Builds on Task 2's decomposition (`answer_statements`). Each `AnswerStatement`
with a citation becomes a `GroundingClaim` and is checked by the fail-closed
entailment verifier (`verify_grounding_claims`) in a SINGLE batch — so the
verifier runs at most once per turn, covering every statement. Statements with no
citation cannot be verified against a source and are marked `needs_source`.

The verifier gets the evidence-mode token budget so it can read a real extracted
passage instead of truncating (a truncated verifier fails closed and silently
degrades answers). The overall confidence is the *weakest* confidence among the
sources actually relied upon, so a mix of established + anecdotal is labeled
anecdotal — never dressed up as the higher tier (invariant #3).
"""

from __future__ import annotations

from app.config import GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS
from app.llm import CoachRequestBudget
from app.rag.answer_statements import (
    AnswerAssessment,
    AnswerStatement,
    StatementAssessment,
)
from app.rag.grounding import GroundingClaim
from app.rag.retrieval import RetrievedChunk
from app.rag.verifier import verify_grounding_claims

# Weakest -> strongest. The roll-up reports the weakest evidence relied upon.
_CONFIDENCE_ORDER = ("insufficient", "anecdotal", "reported", "established")
_CONFIDENCE_RANK = {name: rank for rank, name in enumerate(_CONFIDENCE_ORDER)}


def _chunk_confidence(chunk: RetrievedChunk) -> str:
    """Confidence label for one source chunk. Corpus is treated as established."""
    if getattr(chunk, "source_type", "corpus") != "web":
        return "established"  # curated corpus is the trusted internal source
    return getattr(chunk, "confidence", None) or "insufficient"


def _weakest(labels: list[str]) -> str:
    """Return the least-authoritative confidence among ``labels``."""
    if not labels:
        return "insufficient"
    return min(labels, key=lambda label: _CONFIDENCE_RANK.get(label, 0))


def assess_answer(
    statements: list[AnswerStatement],
    chunks: list[RetrievedChunk],
    *,
    budget: CoachRequestBudget,
    verifier_timeout_seconds: float,
    max_tokens: int = GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS,
) -> AnswerAssessment:
    """Assess every statement against its cited source in one verifier batch.

    - A statement with no cited source -> ``needs_source`` (unverifiable here).
    - Cited statements are verified together in ONE call; a statement whose cited
      source does not entail it -> ``unsupported`` (fails closed on verifier
      error too). A statement entailed by its source -> ``supported``.
    - Overall confidence = weakest confidence among the sources that actually
      entailed a supported statement; ``insufficient`` if nothing is supported.
    """
    reference_contents = [chunk.content for chunk in chunks]
    cited = [s for s in statements if s.cited_indices]
    uncited = [s for s in statements if not s.cited_indices]

    verdicts: dict[int, str] = {}
    entailed_by: dict[int, int | None] = {}

    if cited:
        claims = [
            GroundingClaim(
                id=statement.id,
                text=statement.text,
                cited_indices=statement.cited_indices,
                requires_citation=False,
            )
            for statement in cited
        ]
        verification = verify_grounding_claims(
            claims,
            reference_contents,
            timeout_seconds=min(
                verifier_timeout_seconds, budget.timeout_for("verifier")
            ),
            max_tokens=max_tokens,
        )
        for statement in cited:
            verdict = verification.verdicts.get(statement.id)
            # Fail closed: any non-"supported" verdict, or a verifier error
            # (empty verdicts), makes the statement unsupported.
            if verdict == "supported":
                verdicts[statement.id] = "supported"
                entailed_by[statement.id] = verification.source_indices.get(
                    statement.id
                )
            else:
                verdicts[statement.id] = "unsupported"
                entailed_by[statement.id] = None

    for statement in uncited:
        verdicts[statement.id] = "needs_source"
        entailed_by[statement.id] = None

    assessments = tuple(
        StatementAssessment(
            statement_id=statement.id,
            verdict=verdicts[statement.id],  # type: ignore[arg-type]
            entailed_by=entailed_by[statement.id],
        )
        for statement in statements
    )

    supported = [a for a in assessments if a.verdict == "supported"]
    relied_confidences = [
        _chunk_confidence(chunks[a.entailed_by - 1])
        for a in supported
        if a.entailed_by is not None and 1 <= a.entailed_by <= len(chunks)
    ]
    confidence = _weakest(relied_confidences) if supported else "insufficient"

    return AnswerAssessment(
        statements=assessments,
        confidence=confidence,  # type: ignore[arg-type]
        supported_count=len(supported),
        unsupported_count=sum(
            1 for a in assessments if a.verdict in ("unsupported", "needs_source")
        ),
    )
