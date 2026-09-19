"""Deterministic routing for the four FinCoach response paths."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from app.rag.query_analysis import detect_knowledge_topics


class CoachingRoute(str, Enum):
    CASUAL = "casual"
    PERSONAL_FINANCE = "personal_finance"
    FINANCIAL_EDUCATION = "financial_education"
    COMBINED = "combined"


@dataclass(frozen=True)
class ResolvedReadRequest:
    """The deterministic personal-data read selected for this message."""

    route: CoachingRoute
    tool_name: str | None
    arguments: dict[str, object]
    inherited: bool = False
    clarification: str | None = None


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
    r"savings? goals?|allowance|category limit|rm\s*\d|"
    r"berapa\s+(?:saya|aku)\s+(?:belanja|habis)|"
    r"(?:belanja|perbelanjaan|transaksi|bajet|had\s+kategori|"
    r"matlamat\s+simpanan)\s+(?:saya|aku)|"
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
    r"\b(?:what is (?:a )?budget|what is budgeting|explain budgeting|how to budget)\b",
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
    r"\b(?:savings?\s+goals?|saving\s+goal|goal|target|deadline|"
    r"save\s+for|reach\s+(?:my\s+)?goal|matlamat\s+simpanan|"
    r"simpanan\s+saya)\b",
    re.IGNORECASE,
)

_BUDGET_QUERY = re.compile(
    r"\b(?:budget|overspent|overspend|over\s+budget|spending\s+limit|"
    r"category\s+limit|cut\s+spending|afford|allowance|bajet|"
    r"had\s+kategori|had\s+belanja)\b",
    re.IGNORECASE,
)
_BUDGET_PLANNING_QUERY = re.compile(
    r"\b(?:plan|recommend|suggest|rancang|cadang)\b.{0,80}"
    r"\b(?:budget|budget\s+limit|spending\s+limit|bajet|had\s+belanja)\b|"
    r"\b(?:budget|budget\s+limit|spending\s+limit|bajet|had\s+belanja)\b"
    r".{0,80}\b(?:plan|recommend|suggest|rancang|cadang)\b",
    re.IGNORECASE,
)

_TRANSACTION_QUERY = re.compile(
    r"\b(?:expenses?|transactions?|purchases?|i\s+spent|i\s+spend|"
    r"spent|spending|overspent|overspend|where\s+(?:did|does).*(?:money|spend)|"
    r"belanja|perbelanjaan|transaksi|pembelian)\b",
    re.IGNORECASE,
)
_TRANSACTION_SEARCH_QUERY = re.compile(
    r"\b(?:find|list|show|view|search)\b.{0,50}\b(?:transactions?|purchases?)\b",
    re.IGNORECASE,
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
    message = " ".join(content.strip().split())
    if not message or _CASUAL_ONLY.fullmatch(message) or _CASUAL_NON_FINANCIAL.search(message):
        return CoachingRoute.CASUAL

    # The mobile Coach exposes these without finance keywords. They are still
    # personal-finance questions because a useful answer requires live records.
    if is_financial_triage_query(message):
        return CoachingRoute.PERSONAL_FINANCE

    # App actions need the tool-capable path even when the user does not use
    # a finance keyword (for example, "Create a reminder to pay rent").
    # The agent still prepares a confirmation card; it never writes data here.
    if required_agent_tool_name(message):
        return CoachingRoute.PERSONAL_FINANCE
    if ambiguous_reminder_title(message):
        return CoachingRoute.PERSONAL_FINANCE
    if _REMINDER_REFERENCE.search(message) or _REPORT_REFERENCE.search(message):
        return CoachingRoute.PERSONAL_FINANCE
    if _DEADLINE_QUERY.search(message):
        return CoachingRoute.PERSONAL_FINANCE
    is_saved_finance_topic = bool(
        _SAVINGS_GOAL_QUERY.search(message)
        or _BUDGET_QUERY.search(message)
        or _TRANSACTION_QUERY.search(message)
        or _PROFILE_QUERY.search(message)
        or _CASHFLOW_FORECAST_QUERY.search(message)
        or _PREDICTION_QUERY.search(message)
    )

    needs_personal_context = bool(_PERSONAL_FINANCE.search(message))
    needs_knowledge = bool(
        _FINANCIAL_EDUCATION.search(message)
        or detect_knowledge_topics(message)
    )

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
    return bool(_BUDGET_PLANNING_QUERY.search(" ".join(content.strip().split())))


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

    message = " ".join(content.strip().split())
    if _CASHFLOW_FORECAST_QUERY.search(message):
        return "get_cashflow_forecast"
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
    if _TRANSACTION_SEARCH_QUERY.search(message):
        return "search_transactions"
    if _TRANSACTION_QUERY.search(message):
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
    start, end = _explicit_period(message, tool_name, current_day)
    if tool_name in {"get_spending_summary", "get_report_summary", "search_transactions"} and start and end:
        arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
    elif tool_name in {"get_budget_status", "get_financial_overview", "predict_savings"} and start:
        arguments["month"] = start.strftime("%Y-%m")
    category = _category_filter(message)
    if category and tool_name in {
        "get_spending_summary",
        "get_report_summary",
        "search_transactions",
        "get_budget_status",
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
        route = route_coach_message(text)
        direct_tool = required_read_agent_tool_name(text, route)
        is_modifier = _is_follow_up_modifier(text) and not any(pattern.search(text) for pattern in (
            _TRANSACTION_QUERY, _BUDGET_QUERY, _SAVINGS_GOAL_QUERY,
            _PROFILE_QUERY, _REMINDER_REFERENCE, _CASHFLOW_FORECAST_QUERY, _PREDICTION_QUERY,
        ))
        if route in (CoachingRoute.FINANCIAL_EDUCATION, CoachingRoute.COMBINED) or required_agent_tool_names(text):
            is_modifier = False
        inherited = bool(is_modifier and context and context.tool_name)
        tool = context.tool_name if inherited else direct_tool
        arguments = dict(context.arguments) if inherited else {}
        clarification = None
        if tool:
            try:
                arguments.update(required_read_agent_tool_arguments(text, tool, now=now))
                if re.search(r"\b(?:all\s+categories|semua\s+kategori)\b", text, re.I):
                    arguments.pop("category_name", None)
                if tool in {"get_budget_status", "get_financial_overview", "predict_savings"}:
                    start, end = _explicit_period(text, tool, _malaysia_date(now))
                    if start and end and (start.day != 1 or end != _month_end(start)):
                        subject = "Savings predictions" if tool == "predict_savings" else "Budgets"
                        raise ValueError(f"{subject} use calendar months. Please specify a month and year.")
            except ValueError as error:
                arguments = {}
                clarification = str(error) if "Please" in str(error) else "Please provide valid dates in YYYY-MM-DD format, with the start before the end."
        elif is_modifier and route == CoachingRoute.CASUAL:
            clarification = "Which financial record should I use? For example, ask for your expenses, budget, savings goal, or reminders."
        resolved = ResolvedReadRequest(
            route=CoachingRoute.PERSONAL_FINANCE if inherited else route,
            tool_name=tool, arguments=arguments, inherited=inherited,
            clarification=clarification,
        )
        context = resolved if tool and not clarification and not required_agent_tool_names(text) else None
    return resolved


def _malaysia_date(value: datetime | date | None) -> date:
    if value is None:
        return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Kuala_Lumpur"))
        return value.astimezone(ZoneInfo("Asia/Kuala_Lumpur")).date()
    return value


def _explicit_period(
    message: str,
    tool_name: str,
    current_day: date,
) -> tuple[date | None, date | None]:
    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)
    if iso_dates:
        parsed = [date.fromisoformat(value) for value in iso_dates]
        if len(parsed) > 2 or parsed[0] > parsed[-1]:
            raise ValueError("Provide a valid start date followed by an end date.")
        return parsed[0], parsed[-1]
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
    elif is_budget_planning_request(message) or tool_name == "predict_savings":
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
    match = re.search(
        r"\b(?:spend(?:ing)?|spent|expenses?|transactions?|belanja|perbelanjaan|"
        r"budget|bajet)\s+(?:on|for|untuk|kategori|category)\s+"
        r"(?P<category>[\w&'\- ]{1,80}?)[?.!\s]*$", text, re.I,
    )
    if match:
        return " ".join(match.group("category").split()).title()
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

    message = " ".join(content.strip().split())
    asks_about_goals = bool(_SAVINGS_GOAL_QUERY.search(message))
    asks_about_budget = bool(_BUDGET_QUERY.search(message))
    asks_about_transactions = bool(_TRANSACTION_QUERY.search(message))
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
