"""Persist and resume a pending read clarification as pure, versioned state.

``build_read_clarification`` serialises a non-ready read (an ambiguous savings
topic, an unresolved transaction reference, an invalid/missing period, or an
under-specified comparison) into a ``ui_payload`` the client renders as a
question with optional chips, and that the server can later trust.

``resume_read_clarification`` takes that saved payload plus the user's short
answer and returns a fresh :class:`ResolvedReadRequest`: it resolves the missing
field, re-validates it, and — when the saved state is malformed or the answer is
still unusable — asks again instead of broadening the read. A cancellation or
thanks ends the pending read without executing anything.

These are pure functions: no Supabase and no LLM. The caller establishes owner
and session eligibility before passing saved state back in.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.rag.routing import (
    _TOOL_INTENT,
    CoachingRoute,
    ReadReadiness,
    ResolvedReadRequest,
    parse_comparison_request,
    required_read_agent_tool_arguments,
)

STATE_VERSION = 1
PAYLOAD_TYPE = "read_clarification"
_MAX_STR = 200

# Only these may be reconstructed from saved state; anything else is treated as
# unavailable context (a fresh, helpful question), never as permission to read.
_ALLOWED_TOOLS = frozenset(_TOOL_INTENT)
_ALLOWED_ROUTES = frozenset(route.value for route in CoachingRoute)
_ALLOWED_INTENTS = frozenset(_TOOL_INTENT.values()) | {
    "savings_unspecified",
    "transaction_reference",
    "transaction_search",
}
_ALLOWED_FIELDS = frozenset(
    {"month", "savings_intent", "transaction_filter", "amount", "periods", "date_range"}
)

_SAVINGS_OPTIONS = (
    {"id": "goal_progress", "label": "Savings-goal progress", "value": "goal_progress"},
    {"id": "saving_capacity", "label": "How much I could save", "value": "saving_capacity"},
)

_CANCEL = re.compile(
    r"^(?:cancel|never\s*mind|nvm|forget\s+it|batal|tak\s+jadi|"
    r"stop|no|nope|thanks?|thank\s+you|terima\s+kasih)[!.\s]*$",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_YEAR_MONTH = re.compile(r"^\s*(20\d{2})-(0[1-9]|1[0-2])\s*$")


# Transaction filters that survive a clarification unchanged; the reply resolves
# only the one missing constraint (merchant / category / amount / date).
_TXN_KEEP_KEYS = frozenset({
    "start_date", "end_date", "category_name", "transaction_type",
    "amount", "limit", "result_mode", "text",
})


def _txn_constraint_satisfied(reason: str | None, merged: dict, has_dates: bool) -> bool:
    """Whether the reply has resolved the *specific* constraint that was asked."""
    if reason == "multiple_merchants":
        return "text" in merged
    if reason == "excluded_category":
        return "category_name" in merged
    if reason == "unresolved_reference":
        return "text" in merged or has_dates
    return "text" in merged or "category_name" in merged or has_dates


def _txn_reask_message(reason: str | None) -> str:
    if reason == "excluded_category":
        return "Which category should I include? Name one, for example 'Food'."
    return "Please name one merchant to search, for example 'Grab'."


# --- Build -----------------------------------------------------------------

def _field_for(request: ResolvedReadRequest) -> str:
    if request.invalid_fields:
        return request.invalid_fields[0]
    if request.missing_required:
        return request.missing_required[0]
    return "date_range"


def _month_options(anchor: date) -> list[dict]:
    this_start = anchor.replace(day=1)
    last_start = (this_start - timedelta(days=1)).replace(day=1)
    return [
        {"id": "this_month", "label": "This month", "value": this_start.strftime("%Y-%m")},
        {"id": "last_month", "label": "Last month", "value": last_start.strftime("%Y-%m")},
    ]


def _question_for(field: str, request: ResolvedReadRequest, anchor: date):
    """Return (question, input_type, options, allow_other, resolved_field)."""
    if field == "month":
        subject = "your budget" if request.tool_name == "get_budget_status" else "this"
        return (
            f"Which month should I use for {subject}?",
            "single_select",
            _month_options(anchor),
            True,
            "month",
        )
    if field == "savings_intent":
        return (
            "Do you want your savings-goal progress, or an estimate of how much "
            "you could save?",
            "single_select",
            [dict(option) for option in _SAVINGS_OPTIONS],
            False,
            "savings_intent",
        )
    if field == "transaction_filter":
        return (
            "Which transaction do you mean? Share its date, the merchant, or a "
            "short description.",
            "text",
            [],
            True,
            "transaction_filter",
        )
    if field == "periods":
        return (
            "Which calendar months should I compare? Name at least two, for "
            "example 'July and September 2026'.",
            "text",
            [],
            True,
            "periods",
        )
    if field == "amount":
        return (
            "Which exact amount should I search for, for example RM25?",
            "text",
            [],
            True,
            "amount",
        )
    return (
        "Which period should I use? Give a start and end date as "
        "YYYY-MM-DD to YYYY-MM-DD.",
        "text",
        [],
        True,
        "date_range",
    )


def build_read_clarification(
    request: ResolvedReadRequest,
    *,
    origin_message_id: str,
    anchor_date: date,
) -> dict:
    """Serialise a non-ready read into a versioned, resumable ui_payload."""
    field = _field_for(request)
    question, input_type, options, allow_other, field = _question_for(
        field, request, anchor_date
    )
    return {
        "type": PAYLOAD_TYPE,
        "question": request.clarification or question,
        "input_type": input_type,
        "field": field,
        "options": options,
        "allow_other": allow_other,
        "state": {
            "version": STATE_VERSION,
            "origin_message_id": str(origin_message_id),
            "anchor_date": anchor_date.isoformat(),
            "intent": request.intent,
            "route": request.route.value,
            "tool_name": request.tool_name,
            "arguments": dict(request.arguments),
            "parameter_sources": dict(request.parameter_sources),
            "missing_required": list(request.missing_required),
            "invalid_fields": list(request.invalid_fields),
            "reason": request.clarify_reason,
        },
    }


# --- Resume ----------------------------------------------------------------

def _coerce_state(payload: object) -> dict | None:
    if not isinstance(payload, dict) or payload.get("type") != PAYLOAD_TYPE:
        return None
    if payload.get("field") not in _ALLOWED_FIELDS:
        return None
    state = payload.get("state")
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return None
    route = state.get("route")
    if route not in _ALLOWED_ROUTES:
        return None
    tool_name = state.get("tool_name")
    if tool_name is not None and tool_name not in _ALLOWED_TOOLS:
        return None
    intent = state.get("intent")
    if intent is not None and intent not in _ALLOWED_INTENTS:
        return None
    arguments = state.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    clean_arguments: dict[str, object] = {}
    for key, value in arguments.items():
        if not isinstance(key, str) or len(key) > _MAX_STR:
            return None
        if isinstance(value, str) and len(value) > _MAX_STR:
            return None
        clean_arguments[key] = value
    reason = state.get("reason")
    if reason is not None and not isinstance(reason, str):
        reason = None
    return {"route": route, "tool_name": tool_name, "intent": intent, "arguments": clean_arguments, "reason": reason}


def _unavailable() -> ResolvedReadRequest:
    return ResolvedReadRequest(
        route=CoachingRoute.PERSONAL_FINANCE,
        tool_name=None,
        arguments={},
        readiness=ReadReadiness.NEEDS_CLARIFICATION,
        clarification=(
            "I lost track of that question. Which financial record should I use "
            "— your expenses, budget, savings, or reminders?"
        ),
    )


def _cancelled() -> ResolvedReadRequest:
    return ResolvedReadRequest(
        route=CoachingRoute.CASUAL,
        tool_name=None,
        arguments={},
        readiness=ReadReadiness.READY,
    )


def _reask(field: str, tool_name: str | None, intent: str | None, message: str,
           *, arguments: dict | None = None, reason: str | None = None) -> ResolvedReadRequest:
    return ResolvedReadRequest(
        route=CoachingRoute.PERSONAL_FINANCE,
        tool_name=tool_name,
        arguments=dict(arguments or {}),
        readiness=ReadReadiness.NEEDS_CLARIFICATION,
        intent=intent,
        invalid_fields=(field,) if field in {"month", "date_range", "amount"} else (),
        missing_required=() if field in {"month", "date_range", "amount"} else (field,),
        clarification=message,
        clarify_reason=reason,
    )


def _ready(route_value, tool_name, arguments, intent, sources) -> ResolvedReadRequest:
    route = CoachingRoute(route_value) if route_value in _ALLOWED_ROUTES else CoachingRoute.PERSONAL_FINANCE
    return ResolvedReadRequest(
        route=route,
        tool_name=tool_name,
        arguments=arguments,
        readiness=ReadReadiness.READY,
        intent=intent,
        parameter_sources=sources,
    )


def resume_read_clarification(payload: dict, reply: str, *, now: date) -> ResolvedReadRequest:
    """Resolve a pending read from its saved payload and the user's short answer."""
    state = _coerce_state(payload)
    if state is None:
        return _unavailable()

    reply = " ".join((reply or "").split())
    if not reply:
        return _unavailable()
    if _CANCEL.match(reply):
        return _cancelled()

    field = payload["field"]
    route_value = state["route"]
    tool_name = state["tool_name"]
    intent = state["intent"]
    arguments = dict(state["arguments"])

    if field == "month":
        month = _parse_month(reply, tool_name, now)
        if not month:
            return _reask("month", tool_name, intent,
                          "Please give a calendar month, for example 'July 2026'.")
        arguments["month"] = month
        return _ready(route_value, tool_name, arguments, intent, {"month": "explicit"})

    if field == "savings_intent":
        choice = reply.casefold()
        if choice in {"goal_progress", "goal"} or "goal" in choice:
            return _ready(route_value, "get_savings_goals", {}, "savings_goals", {})
        if choice in {"saving_capacity", "capacity"} or "save" in choice or "capac" in choice:
            return _ready(route_value, "predict_savings", {}, "savings_prediction", {})
        return _reask("savings_intent", None, "savings_unspecified",
                      "Please choose savings-goal progress, or how much you could save.")

    if field == "transaction_filter":
        reason = state.get("reason")
        # Keep every filter that survived clarification; the reply resolves only
        # the one missing constraint.
        merged = {k: v for k, v in arguments.items() if k in _TXN_KEEP_KEYS}
        sources = {k: "context" for k in merged}
        try:
            reply_args = required_read_agent_tool_arguments(reply, "search_transactions", now=now)
        except ValueError:
            reply_args = {}
        has_dates = bool(reply_args.get("start_date") and reply_args.get("end_date"))
        if has_dates:
            merged["start_date"] = reply_args["start_date"]
            merged["end_date"] = reply_args["end_date"]
            sources["start_date"] = sources["end_date"] = "explicit"
            merged.pop("all_dates", None)
        elif _ISO_DATE.search(reply):
            iso = _ISO_DATE.search(reply).group(0)
            merged["start_date"] = merged["end_date"] = iso
            sources["start_date"] = sources["end_date"] = "explicit"
            merged.pop("all_dates", None)
            has_dates = True
        # A non-date reply names the missing merchant (or category, for exclusions).
        merchant = reply_args.get("text")
        if not merchant and not has_dates:
            merchant = reply[:_MAX_STR]
        if merchant:
            if reason == "excluded_category":
                merged["category_name"] = merchant
                sources["category_name"] = "explicit"
            else:
                merged["text"] = merchant
                sources["text"] = "explicit"
        if not _txn_constraint_satisfied(reason, merged, has_dates):
            return _reask("transaction_filter", "search_transactions", "transaction_search",
                          _txn_reask_message(reason), arguments=merged, reason=reason)
        if (merged.get("result_mode", "list") == "list"
                and ("text" in merged or "amount" in merged)
                and not (merged.get("start_date") and merged.get("end_date"))):
            merged["all_dates"] = True
            sources["all_dates"] = "default"
        return _ready(route_value, "search_transactions", merged, "transaction_search", sources)

    if field == "amount":
        merged = {k: v for k, v in arguments.items() if k in _TXN_KEEP_KEYS}
        sources = {k: "context" for k in merged}
        try:
            reply_args = required_read_agent_tool_arguments(reply, "search_transactions", now=now)
        except ValueError:
            reply_args = {}
        amount = reply_args.get("amount")
        if not amount:
            return _reask("amount", "search_transactions", "transaction_search",
                          "Please give one exact amount, for example RM25.",
                          arguments=merged, reason="amount")
        merged["amount"] = amount
        sources["amount"] = "explicit"
        if (merged.get("result_mode", "list") == "list"
                and not (merged.get("start_date") and merged.get("end_date"))):
            merged["all_dates"] = True
            sources["all_dates"] = "default"
        return _ready(route_value, "search_transactions", merged, "transaction_search", sources)

    if field == "periods":
        try:
            parsed = parse_comparison_request(reply, now=now)
        except ValueError:
            parsed = None
        if not parsed:
            return _reask("periods", "get_period_comparison", "period_comparison",
                          "Please name at least two calendar months, for example "
                          "'July and September 2026'.")
        resolved = {"metric": parsed["metric"], "periods": parsed["periods"]}
        if parsed.get("category_name"):
            resolved["category_name"] = parsed["category_name"]
        if parsed.get("baseline"):
            resolved["baseline"] = parsed["baseline"]
        return _ready(route_value, "get_period_comparison", resolved, "period_comparison",
                      {"periods": "explicit"})

    if field == "date_range":
        if tool_name not in _ALLOWED_TOOLS:
            return _unavailable()
        try:
            resolved = required_read_agent_tool_arguments(reply, tool_name, now=now)
        except ValueError:
            resolved = {}
        if "start_date" in resolved and "end_date" in resolved:
            arguments.update(resolved)
            return _ready(route_value, tool_name, arguments, intent,
                          {key: "explicit" for key in resolved})
        return _reask("date_range", tool_name, intent,
                      "Please give the period as YYYY-MM-DD to YYYY-MM-DD.")

    return _unavailable()


def _parse_month(reply: str, tool_name: str | None, now: date) -> str | None:
    """Resolve a month reply, whether an option value or free text like 'July'."""
    direct = _YEAR_MONTH.match(reply)
    if direct:
        return f"{direct.group(1)}-{direct.group(2)}"
    lookup_tool = tool_name if tool_name in _ALLOWED_TOOLS else "get_budget_status"
    try:
        resolved = required_read_agent_tool_arguments(reply, lookup_tool, now=now)
    except ValueError:
        return None
    month = resolved.get("month")
    return str(month) if month else None
