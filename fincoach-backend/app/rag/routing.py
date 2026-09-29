"""Deterministic routing for the four FinCoach response paths."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo

from app.category_resolution import extract_category_candidate, is_category_ranking_query
from app.rag.query_analysis import detect_knowledge_topics
from app.rag.text_normalize import normalize_for_intent


class CoachingRoute(str, Enum):
    CASUAL = "casual"
    PERSONAL_FINANCE = "personal_finance"
    FINANCIAL_EDUCATION = "financial_education"
    COMBINED = "combined"


class ReadReadiness(str, Enum):
    """Whether a resolved read can execute, needs a question, or is out of scope."""

    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class UnsupportedTransactionFilter(ValueError):
    """A requested search constraint has no faithful executor representation."""


# Stable read-intent labels, kept separate from the coarse CoachingRoute and from
# the tool name so the contract can name an intent even before a tool is chosen
# (ambiguous savings) or when no read applies (casual/education -> None).
_TOOL_INTENT = {
    "get_spending_summary": "spending_summary",
    "get_period_comparison": "period_comparison",
    "search_transactions": "transaction_search",
    "get_budget_status": "budget_status",
    "get_category_budget_recommendation": "category_budget_recommendation",
    "get_financial_overview": "financial_overview",
    "get_financial_profile": "financial_profile",
    "get_savings_goals": "savings_goals",
    "predict_savings": "savings_prediction",
    "get_weekly_savings_plan": "weekly_savings_plan",
    "get_cashflow_forecast": "cashflow_forecast",
    "get_upcoming_reminders": "upcoming_reminders",
    "get_report_summary": "report_summary",
}

# Tools whose default period is a calendar-month date range, and those whose
# default period is a single month key. Missing periods are materialised from the
# request's `now` with provenance "default"; the executor keeps its own defaults
# for older callers that pass no dates at all.
_RANGE_PERIOD_TOOLS = {"get_spending_summary", "get_report_summary", "search_transactions"}
_MONTH_PERIOD_TOOLS = {
    "get_budget_status",
    "get_category_budget_recommendation",
    "get_financial_overview",
    "predict_savings",
    "get_weekly_savings_plan",
}


@dataclass(frozen=True)
class ResolvedReadRequest:
    """The deterministic personal-data read selected for this message."""

    route: CoachingRoute
    tool_name: str | None
    arguments: dict[str, object]
    inherited: bool = False
    clarification: str | None = None
    intent: str | None = None
    readiness: ReadReadiness = ReadReadiness.READY
    missing_required: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    parameter_sources: dict[str, str] = field(default_factory=dict)


_MONTH_NUMBERS = {
    "january": 1, "jan": 1, "januari": 1,
    "february": 2, "feb": 2, "februari": 2,
    "march": 3, "mar": 3, "mac": 3,
    "april": 4, "apr": 4,
    "may": 5, "mei": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7, "julai": 7,
    "august": 8, "aug": 8, "ogos": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12, "disember": 12, "dis": 12,
}
_MONTH_NAME_QUERY = re.compile(
    r"\b(?:for|in|bulan)?\s*(?P<month>" + "|".join(_MONTH_NUMBERS) + r")\b"
    r"(?:\s+(?P<year>20\d{2}))?",
    re.IGNORECASE,
)
_THIS_MONTH_QUERY = re.compile(r"\b(?:this\s+month|bulan\s+ini)\b", re.IGNORECASE)
_LAST_MONTH_QUERY = re.compile(
    r"\b(?:last\s+month|previous\s+month|bulan\s+lepas)\b", re.IGNORECASE
)
_FOLLOW_UP_PREFIX = re.compile(
    r"^(?:what\s+about|how\s+about|and|for)\b", re.IGNORECASE
)
_CATEGORY_ONLY_QUERY = re.compile(
    r"\b(?:only|just|hanya)\s+(?P<category>[\w&'\- ]{1,80}?)[?.!\s]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FinancialContextScope:
    """The minimum set of saved FinCoach records needed for one question."""

    include_transactions: bool = False
    include_monthly_budget: bool = False
    include_category_limits: bool = False
    include_savings_goals: bool = False
    include_previous_transactions: bool = False

    @classmethod
    def full_overview(cls) -> "FinancialContextScope":
        """Use every financial module only for an explicitly broad overview."""
        return cls(
            include_transactions=True,
            include_monthly_budget=True,
            include_category_limits=True,
            include_savings_goals=True,
            include_previous_transactions=True,
        )


_CASUAL_ONLY = re.compile(
    r"^(?:oi+|hi+|hello+|hey+|good\s+(?:morning|afternoon|evening|night)|"
    r"how are you|thanks?|thank you|bye|goodbye)[!,.?\s]*$",
    re.IGNORECASE,
)
_CASUAL_NON_FINANCIAL = re.compile(
    r"^\s*(?:weather|cuaca|tell\s+me\s+(?:a\s+)?joke|make\s+(?:a\s+)?joke)\b",
    re.IGNORECASE,
)

_PERSONAL_FINANCE = re.compile(
    r"\b(?:my|mine|i have|i spent|i spend|i save|i saved|"
    r"this month|last month|previous month|compare|comparison|"
    r"recorded|expenses?|transactions?|purchases?|spent|spending|"
    r"cut spending|how am i doing|monthly budget|budget limit|"
    r"savings?\s+goals?|savings?\s+plan|allowance|category limit|rm\s*\d|"
    r"weekly\s+savings?|monthly\s+savings?|"
    r"berapa\s+(?:saya|aku)\s+(?:belanja|habis)|"
    r"(?:belanja|perbelanjaan|transaksi|bajet|had\s+kategori|"
    r"matlamat\s+simpanan|pelan\s+simpanan)\s+(?:saya|aku)|"
    r"(?:pendapatan|elaun)\s+(?:saya|aku)|bulan\s+(?:ini|lepas))\b",
    re.IGNORECASE,
)

_FINANCIAL_EDUCATION = re.compile(
    r"\b(?:emergency fund|ptptn|epf|kwsp|socso|perkeso|akpk|bnpl|"
    r"buy now pay later|pidm|"
    r"ccris|eccris|interest|loan|debt|credit|insurance|takaful|investment|"
    r"crypto|kripto|digital assets?|digital bank|e-?wallet|scam|fraud|"
    r"complaint|complain|financial service|"
    r"scholarships?|financial aid|shariah|syariah|inflation|tax|zakat|"
    r"financial literacy|budgeting method|compound interest|opr)\b|"
    r"\b(?:dana kecemasan|simpanan kecemasan|bajet|hutang|pinjaman|"
    r"beli sekarang bayar kemudian|"
    r"aset kripto|kredit|pelaburan|penipuan|"
    r"aduan|biasiswa|bantuan kewangan|bank digital|e-?dompet|"
    r"perlindungan deposit|cukai|insurans|patuh syariah)\b|"
    r"\b(?:what is (?:a )?budget|what is budgeting|explain budgeting|how to budget)\b|"
    r"\b(?:how\s+to\s+save|ways?\s+to\s+save|saving\s+tips|tips?\s+(?:on|for)\s+saving|"
    r"how\s+to\s+make\s+a\s+savings?\s+plan|cara\s+simpan\s+duit|cara\s+menabung)\b",
    re.IGNORECASE,
)

# Normative/general cues: the user is asking what is TYPICAL/RECOMMENDED, not about
# their own records. "people normally set what budget", "how much should a student
# save" -> educational, even though a finance keyword ("budget", "save") is present.
_GENERAL_KNOWLEDGE_CUE = re.compile(
    r"\b(?:people|others|everyone|most\s+(?:people|students|malaysians|folks)|"
    r"normally|usually|typically|generally|commonly|average|on\s+average|"
    r"in\s+general|standard|recommended|rule\s+of\s+thumb|benchmark|ideal|"
    r"how\s+much\s+should\s+(?:a|an|one|someone|i)\b|what\s+do\s+most)\b",
    re.IGNORECASE,
)

_AMBIGUOUS_REMINDER_TASK = re.compile(
    r"^(?:(?:please|pls|tolong)\s+)?"
    r"(?P<title>(?:pay|settle)\s+"
    r"(?:(?:[\w&'\u2019-]+\s+){0,8}(?:bills?|rent|fees?|payments?|"
    r"instalments?|loans?)|ptptn)|"
    r"bayar\s+(?:bil(?:\s+[\w&'\u2019-]+){0,8}|sewa|ptptn))"
    r"[\s.!?]*$",
    re.IGNORECASE,
)

_REMINDER_ACTION_REQUEST = re.compile(
    r"\b(?:remind(?:\s+(?:me|us|myself))?|remi(?:n)?ders?|alerts?|"
    r"notif(?:y|ication|ications)?|ingatkan|peringatan|notifikasi|"
    r"(?:help\s+(?:me|us)\s+)?remember|"
    r"(?:make\s+sure\s+)?(?:i\s+)?don['’]?t\s+forget|"
    r"don't\s+let\s+(?:me|us)\s+forget|jangan\s+lupa|"
    r"schedule\s+(?:my\s+)?(?:[\w'-]+\s+){0,4}(?:payment|bill|instalment)|"
    r"(?:create|set|add|schedule|make|buat)\s+(?:me\s+)?(?:(?:a|an)\s+)?"
    r"(?:remi(?:n)?der|alert|notification|peringatan))\b",
    re.IGNORECASE,
)

_REPORT_ACTION_REQUEST = re.compile(
    r"\b(?:laporan|"
    r"(?:generate|create|make|download|export|buat|jana)\b.{0,80}\b(?:report|laporan|pdf)|"
    r"(?:show|give|need|want)\b.{0,80}\b(?:report|pdf)|"
    r"(?:spending\s+)?summary\b.{0,30}\b(?:as\s+(?:a\s+)?)?pdf|"
    r"(?:pdf\s+)?financial\s+report)\b",
    re.IGNORECASE,
)

_REMINDER_REFERENCE = re.compile(
    r"\b(?:remi(?:n)?ders?|remind|remember|alerts?|notif(?:y|ication|ications)?|"
    r"ingatkan|peringatan|notifikasi|heads?(?:-|\s)?up|nudge|ping|alarm)\b",
    re.IGNORECASE,
)

_REMINDER_NON_CREATE = re.compile(
    r"\b(?:show|list|view|find|check|why|explain|cancel|delete|remove|"
    r"turn\s+off|disable|stop|change|edit|update|mark|open|settings?|"
    r"received?|history|padam|matikan|tukar|ubah|tunjuk)\b|"
    r"\b(?:do\s+not|don['’]?t|dont)\s+(?:create|set|add|schedule|make|want)\b|"
    r"\b(?:do\s+not|don['’]?t|dont)\s+remind\b|"
    r"\bnot\s+now\b|"
    r"\bremind\s+(?:me|us|saya|aku)\s+(?:what|how|why|whether|if)\b|"
    r"\bi\s+remember\b|\bremember\s+(?:when|what|how|why)\b|"
    r"\bjangan\s+(?:buat|cipta|tetapkan|jana)\b",
    re.IGNORECASE,
)

_REMINDER_CREATE_REQUEST = re.compile(
    r"\b(?:remind\s+(?:me|us|myself|saya|aku)|ingatkan\s+(?:saya|aku|kami)|"
    r"(?:give|send)\s+(?:me|us)\s+(?:a\s+)?heads?(?:-|\s)?up|"
    r"(?:nudge|ping|alert|notify)\s+(?:me|us)|"
    r"(?:help\s+(?:me|us)\s+)?remember|"
    r"(?:make\s+sure\s+)?(?:i\s+)?don['’]?t\s+forget|"
    r"don['’]?t\s+let\s+(?:me|us)\s+forget|jangan\s+lupa|"
    r"schedule\s+(?:my\s+)?(?:[\w'-]+\s+){0,4}(?:payment|bill|instalment)|"
    r"(?:create|set|add|schedule|make|buat)\s+(?:me\s+)?(?:(?:a|an)\s+)?"
    r"(?:remi(?:n)?der|alert|alarm|notification|peringatan))\b",
    re.IGNORECASE,
)

_REPORT_REFERENCE = re.compile(r"\b(?:reports?|laporan|pdf)\b", re.IGNORECASE)

_REPORT_NON_CREATE = re.compile(
    r"\b(?:history|sejarah|list|view|delete|remove|padam|failed?|gagal)\b|"
    r"\b(?:what\s+is|what\s+are|explain|why|how)\b.{0,40}\b"
    r"(?:report|laporan|pdf|generation)\b|"
    r"\b(?:summari[sz]e\s+what|contains?|works?)\b|"
    r"\b(?:do\s+not|don['’]?t|dont)\s+(?:generate|create|make|download|"
    r"export|build|prepare|want)\b|"
    r"\bjangan\s+(?:jana|buat|sediakan)\b",
    re.IGNORECASE,
)

_REPORT_CREATE_REQUEST = re.compile(
    r"\b(?:(?:generate|create|make|download|export|build|prepare|buat|jana|sediakan|"
    r"muat\s+turun)"
    r"\b.{0,80}\b(?:report|laporan|pdf)|"
    r"(?:show|give|need|want|mahu)\b.{0,80}\b(?:report|laporan|pdf)|"
    r"(?:spending\s+)?summary\b.{0,30}\b(?:as\s+(?:a\s+)?)?pdf|"
    r"(?:pdf\s+)?financial\s+report)\b",
    re.IGNORECASE,
)

_SAVINGS_GOAL_QUERY = re.compile(
    r"\b(?:savings?\s+goals?|saving\s+goal|savings?\s+plan|saving\s+plan|"
    r"plan\s+(?:my\s+)?savings?|weekly\s+savings?|monthly\s+savings?|"
    r"goal|target|deadline|save\s+for|reach\s+(?:my\s+)?goal|"
    r"matlamat\s+simpanan|simpanan\s+saya|pelan\s+simpanan|rancang\s+simpanan)\b",
    re.IGNORECASE,
)

_SAVINGS_MENTION = re.compile(r"\b(?:savings?|simpanan)\b", re.IGNORECASE)
# A clear savings intent names a goal, a plan, or a saving amount to hit. Bare
# "my savings" / "simpanan saya" does neither: the user could mean saved-goal
# progress OR an estimate of how much they can save. That is ambiguous, so it
# must ask which meaning rather than inherit an unrelated read or pick one.
_SAVINGS_CLEAR_INTENT = re.compile(
    r"\b(?:savings?\s+goals?|saving\s+goal|savings?\s+plan|saving\s+plan|"
    r"plan\s+(?:my\s+)?savings?|weekly\s+savings?|monthly\s+savings?|"
    r"matlamat\s+simpanan|pelan\s+simpanan|rancang\s+simpanan)\b",
    re.IGNORECASE,
)


def _is_ambiguous_savings(message: str) -> bool:
    """Whether a savings mention names neither a goal nor a saving-capacity ask."""
    message = normalize_for_intent(message)
    if not _SAVINGS_MENTION.search(message):
        return False
    if _SAVINGS_CLEAR_INTENT.search(message) or _PREDICTION_QUERY.search(message):
        return False
    return not is_weekly_savings_plan_request(message)


def is_weekly_savings_plan_request(content: str) -> bool:
    """A weekly saving amount needs cash-flow evidence as well as goal progress."""
    content = normalize_for_intent(content)
    return bool(
        re.search(r"\b(?:weekly|(?:each|every|per)\s+week|mingguan|setiap\s+minggu)\b", content, re.I)
        and re.search(r"\b(?:save|savings?|simpanan|simpan|menabung)\b", content, re.I)
    )

_BUDGET_QUERY = re.compile(
    r"\b(?:budget|overspent|overspend|over\s+budget|spending\s+limit|"
    r"category\s+limit|cut\s+spending|afford|allowance|bajet|"
    r"had\s+kategori|had\s+belanja)\b",
    re.IGNORECASE,
)
_BUDGET_SAVE_COMMAND = re.compile(
    r"^\s*(?:please\s+)?(?:save|set|add|create|update|change|edit)\b.{0,60}"
    r"\b(?:budget|category\s+limit|spending\s+limit|bajet|had\s+kategori)\b|"
    r"^\s*(?:can|could)\s+i\s+(?:save|set|add|create|update|change)\b.{0,45}"
    r"\b(?:budget|category\s+limit|spending\s+limit|bajet|had\s+kategori)\b|"
    r"^\s*(?:can|could)\s+you\s+(?:save|set|add|create|update|change)\b.{0,45}"
    r"\b(?:budget|category\s+limit|spending\s+limit|bajet|had\s+kategori)\b",
    re.IGNORECASE,
)
_CATEGORY_BUDGET_RECOMMENDATION_QUERY = re.compile(
    r"\b(?:suggest|recommend)\b.{0,60}\b(?:another|new|categor(?:y|ies))\b"
    r".{0,60}\b(?:budget|limit|bajet|had)\b|"
    r"\b(?:which|what)\s+(?:(?:other|another|additional)\s+)?"
    r"(?:(?:expense|spending)\s+)?categor(?:y|ies)\b.{0,60}"
    r"\b(?:need|needs|should|deserve|deserves|can\s+i\s+add|could\s+i\s+add)\b.{0,35}"
    r"\b(?:budget|limit|cap|bajet|had)\b|"
    r"\b(?:which|what)\s+(?:expense|spending)\b.{0,45}"
    r"\b(?:need|needs|should)\b.{0,35}\b(?:budget|limit|cap)\b|"
    r"\b(?:what|which)\s+(?:other|another|additional)\s+"
    r"(?:budget|limit)\b.{0,45}\b(?:add|set|create|make)\b|"
    r"\b(?:pick|choose|select)\b.{0,45}\bcategor(?:y|ies)\b"
    r".{0,45}\b(?:budget|limit|cap)\b|"
    r"\b(?:suggest|recommend)\b.{0,60}\b(?:budget|limit|bajet|had)\b.{0,30}"
    r"\bfor\s+(?!me\b|myself\b|our\b|overall\b|everyone\b|all\b|every\b|"
    r"(?:this|last|next|current)\s+month\b|a\s+student\b)"
    r"[\w&'-]+|"
    r"\bwhat\s+(?:budget|category\s+budget)\b.{0,45}"
    r"\b(?:can|could|should)\s+i\s+(?:add|set|create|allocate)\b",
    re.IGNORECASE,
)
_BUDGET_PLANNING_QUERY = re.compile(
    r"\b(?:plan|recommend|suggest|rancang|cadang)\b.{0,80}"
    r"\b(?:budget|budget\s+limit|spending\s+limit|bajet|had\s+belanja)\b|"
    r"\b(?:budget|budget\s+limit|spending\s+limit|bajet|had\s+belanja)\b"
    r".{0,80}\b(?:plan|recommend|suggest|rancang|cadang)\b",
    re.IGNORECASE,
)

# "How should I allocate/split my budget?" is a request for a budgeting METHOD
# (educational), not a lookup of the user's recorded budget rows. Matching this
# routes to FINANCIAL_EDUCATION so the coach explains an allocation framework
# (e.g. 50/30/20) instead of dumping "month limit / remaining".
_BUDGET_ALLOCATION_QUERY = re.compile(
    r"\b(?:how\s+(?:to|do|should|can|much)|ways?\s+to|help\s+me|best\s+way)\b"
    r".{0,40}\b(?:allocate|split|divide|distribute|break\s*down|structure|"
    r"organi[sz]e|manage|budget|spend)\b"
    r".{0,40}(?:\b(?:budget|money|income|allowance|salary|amount|funds?|cash|"
    r"categor(?:y|ies))\b|rm\s*\d)|"
    r"\ballocate\b.{0,40}(?:\b(?:budget|money|income|allowance|salary|"
    r"categor(?:y|ies))\b|rm\s*\d)|"
    r"\bbudget(?:ing)?\s+(?:method|strategy|framework|rule)\b|"
    r"\b\d{1,3}\s*/\s*\d{1,3}\s*/\s*\d{1,3}\b|"  # 50/30/20-style rules
    r"\b(?:cara|bagaimana)\b.{0,40}\b(?:agih|bahagi|urus|rancang)\b"
    r".{0,40}\b(?:bajet|duit|wang|pendapatan)\b",
    re.IGNORECASE,
)

# A hypothetical amount ("if I have RM6000", "say I earn 3000") is planning
# framing, NOT a reference to the user's recorded figures — so it must not force
# the personal-records path.
_HYPOTHETICAL_AMOUNT = re.compile(
    r"\b(?:if|say|suppose|assuming|imagine|let'?s\s+say|katakan|andai(?:kan)?|"
    r"jika|kalau)\b.{0,20}"
    r"(?:\bi\s+(?:have|had|get|got|make|earn|receive)\b|\brm?\s*\d|\b\d{3,})",
    re.IGNORECASE,
)

# "spend" as a verb about money vs about time is decided by what follows it.
# These objects mark the non-financial sense ("spend time", "spend the weekend").
_SPEND_NONFIN_OBJECT = (
    r"(?:time|times|hours?|the\s+(?:night|day|evening|weekend|afternoon|morning)|"
    r"quality\s+time|ages|forever|all\s+day)"
)
_TRANSACTION_QUERY = re.compile(
    r"\b(?:expenses?|transactions?|purchases?|overspent|overspend|"
    r"belanja|perbelanjaan|transaksi|pembelian)\b"
    r"|\b(?:i\s+spend|i\s+spent|spent|spending)\b(?!\s+" + _SPEND_NONFIN_OBJECT + r"\b)"
    r"|\bwhere\s+(?:did|does).*(?:money|spend(?!\s+" + _SPEND_NONFIN_OBJECT + r"\b))\b"
    # Shorthand "<category> spend" ("food spend") is a spending lookup, but not
    # when "spend" takes a non-financial or non-category object.
    r"|\b[\w&'-]+\s+spend\b(?!\s+(?:time|times|hours?|money|cash|it|them|less|"
    r"more|wisely|the|a|an|my|your|his|her|our|their|to|with|on)\b)",
    re.IGNORECASE,
)
# A clearly non-financial "spend time/hours/..." with no financial signal must
# not be pulled onto the personal-records path by an incidental "my" or "I".
_NON_FINANCIAL_ACTIVITY = re.compile(
    r"\bspen[dt](?:ing)?\s+" + _SPEND_NONFIN_OBJECT + r"\b",
    re.IGNORECASE,
)
_TRANSACTION_SEARCH_QUERY = re.compile(
    r"\b(?:find|list|show|view|search|tunjuk|senarai|cari)\b.{0,50}"
    r"\b(?:transactions?|purchases?|transaksi|pembelian)\b",
    re.IGNORECASE,
)
_TRANSACTION_NOUN = re.compile(r"\b(?:transactions?|purchases?|transaksi|pembelian)\b", re.IGNORECASE)
# "top/biggest 5 transactions" implies ranking by value, which is not supported.
_TXN_TOP_QUERY = re.compile(
    r"\b(?:top|biggest|largest|highest)\s+(?:\d+\s+)?(?:transactions?|purchases?)\b",
    re.IGNORECASE,
)
# "how many / number of / count of transactions" -> a count, not a list.
_TXN_COUNT_QUERY = re.compile(
    r"\b(?:how\s+many|number\s+of|count\s+of|berapa\s+banyak)\b[\w\s'&\-]{0,30}?"
    r"\b(?:transactions?|purchases?|transaksi|pembelian)\b",
    re.IGNORECASE,
)
_TXN_OLDEST_QUERY = re.compile(
    r"\b(?:first|oldest|earliest)\s+(?:\d{1,2}\s+)?"
    r"(?:transactions?|purchases?|transaksi|pembelian)\b",
    re.IGNORECASE,
)
_TXN_TYPE_QUERY = re.compile(
    r"\b(?P<type>income|expense)\s+(?:transactions?|purchases?)\b",
    re.IGNORECASE,
)
_TXN_EXCLUSION_QUERY = re.compile(
    r"\b(?:not|except|excluding|without|kecuali|selain)\s+"
    r"(?:category\s+|kategori\s+)?[\w&'\-]+",
    re.IGNORECASE,
)
_TXN_MERCHANT_JOIN = re.compile(
    r"\b(?:at|from|di|daripada)\s+[\w'&\-]+\s+"
    r"(?:and|or|atau|&)\s+(?:(?:at|from|di|daripada)\s+)?[\w'&\-]+",
    re.IGNORECASE,
)
# "how much did I spend at Grab" -> a filtered expense total, not an unfiltered
# summary. The merchant after at/from must not be a month or a filler word.
_TXN_MERCHANT_TOTAL = re.compile(
    r"\b(?:how\s+much|berapa|total)\b.{0,40}?\b(?:spend|spent|spending|belanja)\b"
    r".{0,40}?\b(?:at|from|di|daripada)\s+"
    r"(?!(?:" + "|".join(_MONTH_NUMBERS) + r"|all|least|most|the|home|work)\b)[A-Za-z]",
    re.IGNORECASE,
)
# Keep merchant extraction shared between tool selection and argument building.
# Numeric-leading names such as 7-Eleven are valid; date phrases are not names.
# A following at/from/di/daripada starts a *new* merchant, so it never extends the
# current name — "at Grab at Foodpanda" yields two merchants, not "Grab".
_TXN_MERCHANT_PHRASE = re.compile(
    r"\b(?:at|from|di|daripada)\s+(?P<merchant>[A-Za-z0-9][\w'&\-]*"
    r"(?:\s+(?!(?:at|from|di|daripada)\b)[A-Za-z0-9][\w'&\-]*){0,2})",
    re.IGNORECASE,
)


def _transaction_merchant_texts(message: str) -> list[str]:
    merchants = []
    for match in _TXN_MERCHANT_PHRASE.finditer(message):
        text = re.split(
            r"\s+(?:for|and|or|atau|on|in|to|at|from|di|daripada|rm|"
            r"last|latest|recent|over|under|about|around|between|"
            r"this|next|previous|bulan|hari|today|yesterday|tomorrow|"
            r"semalam|esok)\b",
            match.group("merchant"), flags=re.I,
        )[0].strip()
        if (not text or _MONTH_NAME_QUERY.fullmatch(text)
                or _NAMED_DAY_DATE_QUERY.fullmatch(text)
                or re.match(r"rm\s*\d", text, re.I)):
            continue
        # A date following "from" belongs to the period parser. Never turn it
        # into a text filter and accidentally return zero matching transactions.
        if re.match(
            r"^(?:\d{4}-\d{2}-\d{2}\b|\d{1,2}\s+(?:"
            + "|".join(_MONTH_NUMBERS)
            + r")\b|today\b|yesterday\b|tomorrow\b|semalam\b|esok\b|"
            r"hari\s+ini\b|this\s+month\b|last\s+month\b|next\s+month\b)",
            text, re.I,
        ):
            continue
        merchants.append(text)
    return merchants


def _transaction_merchant_text(message: str) -> str | None:
    merchants = _transaction_merchant_texts(message)
    return merchants[0] if merchants else None
# A period phrase ("from July", "this month", "2026-07") turns a verb-free
# "transactions ..." into a list, unless it is an aggregate or ranking question.
_TXN_PERIOD_CUE = re.compile(
    r"\b(?:this|last|next|previous)\s+month\b|\bbulan\s+(?:ini|lepas|depan)\b|"
    r"\b(?:today|yesterday|tomorrow|semalam|hari\s+ini|esok)\b|"
    r"\bfrom\s+\d|\bsince\s+\d|\d{4}-\d{2}|"
    r"\b(?:" + "|".join(_MONTH_NUMBERS) + r")\b",
    re.IGNORECASE,
)
_TXN_AGGREGATE_CUE = re.compile(
    r"\b(?:how\s+much|total|average|avg|sum)\b", re.IGNORECASE
)
# A demonstrative reference to a single record ("that transaction", "transaksi
# itu") cannot be resolved by a broad search. Without a concrete date/merchant
# locator it must ask which record, not silently dump every transaction.
_TRANSACTION_REFERENCE = re.compile(
    r"\b(?:that|this|the)\s+(?:transaction|purchase|expense|payment|charge|"
    r"one|record|item)\b|"
    r"\b(?:transaksi|pembelian|perbelanjaan|bayaran|rekod)\s+"
    r"(?:itu|ini|tersebut)\b",
    re.IGNORECASE,
)


def _has_transaction_locator(message: str) -> bool:
    """Whether a single-record reference is pinned to a resolvable filter."""
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", message):
        return True
    calendar_text = re.sub(r"\bmay\s+(?:i|we|you)\b", "", message, flags=re.I)
    if _MONTH_NAME_QUERY.search(calendar_text):
        return True
    if re.search(
        r"\b(?:yesterday|today|tomorrow|this\s+month|last\s+month|"
        r"semalam|hari\s+ini|esok|bulan\s+(?:ini|lepas))\b",
        message, re.I,
    ):
        return True
    # A named merchant/description filter, e.g. "that transaction at Speedmart".
    if re.search(r"\b(?:on|for|at|from|about|di|pada)\s+[\w&'\-]{2,}", message, re.I):
        return True
    return False


# Inspecting a stored image/receipt/attachment is a known read the coach cannot
# perform. It is UNSUPPORTED (out of capability), distinct from an ambiguous
# request that only needs clarification.
_UNSUPPORTED_MEDIA_READ = re.compile(
    r"\b(?:image|images|photo|photos|picture|pictures|attachment|attachments|"
    r"scan|scanned|screenshot|gambar|imej)\b",
    re.IGNORECASE,
)


def _is_unsupported_read(message: str) -> bool:
    """A known but out-of-scope read: opening a transaction's image/attachment."""
    if not _UNSUPPORTED_MEDIA_READ.search(message):
        return False
    return bool(
        _TRANSACTION_QUERY.search(message)
        or _TRANSACTION_REFERENCE.search(message)
        or re.search(r"\b(?:receipt|resit|transaction|transaksi)\b", message, re.I)
    )
_PROFILE_QUERY = re.compile(
    r"\b(?:income\s+source|financial\s+profile|coaching\s+style|"
    r"year\s+of\s+study)\b",
    re.IGNORECASE,
)
_CASHFLOW_FORECAST_QUERY = re.compile(
    r"\b(?:cash\s*flow|enough\s+until\s+(?:month[\s-]*end|the\s+end\s+of\s+the\s+month)|"
    r"available\s+until\s+month[\s-]*end)\b",
    re.IGNORECASE,
)
_PREDICTION_QUERY = re.compile(
    r"\b(?:predict(?:ion|ions|ed|ing)?|estimat(?:e|es|ed|ing|ion|ions)|"
    r"forecast(?:s|ing)?|project(?:ed|ion|ions)?|anggaran|ramalan|"
    r"how\s+much\s+(?:money\s+)?(?:can|could|will)\s+i\s+save|can\s+i\s+(?:save|afford)|"
    r"will\s+i\s+have\s+enough|enough\s+to\s+save|"
    r"savings?\s+potential|savings?\s+prediction|"
    r"berapa\s+boleh\s+simpan|boleh\s+(?:saya|aku)\s+simpan)\b",
    re.IGNORECASE,
)

_PERIOD_COMPARISON_QUERY = re.compile(
    r"\b(?:last\s+month|previous\s+month|compare|comparison|versus|vs|"
    r"bulan\s+lepas|banding(?:kan)?)\b",
    re.IGNORECASE,
)
_TODAY_RANGE_QUERY = re.compile(r"\b(?:today|hari\s+ini)\b", re.IGNORECASE)
_NEXT_WEEK_RANGE_QUERY = re.compile(
    r"\b(?:next\s+week|minggu\s+depan)\b", re.IGNORECASE
)
_NEXT_MONTH_RANGE_QUERY = re.compile(
    r"\b(?:next\s+month|bulan\s+depan)\b", re.IGNORECASE
)

# --- Multi-period comparison parsing ---------------------------------------
# A comparison over an arbitrary set of calendar months ("compare July, August
# and September", "the last six months", "this month with the previous three")
# routes to the dedicated get_period_comparison tool. Selection and the period
# list are resolved deterministically here; the backend validates and computes
# the figures, so no extra provider call is needed. Only calendar months are
# supported in this version — custom day ranges still clarify.
_MONTH_RANGE_SEPARATOR = re.compile(
    r"^\s*(?:-|–|—|to|through|thru|till|until|hingga|sehingga|sampai)\s*$",
    re.IGNORECASE,
)
_LAST_N_MONTHS_QUERY = re.compile(
    r"\b(?:last|past|previous|recent)\s+(?P<n>\d{1,2}|two|three|four|five|six|"
    r"seven|eight|nine|ten|eleven|twelve)\s+months?\b",
    re.IGNORECASE,
)
_PREVIOUS_N_QUERY = re.compile(
    r"\bprevious\s+(?P<n>\d{1,2}|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\b",
    re.IGNORECASE,
)
_COMPARISON_BASELINE_QUERY = re.compile(
    r"\b(?:against|compared\s+to|relative\s+to|baseline\s+(?:of|month)?)\s+"
    r"(?P<month>" + "|".join(_MONTH_NUMBERS) + r")\b(?:\s+(?P<year>20\d{2}))?",
    re.IGNORECASE,
)
_WORD_NUMBERS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_MAX_COMPARISON_MONTHS = 12


def _word_or_int(token: str) -> int | None:
    token = token.strip().casefold()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _infer_comparison_year(month: int, explicit_year: str | None, current_day: date) -> int:
    if explicit_year:
        return int(explicit_year)
    # A comparison looks backward: a month later than the current one belongs to
    # the previous year (e.g. "December" asked in September is last December).
    return current_day.year - (1 if month > current_day.month else 0)


def _shift_month(anchor: date, delta: int) -> date:
    """Return the first day of the month `delta` months from `anchor`."""
    index = (anchor.year * 12 + (anchor.month - 1)) + delta
    return date(index // 12, index % 12 + 1, 1)


def _named_comparison_months(message: str, current_day: date) -> list[date]:
    """Resolve every explicitly named calendar month, expanding a 'X to Y' range."""
    cleaned = re.sub(r"\bmay\s+(?:i|we|you)\b", "", message, flags=re.I)
    matches = list(_MONTH_NAME_QUERY.finditer(cleaned))
    resolved: list[tuple[int, int, date]] = []  # (start, end, month-start)
    for match in matches:
        month = _MONTH_NUMBERS[match.group("month").casefold()]
        year = _infer_comparison_year(month, match.group("year"), current_day)
        resolved.append((match.start("month"), match.end(), date(year, month, 1)))

    if len(resolved) == 2:
        between = cleaned[resolved[0][1]:resolved[1][0]]
        if _MONTH_RANGE_SEPARATOR.match(between):
            start, end = sorted((resolved[0][2], resolved[1][2]))
            months, cursor = [], start
            while cursor <= end and len(months) <= _MAX_COMPARISON_MONTHS:
                months.append(cursor)
                cursor = _shift_month(cursor, 1)
            return months
    unique = sorted({item[2] for item in resolved})
    return unique


def parse_comparison_request(
    content: str,
    *,
    now: datetime | date | None = None,
) -> dict[str, object] | None:
    """Resolve a multi-month comparison into metric, periods, category, baseline.

    Returns ``None`` when the message is not a multi-period comparison. Raises
    ``ValueError`` with a user-facing message when a comparison is clearly meant
    but the months cannot be resolved to at least two calendar months.
    """
    message = " ".join(content.strip().split())
    current_day = _malaysia_date(now)
    current_start = current_day.replace(day=1)

    # A pair of named days is a date range, even when the days fall in
    # different months. Treating its month words as a month comparison drops
    # the stated day boundaries.
    if _NAMED_DAY_DATE_QUERY.search(message):
        if _PERIOD_COMPARISON_QUERY.search(message):
            raise ValueError("Please use calendar months for a comparison, or ask for a date-range spending total.")
        return None

    months = _named_comparison_months(message, current_day)

    if not months:
        last_n = _LAST_N_MONTHS_QUERY.search(message)
        if last_n:
            count = _word_or_int(last_n.group("n")) or 0
            if count >= 2:
                includes_current = bool(_THIS_MONTH_QUERY.search(message))
                # "last six months" means six completed months; "including this
                # month" keeps the in-progress current month in the window.
                offset = 0 if includes_current else 1
                months = sorted(
                    _shift_month(current_start, -(i + offset)) for i in range(count)
                )

    if not months:
        previous_n = _PREVIOUS_N_QUERY.search(message)
        if previous_n and _THIS_MONTH_QUERY.search(message):
            count = _word_or_int(previous_n.group("n")) or 0
            if count >= 1:
                months = sorted(
                    [current_start, *(_shift_month(current_start, -(i + 1)) for i in range(count))]
                )

    if not months:
        return None

    months = sorted(set(months))[:_MAX_COMPARISON_MONTHS]

    # A single resolvable month is an ordinary month lookup, not a comparison —
    # unless the user clearly asked to compare, in which case ask for the months.
    if len(months) < 2:
        if _PERIOD_COMPARISON_QUERY.search(message):
            raise ValueError(
                "Please name at least two calendar months to compare, for "
                "example 'compare July and September 2026'."
            )
        return None

    metric = "budget" if (_BUDGET_QUERY.search(message) and not _TRANSACTION_QUERY.search(message)) else "spending"

    baseline = None
    baseline_match = _COMPARISON_BASELINE_QUERY.search(message)
    if baseline_match:
        b_month = _MONTH_NUMBERS[baseline_match.group("month").casefold()]
        b_year = _infer_comparison_year(b_month, baseline_match.group("year"), current_day)
        baseline = date(b_year, b_month, 1)

    return {
        "metric": metric,
        "periods": [month.strftime("%Y-%m") for month in months],
        "category_name": _category_filter(message),
        "baseline": baseline.strftime("%Y-%m") if baseline else None,
    }


def is_multi_period_comparison(content: str, *, now: datetime | date | None = None) -> bool:
    """Whether the message compares two or more explicit calendar months."""
    try:
        return parse_comparison_request(content, now=now) is not None
    except ValueError:
        # A comparison was clearly meant but under-specified; the tool selector
        # still claims it so the resolver can raise a clarification.
        return True

# These are the short, data-dependent Coach quick actions shown in the mobile
# UI.  They must not fall through to casual chat: an answer about what the user
# should do first or a calculation needs current owner-scoped records.
_FINANCIAL_PRIORITY_QUERY = re.compile(
    r"\b(?:what\s+(?:should|do)\s+i\s+do\s+first|"
    r"what\s+do\s+i\s+do\s+first|next\s+(?:step|steps|priority|priorities)|"
    r"highest\s+priorit(?:y|ies)|what\s+should\s+i\s+prioriti[sz]e)\b",
    re.IGNORECASE,
)
_CALCULATION_QUERY = re.compile(
    r"\b(?:show\s+(?:me\s+)?the\s+calculation|show\s+(?:me\s+)?the\s+math|"
    r"how\s+(?:did|do)\s+you\s+calculate)\b",
    re.IGNORECASE,
)
_FINANCIAL_TRIAGE_QUERY = re.compile(
    r"\b(?:what\s+(?:should|do)\s+i\s+do\s+first|"
    r"what\s+do\s+i\s+do\s+first|next\s+(?:step|steps|priority|priorities)|"
    r"highest\s+priorit(?:y|ies)|what\s+should\s+i\s+prioriti[sz]e|"
    r"show\s+(?:me\s+)?the\s+calculation|show\s+(?:me\s+)?the\s+math|"
    r"how\s+(?:did|do)\s+you\s+calculate|can\s+i\s+afford|"
    r"how\s+am\s+i\s+doing|(?:review|plan|optimise|optimize)\s+(?:my\s+)?finances?)\b",
    re.IGNORECASE,
)
_DEADLINE_QUERY = re.compile(
    r"\b(?:due|deadline|upcoming\s+(?:bill|payment)|"
    r"(?:bill|payment).{0,30}(?:due|when))\b",
    re.IGNORECASE,
)


def required_agent_tool_names(content: str) -> tuple[str, ...]:
    """Return every explicit confirmation-gated action requested in the turn."""
    message = " ".join(content.strip().split())
    names: list[str] = []
    if (
        not _REMINDER_NON_CREATE.search(message)
        and _REMINDER_CREATE_REQUEST.search(message)
    ):
        names.append("prepare_reminder")
    if (
        not _REPORT_NON_CREATE.search(message)
        and _REPORT_CREATE_REQUEST.search(message)
    ):
        names.append("prepare_report")
    return tuple(names)


def required_agent_tool_name(content: str) -> str | None:
    """Return the first safe action tool for single-action provider forcing."""
    names = required_agent_tool_names(content)
    return names[0] if names else None


def ambiguous_reminder_title(content: str) -> str | None:
    """Return a task title when a payment command needs intent clarification."""
    message = " ".join(content.strip().split())
    match = _AMBIGUOUS_REMINDER_TASK.fullmatch(message)
    if not match:
        return None
    title = match.group("title").strip(" .!?")
    return title[:1].upper() + title[1:]


def route_coach_message(content: str) -> CoachingRoute:
    """Classify without another provider call, keeping routing fast and predictable."""
    message = normalize_for_intent(content)
    if not message or _CASUAL_ONLY.fullmatch(message) or _CASUAL_NON_FINANCIAL.search(message):
        return CoachingRoute.CASUAL

    if (re.search(r"^(?:what\s+is|what\s+are|explain|how\s+to)\b", message, re.I)
            and (is_weekly_savings_plan_request(message) or _SAVINGS_GOAL_QUERY.search(message))
            and not re.search(r"\b(?:my|me|i|saya|aku)\b", message, re.I)):
        return CoachingRoute.FINANCIAL_EDUCATION

    # The mobile Coach exposes these without finance keywords. They are still
    # personal-finance questions because a useful answer requires live records.
    if is_financial_triage_query(message):
        return CoachingRoute.PERSONAL_FINANCE

    # App actions need the tool-capable path even when the user does not use
    # a finance keyword (for example, "Create a reminder to pay rent").
    # The agent still prepares a confirmation card; it never writes data here.
    if required_agent_tool_name(message):
        return CoachingRoute.PERSONAL_FINANCE
    if is_category_budget_recommendation_request(message):
        return CoachingRoute.PERSONAL_FINANCE
    if ambiguous_reminder_title(message):
        return CoachingRoute.PERSONAL_FINANCE
    if _REMINDER_REFERENCE.search(message) or _REPORT_REFERENCE.search(message):
        return CoachingRoute.PERSONAL_FINANCE
    if _DEADLINE_QUERY.search(message):
        return CoachingRoute.PERSONAL_FINANCE
    # "I spend time with friends", "spend hours on homework": a non-financial
    # activity with no financial signal is casual, even though "my"/"I" appears.
    if _NON_FINANCIAL_ACTIVITY.search(message) and not (
        _TRANSACTION_QUERY.search(message)
        or _BUDGET_QUERY.search(message)
        or _SAVINGS_GOAL_QUERY.search(message)
        or _PREDICTION_QUERY.search(message)
        or _FINANCIAL_EDUCATION.search(message)
        or detect_knowledge_topics(message)
        or re.search(r"\brm\s*\d", message, re.I)
    ):
        return CoachingRoute.CASUAL
    is_saved_finance_topic = bool(
        _SAVINGS_GOAL_QUERY.search(message)
        or _BUDGET_QUERY.search(message)
        or _TRANSACTION_QUERY.search(message)
        or is_category_ranking_query(message)
        or _PROFILE_QUERY.search(message)
        or _CASHFLOW_FORECAST_QUERY.search(message)
        or _PREDICTION_QUERY.search(message)
        or is_weekly_savings_plan_request(message)
        or is_multi_period_comparison(message)
    )

    needs_personal_context = bool(_PERSONAL_FINANCE.search(message))
    needs_knowledge = bool(
        _FINANCIAL_EDUCATION.search(message)
        or detect_knowledge_topics(message)
    )

    # A budget-allocation/method request is educational, even though it mentions
    # "budget". A hypothetical amount ("if I have RM6000") is planning framing,
    # not a recorded figure, so it must not pin the query to personal records.
    if _BUDGET_ALLOCATION_QUERY.search(message):
        needs_knowledge = True
    if _HYPOTHETICAL_AMOUNT.search(message):
        needs_personal_context = False

    # A normative/general question ("what budget do people normally set") that
    # carries no personal marker is educational, not a lookup of the user's saved
    # records — even though it mentions a finance keyword like "budget".
    if _GENERAL_KNOWLEDGE_CUE.search(message) and not needs_personal_context:
        needs_knowledge = True
        is_saved_finance_topic = False

    if is_saved_finance_topic:
        if needs_knowledge:
            return (
                CoachingRoute.COMBINED
                if needs_personal_context
                else CoachingRoute.FINANCIAL_EDUCATION
            )
        return CoachingRoute.PERSONAL_FINANCE

    if needs_personal_context and needs_knowledge:
        return CoachingRoute.COMBINED
    if needs_personal_context:
        return CoachingRoute.PERSONAL_FINANCE
    if needs_knowledge:
        return CoachingRoute.FINANCIAL_EDUCATION
    return CoachingRoute.CASUAL


def is_budget_planning_request(content: str) -> bool:
    """Whether a user wants a proposed monthly limit rather than a saved status."""
    message = normalize_for_intent(content)
    return bool(
        _BUDGET_PLANNING_QUERY.search(message)
        and not is_category_budget_recommendation_request(message)
    )


def is_category_budget_recommendation_request(content: str) -> bool:
    """Whether the user wants a data-backed category limit recommendation."""
    return bool(_CATEGORY_BUDGET_RECOMMENDATION_QUERY.search(normalize_for_intent(content)))


def is_budget_save_command(content: str) -> bool:
    """Whether the user is commanding a budget write from the Coach chat."""
    message = normalize_for_intent(content)
    return bool(
        _BUDGET_SAVE_COMMAND.search(message)
        and not is_category_budget_recommendation_request(message)
    )


_MARKET_PRODUCT_NOUN = re.compile(
    r"\b(?:banks?|e-?wallets?|broker(?:age)?s?|unit\s+trusts?|"
    r"mutual\s+funds?|funds?|insurances?|takaful|credit\s+cards?|"
    r"debit\s+cards?|robo[-\s]?advisors?|crypto(?:currenc(?:y|ies))?|"
    r"coins?|bitcoin|ethereum|stocks?|shares?|fixed\s+deposits?|"
    r"savings?\s+accounts?|current\s+accounts?)\b",
    re.IGNORECASE,
)
# Ranking/recommendation asks ("best", "recommend") signal product selection.
# Bare "what is"/"which" is deliberately excluded so a definitional question
# ("what is an emergency fund?") stays on the educational path.
_RANKING_CUE = re.compile(
    r"\b(?:best|better|top|recommend(?:ation)?s?|suggest)\b",
    re.IGNORECASE,
)
_ACQUISITION_VERB = re.compile(
    r"\b(?:open|get|choose|buy|use|pick|sign\s+up|subscribe|invest|"
    r"switch\s+to|apply\s+for)\b",
    re.IGNORECASE,
)
_PERSONAL_OWNERSHIP = re.compile(
    r"\b(?:my|mine|i\s+have|i\s+own|recorded)\b",
    re.IGNORECASE,
)


def is_product_selection_request(content: str) -> bool:
    """Whether the user is asking FinCoach to pick or rank a market product.

    Fires only when a market-product noun is paired with a ranking cue or an
    acquisition verb, so "which e-wallet is best?" or "should I buy this fund?"
    is intercepted with a neutral redirect, while a definitional question ("what
    is an emergency fund?") or one about the user's own recorded products
    ("which of my funds performed best?") is left to the normal path.
    """
    message = " ".join((content or "").strip().split())
    if not message or not _MARKET_PRODUCT_NOUN.search(message):
        return False
    ranking = bool(_RANKING_CUE.search(message))
    acquires = bool(_ACQUISITION_VERB.search(message))
    if not (ranking or acquires):
        return False
    if bool(_PERSONAL_OWNERSHIP.search(message)) and not acquires:
        return False
    return True


def required_read_agent_tool_name(
    content: str,
    route: CoachingRoute | None = None,
) -> str | None:
    """Return the first read tool required before a personal factual answer.

    The provider can still request additional allowlisted read tools afterwards,
    but the first call establishes a current, owner-scoped evidence baseline.
    Casual chat and financial education never read personal records.
    """
    route = route or route_coach_message(content)
    if route not in (CoachingRoute.PERSONAL_FINANCE, CoachingRoute.COMBINED):
        return None

    message = normalize_for_intent(content)
    if is_multi_period_comparison(message):
        return "get_period_comparison"
    if _CASHFLOW_FORECAST_QUERY.search(message):
        return "get_cashflow_forecast"
    if is_weekly_savings_plan_request(message):
        return "get_weekly_savings_plan"
    if is_category_budget_recommendation_request(message):
        return "get_category_budget_recommendation"
    if is_budget_save_command(message):
        return None
    if _PREDICTION_QUERY.search(message):
        return "predict_savings"
    if _PROFILE_QUERY.search(message):
        return "get_financial_profile"
    if is_financial_triage_query(message):
        return "get_financial_overview"
    if _REMINDER_REFERENCE.search(message) or _DEADLINE_QUERY.search(message):
        return "get_upcoming_reminders"
    if _SAVINGS_GOAL_QUERY.search(message):
        return "get_savings_goals"
    if _BUDGET_QUERY.search(message):
        return "get_budget_status"
    # Transaction search covers verb-free lists, counts, and merchant totals, so
    # a stated filter is never answered by an unfiltered summary. Ranking asks
    # for clarification (handled when arguments are derived).
    if (_TXN_TOP_QUERY.search(message) or _TXN_OLDEST_QUERY.search(message)
            or _TXN_MERCHANT_TOTAL.search(message)):
        return "search_transactions"
    has_transaction_noun = bool(_TRANSACTION_NOUN.search(message))
    if has_transaction_noun and _TXN_COUNT_QUERY.search(message):
        return "search_transactions"
    if _TRANSACTION_SEARCH_QUERY.search(message):
        return "search_transactions"
    if has_transaction_noun and (
        re.search(r"\b(?:last|latest|recent)\s+\d", message, re.I)
        or _transaction_merchant_text(message)
        or re.search(r"\brm\s*\d", message, re.I)
        or extract_category_candidate(message)
        or (
            _TXN_PERIOD_CUE.search(message)
            and not is_category_ranking_query(message)
            and not _TXN_AGGREGATE_CUE.search(message)
        )
    ):
        return "search_transactions"
    if _TRANSACTION_QUERY.search(message) or is_category_ranking_query(message):
        return "get_spending_summary"
    return "get_financial_overview"


def required_read_agent_tool_arguments(
    content: str,
    tool_name: str,
    *,
    now: datetime | date | None = None,
) -> dict[str, object]:
    """Derive only unambiguous filters for the deterministic read tool."""
    message = " ".join(content.strip().split())
    arguments: dict[str, object] = {}
    current_day = _malaysia_date(now)
    if tool_name == "get_period_comparison":
        parsed = parse_comparison_request(message, now=now)
        if not parsed:
            raise ValueError(
                "Please name at least two calendar months to compare, for "
                "example 'compare July and September 2026'."
            )
        arguments["metric"] = parsed["metric"]
        arguments["periods"] = parsed["periods"]
        if parsed["category_name"]:
            arguments["category_name"] = parsed["category_name"]
        if parsed["baseline"]:
            arguments["baseline"] = parsed["baseline"]
        return arguments
    # Reminder reads accept a relative range enum, not an arbitrary date span.
    # In a write command, a named date belongs to the reminder draft parser.
    start, end = ((None, None) if tool_name == "get_upcoming_reminders"
                  else _explicit_period(message, tool_name, current_day))
    if tool_name in {"get_spending_summary", "get_report_summary", "search_transactions"} and start and end:
        arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
    elif tool_name in {"get_budget_status", "get_category_budget_recommendation", "get_financial_overview", "predict_savings", "get_weekly_savings_plan"} and start:
        arguments["month"] = start.strftime("%Y-%m")
    type_match = _TXN_TYPE_QUERY.search(message) if tool_name == "search_transactions" else None
    category = _category_filter(message)
    if type_match and category and category.casefold() == type_match.group("type").casefold():
        category = None
    if category and tool_name in {
        "get_spending_summary",
        "get_report_summary",
        "search_transactions",
        "get_budget_status",
        "get_category_budget_recommendation",
        "get_financial_overview",
    }:
        arguments["category_name"] = category
    if tool_name in {"get_spending_summary", "get_financial_overview"} and (
        _PERIOD_COMPARISON_QUERY.search(message)
    ):
        arguments["compare_previous_period"] = True
    if tool_name == "get_upcoming_reminders":
        if _TODAY_RANGE_QUERY.search(message):
            arguments["range"] = "today"
        elif _NEXT_WEEK_RANGE_QUERY.search(message):
            arguments["range"] = "next_week"
        elif _NEXT_MONTH_RANGE_QUERY.search(message):
            arguments["range"] = "next_month"
    if tool_name == "search_transactions":
        # Amount-ranked lists ("top 5 transactions") are not supported yet.
        if _TXN_TOP_QUERY.search(message):
            raise ValueError(
                "Please tell me which transactions you mean — ranking transactions "
                "by value isn't supported yet, but I can show your recent "
                "transactions or search by merchant."
            )
        if _TXN_OLDEST_QUERY.search(message):
            raise UnsupportedTransactionFilter(
                "Please ask for recent transactions; earliest-first ordering is not supported yet."
            )
        if _TXN_EXCLUSION_QUERY.search(message):
            raise UnsupportedTransactionFilter(
                "Please choose a category to include; excluding a category is not supported yet."
            )
        merchants = _transaction_merchant_texts(message)
        if _TXN_MERCHANT_JOIN.search(message) or len(merchants) > 1:
            raise UnsupportedTransactionFilter(
                "Please search one merchant at a time; combining merchants is not supported yet."
            )
        if type_match:
            arguments["transaction_type"] = type_match.group("type").casefold()
        if _TXN_COUNT_QUERY.search(message):
            arguments["result_mode"] = "count"
        elif _TXN_MERCHANT_TOTAL.search(message):
            arguments["result_mode"] = "expense_total"
        # "last 5 [transactions]" / "5 transactions" -> newest N (list mode only).
        count = (
            re.search(r"\b(?:last|latest|recent)\s+(\d{1,2})\b", message, re.I)
            or re.search(r"\b(\d{1,2})\s+(?:transactions?|purchases?|records?)\b", message, re.I)
        )
        if count and arguments.get("result_mode", "list") == "list":
            value = int(count.group(1))
            if 1 <= value <= 50:
                arguments["limit"] = value
        # Match the complete money token before validating it. A prefix match on
        # RM1,000 or RM25.999 would query the wrong amount; a magnitude suffix
        # (RM25k) or a sign (RM-25) must also reach validation, not be truncated
        # to RM25 or dropped so the token leaks into the category filter.
        amounts = re.findall(r"\brm\s*(-?[\w.,]+)", message, re.I)
        if amounts:
            if len(amounts) != 1 or not re.fullmatch(
                r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?",
                amounts[0].rstrip("."),
            ):
                raise ValueError("Please provide one exact amount, with at most two decimal places.")
            if re.search(
                r"\b(?:over|under|above|below|more\s+than|less\s+than|at\s+least|"
                r"at\s+most|greater\s+than|fewer\s+than|between|min|max|minimum|"
                r"maximum|around|about|approximately)\b",
                message, re.I,
            ):
                raise ValueError(
                    "I can match an exact amount like RM25 for now. Which exact "
                    "amount should I search for?"
                )
            arguments["amount"] = f"{Decimal(amounts[0].rstrip('.').replace(',', '')):.2f}"
        if merchants:
            arguments["text"] = merchants[0]
    return arguments


def resolve_read_request(
    content: str,
    history: list[dict],
    *,
    current_message_id: str | None = None,
    now: datetime | date | None = None,
) -> ResolvedReadRequest:
    """Resolve a direct personal read or a safe follow-up from bounded history.

    Only read-only requests can be inherited. Reminder/report preparation and
    every other write action are intentionally excluded from this resolver.
    """
    # Replay the bounded user turns chronologically so a category-only modifier
    # becomes part of the effective context for a later month-only modifier.
    # Explicit topic changes reset it; writes and educational turns never inherit.
    context: ResolvedReadRequest | None = None
    turns = [str(message.get("content") or "") for message in history
             if message.get("role") == "user" and message.get("status") != "failed"
             and not (current_message_id and message.get("id") == current_message_id)]
    for text in [*turns, content]:
        intent_text = normalize_for_intent(text)
        route = route_coach_message(text)
        direct_tool = required_read_agent_tool_name(text, route)
        is_modifier = _is_follow_up_modifier(text) and not any(pattern.search(intent_text) for pattern in (
            _TRANSACTION_QUERY, _BUDGET_QUERY, _SAVINGS_GOAL_QUERY,
            _PROFILE_QUERY, _REMINDER_REFERENCE, _CASHFLOW_FORECAST_QUERY, _PREDICTION_QUERY,
        )) and not is_category_ranking_query(intent_text)
        if route in (CoachingRoute.FINANCIAL_EDUCATION, CoachingRoute.COMBINED) or required_agent_tool_names(text):
            is_modifier = False
        # Opening a stored image/attachment is a known but unsupported read; a
        # bare savings mention or a demonstrative single-record reference is
        # ambiguous. None of these may inherit a read or run a broad search.
        unsupported = _is_unsupported_read(text)
        ambiguous_savings = _is_ambiguous_savings(text)
        unresolved_txn_ref = bool(
            _TRANSACTION_REFERENCE.search(text) and not _has_transaction_locator(text)
        )
        inherited = bool(
            is_modifier and context and context.tool_name
            and not (unsupported or ambiguous_savings or unresolved_txn_ref)
        )
        tool = context.tool_name if inherited else direct_tool
        arguments = dict(context.arguments) if inherited else {}
        # Inherited parameters carry provenance "context"; explicit/default are
        # recorded as they are resolved below.
        parameter_sources: dict[str, str] = (
            {key: "context" for key in (context.parameter_sources if context else {})}
            if inherited else {}
        )
        clarification: str | None = None
        readiness = ReadReadiness.READY
        missing_required: tuple[str, ...] = ()
        invalid_fields: tuple[str, ...] = ()
        intent = _TOOL_INTENT.get(tool) if tool else None

        if unsupported:
            tool, arguments, parameter_sources, intent = None, {}, {}, None
            readiness = ReadReadiness.UNSUPPORTED
            clarification = (
                "I can't open receipts or images from here. I can still summarise "
                "that transaction if you tell me its date, merchant, or amount."
            )
        elif ambiguous_savings:
            tool, arguments, parameter_sources = None, {}, {}
            intent = "savings_unspecified"
            readiness = ReadReadiness.NEEDS_CLARIFICATION
            missing_required = ("savings_intent",)
            clarification = (
                "Do you mean your savings-goal progress, or an estimate of how "
                "much you could save? Let me know which and I'll pull it up."
            )
        elif unresolved_txn_ref:
            tool, arguments, parameter_sources = None, {}, {}
            intent = "transaction_reference"
            readiness = ReadReadiness.NEEDS_CLARIFICATION
            missing_required = ("transaction_filter",)
            clarification = (
                "Which transaction do you mean? Share its date, the merchant, or "
                "a short description and I'll find it."
            )
        elif tool:
            try:
                explicit = required_read_agent_tool_arguments(text, tool, now=now)
                for key in explicit:
                    parameter_sources[key] = "explicit"
                arguments.update(explicit)
                if re.search(r"\b(?:all\s+categories|semua\s+kategori)\b", text, re.I):
                    arguments.pop("category_name", None)
                    parameter_sources.pop("category_name", None)
                if tool in _MONTH_PERIOD_TOOLS:
                    start, end = _explicit_period(text, tool, _malaysia_date(now))
                    if start and end and (start.day != 1 or end != _month_end(start)):
                        subject = "Savings plans and predictions" if tool in {"predict_savings", "get_weekly_savings_plan"} else "Budgets"
                        raise ValueError(f"{subject} use calendar months. Please specify a month and year.")
                # Materialise the default period with provenance so the answer can
                # state it; the executor keeps its own default for bare callers.
                for key, value in _default_period_arguments(tool, now).items():
                    if key not in arguments:
                        arguments[key] = value
                        parameter_sources[key] = "default"
            except ValueError as error:
                arguments, parameter_sources = {}, {}
                readiness = ReadReadiness.NEEDS_CLARIFICATION
                message_text = str(error)
                if isinstance(error, UnsupportedTransactionFilter):
                    invalid_fields = ("transaction_filter",)
                    clarification = message_text
                elif "amount" in message_text.lower():
                    invalid_fields = ("amount",)
                    clarification = message_text
                elif "ranking" in message_text.lower():
                    invalid_fields = ()
                    clarification = message_text
                else:
                    invalid_fields = _period_invalid_fields(tool)
                    clarification = message_text if "Please" in message_text else "Please provide valid dates in YYYY-MM-DD format, with the start before the end."
        elif is_modifier and route == CoachingRoute.CASUAL:
            readiness = ReadReadiness.NEEDS_CLARIFICATION
            missing_required = ("read_intent",)
            clarification = "Which financial record should I use? For example, ask for your expenses, budget, savings goal, or reminders."

        resolved = ResolvedReadRequest(
            route=CoachingRoute.PERSONAL_FINANCE if inherited else route,
            tool_name=tool, arguments=arguments, inherited=inherited,
            clarification=clarification, intent=intent, readiness=readiness,
            missing_required=missing_required, invalid_fields=invalid_fields,
            parameter_sources=parameter_sources,
        )
        context = (
            resolved
            if tool and readiness == ReadReadiness.READY and not clarification
            and not required_agent_tool_names(text)
            else None
        )
    return resolved


def _malaysia_date(value: datetime | date | None) -> date:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Kuala_Lumpur"))
        return value.astimezone(ZoneInfo("Asia/Kuala_Lumpur")).date()
    return value


_NAMED_DAY_DATE_QUERY = re.compile(
    r"\b(?:"
    r"(?P<day_first>\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?P<month_first>" + "|".join(_MONTH_NUMBERS) + r")\b"
    r"(?:,?\s+(?P<year_first>20\d{2}))?"
    r"|(?P<month_second>" + "|".join(_MONTH_NUMBERS) + r")\s+"
    r"(?P<day_second>\d{1,2})(?:st|nd|rd|th)?\b"
    r"(?:,?\s+(?P<year_second>20\d{2}))?"
    r")",
    re.I,
)


def _named_day_period(message: str, current_day: date) -> tuple[date, date] | None:
    matches = list(_NAMED_DAY_DATE_QUERY.finditer(message))
    if not matches:
        return None
    if len(matches) > 2:
        raise ValueError("Please specify one date or a start and end date.")
    if len(matches) == 2:
        connector = message[matches[0].end():matches[1].start()]
        if not re.fullmatch(r"\s*(?:to|until|through|and|-|–|—)\s*", connector, re.I):
            raise ValueError("Please specify the start and end dates clearly.")
    elif re.search(r"(?:\b(?:to|until|through|and)\s+|[-–—]\s*)"
                   r"(?:\d{1,2}|(?:" + "|".join(_MONTH_NUMBERS) + r")\b)",
                   message[matches[0].end():], re.I):
        # A partial second endpoint must never silently collapse to one day.
        raise ValueError("Please specify both dates with their day and month.")

    explicit_years = {
        int(year) for match in matches
        if (year := match.group("year_first") or match.group("year_second"))
    }
    if not explicit_years and len(matches) == 2:
        first_month = _MONTH_NUMBERS[(matches[0].group("month_first") or matches[0].group("month_second")).casefold()]
        last_month = _MONTH_NUMBERS[(matches[1].group("month_first") or matches[1].group("month_second")).casefold()]
        if first_month > last_month:
            raise ValueError("Please include the year for a range crossing calendar years.")
    inferred_year = None
    if len(explicit_years) == 1:
        inferred_year = next(iter(explicit_years))
    elif not explicit_years:
        last_month = _MONTH_NUMBERS[(matches[-1].group("month_first") or matches[-1].group("month_second")).casefold()]
        inferred_year = current_day.year - (last_month > current_day.month)

    dates = []
    for match in matches:
        month_name = match.group("month_first") or match.group("month_second")
        day_text = match.group("day_first") or match.group("day_second")
        year_text = match.group("year_first") or match.group("year_second")
        dates.append(date(int(year_text) if year_text else inferred_year,
                          _MONTH_NUMBERS[month_name.casefold()], int(day_text)))
    if dates[0] > dates[-1]:
        raise ValueError("Please provide a start date before the end date.")
    return dates[0], dates[-1]


def _explicit_period(
    message: str,
    tool_name: str,
    current_day: date,
) -> tuple[date | None, date | None]:
    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)
    named_day = _named_day_period(message, current_day)
    if iso_dates and named_day:
        raise ValueError("Please use the same date format for both range endpoints.")
    if iso_dates:
        parsed = [date.fromisoformat(value) for value in iso_dates]
        if len(parsed) > 2 or parsed[0] > parsed[-1]:
            raise ValueError("Provide a valid start date followed by an end date.")
        return parsed[0], parsed[-1]
    if named_day:
        return named_day
    if re.search(r"\b(?:yesterday|semalam)\b", message, re.I):
        day = current_day - timedelta(days=1)
        return day, day
    if _TODAY_RANGE_QUERY.search(message):
        return current_day, current_day
    if re.search(r"\b(?:tomorrow|esok)\b", message, re.I):
        day = current_day + timedelta(days=1)
        return day, day
    if _NEXT_MONTH_RANGE_QUERY.search(message):
        start = _month_end(current_day.replace(day=1)) + timedelta(days=1)
        return start, _month_end(start)
    if _THIS_MONTH_QUERY.search(message):
        start = current_day.replace(day=1)
        return start, _month_end(start)
    if _LAST_MONTH_QUERY.search(message):
        # 'Compare spending with last month' means current vs previous, not
        # previous vs the month before that. Explicit two-named-month requests
        # require a separate range clarification rather than guessing.
        if re.search(r"\b(?:compare|comparison|banding(?:kan)?)\b", message, re.I):
            start = current_day.replace(day=1)
            return start, _month_end(start)
        start = (current_day.replace(day=1) - timedelta(days=1)).replace(day=1)
        return start, _month_end(start)
    # 'May I ...' is a modal request, not an explicit calendar month.
    calendar_text = re.sub(r"\bmay\s+(?:i|we|you)\b", "", message, flags=re.I)
    # A month word inside an explicit category marker or quotes is a CATEGORY
    # name, not a period ("category May", "\"May\" spending"): mask it so the read
    # uses the default month while the resolver keeps the category.
    calendar_text = re.sub(r"[\"“”][^\"“”]*[\"“”]", " ", calendar_text)
    calendar_text = re.sub(
        r"\b(?:category|categories|kategori)\s*:?\s+[\w&'\-]+",
        " ", calendar_text, flags=re.I,
    )
    match = _MONTH_NAME_QUERY.search(calendar_text)
    if not match:
        if tool_name != "get_upcoming_reminders" and re.search(
            r"\b(?:(?:last|next|this|previous)\s+(?:week|fortnight|year|quarter)|"
            r"from\s+\d|between\s+\d|since\s+\d|minggu\s+(?:ini|lepas|depan))\b", message, re.I
        ):
            raise ValueError("Please specify the period as YYYY-MM-DD to YYYY-MM-DD.")
        return None, None
    month = _MONTH_NUMBERS[match.group("month").casefold()]
    explicit_year = match.group("year")
    if explicit_year:
        year = int(explicit_year)
    elif is_budget_planning_request(message) or tool_name in {"predict_savings", "get_weekly_savings_plan"}:
        year = current_day.year + (month < current_day.month)
    else:
        year = current_day.year - (month > current_day.month)
    start = date(year, month, 1)
    return start, _month_end(start)


def _month_end(start: date) -> date:
    next_month = date(
        start.year + (start.month == 12),
        1 if start.month == 12 else start.month + 1,
        1,
    )
    return next_month - timedelta(days=1)


def _default_period_arguments(
    tool_name: str, now: datetime | date | None
) -> dict[str, object]:
    """The current-Malaysia-month range a spending-style read falls back to.

    Only date-range reads materialise a concrete default here so the answer can
    state the period it used. Month-key reads (budget/overview/prediction/plan)
    keep the executor's own current-month default, so a broad overview is not
    silently narrowed and older callers stay unchanged.
    """
    if tool_name in _RANGE_PERIOD_TOOLS:
        start = _malaysia_date(now).replace(day=1)
        return {"start_date": start.isoformat(), "end_date": _month_end(start).isoformat()}
    if tool_name == "get_category_budget_recommendation":
        return {"month": _malaysia_date(now).strftime("%Y-%m")}
    return {}


def _period_invalid_fields(tool_name: str) -> tuple[str, ...]:
    """Which parameter a rejected period maps to, for the read contract."""
    if tool_name in _MONTH_PERIOD_TOOLS:
        return ("month",)
    return ("start_date", "end_date")


def _category_filter(message: str) -> str | None:
    # Separate trailing period modifiers from category text before parsing.
    text = re.split(
        r"\b(?:this\s+month|last\s+month|next\s+month|today|yesterday|tomorrow|"
        r"bulan\s+(?:ini|lepas|depan)|hari\s+ini|semalam|esok|from\s+\d|"
        r"in\s+(?:" + "|".join(_MONTH_NUMBERS) + r")\b)",
        message, maxsplit=1, flags=re.I,
    )[0].strip()
    only = _category_only(text)
    if only:
        return only
    candidate = extract_category_candidate(text)
    if candidate:
        return candidate
    match = re.search(
        r"\b(?:spend(?:ing)?|spent|expenses?|transactions?|belanja|perbelanjaan|"
        r"budget|bajet)\s+(?:on|for|untuk|kategori|category)\s+"
        r"(?P<category>[\w&'\- ]{1,80}?)[?.!\s]*$", text, re.I,
    )
    if match:
        candidate = " ".join(match.group("category").split())
        # An amount ("RM25") or bare number is a search filter, not a category.
        if not re.fullmatch(r"(?:rm\s*)?\d+(?:\.\d+)?", candidate, re.I):
            return candidate.title()
    return None


def _category_only(message: str) -> str | None:
    match = _CATEGORY_ONLY_QUERY.search(message)
    if not match:
        return None
    category = " ".join(match.group("category").split()).strip(" .?!")
    return category.title() if category else None


def _is_follow_up_modifier(content: str) -> bool:
    message = " ".join(content.strip().split())
    return bool(
        _FOLLOW_UP_PREFIX.search(message)
        or _MONTH_NAME_QUERY.search(message)
        or _THIS_MONTH_QUERY.search(message)
        or _LAST_MONTH_QUERY.search(message)
        or _CATEGORY_ONLY_QUERY.search(message)
        or _PERIOD_COMPARISON_QUERY.search(message)
    )


def is_financial_triage_query(content: str) -> bool:
    """Whether a question needs a full, evidence-based financial prioritisation."""
    return bool(_FINANCIAL_TRIAGE_QUERY.search(" ".join(content.strip().split())))


def select_financial_context_scope(
    content: str,
    route: CoachingRoute | None = None,
) -> FinancialContextScope | None:
    """Map a personal question to only the stored FinCoach modules it needs.

    General education and casual chat never read a user's financial records.
    A broad personal status question is the sole fallback that requests a full
    overview, because every available module may be relevant to that question.
    """
    route = route or route_coach_message(content)
    if route not in (CoachingRoute.PERSONAL_FINANCE, CoachingRoute.COMBINED):
        return None

    message = normalize_for_intent(content)
    asks_about_goals = bool(_SAVINGS_GOAL_QUERY.search(message))
    asks_about_budget = bool(_BUDGET_QUERY.search(message))
    asks_about_transactions = bool(_TRANSACTION_QUERY.search(message) or is_category_ranking_query(message))
    asks_for_comparison = bool(_PERIOD_COMPARISON_QUERY.search(message))

    if not (asks_about_goals or asks_about_budget or asks_about_transactions):
        return FinancialContextScope.full_overview()

    return FinancialContextScope(
        include_transactions=asks_about_transactions,
        include_monthly_budget=asks_about_budget,
        include_category_limits=asks_about_budget,
        include_savings_goals=asks_about_goals,
        include_previous_transactions=(asks_about_transactions and asks_for_comparison),
    )
