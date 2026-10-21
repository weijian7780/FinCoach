"""Regression coverage for natural financial phrasing, without live records."""

from datetime import date

import pytest

from app.category_resolution import resolve_category_phrase
from app.rag.follow_ups import build_follow_ups
from app.rag.routing import (
    CoachingRoute, ReadReadiness, resolve_read_request, select_financial_context_scope,
)
from app.rag.text_normalize import normalize_for_intent

NOW = date(2026, 9, 22)


@pytest.mark.parametrize("text, tool", [
    ("show me food spend", "get_spending_summary"),
    ("Food spend", "get_spending_summary"),
    ("check my food spend this month", "get_spending_summary"),
    ("Savings-goal progress", "get_savings_goals"),
    ("savings\u2013goal progress", "get_savings_goals"),
    ("savings\u2011goal progress", "get_savings_goals"),
    ("Which category costs most?", "get_spending_summary"),
    ("Show my top categories", "get_spending_summary"),
])
def test_short_requests_select_the_correct_record_tool(text, tool):
    result = resolve_read_request(text, [], now=NOW)
    assert result.route == CoachingRoute.PERSONAL_FINANCE
    assert result.tool_name == tool
    assert result.readiness == ReadReadiness.READY
    assert result.clarification is None


@pytest.mark.parametrize("text", [
    "Which category am I spending the most on?", "Which category costs most?",
    "Show my top categories", "monthly spending", "my total expenses",
    "overall spending", "show me my weekly expenses",
    "Where can I cut spending?", "Plan my budget limit",
])
def test_ranking_and_qualifiers_do_not_become_category_names(text):
    assert resolve_category_phrase(text, ["Food", "Transport"]).status == "none"
    assert not resolve_read_request(text, [], now=NOW).arguments.get("category_name")


@pytest.mark.parametrize("text", [
    "spend time with friends", "I spend time with friends",
    "Where did I spend the weekend?", "How to spend less?",
    "What is a savings-goal?",
])
def test_general_or_nonfinancial_requests_do_not_read_private_records(text):
    assert resolve_read_request(text, [], now=NOW).tool_name is None


def test_normalization_preserves_dates_amounts_and_custom_category_names():
    original = "  Savings\u2013goal  progress 2026-09-22 -50 Take-away Food & Drink "
    assert normalize_for_intent(original) == (
        "savings goal progress 2026-09-22 -50 Take-away Food & Drink"
    )
    assert original.startswith("  ")  # The matching view does not replace user text.


def test_original_category_and_explicit_dates_survive_resolution():
    text = "Show Take-away spend from 2026-07-01 to 2026-07-31"
    result = resolve_read_request(text, [], now=NOW)
    assert result.arguments == {
        "start_date": "2026-07-01", "end_date": "2026-07-31", "category_name": "Take-Away",
    }
    assert resolve_category_phrase(text, ["Take-away", "Food"]).category == "Take-away"


def test_unmarked_unknown_after_ranking_language_is_not_dropped():
    # "highest" must not drop the reference to nothing: an unfamiliar unmarked
    # phrase is interpreted (which clarifies when disabled), never unfiltered.
    result = resolve_category_phrase("Show highest spending for Yachts", ["Food", "Transport"])
    assert result.status == "needs_interpretation"


def test_monthly_category_can_still_be_requested_by_exact_name():
    assert resolve_category_phrase("spending on Monthly", ["Monthly"]).category == "Monthly"


def test_normalized_topic_switch_does_not_inherit_spending_filters():
    result = resolve_read_request(
        "What about savings-goal progress?",
        [{"role": "user", "content": "Show my Food spending in July"}], now=NOW,
    )
    assert result.tool_name == "get_savings_goals"
    assert "category_name" not in result.arguments
    assert "start_date" not in result.arguments


def test_normalized_goal_intent_limits_the_requested_context():
    scope = select_financial_context_scope("Savings-goal progress")
    assert scope.include_savings_goals
    assert not scope.include_transactions
    assert not scope.include_monthly_budget


def test_top_category_followup_is_not_offered_after_a_ranking_question():
    chips = build_follow_ups(
        content="Show my top categories", response_mode="fast_verified_read",
        tool_names=("get_spending_summary",),
    )
    assert all(chip["query"] != "Which category am I spending the most on?" for chip in chips)
