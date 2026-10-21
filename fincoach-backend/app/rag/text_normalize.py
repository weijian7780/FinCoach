"""Shared text normalisation for INTENT MATCHING ONLY.

Deterministic routing spreads its own ad-hoc whitespace handling across several
modules. This helper gives them one consistent normaliser for *matching intent*
— it must never be used to parse dates, amounts, or category names, which always
read the ORIGINAL message.

It does two safe things and nothing else:

* collapse runs of whitespace to single spaces;
* expand a small allow-list of hyphenated financial compound phrases
  ("savings-goal" -> "savings goal") so grammatical variants match the routing
  patterns, which were written with whitespace between the words.

It deliberately does NOT:

* lowercase — every routing pattern already compiles with ``re.IGNORECASE``;
* rewrite "spend" — "spend" as a noun vs a verb is decided in context by the
  router, not here (blindly widening it would misread "spend time with friends");
* touch any hyphen outside the allow-list — so ISO dates ("2026-09-22"), negative
  amounts ("-50"), and hyphenated category names ("Take-away") survive unchanged.
"""

from __future__ import annotations

import re

# Hyphenated spellings of multi-word finance phrases the routing patterns expect
# to see with a space. Longest first so "savings-goals" wins over "savings-goal".
_COMPOUND_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("savings-goals", "savings goals"),
    ("saving-goals", "saving goals"),
    ("savings-goal", "savings goal"),
    ("saving-goal", "saving goal"),
    ("savings-plan", "savings plan"),
    ("saving-plan", "saving plan"),
    ("emergency-fund", "emergency fund"),
)
_COMPOUND_PATTERN = re.compile(
    r"\b(?:" + "|".join(
        re.escape(key).replace(r"\-", r"[-\u2010-\u2014]")
        for key, _ in _COMPOUND_REPLACEMENTS
    ) + r")\b",
    re.IGNORECASE,
)
_COMPOUND_MAP = {key.lower(): value for key, value in _COMPOUND_REPLACEMENTS}


def normalize_for_intent(message: str) -> str:
    """Return a whitespace-collapsed, compound-expanded copy for intent matching.

    The original ``message`` must still be used for any date/amount/category
    resolution — this output is only safe for deciding *what the user is asking*.
    """
    collapsed = " ".join((message or "").strip().split())
    if not collapsed:
        return collapsed
    return _COMPOUND_PATTERN.sub(
        lambda match: _COMPOUND_MAP[
            re.sub(r"[\u2010-\u2014]", "-", match.group(0)).lower()
        ], collapsed
    )
