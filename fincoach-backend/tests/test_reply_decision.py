"""The one reply decision table: each row and the precedence between rows."""
from dataclasses import replace

import pytest

from app.rag.routing import CoachingRoute  # noqa: F401  (documents the route signals)
from app.rag.service import ReplySignals, _decide_reply

BASE = ReplySignals(
    failure=None, writes_enabled=False, write_tools=(), implied_reminder=None, budget_change=False,
    product_pick=False, full_research_clarification=False, read_clarification=False, casual=False,
    invalid_date=False, legacy_ambiguous_calculation=False, legacy_budget_planning=False,
    knowledge_clarification=False, has_read=False, education=False, education_research_owned=False,
)


@pytest.mark.parametrize("changes,handler", [
    ({"failure": "read_constraint"}, "read_constraint"),
    ({"failure": "interpretation_unavailable"}, "outage"),
    ({"write_tools": ("prepare_reminder",)}, "write_disabled"),
    ({"implied_reminder": "Pay rent"}, "write_disabled"),
    ({"budget_change": True}, "budget_change"),
    ({"writes_enabled": True, "implied_reminder": "Pay rent"}, "confirm_reminder"),
    ({"product_pick": True}, "product_pick"),
    ({"full_research_clarification": True}, "research_clarification"),
    ({"read_clarification": True}, "read_clarification"),
    ({"casual": True}, "casual"),
    ({"writes_enabled": True, "write_tools": ("prepare_reminder", "prepare_report")}, "one_at_a_time"),
    ({"writes_enabled": True, "write_tools": ("prepare_reminder",), "invalid_date": True}, "invalid_date"),
    ({"legacy_ambiguous_calculation": True}, "ambiguous_calculation"),
    ({"legacy_budget_planning": True}, "budget_planning"),
    ({"knowledge_clarification": True}, "knowledge_clarification"),
    ({"has_read": True}, "records"),
    ({"education": True, "education_research_owned": True}, "education_research"),
    ({"education": True}, "education"),
    ({"writes_enabled": True, "write_tools": ("prepare_reminder",)}, "agent"),
    ({}, "agent"),
])
def test_each_row_names_its_handler(changes, handler):
    assert _decide_reply(replace(BASE, **changes)) == handler


@pytest.mark.parametrize("changes,handler", [
    # An outage is decided before anything the (missing) interpretation would say.
    ({"failure": "interpretation_unavailable", "product_pick": True, "has_read": True}, "outage"),
    # Refusing a disabled write comes before any other policy reply.
    ({"write_tools": ("prepare_reminder",), "product_pick": True}, "write_disabled"),
    ({"write_tools": ("prepare_reminder", "prepare_report")}, "write_disabled"),
    # A budget change outranks a product pick and a read.
    ({"budget_change": True, "product_pick": True, "has_read": True}, "budget_change"),
    # Clarifications are asked before a casual or provider answer.
    ({"read_clarification": True, "casual": True}, "read_clarification"),
    ({"full_research_clarification": True, "education": True}, "research_clarification"),
    # A read plus a write goes to the confirmation-gated write path.
    ({"writes_enabled": True, "write_tools": ("prepare_reminder",), "has_read": True}, "agent"),
    # A read outranks education when both apply (combined research runs inside it).
    ({"has_read": True, "education": True}, "records"),
])
def test_precedence_between_rows(changes, handler):
    assert _decide_reply(replace(BASE, **changes)) == handler
