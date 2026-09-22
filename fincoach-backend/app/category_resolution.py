"""Resolve a category phrase in a coach message against the user's real categories.

A single pure resolver is shared by single-period and multi-period reads. It is
given the user's actual category names (loaded once by the caller through the
existing owner/shared-category scope) so it can:

* match a complete category name inside a category phrase, supporting both
  "Food spending" and "spending on Food";
* prefer the longest complete match, so "Public Transport" wins over "Transport";
* separate date phrases first, so "spending on Food across July to September"
  resolves to Food, not "Food Across July To September".

It returns one of three outcomes, and never turns an unknown category into an
unfiltered query — an unrecognised category asks for clarification instead:

* ``none``       — no category was requested; the caller uses all categories.
* ``resolved``   — exactly one real category; the caller filters every period.
* ``unresolved`` — a category was named but does not match; clarify (with a
  "did you mean" suggestion when one is close).

No database access and no LLM call: pure text over a supplied name list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Iterable, Literal

# Month names (English + common Malay) plus the connectives that glue a date
# range together. Removing these first stops a trailing period from being read
# as part of the category name.
_MONTH_WORDS = (
    "january|jan|januari|february|feb|februari|march|mar|mac|april|apr|may|mei|"
    "june|jun|july|jul|julai|august|aug|ogos|september|sep|sept|october|oct|"
    "oktober|okt|november|nov|december|dec|disember|dis"
)
_DATE_NOISE = re.compile(
    r"\b(?:for|in|bulan)?\s*(?:" + _MONTH_WORDS + r")\b(?:\s+20\d{2})?"
    r"|\b20\d{2}\b"
    r"|\b\d{4}-\d{2}(?:-\d{2})?\b"
    r"|\b(?:this|last|next|previous)\s+month\b"
    r"|\bbulan\s+(?:ini|lepas|depan)\b"
    r"|\b(?:today|yesterday|tomorrow|hari\s+ini|semalam|esok)\b"
    r"|\b(?:the\s+)?(?:last|past|previous|recent)\s+\w+\s+months?\b"
    r"|\b(?:across|through|thru|between|from|since|until|till|to|hingga|sampai)\b",
    re.IGNORECASE,
)

# A category phrase: either "<verb> on/for <cat>" or "<cat> spending/budget/...".
_CATEGORY_SLOT = re.compile(
    r"(?:\b(?:on|for|about|regarding|kategori|category|untuk)\s+(?P<lead>[\w&'\- ]{2,60}))"
    r"|(?P<trail>[\w&'\- ]{2,60}?)\s+(?:spending|spend|spent|expenses?|budget|"
    r"transactions?|belanja|perbelanjaan|bajet)\b",
    re.IGNORECASE,
)

# Words that never form a category on their own, so a slot made only of these is
# "no category requested" rather than an unknown one.
_STOPWORDS = frozenset(
    {
        "my", "your", "our", "the", "a", "an", "this", "that", "these", "those",
        "show", "tell", "give", "see", "view", "check", "compare", "me", "i",
        "what", "whats", "how", "much", "is", "are", "of", "in", "on", "for",
        "please", "current", "total", "all", "any", "some", "and", "with",
        "recorded", "spending", "budget", "breakdown", "summary",
    }
)


@dataclass(frozen=True)
class CategoryResolution:
    status: Literal["none", "resolved", "unresolved"]
    category: str | None = None
    requested: str | None = None
    suggestion: str | None = None


def _clean_names(available_categories: Iterable[str]) -> list[str]:
    seen: dict[str, str] = {}
    for raw in available_categories:
        name = " ".join(str(raw or "").split())
        if name:
            seen.setdefault(name.casefold(), name)
    # Longest first so the longest complete match is preferred.
    return sorted(seen.values(), key=lambda name: (-len(name), name.casefold()))


def _strip_dates(message: str) -> str:
    return " ".join(_DATE_NOISE.sub(" ", message).split())


def _slot_candidate(text: str) -> str | None:
    match = _CATEGORY_SLOT.search(text)
    if not match:
        return None
    raw = match.group("lead") or match.group("trail") or ""
    tokens = [token for token in re.split(r"[\s]+", raw.strip()) if token]
    kept = [token for token in tokens if token.casefold() not in _STOPWORDS]
    if not kept:
        return None
    return " ".join(kept)


def resolve_category_phrase(
    message: str,
    available_categories: Iterable[str],
) -> CategoryResolution:
    names = _clean_names(available_categories)
    text = _strip_dates(" ".join((message or "").split()))
    if not text:
        return CategoryResolution(status="none")

    # 1) Longest complete category name mentioned as a whole word wins.
    for name in names:  # already sorted longest-first
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
            return CategoryResolution(status="resolved", category=name)

    # 2) No known category matched. If a category phrase names something real to
    #    the user, it is unknown/ambiguous — clarify rather than drop the filter.
    candidate = _slot_candidate(text)
    if candidate:
        suggestion = get_close_matches(candidate, names, n=1, cutoff=0.6)
        return CategoryResolution(
            status="unresolved",
            requested=candidate,
            suggestion=suggestion[0] if suggestion else None,
        )

    # 3) No category was requested.
    return CategoryResolution(status="none")
