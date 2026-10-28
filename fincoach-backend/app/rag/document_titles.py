"""Deterministic resolution of published knowledge-document titles.

The curated topic catalogue (``query_analysis.KNOWLEDGE_TOPICS``) covers the
official finance corpus. Documents an admin publishes later have no aliases, so
a question that names one ("what is a1 group") only reaches it through its
title. This module is pure: callers supply the published (source, title) rows,
and matching is against real titles only, never a list of intent keywords.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.rag.query_analysis import normalise_knowledge_text

# File-name leftovers only: a trailing upload extension and repeated copy
# markers such as " (1) (1)" or " - Copy". Numbers inside a title ("Budget
# 2026", "a1") are meaningful and are kept.
_EXTENSION = re.compile(r"\.(?:md|markdown|txt|pdf|docx?)\s*$", re.IGNORECASE)
_COPY_MARKERS = re.compile(r"(?:\s*(?:\(\d{1,3}\)|-\s*copy(?:\s*\(\d{1,3}\))?))+\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class DocumentTitleMatch:
    source: str
    title: str
    cleaned_title: str


def clean_document_title(title: str) -> str:
    """Normalise a stored title, removing only upload/file-name leftovers."""
    text = _EXTENSION.sub("", str(title or "").strip())
    text = _COPY_MARKERS.sub("", text)
    text = text.replace("_", " ")
    return normalise_knowledge_text(text)


# Words that only point at the document itself ("the a1 group document").
_DOCUMENT_REFERENCE_WORDS = frozenset(
    "the this that my a an document doc file guide notes note pdf brief handout".split())


def topic_is_document(topic: str, match: DocumentTitleMatch) -> bool:
    """Whether the interpreted topic IS the named document, not something in it.

    "a1 group" or "the a1 group document" ask about the document; "amortisation
    in student money guide" asks about amortisation, using that document.
    """
    padded = f" {normalise_knowledge_text(topic)} "
    if f" {match.cleaned_title} " not in padded:
        return False
    rest = padded.replace(f" {match.cleaned_title} ", " ", 1).split()
    return all(word in _DOCUMENT_REFERENCE_WORDS for word in rest)


def resolve_document_titles(
    text: str,
    documents: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    *,
    excluded_sources: frozenset[str] = frozenset(),
) -> tuple[DocumentTitleMatch, ...]:
    """Documents whose WHOLE cleaned title appears in ``text`` with word boundaries.

    A fragment ("group", "a1") never matches "a1 group". When one matching title
    contains another ("budget" inside "budget 2026"), only the longer, more
    specific title is kept. More than one remaining match is ambiguous and is
    returned as-is for the caller to clarify.
    """
    padded = f" {normalise_knowledge_text(text)} "
    if not padded.strip():
        return ()
    matches: dict[str, DocumentTitleMatch] = {}
    for source, title in documents:
        if not source or source in excluded_sources or source in matches:
            continue
        cleaned = clean_document_title(title)
        if len(cleaned) < 2 or f" {cleaned} " not in padded:
            continue
        matches[source] = DocumentTitleMatch(source, str(title), cleaned)
    specific = [
        match for match in matches.values()
        if not any(other.cleaned_title != match.cleaned_title
                   and f" {match.cleaned_title} " in f" {other.cleaned_title} "
                   for other in matches.values())
    ]
    return tuple(sorted(specific, key=lambda match: (-len(match.cleaned_title), match.source)))
