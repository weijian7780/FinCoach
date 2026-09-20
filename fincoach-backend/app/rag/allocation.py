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
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"      # 6,000 / 1,234,567.89
    r"|\d+(?:\.\d{1,2})?\s*k"                          # 6k / 6.5k
    r"|(?<!\d)\d{3,7}(?:\.\d{1,2})?(?!\d))",           # 6000 / 6000.00 — a COMPLETE 3-7 digit run
    re.IGNORECASE,
)

# No monthly student budget is ten million ringgit; a value this large is an
# identifier (phone, account, reference) that slipped past the run guard.
_MAX_PLAUSIBLE_AMOUNT = 10_000_000.0

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

# Gross-income cue: the stated amount is pre-deduction pay, so a 50/30/20 split of
# it would budget money the user never receives. We do NOT compute the net (SOCSO
# and EIS are banded tables, not flat rates, and every rate drifts over time —
# computing a net and citing it would be a fabricated statutory figure). We detect
# the cue, suppress the numeric split, and ask for take-home pay instead.
_GROSS_INCOME_CUE = re.compile(
    r"\b(?:gross|before\s+(?:tax|epf|kwsp|socso|perkeso|eis|deductions?)|"
    r"pre[-\s]?tax|basic\s+salary|gaji\s+(?:pokok|asas|kasar)|"
    r"sebelum\s+(?:tolak|potong|epf|kwsp|cukai)|belum\s+tolak)\b",
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
GROSS_INCOME_GUIDANCE = (
    "The stated amount is GROSS pay (before statutory deductions). Do NOT split it "
    "with the 50/30/20 framework and do NOT state any RM figure or percentage. In "
    "Insight, state the cited fact in POSITIVE, affirmative wording (avoid 'not' / "
    "'isn't'): say that EPF, SOCSO, and EIS are deducted from gross pay before it "
    "reaches the bank account, so a budget should use take-home (net) pay. Do NOT "
    "compute, estimate, or cite a specific net figure or deduction rate. In "
    "Recommended action, ask the user for their monthly take-home (net) pay — the "
    "amount that actually reaches their bank account — so the next answer can "
    "allocate it accurately."
)


def parse_amount(text: str) -> float | None:
    """Extract a single ringgit amount from the message, or None."""
    match = _AMOUNT.search(str(text or ""))
    if not match:
        return None
    raw = match.group("num").lower().replace(",", "").replace(" ", "")
    try:
        value = float(raw[:-1]) * 1000.0 if raw.endswith("k") else float(raw)
    except ValueError:
        return None
    # Reject implausible magnitudes: a phone/account/reference number that still
    # slipped through (e.g. a comma-grouped 13-digit string) is not an amount.
    if value <= 0 or value >= _MAX_PLAUSIBLE_AMOUNT:
        return None
    return value


def is_allocation_query(text: str) -> bool:
    """A planning request to allocate a concrete (hypothetical) amount."""
    return bool(_ALLOCATION_INTENT.search(text or "")) and parse_amount(text) is not None


def is_diagnostic_query(text: str) -> bool:
    """A vague, open money-management question with no concrete amount."""
    return bool(_DIAGNOSTIC_INTENT.search(text or "")) and parse_amount(text) is None


def is_gross_income_query(text: str) -> bool:
    """An allocation request whose stated amount is gross (pre-deduction) pay.

    Must be checked BEFORE is_allocation_query in the injection path: both match,
    but a gross amount must suppress the numeric split rather than divide money the
    user never receives.
    """
    return (
        bool(_GROSS_INCOME_CUE.search(text or ""))
        and bool(_ALLOCATION_INTENT.search(text or ""))
        and parse_amount(text) is not None
    )


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


def gross_income_chunk(*, chunk_id: int = -903) -> RetrievedChunk:
    """Gross-vs-net literacy note for a split request on pre-deduction pay.

    Deliberately carries NO percentage and NO RM figure: SOCSO and EIS are banded
    contribution tables (not flat rates) and every statutory rate drifts over time,
    so a computed net or a stated rate would be a fabricated figure the verifier
    cannot catch. The stable, citable facts are only that these deductions exist
    and are taken before pay reaches the bank — which is all this note asserts.
    """
    # Deliberately all-affirmative (no "not"/"never"): the grounding verifier splits
    # evidence by negation polarity, so a positively-phrased answer can only draw on
    # positively-phrased passages. Keeping the key vocabulary (deducted, budget,
    # take-home, net) in affirmative sentences lets a correct answer be supported.
    content = (
        "In Malaysia, gross monthly pay is the amount earned before statutory "
        "deductions. The Employees Provident Fund (EPF), the Social Security "
        "Organisation (SOCSO), and the Employment Insurance System (EIS) are "
        "deducted from gross pay before it reaches the bank account. The remaining "
        "take-home pay, also called net pay, is the amount available to spend and "
        "save. A monthly budget should be built on take-home pay so the plan matches "
        "the money that actually reaches the bank account. The exact deduction "
        "amounts depend on current statutory rates, so the reliable figure to use is "
        "the net take-home pay shown on the payslip or bank credit."
    )
    return RetrievedChunk(
        id=chunk_id,
        title="Gross versus net pay (Malaysian statutory deductions)",
        source="Gross-vs-net pay note",
        page_number=None,
        chunk_index=None,
        content=content,
        similarity=1.0,
        source_type="corpus",
    )
