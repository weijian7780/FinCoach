"""Deterministic budget-allocation + diagnostic-coaching grounding.

Two failure modes this fixes for open/planning queries:
- "if I have 6000, how to allocate my budget" used to dump the user's recorded
  budget rows (wrong intent) or invent numbers the verifier then rejected.
- "how should I manage my money?" (vague) used to over-retrieve or refuse.

Approach (synthetic grounding injection): compute the split in PYTHON (no LLM
arithmetic drift), then hand the derived figures to the model as a normal
retrieved chunk. Because the numbers now exist in the reference text, they pass
`validate_coach_answer`'s numeric check and the entailment verifier by
construction — no guard is loosened. A hypothetical amount never touches the
personal database (that path is the education route, which reads no records).

Pure and offline: no network, no LLM, no DB. Fully unit-testable.
"""

from __future__ import annotations

import re

from app.rag.retrieval import RetrievedChunk

# --- Amount parsing ----------------------------------------------------------
# Handles "6000", "RM6,000", "RM 6000.00", "6k". Deliberately conservative: it
# only fires on a plausible ringgit amount, not on years or small counts.
_AMOUNT = re.compile(
    r"(?:rm|myr)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"   # 6,000 / 1,234,567.89
    r"|\d+(?:\.\d{1,2})?\s*k"                       # 6k / 6.5k
    r"|\d{3,}(?:\.\d{1,2})?)",                       # 6000 / 6000.00 (>=3 digits)
    re.IGNORECASE,
)

# Allocation / "how do I budget this amount" intent.
_ALLOCATION_INTENT = re.compile(
    r"\b(?:allocate|split|divide|distribute|break\s*down|budget|spend|manage|"
    r"agih|bahagi)\b",
    re.IGNORECASE,
)

# Vague, open "manage my money" intent with no concrete parameters.
_DIAGNOSTIC_INTENT = re.compile(
    r"\b(?:manage\s+(?:my\s+)?(?:money|finances?|budget)|"
    r"budget\s+better|get\s+better\s+with\s+money|"
    r"where\s+(?:do|should)\s+i\s+start|how\s+(?:do|should)\s+i\s+start|"
    r"good\s+with\s+money|handle\s+(?:my\s+)?(?:money|finances?)|"
    r"financial\s+tips|tips?\s+(?:for|on)\s+(?:personal\s+)?"
    r"(?:finance|money|budgeting|saving)|improve\s+(?:my\s+)?finances?|"
    r"urus\s+(?:duit|wang|kewangan))\b",
    re.IGNORECASE,
)


# Prompt guidance so the FIRST draft satisfies the numeric guard (every RM figure
# cited once in Insight; actions carry no bare figures) instead of relying on a
# retry. Passed to build_coach_prompt(extra_guidance=...).
ALLOCATION_GUIDANCE = (
    "This is a hypothetical planning question about the stated amount only. Do not "
    "mention or imply the user's recorded budget, balance, or spending. State every "
    "RM figure and percentage exactly once, in the Insight sentence that carries the "
    "[S1] marker. In Recommended action, give sequenced steps in words and do NOT "
    "repeat any RM amount. Do not name or recommend a specific commercial product."
)
DIAGNOSTIC_GUIDANCE = (
    "The question is open-ended and gives no amount. In Insight, give one core "
    "principle from the cited priority framework. In Recommended action, give one "
    "concrete first step, then ask one short clarifying question for the user's "
    "monthly take-home income and any debts so the next answer can be specific. Do "
    "not invent any RM amounts or percentages."
)


def parse_amount(text: str) -> float | None:
    """Extract a single ringgit amount from the message, or None."""
    match = _AMOUNT.search(str(text or ""))
    if not match:
        return None
    raw = match.group("num").lower().replace(",", "").replace(" ", "")
    try:
        if raw.endswith("k"):
            return float(raw[:-1]) * 1000.0
        return float(raw)
    except ValueError:
        return None


def is_allocation_query(text: str) -> bool:
    """A planning request to allocate a concrete (hypothetical) amount."""
    return bool(_ALLOCATION_INTENT.search(text or "")) and parse_amount(text) is not None


def is_diagnostic_query(text: str) -> bool:
    """A vague, open money-management question with no concrete amount."""
    return bool(_DIAGNOSTIC_INTENT.search(text or "")) and parse_amount(text) is None


# --- Deterministic split -----------------------------------------------------

# 50/30/20 baseline (needs / wants / savings). Kept flat and well-known so the
# framework itself is an uncontroversial educational anchor; the arithmetic is
# exact so the model never has to compute (or mis-compute) it.
_NEEDS, _WANTS, _SAVINGS = 0.50, 0.30, 0.20


def allocation_split(amount: float) -> dict[str, float]:
    return {
        "needs": round(amount * _NEEDS, 2),
        "wants": round(amount * _WANTS, 2),
        "savings": round(amount * _SAVINGS, 2),
    }


def _money(value: float) -> str:
    return f"RM{value:,.2f}"


def synthetic_allocation_chunk(amount: float, *, chunk_id: int = -901) -> RetrievedChunk:
    """A grounding chunk carrying the pre-computed 50/30/20 split.

    Injected as a normal reference so the derived figures are supported evidence:
    the answer may cite RM values and the 50/30/20 percentages, and both the
    numeric guard and the entailment verifier find them here. Negative id keeps it
    out of persistence (it is not a real knowledge document).
    """
    split = allocation_split(amount)
    content = (
        f"The 50/30/20 budgeting framework allocates 50% of monthly net income to "
        f"needs, 30% to wants, and 20% to savings and debt repayment. "
        f"For a monthly net take-home income of {_money(amount)}, this framework gives: "
        f"needs (50%) = {_money(split['needs'])}, "
        f"wants (30%) = {_money(split['wants'])}, "
        f"savings and debt (20%) = {_money(split['savings'])}. "
        f"Needs cover housing, utilities, groceries, and transport. Wants cover "
        f"dining out, subscriptions, and leisure. Savings cover an emergency fund "
        f"and long-term goals. The percentages are an adaptable guideline, not a "
        f"fixed rule, and assume the amount is take-home pay after statutory "
        f"deductions such as EPF and SOCSO."
    )
    return RetrievedChunk(
        id=chunk_id,
        title="50/30/20 budgeting framework",
        source="Budgeting framework (50/30/20)",
        page_number=None,
        chunk_index=None,
        content=content,
        similarity=1.0,
        source_type="corpus",
    )


def financial_priority_chunk(*, chunk_id: int = -902) -> RetrievedChunk:
    """Universal financial-priority hierarchy for vague diagnostic questions.

    These are uncontroversial educational principles, so the verifier accepts
    them; no personal data or web search is needed to answer at this level.
    """
    content = (
        "A standard personal-finance priority order for someone getting started: "
        "first, build cash-flow awareness by knowing monthly income versus expenses; "
        "second, build an emergency buffer of one to three months of essential "
        "expenses; third, clear high-interest debt such as credit cards; fourth, "
        "move to long-term protection and growth. Visibility comes before "
        "restriction: tracking spending is the practical first step before setting "
        "limits. This is a general framework, not tied to any specific product."
    )
    return RetrievedChunk(
        id=chunk_id,
        title="Financial priority hierarchy",
        source="Personal-finance priority framework",
        page_number=None,
        chunk_index=None,
        content=content,
        similarity=1.0,
        source_type="corpus",
    )
