"""Pure round-trip tests for saving and resuming a pending read clarification."""

from datetime import date

from app.rag.read_clarification import (
    PAYLOAD_TYPE,
    build_read_clarification,
    resume_read_clarification,
)
from app.rag.routing import ReadReadiness, resolve_read_request


NOW = date(2026, 9, 22)


def _pending(text):
    return resolve_read_request(text, [], now=NOW)


def test_short_answer_resumes_budget_not_casual():
    pending = _pending("Show my budget last week")
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=NOW)
    resumed = resume_read_clarification(payload, "July", now=NOW)
    assert resumed.tool_name == "get_budget_status"
    assert resumed.arguments["month"] == "2026-07"
    assert resumed.readiness == ReadReadiness.READY


def test_build_month_payload_shape():
    payload = build_read_clarification(
        _pending("Show my budget last week"), origin_message_id="u1", anchor_date=NOW
    )
    assert payload["type"] == PAYLOAD_TYPE
    assert payload["field"] == "month"
    assert payload["input_type"] == "single_select"
    assert payload["allow_other"] is True
    assert {option["value"] for option in payload["options"]} == {"2026-09", "2026-08"}
    assert payload["state"]["version"] == 1
    assert payload["state"]["tool_name"] == "get_budget_status"
    assert payload["state"]["origin_message_id"] == "u1"


def test_option_value_resumes_directly():
    payload = build_read_clarification(
        _pending("Show my budget last week"), origin_message_id="u1", anchor_date=NOW
    )
    resumed = resume_read_clarification(payload, "2026-08", now=NOW)
    assert resumed.arguments["month"] == "2026-08"
    assert resumed.readiness == ReadReadiness.READY


def test_savings_intent_resumes_to_the_chosen_tool():
    payload = build_read_clarification(
        _pending("What about my savings?"), origin_message_id="u1", anchor_date=NOW
    )
    assert payload["field"] == "savings_intent"
    goals = resume_read_clarification(payload, "goal_progress", now=NOW)
    assert goals.tool_name == "get_savings_goals"
    assert goals.readiness == ReadReadiness.READY
    capacity = resume_read_clarification(payload, "how much I could save", now=NOW)
    assert capacity.tool_name == "predict_savings"
    assert capacity.readiness == ReadReadiness.READY


def test_transaction_filter_resumes_to_a_search():
    payload = build_read_clarification(
        _pending("Show me that transaction"), origin_message_id="u1", anchor_date=NOW
    )
    assert payload["field"] == "transaction_filter"
    resumed = resume_read_clarification(payload, "Speedmart groceries", now=NOW)
    assert resumed.tool_name == "search_transactions"
    assert resumed.arguments["text"] == "Speedmart groceries"
    assert resumed.readiness == ReadReadiness.READY


def test_invalid_month_reply_asks_again_and_keeps_the_tool():
    payload = build_read_clarification(
        _pending("Show my budget last week"), origin_message_id="u1", anchor_date=NOW
    )
    resumed = resume_read_clarification(payload, "last week", now=NOW)
    assert resumed.readiness == ReadReadiness.NEEDS_CLARIFICATION
    assert resumed.tool_name == "get_budget_status"
    assert resumed.arguments == {}


def test_cancellation_ends_the_pending_read():
    payload = build_read_clarification(
        _pending("Show my budget last week"), origin_message_id="u1", anchor_date=NOW
    )
    for reply in ("never mind", "batal", "thanks"):
        resumed = resume_read_clarification(payload, reply, now=NOW)
        assert resumed.tool_name is None
        assert resumed.readiness == ReadReadiness.READY
        assert resumed.clarification is None


def test_malformed_state_is_unavailable_not_a_broad_read():
    for payload in (
        {"type": PAYLOAD_TYPE, "field": "month", "state": {"version": 2, "route": "personal_finance", "tool_name": "get_budget_status"}},
        {"type": PAYLOAD_TYPE, "field": "month", "state": {"version": 1, "route": "hacked", "tool_name": "get_budget_status"}},
        {"type": PAYLOAD_TYPE, "field": "month", "state": {"version": 1, "route": "personal_finance", "tool_name": "drop_tables"}},
        {"type": "not_a_read", "field": "month", "state": {"version": 1, "route": "personal_finance", "tool_name": "get_budget_status"}},
    ):
        resumed = resume_read_clarification(payload, "July", now=NOW)
        assert resumed.tool_name is None
        assert resumed.readiness == ReadReadiness.NEEDS_CLARIFICATION


def test_multi_merchant_reply_searches_all_dates():
    pending = _pending("Show transactions at Grab and Foodpanda")
    assert pending.readiness == ReadReadiness.NEEDS_CLARIFICATION
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=NOW)
    assert payload["field"] == "transaction_filter"
    resumed = resume_read_clarification(payload, "IPOH KOPI KIA", now=NOW)
    assert resumed.tool_name == "search_transactions"
    assert resumed.readiness == ReadReadiness.READY
    assert resumed.arguments == {"text": "IPOH KOPI KIA", "all_dates": True}


def test_multi_merchant_date_only_reply_saves_date_and_reasks():
    pending = _pending("Show transactions at Grab and Foodpanda")
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=NOW)
    resumed = resume_read_clarification(payload, "in July 2026", now=NOW)
    assert resumed.readiness == ReadReadiness.NEEDS_CLARIFICATION
    assert resumed.arguments.get("start_date") == "2026-07-01"
    assert resumed.arguments.get("end_date") == "2026-07-31"
    assert "text" not in resumed.arguments
    assert "all_dates" not in resumed.arguments


def test_merchant_count_clarification_keeps_current_month():
    pending = _pending("how many transactions at Grab and Foodpanda")
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=NOW)
    resumed = resume_read_clarification(payload, "IPOH KOPI KIA", now=NOW)
    assert resumed.readiness == ReadReadiness.READY
    assert resumed.arguments.get("result_mode") == "count"
    assert resumed.arguments.get("text") == "IPOH KOPI KIA"
    assert "all_dates" not in resumed.arguments


def test_clarification_preserves_valid_filters_changing_only_merchant():
    pending = _pending(
        "Show my last 5 Food transactions at Grab and Foodpanda for RM25 in July 2026"
    )
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=NOW)
    resumed = resume_read_clarification(payload, "IPOH KOPI KIA", now=NOW)
    assert resumed.readiness == ReadReadiness.READY
    assert resumed.arguments.get("start_date") == "2026-07-01"
    assert resumed.arguments.get("end_date") == "2026-07-31"
    assert resumed.arguments.get("category_name") == "Food"
    assert resumed.arguments.get("amount") == "25.00"
    assert resumed.arguments.get("limit") == 5
    assert resumed.arguments.get("text") == "IPOH KOPI KIA"
    assert "all_dates" not in resumed.arguments


def test_amount_clarification_then_corrected_amount_searches_all_dates():
    pending = _pending("Show transactions for RM25k")
    assert pending.readiness == ReadReadiness.NEEDS_CLARIFICATION
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=NOW)
    assert payload["field"] == "amount"
    resumed = resume_read_clarification(payload, "RM25", now=NOW)
    assert resumed.readiness == ReadReadiness.READY
    assert resumed.arguments.get("amount") == "25.00"
    assert resumed.arguments.get("all_dates") is True
