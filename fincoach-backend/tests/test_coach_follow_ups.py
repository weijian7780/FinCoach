"""Unit tests for deterministic, context-aware follow-up chip selection."""

from app.rag.follow_ups import MAX_FOLLOW_UPS, build_follow_ups


def _labels(chips):
    return [chip["label"] for chip in chips]


def test_budget_answer_offers_unasked_next_steps():
    chips = build_follow_ups(
        content="Show my budget breakdown",
        response_mode="fast_verified_read",
        tool_names=("get_budget_status",),
        history=[{"role": "user", "content": "Show my budget breakdown"}],
    )
    # budget_status is already asked, so it is dropped; the next unasked
    # candidates are offered instead.
    assert _labels(chips) == ["Where can I cut spending?", "Compare with last month"]
    for chip in chips:
        assert chip["query"] and chip["label"]


def test_repeated_thread_is_deduped_across_history():
    # Mirrors the screenshot: user cut-spending, then budget breakdown, then
    # compare-with-last-month. The only unasked candidate left is goal tracking.
    history = [
        {"role": "user", "content": "Where can I cut spending?"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "Show my budget breakdown"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "Compare my spending with last month"},
    ]
    chips = build_follow_ups(
        content="Compare my spending with last month",
        response_mode="fast_verified_read",
        tool_names=("get_budget_status",),
        history=history,
    )
    assert _labels(chips) == ["Am I on track for my goal?"]


def test_never_exceeds_cap():
    chips = build_follow_ups(
        content="hello",
        response_mode="fast_verified_read",
        tool_names=("get_spending_summary",),
        history=[],
    )
    assert len(chips) <= MAX_FOLLOW_UPS


def test_savings_goal_answer_offers_plan_and_tracking():
    chips = build_follow_ups(
        content="How are my savings goals?",
        response_mode="fast_verified_read",
        tool_names=("get_savings_goals",),
        history=[],
    )
    assert _labels(chips) == ["Make me a weekly saving plan", "Am I on track for my goal?"]


def test_budget_planning_mode_without_tool_still_suggests():
    chips = build_follow_ups(
        content="How much should I set aside each month?",
        response_mode="budget_planning",
        tool_names=(),
        history=[],
    )
    assert _labels(chips) == ["Am I on track for my goal?", "Show my budget breakdown"]


def test_clarification_and_policy_modes_get_no_chips():
    for mode in ("clarification", "permission_policy", "read_policy", "product_policy", "action_policy"):
        assert build_follow_ups(
            content="anything",
            response_mode=mode,
            tool_names=("get_budget_status",),
            history=[],
        ) == []


def test_educational_answer_without_tool_gets_no_chips():
    assert build_follow_ups(
        content="What is EPF?",
        response_mode="llm",
        tool_names=(),
        history=[],
    ) == []
