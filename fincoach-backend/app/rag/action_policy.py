"""Hard boundaries between coaching text and confirmation-gated app actions."""

from __future__ import annotations

import re
from typing import Any


WRITE_TOOL_NAMES = frozenset({"prepare_reminder", "prepare_report"})

_ACTION_OBJECT = (
    r"(?:reminders?|reports?|transactions?|budgets?|categor(?:y|ies)|"
    r"savings?\s+goals?|alerts?|notifications?|backups?|records?)"
)
_WRITE_VERB = (
    r"(?:set|creat(?:e|ed)|schedul(?:e|ed)|add(?:ed)?|generat(?:e|ed)|"
    r"sav(?:e|ed)|updat(?:e|ed)|delet(?:e|ed)|remov(?:e|ed)|"
    r"cancel(?:led|ed)|record(?:ed)?|export(?:ed)?|download(?:ed)?|"
    r"submit(?:ted)?|send|sent|notif(?:y|ied)|remind(?:ed)?)"
)
_COMPLETED_STATE = (
    r"(?:set|created|scheduled|added|generated|saved|updated|deleted|"
    r"removed|cancelled|canceled|recorded|exported|downloaded|submitted|"
    r"sent|ready(?:\s+for\s+download)?)"
)

_FIRST_PERSON_WRITE_CLAIM = re.compile(
    rf"\b(?:i(?:['\u2019](?:ll|ve))?|we(?:['\u2019](?:ll|ve))?|"
    rf"fincoach|the\s+app)\s+"
    rf"(?:(?:will|have|has|just|already)\s+)?{_WRITE_VERB}\b"
    rf".{{0,100}}\b{_ACTION_OBJECT}\b",
    re.IGNORECASE,
)
_DIRECT_REMINDER_PROMISE = re.compile(
    r"\b(?:i(?:['\u2019]ll)?|we(?:['\u2019]ll)?)\s+"
    r"(?:(?:will|can)\s+)?(?:remind|notify|alert)\s+"
    r"(?:you|me|us|him|her|them)\b",
    re.IGNORECASE,
)
_ACTION_STATE_CLAIM = re.compile(
    rf"\b(?:your|the|this|a|an)?\s*(?:[\w-]+\s+){{0,4}}"
    rf"{_ACTION_OBJECT}\s+"
    rf"(?:(?:(?:is|was)\s+(?:now\s+)?|has\s+been\s+)"
    rf"{_COMPLETED_STATE}|{_COMPLETED_STATE})\b",
    re.IGNORECASE,
)
_DONE_ACTION_CLAIM = re.compile(
    rf"\b(?:done|all\s+set|completed)\b.{{0,80}}\b{_ACTION_OBJECT}\b",
    re.IGNORECASE,
)
_FIRST_PERSON_ACTION_OFFER = re.compile(
    rf"\b(?:(?:i|we)\s+(?:can|could|will|would|am\s+able\s+to|"
    rf"are\s+able\s+to).{{0,120}}|would\s+you\s+like\s+me\s+to\s+|"
    rf"let\s+me\s+){_WRITE_VERB}\b.{{0,100}}\b{_ACTION_OBJECT}\b",
    re.IGNORECASE,
)
_NEGATED_ACTION_STATE = re.compile(
    rf"\bno\b.{{0,80}}\b{_ACTION_OBJECT}\b.{{0,30}}"
    rf"(?:(?:is|was)\s+|has\s+been\s+){_COMPLETED_STATE}\b|"
    rf"\b{_ACTION_OBJECT}\s+(?:(?:is|was)\s+|has\s+been\s+)"
    rf"not\s+{_COMPLETED_STATE}\b",
    re.IGNORECASE,
)


def has_structured_action_ui(ui_payload: Any) -> bool:
    """Return true only for a server-produced clarification or action card."""
    return isinstance(ui_payload, dict) and ui_payload.get("type") in {
        "clarification",
        "action",
    }


def is_unverified_action_claim(
    content: str,
    *,
    has_action_ui: bool,
) -> bool:
    """Identify action promises that are unsupported by structured app state."""
    if has_action_ui:
        return False
    text = " ".join(str(content or "").split())
    text_without_negated_states = _NEGATED_ACTION_STATE.sub("", text)
    return bool(
        _FIRST_PERSON_WRITE_CLAIM.search(text)
        or _DIRECT_REMINDER_PROMISE.search(text)
        or _ACTION_STATE_CLAIM.search(text_without_negated_states)
        or _DONE_ACTION_CLAIM.search(text)
    )


def ground_unverified_action_claim(
    content: str,
    *,
    has_action_ui: bool,
) -> str:
    """Replace unsupported action claims with a deterministic safe response."""
    if not is_unverified_action_claim(content, has_action_ui=has_action_ui):
        return content
    return (
        "App action not completed. Reminder or report not created; no FinCoach "
        "record was changed. "
        "Make an explicit reminder or report request, review the action card, "
        "and confirm it before FinCoach changes anything."
    )


def ground_disabled_action_offer(content: str) -> str:
    """Remove first-person write offers while Coaching is advice-only."""
    text = " ".join(str(content or "").split())
    if not _FIRST_PERSON_ACTION_OFFER.search(text):
        return content
    return (
        "AI Coaching is advice-only and cannot create reminders or reports. "
        "To add or change a reminder, open Alerts > Manage reminders. "
        "I can still help you plan the payment or understand your finances."
    )


def bounded_tool_definitions(
    definitions: list[dict],
    *,
    requested_write_tool: str | None = None,
    writes_enabled: bool = True,
) -> list[dict]:
    """Expose read tools plus at most one explicitly requested write tool."""
    allowed_write_tool = (
        requested_write_tool
        if writes_enabled and requested_write_tool in WRITE_TOOL_NAMES
        else None
    )
    bounded: list[dict] = []
    for definition in definitions:
        function = definition.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        if name in WRITE_TOOL_NAMES and name != allowed_write_tool:
            continue
        bounded.append(definition)
    return bounded
