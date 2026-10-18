"""The shared read contract: readiness, intent, and parameter provenance.

These assert the *contract* fields on ``ResolvedReadRequest`` — why a read can
execute, why it cannot, and where each resolved parameter came from — rather than
re-testing routing selection (covered by test_accuracy_routing).
"""

from datetime import date

from app.rag.routing import ReadReadiness, resolve_read_request


def test_default_period_is_explicit_in_contract():
    result = resolve_read_request("Show my spending", [], now=date(2026, 9, 22))
    assert result.readiness == ReadReadiness.READY
    assert result.arguments["start_date"] == "2026-09-01"
    assert result.parameter_sources["start_date"] == "default"


def test_invalid_period_keeps_budget_intent():
    result = resolve_read_request("Show my budget last week", [], now=date(2026, 9, 22))
    assert result.tool_name == "get_budget_status"
    assert result.readiness == ReadReadiness.NEEDS_CLARIFICATION
    assert result.invalid_fields == ("month",)


def test_explicit_month_is_recorded_as_explicit():
    result = resolve_read_request("Show my July spending", [], now=date(2026, 9, 22))
    assert result.arguments["start_date"] == "2026-07-01"
    assert result.parameter_sources["start_date"] == "explicit"
    assert result.readiness == ReadReadiness.READY


def test_topic_change_has_no_stale_category():
    result = resolve_read_request(
        "Show my budget this month",
        [{"role": "user", "content": "Show spending only Food"}],
        now=date(2026, 9, 22),
    )
    assert result.tool_name == "get_budget_status"
    assert "category_name" not in result.arguments
    assert result.readiness == ReadReadiness.READY


def test_ambiguous_savings_needs_clarification_with_intent():
    result = resolve_read_request("What about my savings?", [], now=date(2026, 9, 22))
    assert result.tool_name is None
    assert result.intent == "savings_unspecified"
    assert result.readiness == ReadReadiness.NEEDS_CLARIFICATION


def test_receipt_image_request_is_unsupported():
    result = resolve_read_request(
        "Show me the receipt image for that transaction", [], now=date(2026, 9, 22)
    )
    assert result.readiness == ReadReadiness.UNSUPPORTED
    assert result.tool_name is None


def test_education_follow_up_has_no_read_intent():
    result = resolve_read_request(
        "What is PTPTN?",
        [{"role": "user", "content": "Show my spending on Food"}],
        now=date(2026, 9, 22),
    )
    assert result.tool_name is None
    assert result.intent is None
    assert result.readiness == ReadReadiness.READY
