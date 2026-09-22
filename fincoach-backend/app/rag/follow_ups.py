"""Deterministic, context-aware follow-up chips for coaching answers.

The mobile app used to derive "CONTINUE WITH" chips from a client-side keyword
match on the answer text, so a budget answer always offered the same two prompts
even after the user had already asked them. Selection now lives here, beside the
routing and verified-tool logic, and is delivered to the client through the
assistant message's ``ui_payload["follow_ups"]``.

Two rules drive the choice:

1. Branch on the tool that actually produced the answer (the strongest signal of
   what data the user just saw), not on words in the reply.
2. Never suggest an intent the user has already raised in this conversation
   (current turn included), matching paraphrases.

No extra model request is made: this is a pure function over the turn's metadata
and recent history. It returns an empty list whenever there is no useful next
step (educational answers, clarifications, errors, or a fully-explored thread).
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

# --- Intent vocabulary ------------------------------------------------------
# Each next-step candidate is tagged with a stable intent key. The same keys are
# used to recognise what the user has already asked, so a candidate can be
# dropped when its intent is already covered.
BUDGET_STATUS = "budget_status"
CUT_SPENDING = "cut_spending"
COMPARE_LAST_MONTH = "compare_last_month"
GOAL_TRACK = "goal_track"
WEEKLY_PLAN = "weekly_plan"
TOP_CATEGORY = "top_category"
UPCOMING_REMINDERS = "upcoming_reminders"

# Canonical chip text per intent. label = what the button reads; query = the
# self-contained message sent when tapped (it re-routes on its own).
_CHIP_TEXT: dict[str, dict[str, str]] = {
    BUDGET_STATUS: {"label": "Show my budget breakdown", "query": "Show my budget breakdown"},
    CUT_SPENDING: {"label": "Where can I cut spending?", "query": "Where can I cut spending?"},
    COMPARE_LAST_MONTH: {"label": "Compare with last month", "query": "Compare my spending with last month"},
    GOAL_TRACK: {"label": "Am I on track for my goal?", "query": "Am I on track for my savings goal?"},
    WEEKLY_PLAN: {"label": "Make me a weekly saving plan", "query": "Make me a weekly saving plan"},
    TOP_CATEGORY: {"label": "Which category costs most?", "query": "Which category am I spending the most on?"},
    UPCOMING_REMINDERS: {"label": "Show my upcoming reminders", "query": "Show my upcoming reminders"},
}

# Candidate next steps per tool, ranked best-first. Only tools that report on the
# user's own verified data are listed; educational/casual answers get no chips
# (that hybrid path is deferred to the LLM-suggestion design).
_CANDIDATES_BY_TOOL: dict[str, tuple[str, ...]] = {
    "get_budget_status": (CUT_SPENDING, COMPARE_LAST_MONTH, GOAL_TRACK),
    "get_spending_summary": (BUDGET_STATUS, TOP_CATEGORY, CUT_SPENDING),
    "get_period_comparison": (CUT_SPENDING, BUDGET_STATUS),
    "search_transactions": (BUDGET_STATUS, TOP_CATEGORY),
    "get_savings_goals": (WEEKLY_PLAN, GOAL_TRACK, BUDGET_STATUS),
    "get_weekly_savings_plan": (GOAL_TRACK, BUDGET_STATUS),
    "predict_savings": (WEEKLY_PLAN, GOAL_TRACK),
    "get_cashflow_forecast": (BUDGET_STATUS, GOAL_TRACK),
    "get_upcoming_reminders": (BUDGET_STATUS,),
    "get_financial_profile": (BUDGET_STATUS,),
}

# budget_planning turns are produced without a read-tool record, so key off the
# response mode as well.
_CANDIDATES_BY_MODE: dict[str, tuple[str, ...]] = {
    "budget_planning": (GOAL_TRACK, BUDGET_STATUS),
}

# Response modes where FinCoach did NOT deliver an answer from verified data, so
# a "continue with" chip would be misleading. No chips for these.
_SILENT_MODES = frozenset(
    {
        "clarification",
        "permission_policy",
        "read_policy",
        "product_policy",
        "action_policy",
        "interaction",
    }
)

# Patterns that recognise an intent in the user's own words (English + common
# Malay cues), used only to suppress a candidate the user already asked for.
_ASKED_PATTERNS: dict[str, re.Pattern[str]] = {
    BUDGET_STATUS: re.compile(
        r"\b(budget\s+breakdown|my\s+budget|budget\s+status|how\s+am\s+i\s+doing|"
        r"remaining\s+budget|belanjawan)\b",
        re.IGNORECASE,
    ),
    CUT_SPENDING: re.compile(
        r"\b(cut\s+(?:my\s+)?spending|reduce\s+(?:my\s+)?spending|spend\s+less|"
        r"where\s+can\s+i\s+cut|save\s+money|kurangkan\s+perbelanjaan)\b",
        re.IGNORECASE,
    ),
    COMPARE_LAST_MONTH: re.compile(
        r"\b(compare|last\s+month|previous\s+month|vs\.?\s+last|bulan\s+lepas)\b",
        re.IGNORECASE,
    ),
    GOAL_TRACK: re.compile(
        r"\b(on\s+track|reach\s+(?:my\s+)?goal|goal\s+progress|matlamat)\b",
        re.IGNORECASE,
    ),
    WEEKLY_PLAN: re.compile(
        r"\b(weekly\s+saving|weekly\s+plan|save\s+.*per\s+week|pelan\s+mingguan)\b",
        re.IGNORECASE,
    ),
    TOP_CATEGORY: re.compile(
        r"\b(biggest|top\s+categor|most\s+(?:on|spent|spending)|which\s+categor|"
        r"largest\s+expense|kategori\s+tertinggi)\b",
        re.IGNORECASE,
    ),
    UPCOMING_REMINDERS: re.compile(
        r"\b(upcoming\s+reminder|reminders?|due|peringatan)\b",
        re.IGNORECASE,
    ),
}

MAX_FOLLOW_UPS = 2


def _asked_intents(texts: Iterable[str]) -> set[str]:
    """Intent keys already raised across the supplied user messages."""
    asked: set[str] = set()
    for text in texts:
        if not text:
            continue
        for intent, pattern in _ASKED_PATTERNS.items():
            if intent not in asked and pattern.search(text):
                asked.add(intent)
    return asked


def _user_texts(history: Iterable[Mapping[str, object]]) -> list[str]:
    return [
        str(message.get("content", ""))
        for message in history
        if isinstance(message, Mapping) and message.get("role") == "user"
    ]


def build_follow_ups(
    *,
    content: str,
    response_mode: str,
    tool_names: tuple[str, ...],
    history: Iterable[Mapping[str, object]] = (),
) -> list[dict[str, str]]:
    """Return up to ``MAX_FOLLOW_UPS`` next-step chips for the just-sent answer.

    ``content`` is the current user message, ``tool_names`` the verified tools
    that ran this turn, and ``history`` the recent conversation used to suppress
    already-asked intents. Returns ``[]`` when no useful next step exists.
    """
    if response_mode in _SILENT_MODES:
        return []

    # Pick the candidate list from the tool that ran (last verified read wins),
    # falling back to a response-mode mapping for tool-less data answers.
    candidates: tuple[str, ...] = ()
    for name in reversed(tool_names):
        if name in _CANDIDATES_BY_TOOL:
            candidates = _CANDIDATES_BY_TOOL[name]
            break
    if not candidates:
        candidates = _CANDIDATES_BY_MODE.get(response_mode, ())
    if not candidates:
        return []

    asked = _asked_intents([content, *_user_texts(history)])

    chips: list[dict[str, str]] = []
    for intent in candidates:
        if intent in asked:
            continue
        chips.append(dict(_CHIP_TEXT[intent]))
        if len(chips) >= MAX_FOLLOW_UPS:
            break
    return chips
