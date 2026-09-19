"""Separate an answer's *presentation* from its *checkable statements*.

Task 2 of the evidence-validation re-architecture. The coach answer is a single
block of Markdown in a locked format (three headings, a fixed disclaimer). The
verifier (Task 4) and recovery loop (Task 5) need to reason about the individual
factual statements inside that block without disturbing the presented format.

This module provides:
- Typed contracts (`AnswerStatement`, `StatementAssessment`, `AnswerAssessment`)
  built on `StrictModel` (``extra="forbid"``).
- `split_answer_statements` — decompose a formatted answer into atomic,
  citation-preserving statements tagged by section.
- `format_coach_answer` — reassemble statements into the locked format and
  enforce the ≤120-word limit (which `validate_coach_answer` does NOT check).

Design invariant: ``format_coach_answer`` produces a *normal form*. For any
statements list produced by ``split_answer_statements`` on a valid answer,
``format(split(format(x))) == format(x)`` (idempotent), and the output passes
``validate_coach_answer``.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from app.models import StrictModel
from app.rag.grounding import (
    DISCLAIMER,
    REQUIRED_HEADINGS,
    _HEADING,
    _line_references,
    _PASSAGE_BOUNDARY,
    _SOURCE_MARKER,
)

# Sections that hold checkable prose. "Educational guidance" is boilerplate: its
# only content is the fixed disclaimer, so it is never a checkable statement.
_PROSE_HEADINGS = tuple(h for h in REQUIRED_HEADINGS if h != "Educational guidance")

_MAX_ANSWER_WORDS = 120
_TERMINAL_PUNCTUATION = (".", "!", "?")


class AnswerStatement(StrictModel):
    """One atomic statement lifted from a coach answer, with its citations.

    ``text`` is verbatim (markers included) so reassembly is lossless.
    ``cited_indices`` are the 1-based ``[Sn]`` source markers found in it.
    """

    id: int
    section: str
    text: str
    cited_indices: tuple[int, ...] = ()


class StatementAssessment(StrictModel):
    """The verifier's verdict for a single statement (produced in Task 4)."""

    statement_id: int
    verdict: Literal["supported", "unsupported", "needs_source"]
    entailed_by: int | None = None


class AnswerAssessment(StrictModel):
    """Roll-up over every statement's assessment plus the overall confidence."""

    statements: tuple[StatementAssessment, ...] = ()
    confidence: Literal["established", "reported", "anecdotal", "insufficient"]
    supported_count: int = Field(default=0, ge=0)
    unsupported_count: int = Field(default=0, ge=0)


def _strip_markers(text: str) -> str:
    """Drop ``[Sn]`` markers and bold asterisks for word counting/verification."""
    return _SOURCE_MARKER.sub("", text).replace("*", " ")


def count_answer_words(statements: list[AnswerStatement]) -> int:
    """Word count of the prose sections only (headings and disclaimer excluded).

    The ≤120-word rule targets the answer body. Headings are structure and the
    disclaimer is fixed boilerplate, so neither counts against the budget.
    """
    total = 0
    for statement in statements:
        if statement.section not in _PROSE_HEADINGS:
            continue
        total += len(_strip_markers(statement.text).split())
    return total


def split_answer_statements(answer: str) -> list[AnswerStatement]:
    """Decompose a formatted coach answer into atomic, cited statements.

    Uses the *same* heading/sentence/marker regexes as ``validate_coach_answer``
    so the decomposition tracks exactly what the validator sees. The fixed
    disclaimer line is treated as boilerplate, not a checkable statement.
    """
    statements: list[AnswerStatement] = []
    section = ""
    next_id = 1
    for raw_line in str(answer or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = _HEADING.fullmatch(line)
        if heading_match:
            section = heading_match.group(1).strip()
            continue
        if line == DISCLAIMER:
            continue
        line_indices = _line_references(line)
        for piece in _PASSAGE_BOUNDARY.split(line):
            piece = piece.strip()
            if not piece:
                continue
            piece_indices = _line_references(piece) or line_indices
            statements.append(
                AnswerStatement(
                    id=next_id,
                    section=section,
                    text=piece,
                    cited_indices=tuple(dict.fromkeys(piece_indices)),
                )
            )
            next_id += 1
    return statements


def _ensure_terminal(text: str) -> str:
    """Guarantee a statement ends in sentence punctuation so re-split recovers it.

    Without a terminal ``.!?`` the sentence-boundary regex would merge this
    statement with the next one on reassembly, breaking idempotency.
    """
    stripped = text.rstrip()
    if stripped.endswith(_TERMINAL_PUNCTUATION):
        return stripped
    return f"{stripped}."


def format_coach_answer(
    statements: list[AnswerStatement],
    *,
    max_words: int = _MAX_ANSWER_WORDS,
) -> str:
    """Reassemble statements into the locked 3-heading answer, enforcing length.

    The presented format is unchanged. Statements are grouped into their
    sections in the required heading order; the Educational-guidance section is
    always exactly the fixed disclaimer. If the prose exceeds ``max_words``,
    whole trailing statements are dropped — Recommended-action first, then
    Insight while keeping at least its first (answer) statement — so a citation
    marker is never orphaned mid-statement. The result is a stable normal form:
    splitting and re-formatting it yields the identical string.
    """
    placed: dict[str, list[AnswerStatement]] = {
        heading: [s for s in statements if s.section == heading]
        for heading in _PROSE_HEADINGS
    }

    def prose_words() -> int:
        body: list[AnswerStatement] = []
        for heading in _PROSE_HEADINGS:
            body.extend(placed[heading])
        return count_answer_words(body)

    # Drop least-critical trailing prose until within budget. Recommended-action
    # statements go before Insight; the first Insight statement (the answer) and
    # the disclaimer are always preserved.
    while prose_words() > max_words and placed.get("Recommended action"):
        placed["Recommended action"].pop()
    while prose_words() > max_words and len(placed.get("Insight", [])) > 1:
        placed["Insight"].pop()

    lines: list[str] = []
    for heading in REQUIRED_HEADINGS:
        lines.append(f"**{heading}**")
        if heading == "Educational guidance":
            lines.append(DISCLAIMER)
            continue
        section_statements = placed.get(heading, [])
        if section_statements:
            lines.append(
                " ".join(_ensure_terminal(s.text) for s in section_statements)
            )
    return "\n".join(lines)
