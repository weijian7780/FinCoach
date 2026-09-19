"""Allowlisted, owner-scoped tools used by the FinCoach coaching agent."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


_DAY_OF_MONTH_HINT = re.compile(
    r"\bon\s+(?:the\s+)?(?P<day>\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
_LEAD_DAYS_HINT = re.compile(
    r"\b(?P<days>\d{1,2}|one|two|three|four|five|six|seven)\s+days?\s+"
    r"(?:earlier|before)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
}


def _reminder_arguments_with_user_hints(
    arguments: dict[str, Any],
    request_text: str | None,
) -> dict[str, Any]:
    adjusted = dict(arguments or {})
    if not request_text:
        return adjusted

    due_day = _DAY_OF_MONTH_HINT.search(request_text)
    if due_day:
        value = int(due_day.group("day"))
        if 1 <= value <= 28:
            adjusted["day_of_month"] = value

    lead_days = _LEAD_DAYS_HINT.search(request_text)
    if lead_days:
        raw_value = lead_days.group("days").lower()
        value = _NUMBER_WORDS.get(raw_value, int(raw_value) if raw_value.isdigit() else 0)
        if 0 <= value <= 30:
            adjusted["lead_days"] = value
    return adjusted


def _nullable(schema: dict) -> dict:
    """Allow providers to send `null` for an omitted optional tool field."""
    result = dict(schema)
    value_type = result.get("type")
    if isinstance(value_type, str):
        result["type"] = [value_type, "null"]
    if isinstance(result.get("enum"), list):
        result["enum"] = [*result["enum"], None]
    return result


def _function(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    required = required or []
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                # Groq GPT-OSS can serialise omitted optional fields as JSON
                # null. Accept that standard JSON representation, then the
                # argument model below removes nulls so Python defaults apply.
                "properties": {
                    field: value if field in required else _nullable(value)
                    for field, value in properties.items()
                },
                "required": required,
                "additionalProperties": False,
            },
        },
    }


DATE = {"type": "string", "description": "ISO date in YYYY-MM-DD format."}
OPTIONAL_CATEGORY = {"type": "string", "description": "Category name, if the user named one."}

AGENT_TOOL_DEFINITIONS = [
    _function(
        "get_financial_overview",
        "Use for questions spanning three or more FinCoach modules. Read one compact overview of recorded budget, spending, savings goals, and reminders.",
        {
            "month": DATE,
            "category_name": OPTIONAL_CATEGORY,
            "compare_previous_period": {"type": "boolean"},
            "goal_name": {"type": "string"},
            "reminder_range": {
                "type": "string",
                "enum": ["today", "next_week", "next_month"],
            },
        },
    ),
    _function(
        "get_spending_summary",
        "Summarise authenticated recorded transactions. Use for totals, categories, comparisons, or recent spending.",
        {
            "start_date": DATE,
            "end_date": DATE,
            "category_name": OPTIONAL_CATEGORY,
            "compare_previous_period": {"type": "boolean"},
        },
    ),
    _function(
        "get_budget_status",
        "Read monthly budget and category-limit status for the authenticated user.",
        {"month": DATE, "category_name": OPTIONAL_CATEGORY},
    ),
    _function(
        "get_savings_goals",
        "Read the authenticated user's savings goals and progress.",
        {"name": {"type": "string", "description": "Optional goal name to match."}},
    ),
    _function(
        "get_upcoming_reminders",
        "Read upcoming enabled reminders for the authenticated user.",
        {
            "start_date": DATE,
            "end_date": DATE,
            "range": {
                "type": "string",
                "enum": ["today", "next_week", "next_month"],
            },
        },
    ),
    _function(
        "get_report_summary",
        "Calculate a read-only financial report summary from recorded data.",
        {
            "start_date": DATE,
            "end_date": DATE,
            "category_name": OPTIONAL_CATEGORY,
        },
    ),
    _function(
        "search_transactions",
        "Search the authenticated user's recorded transactions. Use for transaction lists or matching records, not financial advice.",
        {
            "start_date": DATE,
            "end_date": DATE,
            "category_name": OPTIONAL_CATEGORY,
            "text": {"type": "string", "description": "Words to match in the recorded description or source."},
            "transaction_type": {"type": "string", "enum": ["expense", "income"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
    ),
    _function(
        "get_financial_profile",
        "Read only the coaching-safe financial profile fields for the authenticated user.",
        {},
    ),
    _function(
        "get_cashflow_forecast",
        "Estimate available funds through the current month-end from recorded income or allowance, recorded expenses, and enabled reminders. This is not a bank balance.",
        {},
    ),
    _function(
        "predict_savings",
        "Estimate savings for a calendar month from recorded income or allowance and observed spending pace. Automatically use recent history or a labelled monthly-budget scenario when needed. Include goal progress as context, without treating unfinished targets as expenses. Use for savings predictions and forecasts.",
        {
            "month": DATE,
            "include_goals": {"type": "boolean", "description": "Whether to include goal progress as context for allocating the estimated savings."},
        },
    ),
    _function(
        "prepare_reminder",
        "Prepare, but never directly create, a reminder. Call even when details are missing so FinCoach can ask a focused follow-up.",
        {
            "title": {"type": "string"},
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "due_at": {
                "type": "string",
                "description": "ISO 8601 date-time with timezone. Omit when unknown.",
            },
            "due_date": {
                "type": "string",
                "format": "date",
                "description": "Local Malaysia due date when the date is known but the time is separate or unknown.",
            },
            "day_of_month": {
                "type": "integer",
                "minimum": 1,
                "maximum": 28,
                "description": "For monthly reminders such as 'on the 15th'.",
            },
            "time_of_day": {
                "type": "string",
                "description": "Local Malaysia time in HH:MM, such as 20:00.",
            },
            "lead_days": {"type": "integer", "minimum": 0, "maximum": 30},
            "recurrence": {
                "type": "string",
                "enum": ["none", "weekly", "monthly"],
            },
        },
    ),
    _function(
        "prepare_report",
        "Prepare, but never directly generate, a report. Call with missing details to ask the user dynamically.",
        {
            "period": {
                "type": "string",
                "enum": ["current_month", "last_month", "last_3_months", "custom"],
            },
            "start_date": DATE,
            "end_date": DATE,
            "category_name": OPTIONAL_CATEGORY,
        },
    ),
]


class _Args(BaseModel):
    # Identity-like or provider-added fields are discarded. The executor always
    # injects the authenticated JWT owner independently.
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def remove_null_optional_values(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {key: item for key, item in value.items() if item is not None}


class _SpendingArgs(_Args):
    start_date: date | None = None
    end_date: date | None = None
    category_name: str | None = Field(default=None, max_length=80)
    compare_previous_period: bool = False


class _TransactionSearchArgs(_Args):
    start_date: date | None = None
    end_date: date | None = None
    category_name: str | None = Field(default=None, max_length=80)
    text: str | None = Field(default=None, max_length=120)
    transaction_type: str | None = None
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, value: str | None) -> str | None:
        if value is not None and value not in {"expense", "income"}:
            raise ValueError("Unsupported transaction type.")
        return value


def _normalise_month(value: Any) -> Any:
    if isinstance(value, str) and len(value) == 7:
        return f"{value}-01"
    return value


class _BudgetArgs(_Args):
    month: date | None = None
    category_name: str | None = Field(default=None, max_length=80)

    @field_validator("month", mode="before")
    @classmethod
    def accept_month_key(cls, value: Any) -> Any:
        return _normalise_month(value)


class _OverviewArgs(_Args):
    month: date | None = None
    category_name: str | None = Field(default=None, max_length=80)
    compare_previous_period: bool = False
    goal_name: str | None = Field(default=None, max_length=120)
    reminder_range: str = "next_week"

    @field_validator("month", mode="before")
    @classmethod
    def accept_month_key(cls, value: Any) -> Any:
        return _normalise_month(value)


class _GoalArgs(_Args):
    name: str | None = Field(default=None, max_length=120)


class _PredictionArgs(_Args):
    month: date | None = None
    include_goals: bool = True

    @field_validator("month", mode="before")
    @classmethod
    def accept_month_key(cls, value: Any) -> Any:
        return _normalise_month(value)


class _ReminderRangeArgs(_Args):
    start_date: date | None = None
    end_date: date | None = None
    range: str | None = None


class _ReminderDraft(_Args):
    title: str = Field(min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    due_date: date | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    time_of_day: time | None = None
    lead_days: int = Field(default=0, ge=0, le=30)
    recurrence: str = "none"

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("recurrence")
    @classmethod
    def validate_recurrence(cls, value: str) -> str:
        if value not in {"none", "weekly", "monthly"}:
            raise ValueError("Unsupported recurrence.")
        return value


class _ReportDraft(_Args):
    period: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    category_name: str | None = Field(default=None, max_length=80)


def _money(value: Any) -> str:
    return f"RM{Decimal(str(value or 0)):.2f}"


def _month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    next_month = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    return start, next_month


def _previous_month(value: date) -> date:
    return date(value.year - (value.month == 1), 12 if value.month == 1 else value.month - 1, 1)


def _normalise_row(data: Any) -> dict:
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}


class AgentToolExecutor:
    """Execute only registered tools and always inject the verified owner."""

    def __init__(
        self,
        admin_client: Any,
        *,
        user_id: str,
        session_id: str,
        now: Callable[[], datetime] | None = None,
        request_text: str | None = None,
    ):
        self.admin_client = admin_client
        self.user_id = user_id
        self.session_id = session_id
        # Financial months and reminder dates are presented in Malaysia time.
        # Do not let a UTC date boundary silently omit a user's early-morning
        # reminder or place it in the wrong financial month.
        self.now = now or (lambda: datetime.now(ZoneInfo("Asia/Kuala_Lumpur")))
        self.request_text = request_text
        self._handlers = {
            "get_financial_overview": self._financial_overview,
            "get_spending_summary": self._spending_summary,
            "get_budget_status": self._budget_status,
            "get_savings_goals": self._savings_goals,
            "get_upcoming_reminders": self._upcoming_reminders,
            "get_report_summary": self._report_summary,
            "search_transactions": self._search_transactions,
            "get_financial_profile": self._financial_profile,
            "get_cashflow_forecast": self._cashflow_forecast,
            "predict_savings": self._predict_savings,
            "prepare_reminder": self._prepare_reminder,
            "prepare_report": self._prepare_report,
        }

    @staticmethod
    def _execute(query: Any) -> Any:
        response = query.execute()
        error = getattr(response, "error", None)
        if error:
            raise RuntimeError("A FinCoach data tool is temporarily unavailable.")
        return getattr(response, "data", None)

    def execute(self, name: str, arguments: dict[str, Any]) -> dict:
        handler = self._handlers.get(name)
        if not handler:
            return {"status": "not_allowed", "message": "That action is not available."}
        if name in {"prepare_reminder", "prepare_report"} and self.request_text:
            # A provider may voluntarily select a write-preparation tool even
            # when the user asked to view, cancel, explain, or disable data.
            # Re-check the original request at the execution boundary.
            from app.rag.routing import required_agent_tool_names

            if name not in required_agent_tool_names(self.request_text):
                return {
                    "status": "not_allowed",
                    "message": "That preparation tool does not match the user's request.",
                }
        if name == "prepare_reminder":
            arguments = _reminder_arguments_with_user_hints(
                arguments,
                self.request_text,
            )
        try:
            arguments = dict(arguments or {})
            if arguments.get("category_name") and name in {
                "get_spending_summary", "get_budget_status", "search_transactions",
                "get_report_summary", "get_financial_overview",
            }:
                category = self._resolve_category(str(arguments["category_name"]))
                if category is None:
                    return {"status": "needs_clarification", "message": "That category was not found. Please use an exact category name from FinCoach."}
                arguments["category_name"] = category
            return handler(arguments)
        except ValidationError as error:
            return {
                "status": "invalid_arguments",
                "message": "Some requested details are invalid.",
                "details": [
                    {"field": ".".join(str(item) for item in issue["loc"]), "type": issue["type"]}
                    for issue in error.errors()
                ],
            }

    def _resolve_category(self, requested: str) -> str | None:
        # Two explicit scopes avoid exposing another owner's custom categories
        # through the service-role connection. No fuzzy auto-selection of money.
        own = self._execute(self.admin_client.table("categories").select("name").eq("user_id", self.user_id)) or []
        shared = self._execute(self.admin_client.table("categories").select("name").is_("user_id", "null")) or []
        key = " ".join(requested.split()).casefold()
        matches = {str(row["name"]) for row in [*own, *shared]
                   if " ".join(str(row.get("name") or "").split()).casefold() == key}
        return sorted(matches)[0] if matches else None

    def _profile(self) -> dict:
        data = self._execute(
            self.admin_client.table("profiles")
            .select(
                "monthly_allowance,income_source,financial_status,coaching_style,"
                "year_of_study,spending_records_consent"
            )
            .eq("id", self.user_id)
            .maybe_single()
        )
        return _normalise_row(data)

    def _require_spending_consent(self) -> dict | None:
        if self._profile().get("spending_records_consent") != "granted":
            return {
                "status": "permission_required",
                "permission": "spending_records",
                "message": (
                    "Recorded transactions were not read because spending access is not granted. "
                    "Ask whether the user wants to allow access or continue without transaction data."
                ),
            }
        return None

    def _transaction_rows(
        self,
        start: date,
        end: date,
        category_name: str | None = None,
    ) -> list[dict]:
        # Read every page before aggregating/filtering. A display/search limit
        # must never silently become a financial-total limit. The ID tie-breaker
        # keeps equal-date transactions in a stable order between pages.
        page_size = 100
        rows: list[dict] = []
        offset = 0
        while True:
            query = (
                self.admin_client.table("transactions")
                .select("id,amount,source,description,transaction_date,category:categories(name,type)")
                .eq("user_id", self.user_id)
                .gte("transaction_date", start.isoformat())
                .lte("transaction_date", end.isoformat())
                .order("transaction_date", desc=True)
                .order("id", desc=False)
                .range(offset, offset + page_size - 1)
            )
            page = self._execute(query) or []
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        if category_name:
            match = category_name.casefold()
            rows = [
                row
                for row in rows
                if str((row.get("category") or {}).get("name") or "").casefold() == match
            ]
        return rows

    def _search_transactions(self, raw: dict) -> dict:
        args = _TransactionSearchArgs.model_validate(raw)
        blocked = self._require_spending_consent()
        if blocked:
            return blocked
        today = self._malaysia_now().date()
        default_start, next_month = _month_bounds(today)
        start = args.start_date or default_start
        end = args.end_date or next_month - timedelta(days=1)
        if start > end:
            return {"status": "invalid_arguments", "message": "The start date must not be after the end date."}
        rows = self._transaction_rows(start, end, args.category_name)
        needle = (args.text or "").casefold().strip()
        matches = []
        for row in rows:
            category = row.get("category") or {}
            if args.transaction_type and category.get("type") != args.transaction_type:
                continue
            searchable = " ".join(
                str(row.get(field) or "") for field in ("description", "source")
            ).casefold()
            if needle and needle not in searchable:
                continue
            matches.append(
                {
                    "id": row.get("id"),
                    "date": row.get("transaction_date"),
                    "amount": _money(row.get("amount")),
                    "category": category.get("name") or "Uncategorised",
                    "type": category.get("type"),
                    "source": row.get("source"),
                    "description": row.get("description"),
                }
            )
            if len(matches) >= args.limit:
                break
        return {
            "status": "ok",
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "transactions": matches,
        }

    def _financial_profile(self, raw: dict) -> dict:
        _Args.model_validate(raw)
        profile = self._profile()
        allowance = profile.get("monthly_allowance")
        return {
            "status": "ok",
            "monthly_allowance": _money(allowance) if allowance is not None else None,
            "income_source": profile.get("income_source"),
            "financial_status": profile.get("financial_status"),
            "coaching_style": profile.get("coaching_style"),
            "year_of_study": profile.get("year_of_study"),
        }

    def _cashflow_forecast(self, raw: dict) -> dict:
        _Args.model_validate(raw)
        blocked = self._require_spending_consent()
        if blocked:
            return blocked
        today = self._malaysia_now().date()
        month_start, next_month = _month_bounds(today)
        month_end = next_month - timedelta(days=1)
        rows = self._transaction_rows(month_start, month_end)
        recorded_income = sum(
            (Decimal(str(row.get("amount") or 0)) for row in rows if (row.get("category") or {}).get("type") == "income"),
            Decimal("0"),
        )
        recorded_expenses = sum(
            (Decimal(str(row.get("amount") or 0)) for row in rows if (row.get("category") or {}).get("type") == "expense"),
            Decimal("0"),
        )
        profile = self._profile()
        if recorded_income > 0:
            income = recorded_income
            income_basis = "recorded_income"
        else:
            income = Decimal(str(profile.get("monthly_allowance") or 0))
            income_basis = "monthly_allowance"
        reminders = self._upcoming_reminders(
            {"start_date": today.isoformat(), "end_date": month_end.isoformat()}
        ).get("reminders", [])
        scheduled = sum(
            (Decimal(str(row.get("amount") or 0)) for row in reminders),
            Decimal("0"),
        )
        return {
            "status": "ok",
            "period": {"start": today.isoformat(), "end": month_end.isoformat()},
            "income_basis": income_basis,
            "income": _money(income),
            "recorded_expenses": _money(recorded_expenses),
            "scheduled_reminders": _money(scheduled),
            "estimated_available_by_month_end": _money(income - recorded_expenses - scheduled),
            "is_bank_balance": False,
        }

    def _predict_savings(self, raw: dict) -> dict:
        args = _PredictionArgs.model_validate(raw)
        blocked = self._require_spending_consent()
        if blocked:
            return blocked
        today = self._malaysia_now().date()
        month_start, next_month = _month_bounds(args.month or today)
        days_in_month = (next_month - month_start).days
        current_month = today.replace(day=1)

        # Future months have no observed spending yet. Use an actual observation
        # period and expose it separately from the month being predicted. Future-
        # dated entries must not inflate the current daily spending rate.
        basis_start, basis_next = _month_bounds(min(month_start, current_month))
        basis_end = min(today, basis_next - timedelta(days=1))
        rows = self._transaction_rows(basis_start, basis_end)
        income_period = {"start": basis_start.isoformat(), "end": basis_end.isoformat()}
        recorded_income = sum(
            (Decimal(str(row.get("amount") or 0))
             for row in rows
             if (row.get("category") or {}).get("type") == "income"),
            Decimal("0"),
        )
        expenses = [row for row in rows if (row.get("category") or {}).get("type") == "expense"]

        # Empty logs are not proof of zero real-world expenses. Before asking for
        # data, try the previous complete month through the same owner-scoped reader.
        if not expenses and basis_start == current_month:
            previous_start = _previous_month(basis_start)
            previous_end = basis_start - timedelta(days=1)
            previous_rows = self._transaction_rows(previous_start, previous_end)
            previous_expenses = [row for row in previous_rows
                                 if (row.get("category") or {}).get("type") == "expense"]
            if previous_expenses:
                expenses = previous_expenses
                basis_start, basis_end = previous_start, previous_end

        profile = self._profile()
        allowance = profile.get("monthly_allowance")
        if month_start > current_month and allowance is not None:
            income = Decimal(str(allowance))
            income_basis = "monthly_allowance"
        elif recorded_income > 0:
            income = recorded_income
            income_basis = "recorded_income"
        elif allowance is not None:
            # An explicitly recorded zero allowance is valid; a missing allowance
            # is not zero. Never add allowance to recorded income and double count it.
            income = Decimal(str(allowance))
            income_basis = "monthly_allowance"
        else:
            return {
                "status": "needs_data", "missing_fields": ["income"],
                "message": (
                    "I found no recorded income or monthly allowance to use. "
                    "Add your monthly allowance in Financial Profile or record your income "
                    "so I can calculate the savings estimate."
                ),
            }

        recorded_expenses = sum((Decimal(str(row.get("amount") or 0)) for row in expenses), Decimal("0"))
        days_elapsed = (basis_end - basis_start).days + 1 if expenses else 0
        daily_spending_rate = recorded_expenses / days_elapsed if expenses else None
        projection_basis = "spending_pace"
        if daily_spending_rate is not None:
            # Round once at the projected monthly total. Multiplying an already
            # rounded daily rate can change the final saving by several sen.
            projected_month_spending = (daily_spending_rate * days_in_month).quantize(Decimal("0.01"))
        else:
            monthly = _normalise_row(self._execute(
                self.admin_client.table("monthly_budgets").select("limit_amount")
                .eq("user_id", self.user_id).eq("month", month_start.isoformat()).maybe_single()
            ))
            if monthly.get("limit_amount") is None:
                return {
                    "status": "needs_data", "missing_fields": ["spending"],
                    "message": (
                        "I found no expense history for the observation period or previous month, "
                        "and no budget for the selected month. Record your expenses or set that "
                        "month's budget so I can estimate savings."
                    ),
                }
            projected_month_spending = Decimal(str(monthly["limit_amount"]))
            projection_basis = "monthly_budget"
        projected_remaining = income - projected_month_spending

        # A goal's entire unfunded target is not a monthly bill. The projected
        # surplus is what can be allocated to goals; do not subtract it twice.
        goal_details: list[dict] = []
        if args.include_goals:
            goals = self._execute(
                self.admin_client.table("savings_goals")
                .select("name,target_amount,current_amount,deadline")
                .eq("user_id", self.user_id)
                .order("created_at", desc=False)
            ) or []
            for goal in goals:
                target = Decimal(str(goal.get("target_amount") or 0))
                current = Decimal(str(goal.get("current_amount") or 0))
                remaining_to_goal = max(Decimal("0"), target - current)
                if remaining_to_goal > 0:
                    goal_details.append({
                        "name": goal.get("name"),
                        "remaining_to_goal": _money(remaining_to_goal),
                    })

        return {
            "status": "ok",
            "month": month_start.isoformat(),
            "income_basis": income_basis,
            "income_period": income_period if income_basis == "recorded_income" else None,
            "income": _money(income),
            "projection_basis": projection_basis,
            "basis_period": {"start": basis_start.isoformat(), "end": basis_end.isoformat()},
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
            "expense_count": len(expenses),
            "recorded_expenses": _money(recorded_expenses),
            "daily_spending_rate": _money(daily_spending_rate) if daily_spending_rate is not None else None,
            "projected_month_spending": _money(projected_month_spending),
            "projected_remaining": _money(projected_remaining),
            "projected_shortfall": _money(max(Decimal("0"), -projected_remaining)),
            "goal_details": goal_details,
            "projected_saveable": _money(max(Decimal("0"), projected_remaining)),
            "is_estimate": True,
            "assumptions": [
                "Uses the selected income basis without adding allowance to recorded income.",
                "Assumes income continues and spending follows the observed pace or the full recorded budget.",
                "Goal targets are possible uses of the savings, not additional expenses.",
            ],
            "disclaimer": "An estimate from recorded data, not a bank balance or guarantee. Missing transactions can change the result.",
        }

    def _spending_summary(self, raw: dict) -> dict:
        args = _SpendingArgs.model_validate(raw)
        blocked = self._require_spending_consent()
        if blocked:
            return blocked
        today = self._malaysia_now().date()
        start, next_month = _month_bounds(today)
        end = next_month - timedelta(days=1)
        start = args.start_date or start
        end = args.end_date or end
        if start > end:
            return {"status": "invalid_arguments", "message": "The start date must not be after the end date."}
        rows = self._transaction_rows(start, end, args.category_name)
        expenses = [
            row for row in rows if (row.get("category") or {}).get("type") == "expense"
        ]
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for row in expenses:
            totals[(row.get("category") or {}).get("name") or "Uncategorised"] += Decimal(
                str(row.get("amount") or 0)
            )
        result: dict[str, Any] = {
            "status": "ok",
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "expense_total": _money(sum(totals.values(), Decimal("0"))),
            "expense_count": len(expenses),
            "categories": [
                {"name": name, "amount": _money(amount)}
                for name, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)
            ],
        }
        if args.compare_previous_period:
            days = (end - start).days + 1
            previous_end = start - timedelta(days=1)
            # Full calendar months compare with the previous calendar month;
            # custom partial ranges retain equal-length rolling comparisons.
            is_calendar_month = start.day == 1 and end == _month_bounds(start)[1] - timedelta(days=1)
            previous_start = (
                _previous_month(start)
                if is_calendar_month
                else previous_end - timedelta(days=days - 1)
            )
            previous_rows = self._transaction_rows(previous_start, previous_end, args.category_name)
            previous_total = sum(
                (
                    Decimal(str(row.get("amount") or 0))
                    for row in previous_rows
                    if (row.get("category") or {}).get("type") == "expense"
                ),
                Decimal("0"),
            )
            current_total = sum(totals.values(), Decimal("0"))
            result["comparison"] = {
                "previous_start": previous_start.isoformat(),
                "previous_end": previous_end.isoformat(),
                "previous_total": _money(previous_total),
                "difference": _money(current_total - previous_total),
            }
        return result

    def _budget_status(self, raw: dict) -> dict:
        args = _BudgetArgs.model_validate(raw)
        month_start, next_month = _month_bounds(
            args.month or self._malaysia_now().date()
        )
        monthly = _normalise_row(
            self._execute(
                self.admin_client.table("monthly_budgets")
                .select("limit_amount")
                .eq("user_id", self.user_id)
                .eq("month", month_start.isoformat())
                .maybe_single()
            )
        )
        category_limits = self._execute(
            self.admin_client.table("budgets")
            .select("amount,category:categories(name)")
            .eq("user_id", self.user_id)
            .eq("month", month_start.isoformat())
        ) or []
        blocked = self._require_spending_consent()
        spent: Decimal | None = None
        rows: list[dict] = []
        if not blocked:
            rows = self._transaction_rows(month_start, next_month - timedelta(days=1))
            spent = sum(
                (
                    Decimal(str(row.get("amount") or 0))
                    for row in rows
                    if (row.get("category") or {}).get("type") == "expense"
                ),
                Decimal("0"),
            )
        limit = Decimal(str(monthly.get("limit_amount") or 0))
        result = {
            "status": "ok",
            "month": month_start.isoformat(),
            "monthly_limit": _money(limit) if monthly else None,
            "recorded_spending": _money(spent) if spent is not None else None,
            "remaining": _money(limit - spent) if spent is not None and monthly else None,
            "spending_permission_required": bool(blocked),
            "category_limits": category_limits,
        }
        if not args.category_name:
            spending_by_category: dict[str, Decimal] = defaultdict(Decimal)
            if not blocked:
                for row in rows:
                    category = row.get("category") or {}
                    if category.get("type") != "expense":
                        continue
                    category_name = str(category.get("name") or "Uncategorised")
                    spending_by_category[category_name.casefold()] += Decimal(
                        str(row.get("amount") or 0)
                    )
            result["category_statuses"] = [
                {
                    "name": str((row.get("category") or {}).get("name") or "Uncategorised"),
                    "limit": _money(row.get("amount") or 0),
                    "recorded_spending": (
                        _money(
                            spending_by_category.get(
                                str(
                                    (row.get("category") or {}).get("name")
                                    or "Uncategorised"
                                ).casefold(),
                                Decimal("0"),
                            )
                        )
                        if not blocked
                        else None
                    ),
                    "remaining": (
                        _money(
                            Decimal(str(row.get("amount") or 0))
                            - spending_by_category.get(
                                str(
                                    (row.get("category") or {}).get("name")
                                    or "Uncategorised"
                                ).casefold(),
                                Decimal("0"),
                            )
                        )
                        if not blocked
                        else None
                    ),
                }
                for row in category_limits
            ]
        if args.category_name:
            requested = args.category_name.casefold()
            selected = next(
                (
                    row
                    for row in category_limits
                    if str((row.get("category") or {}).get("name") or "").casefold()
                    == requested
                ),
                None,
            )
            if selected:
                category_limit = Decimal(str(selected.get("amount") or 0))
                category_name = str(
                    (selected.get("category") or {}).get("name")
                    or args.category_name
                )
                category_spent = (
                    sum(
                        (Decimal(str(row.get("amount") or 0)) for row in rows
                         if (row.get("category") or {}).get("type") == "expense"
                         and str((row.get("category") or {}).get("name") or "").casefold() == requested),
                        Decimal("0"),
                    )
                    if not blocked else None
                )
                result["selected_category"] = {
                    "name": category_name,
                    "limit": _money(category_limit),
                    "recorded_spending": (
                        _money(category_spent) if category_spent is not None else None
                    ),
                    "remaining": (
                        _money(category_limit - category_spent)
                        if category_spent is not None
                        else None
                    ),
                }
            else:
                result["selected_category"] = {
                    "name": args.category_name, "limit": None, "remaining": None,
                    "recorded_spending": _money(sum(
                        (Decimal(str(row.get("amount") or 0)) for row in rows
                         if (row.get("category") or {}).get("type") == "expense"
                         and str((row.get("category") or {}).get("name") or "").casefold() == requested),
                        Decimal("0"),
                    )) if not blocked else None,
                }
        return result

    def _savings_goals(self, raw: dict) -> dict:
        args = _GoalArgs.model_validate(raw)
        rows = self._execute(
            self.admin_client.table("savings_goals")
            .select("id,name,target_amount,current_amount,deadline")
            .eq("user_id", self.user_id)
            .order("created_at", desc=False)
        ) or []
        if args.name:
            needle = args.name.casefold()
            rows = [row for row in rows if needle in str(row.get("name") or "").casefold()]
        return {"status": "ok", "goals": rows}

    def _reminder_dates(self, args: _ReminderRangeArgs) -> tuple[date, date]:
        today = self._malaysia_now().date()
        if args.range == "today":
            return today, today
        if args.range == "next_week":
            return today, today + timedelta(days=7)
        if args.range == "next_month":
            return today, today + timedelta(days=30)
        return args.start_date or today, args.end_date or today + timedelta(days=30)

    def _upcoming_reminders(self, raw: dict) -> dict:
        args = _ReminderRangeArgs.model_validate(raw)
        start, end = self._reminder_dates(args)
        malaysia = ZoneInfo("Asia/Kuala_Lumpur")
        start_at = datetime.combine(start, time.min, tzinfo=malaysia).astimezone(
            timezone.utc
        )
        end_at = datetime.combine(
            end + timedelta(days=1), time.min, tzinfo=malaysia
        ).astimezone(timezone.utc)
        rows = self._execute(
            self.admin_client.table("reminders")
            .select("id,title,amount,due_at,lead_days,recurrence,next_trigger_at,enabled")
            .eq("user_id", self.user_id)
            .eq("enabled", True)
            .gte("due_at", start_at.isoformat())
            .lt("due_at", end_at.isoformat())
            .order("due_at", desc=False)
            .limit(50)
        ) or []
        return {
            "status": "ok",
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "reminders": rows,
        }

    def _report_summary(self, raw: dict) -> dict:
        args = _SpendingArgs.model_validate(raw)
        spending = self._spending_summary(raw)
        if spending.get("status") != "ok":
            return spending
        budget = self._budget_status({"month": args.start_date, "category_name": args.category_name})
        goals = self._savings_goals({})
        return {
            "status": "ok",
            "spending": spending,
            "budget": budget,
            "savings": goals,
        }

    def _financial_overview(self, raw: dict) -> dict:
        args = _OverviewArgs.model_validate(raw)
        month_value = args.month or self._malaysia_now().date()
        start, next_month = _month_bounds(month_value)
        return {
            "status": "ok",
            "spending": self._spending_summary(
                {
                    "start_date": start,
                    "end_date": next_month - timedelta(days=1),
                    "category_name": args.category_name,
                    "compare_previous_period": args.compare_previous_period,
                }
            ),
            "budget": self._budget_status(
                {"month": start, "category_name": args.category_name}
            ),
            "savings": self._savings_goals({"name": args.goal_name}),
            "reminders": self._upcoming_reminders({"range": args.reminder_range}),
        }

    def _malaysia_now(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo("Asia/Kuala_Lumpur"))

    def _prepare_reminder(self, raw: dict) -> dict:
        # Title is the only field required to identify the intended reminder.
        if not str(raw.get("title") or "").strip():
            return self._clarification(
                action_type="create_reminder",
                question="What should I remind you about?",
                input_type="text",
                field="title",
                options=[],
                draft={},
            )
        args = _ReminderDraft.model_validate(raw)
        draft = args.model_dump(mode="json", exclude_none=True)
        due_at = args.due_at
        malaysia = ZoneInfo("Asia/Kuala_Lumpur")
        if due_at is None and args.due_date and args.time_of_day:
            due_at = datetime.combine(
                args.due_date,
                args.time_of_day,
                tzinfo=malaysia,
            )
        if (
            due_at is None
            and args.recurrence == "monthly"
            and args.day_of_month is not None
            and args.time_of_day is not None
        ):
            local_now = self.now()
            if local_now.tzinfo is None:
                local_now = local_now.replace(tzinfo=timezone.utc)
            local_now = local_now.astimezone(malaysia)
            year = local_now.year
            month = local_now.month
            candidate = datetime(
                year,
                month,
                args.day_of_month,
                args.time_of_day.hour,
                args.time_of_day.minute,
                tzinfo=malaysia,
            )
            if candidate <= local_now:
                year += month == 12
                month = 1 if month == 12 else month + 1
                candidate = datetime(
                    year,
                    month,
                    args.day_of_month,
                    args.time_of_day.hour,
                    args.time_of_day.minute,
                    tzinfo=malaysia,
                )
            due_at = candidate
        if not due_at and not args.due_date:
            today = self.now().date()
            return self._clarification(
                action_type="create_reminder",
                question=f"When should I remind you about “{args.title}”?",
                input_type="date",
                field="due_date",
                options=[
                    ("today", "Today", today.isoformat()),
                    ("tomorrow", "Tomorrow", (today + timedelta(days=1)).isoformat()),
                    ("next_week", "Next week", (today + timedelta(days=7)).isoformat()),
                    ("pick_date", "Pick a date", "pick_date"),
                ],
                draft=draft,
            )
        if not due_at:
            return self._clarification(
                action_type="create_reminder",
                question="What time should I use? You can also type a time in your own words.",
                input_type="time",
                field="time_of_day",
                options=[
                    ("morning", "8:00 AM", "08:00"),
                    ("noon", "12:00 PM", "12:00"),
                    ("evening", "8:00 PM", "20:00"),
                ],
                draft=draft,
            )
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=malaysia)
        current = self.now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if due_at.astimezone(timezone.utc) <= current.astimezone(timezone.utc):
            return {
                "status": "invalid_arguments",
                "message": "The reminder date and time must be in the future.",
            }
        arguments = {
            "title": args.title,
            "amount": float(args.amount) if args.amount is not None else None,
            "due_at": due_at.isoformat(),
            "lead_days": args.lead_days,
            "recurrence": args.recurrence,
        }
        local_due = due_at.astimezone(malaysia)
        local_time = local_due.strftime("%I:%M %p").lstrip("0")
        fields = [
            {"label": "Reminder", "value": args.title},
            {
                "label": "Due",
                "value": f"{local_due.strftime('%d %B %Y')}, {local_time}",
            },
        ]
        if args.amount is not None:
            fields.insert(1, {"label": "Amount", "value": _money(args.amount)})
        if args.recurrence != "none":
            fields.append({"label": "Repeats", "value": args.recurrence.title()})
        if args.lead_days > 0:
            fields.append({
                "label": "Notify",
                "value": f"{args.lead_days} day{'s' if args.lead_days != 1 else ''} before",
            })
        return self._action(
            action_type="create_reminder",
            title="Create reminder?",
            description="FinCoach will add this to your reminders only after you confirm.",
            confirm_label="Create reminder",
            arguments=arguments,
            fields=fields,
        )

    def _prepare_report(self, raw: dict) -> dict:
        blocked = self._require_spending_consent()
        if blocked:
            return blocked
        args = _ReportDraft.model_validate(raw)
        if not args.period and args.start_date and args.end_date:
            args.period = "custom"
        if not args.period:
            return self._clarification(
                action_type="generate_report",
                question="Which period should the report cover?",
                input_type="single_select",
                field="period",
                options=[
                    ("current_month", "This month", "current_month"),
                    ("last_month", "Last month", "last_month"),
                    ("last_3_months", "Last 3 months", "last_3_months"),
                    ("custom", "Choose dates", "custom"),
                ],
                draft=args.model_dump(mode="json", exclude_none=True),
            )
        today = self.now().date()
        current_start, current_next = _month_bounds(today)
        if args.period == "current_month":
            start, end = current_start, current_next - timedelta(days=1)
        elif args.period == "last_month":
            start = _previous_month(current_start)
            end = current_start - timedelta(days=1)
        elif args.period == "last_3_months":
            previous = _previous_month(current_start)
            start = _previous_month(previous)
            end = current_next - timedelta(days=1)
        elif args.start_date and args.end_date:
            start, end = args.start_date, args.end_date
        else:
            return self._clarification(
                action_type="generate_report",
                question="What start and end dates should I use?",
                input_type="date_range",
                field="date_range",
                options=[],
                draft=args.model_dump(mode="json", exclude_none=True),
            )
        if start > end:
            return {"status": "invalid_arguments", "message": "The report start date must not be after its end date."}
        category = args.category_name or "All categories"
        return self._action(
            action_type="generate_report",
            title="Generate financial report?",
            description="FinCoach will create and save a private PDF after you confirm.",
            confirm_label="Generate report",
            arguments={
                "period": args.period,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "category_name": args.category_name,
            },
            fields=[
                {"label": "Period", "value": f"{start.isoformat()} to {end.isoformat()}"},
                {"label": "Categories", "value": category},
            ],
        )

    @staticmethod
    def _clarification(
        *,
        action_type: str,
        question: str,
        input_type: str,
        field: str,
        options: list[tuple[str, str, str]],
        draft: dict,
    ) -> dict:
        return {
            "status": "needs_clarification",
            "ui_payload": {
                "type": "clarification",
                "action_type": action_type,
                "question": question,
                "input_type": input_type,
                "field": field,
                "options": [
                    {"id": option_id, "label": label, "value": value}
                    for option_id, label, value in options
                ],
                "allow_other": True,
                "draft": draft,
            },
        }

    @staticmethod
    def _action(
        *,
        action_type: str,
        title: str,
        description: str,
        confirm_label: str,
        arguments: dict,
        fields: list[dict],
    ) -> dict:
        return {
            "status": "confirmation_required",
            "ui_payload": {
                "type": "action",
                "action_id": str(uuid4()),
                "action_type": action_type,
                "status": "pending",
                "title": title,
                "description": description,
                "confirm_label": confirm_label,
                "arguments": arguments,
                "fields": fields,
            },
        }
