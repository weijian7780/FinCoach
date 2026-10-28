"""Resolve a category phrase in a coach message against the user's real categories.

Separates financial intent, period, and a genuine *category reference*. Leftover
words are never turned into a category name: an unfamiliar phrase sitting in a
category slot becomes ``needs_interpretation`` (a bounded AI fallback, disabled by
default) rather than a false filter or a silent unfiltered read.

Outcomes:

* ``none``               — no category was requested; caller uses all categories.
* ``resolved``           — exactly one real category; caller filters on it.
* ``unresolved``         — an explicit/quoted name is unknown; clarify.
* ``ambiguous``          — multiple names, duplicate names, or a month/category
  collision; clarify (never silently pick the first).
* ``needs_interpretation`` — an unfamiliar phrase might be a category; hand to the
  bounded interpreter when enabled, otherwise clarify.

Pure text over a supplied name list: no database access and no LLM call.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Iterable, Literal

# Month tokens (English + common Malay). Used both to strip date noise and to
# detect a month/category collision (a category literally named "May").
_MONTH_TOKENS = frozenset({
    "january", "jan", "januari", "february", "feb", "februari", "march", "mar",
    "mac", "april", "apr", "may", "mei", "june", "jun", "july", "jul", "julai",
    "august", "aug", "ogos", "september", "sep", "sept", "october", "oct",
    "oktober", "okt", "november", "nov", "december", "dec", "disember", "dis",
})
_MONTH_WORDS = "|".join(sorted(_MONTH_TOKENS, key=len, reverse=True))
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
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
# An explicit marker ("category X", "kategori X") or a double-quoted name makes X
# a deliberate category reference: an unknown one clarifies (never interprets),
# and a real name survives date parsing (so "category May" is the category May).
# The lookahead rejects the common-noun senses ("category limit for X", "which
# category needs a budget") so only a genuine "category <name>" is treated as one.
_MARKER_STOP = (
    r"limit|limits|budget|budgets|cap|caps|need|needs|should|could|can|is|are|"
    r"was|were|that|which|do|does|has|have|for|to|with|of|the|a|an|am|had|will"
)
_EXPLICIT_MARKER = re.compile(
    r"\b(?:category|categories|kategori)\s*:?\s+"
    r"(?!(?:" + _MARKER_STOP + r")\b)"
    r"(?P<name>[\w&'\-.]+(?:\s+[\w&'\-.]+){0,3})",
    re.IGNORECASE,
)
_QUOTED = re.compile(
    r"[\"“”]\s*(?P<name>[\w&'\-. ]{1,60}?)\s*[\"“”]"
)

# A category slot is a grammatical position, not "any leftover word". Lead: a
# preposition introduces the name ("on/for Food"). Trail: the name precedes a
# metric noun ("Food spending/budget/transactions").
_LEAD_SLOT = re.compile(
    r"\b(?:on|for|about|regarding|untuk)\s+(?P<lead>[\w&'\-. ]{2,60})",
    re.IGNORECASE,
)
_TRAIL_SLOT = re.compile(
    r"(?P<trail>[\w&'\-. ]{2,60}?)\s+(?:spending|spend|spent|expenses?|budget|"
    r"transactions?|belanja|perbelanjaan|bajet)\b",
    re.IGNORECASE,
)
_AND_SPLIT = re.compile(r"\s*(?:,|&|\band\b|\bdan\b)\s*", re.IGNORECASE)

# Words that never form a category on their own. A reference reduced to only
# these is "no category" (or a status/period question), not an unknown category.
# Status and period words live here so "over budget" and "this week" resolve to
# ``none`` deterministically, without inventing a filter.
FILLERS = frozenset({
    "my", "your", "our", "the", "a", "an", "this", "that", "these", "those",
    "me", "i", "we", "us", "what", "whats", "which", "who", "where", "when",
    "why", "how", "much", "is", "are", "am", "was", "were", "be", "been",
    "being", "do", "does", "did", "have", "has", "had", "of", "in", "on", "at",
    "to", "by", "with", "and", "or", "for",
    "show", "tell", "give", "see", "view", "check", "compare", "please", "find",
    "list", "get", "display", "tunjuk", "tunjukkan", "papar", "paparkan",
    "lihat", "berapa", "saya", "aku", "kami",
    "recorded", "spending", "spend", "spent", "budget", "bajet", "breakdown",
    "summary", "category", "categories", "kategori", "expense", "expenses",
    "cost", "costs", "transaction", "transactions", "transaksi", "belanja",
    "perbelanjaan", "total", "all", "any", "some", "current", "overall",
    "many", "number", "count",
    "most", "least", "highest", "lowest", "top", "bottom", "more", "less",
    "biggest", "largest", "smallest",
    "over", "under", "within", "exceed", "exceeded", "exceeding", "remaining",
    "left", "still", "track",
    "monthly", "weekly", "daily", "annual", "yearly", "recent", "now", "week",
    "weeks", "day", "days", "month", "months", "year", "years", "fortnight",
    "quarter", "ini", "lepas", "depan", "bulan", "minggu", "hari", "tahun",
    "last", "latest", "first", "past",
    "can", "could", "should", "would", "cut", "reduce", "plan", "need", "needs",
    "limit", "limits", "add", "set", "save", "create", "recommend", "suggest",
    "deserve", "help", "decide", "choose", "pick", "put", "another", "new",
    # Hesitation and conversational particles ("erm spend", "how much lah").
    "erm", "um", "umm", "uh", "uhh", "er", "hmm", "ah", "eh", "lah", "leh", "meh",
})
_CATEGORY_RANKING_QUERY = re.compile(
    r"\b(?:most|highest|top|biggest|largest)\s+(?:(?:spending|expense)\s+)?categor(?:y|ies)\b|"
    r"\bcategor(?:y|ies)\b.{0,45}\b(?:most|highest|top|biggest|largest)\b",
    re.IGNORECASE,
)


def is_category_ranking_query(message: str) -> bool:
    """Recognise an expense-category ranking, shared by routing and follow-ups.

    This identifies intent only. It must never discard a separately requested
    (possibly unknown) category filter.
    """
    return bool(_CATEGORY_RANKING_QUERY.search(message))


@dataclass(frozen=True)
class CategoryResolution:
    status: Literal["none", "resolved", "unresolved", "ambiguous", "needs_interpretation"]
    category: str | None = None
    requested: str | None = None
    suggestion: str | None = None


def _clean_names(available_categories: Iterable[str]) -> list[str]:
    names: list[str] = []
    for raw in available_categories:
        name = " ".join(str(raw or "").split())
        if name:
            names.append(name)
    # Longest first so the longest complete match is preferred.
    return sorted(names, key=lambda name: (-len(name), name.casefold()))


def _index(names: list[str]) -> tuple[dict[str, str], Counter]:
    """Map casefolded name -> display name, and count duplicates (distinct rows)."""
    index: dict[str, str] = {}
    counts: Counter = Counter()
    for name in names:
        key = " ".join(name.split()).casefold()
        counts[key] += 1
        index.setdefault(key, name)
    return index, counts


def _strip_dates(message: str) -> str:
    return " ".join(_DATE_NOISE.sub(" ", message).split())


def _reduce(phrase: str) -> str:
    """Drop filler/status/period words and numeric counts/amounts, leaving only
    candidate category tokens. A count ("5") or an amount ("RM25") is a search
    filter, never a category name."""
    tokens = re.findall(r"[\w&'\-.]+", phrase)
    kept = [
        token for token in tokens
        if token.casefold() not in FILLERS
        and not re.fullmatch(r"rm\d+(?:\.\d+)?", token, re.IGNORECASE)
        and not re.fullmatch(r"\d+(?:\.\d+)?", token)
    ]
    return " ".join(kept)


def _match(phrase: str, index: dict[str, str], counts: Counter) -> tuple[str, str] | None:
    key = " ".join(phrase.split()).casefold()
    if not key or key not in index:
        return None
    return ("ambiguous" if counts[key] > 1 else "resolved"), index[key]


def _marker_name(raw: str) -> str:
    # Trim a trailing period phrase ("category Food this month" -> "Food") but
    # keep a bare month name that is itself the category ("category May").
    trimmed = _strip_dates(raw).strip()
    return trimmed or " ".join(raw.split())
def _classify(
    phrase: str,
    *,
    marked: bool,
    is_lead: bool,
    index: dict[str, str],
    counts: Counter,
    message: str,
) -> CategoryResolution:
    # An explicitly marked/quoted name is a deliberate reference: match it as
    # given (no date stripping), and an unknown one clarifies, never interprets.
    if marked:
        name = " ".join(phrase.split())
        match = _match(name, index, counts)
        if match:
            return CategoryResolution(
                match[0], category=match[1] if match[0] == "resolved" else None,
                requested=match[1],
            )
        suggestion = get_close_matches(name, list(index.values()), n=1, cutoff=0.6)
        return CategoryResolution(
            "unresolved", requested=name or None,
            suggestion=suggestion[0] if suggestion else None,
        )

    reduced_raw = _reduce(phrase)

    # Month/category collision: a bare month word (kept before date stripping) is
    # a period unless it is also a real category and nothing pins it to a date.
    mono = reduced_raw.casefold().strip()
    if mono in _MONTH_TOKENS:
        if _YEAR.search(message):
            return CategoryResolution("none")
        if mono in index:
            return CategoryResolution("ambiguous", requested=index[mono])
        return CategoryResolution("none")

    # Strip date noise before matching so "September food" resolves to Food.
    stripped = _strip_dates(phrase).strip()
    reduced = _reduce(stripped)
    probe = stripped if is_lead else reduced
    match = _match(probe, index, counts)
    if match is None and is_lead:
        match = _match(reduced, index, counts)
    if match:
        return CategoryResolution(
            match[0], category=match[1] if match[0] == "resolved" else None,
            requested=match[1],
        )

    # Two or more names joined by "and"/"&"/comma: one filter cannot serve both.
    parts = [part for part in _AND_SPLIT.split(stripped) if _reduce(part).strip()]
    if len(parts) >= 2:
        return CategoryResolution("ambiguous")

    if not reduced.strip():
        return CategoryResolution("none")

    suggestion = get_close_matches(reduced, list(index.values()), n=1, cutoff=0.6)
    return CategoryResolution(
        "needs_interpretation", requested=reduced,
        suggestion=suggestion[0] if suggestion else None,
    )


def resolve_category_phrase(
    message: str,
    available_categories: Iterable[str],
) -> CategoryResolution:
    index, counts = _index(_clean_names(available_categories))
    text = " ".join((message or "").split())
    if not text:
        return CategoryResolution(status="none")

    # A ranking/selection question ("which category ... most") names no specific
    # category. Checked first so the interrogative "which category" is not read
    # as an explicit "category X" marker.
    if is_category_ranking_query(text):
        return CategoryResolution(status="none")

    marker = _EXPLICIT_MARKER.search(text)
    if marker:
        return _classify(_marker_name(marker.group("name")), marked=True,
                         is_lead=True, index=index, counts=counts, message=text)
    quoted = _QUOTED.search(text)
    if quoted:
        return _classify(quoted.group("name"), marked=True, is_lead=True,
                         index=index, counts=counts, message=text)

    candidates = [
        _classify(match.group("lead"), marked=False, is_lead=True,
                  index=index, counts=counts, message=text)
        for match in _LEAD_SLOT.finditer(text)
    ] + [
        _classify(match.group("trail"), marked=False, is_lead=False,
                  index=index, counts=counts, message=text)
        for match in _TRAIL_SLOT.finditer(text)
    ]
    if not candidates:
        return CategoryResolution(status="none")
    priority = {"resolved": 4, "ambiguous": 3, "unresolved": 2,
                "needs_interpretation": 1, "none": 0}
    return max(candidates, key=lambda result: priority[result.status])
def extract_category_candidate(message: str) -> str | None:
    """Best-effort category phrase for the router's deterministic filter hint.

    Delegates to the same resolver with an empty catalog, so it shapes exactly the
    references the resolver would treat as a category (dropping status/period/
    ranking words and month follow-ups) without a catalog lookup. The executor
    still confirms the hint against the real names, so this only needs to avoid
    inventing a filter where the resolver would not.
    """
    resolution = resolve_category_phrase(message, [])
    if resolution.status in ("needs_interpretation", "unresolved") and resolution.requested:
        return " ".join(resolution.requested.split()).title()
    return None






def category_suggestions(phrase: str, names: Iterable[str], limit: int = 3) -> list[str]:
    """Closest saved category names for a phrase that matched none exactly.

    Pure and catalog-bound: close spellings ("foods" -> "Food") and whole-word
    containment ("food" -> "Food & Dining"). A name saved more than once is
    never offered, because naming it cannot pick one. The caller only ever
    asks with these names; it never selects one on the user's behalf.
    """
    key = " ".join(str(phrase or "").split()).casefold()
    if not key:
        return []
    catalog = [str(name) for name in names if name]
    counts = Counter(" ".join(name.split()).casefold() for name in catalog)
    unique = {}
    for name in catalog:
        normalised = " ".join(name.split()).casefold()
        if counts[normalised] == 1:
            unique[normalised] = name
    words = {word for word in re.findall(r"\w+", key) if word not in FILLERS}
    close = [unique[match] for match in get_close_matches(key, list(unique), n=limit, cutoff=0.6)]
    contained = [
        name for normalised, name in unique.items()
        if words & {word for word in re.findall(r"\w+", normalised) if word not in FILLERS}
    ]
    return list(dict.fromkeys([*close, *contained]))[:limit]
