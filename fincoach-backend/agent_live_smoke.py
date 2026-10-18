"""Live, non-destructive tool-calling smoke tests for the configured FinCoach LLM.

The provider receives realistic synthetic finance records. No Supabase client is
created, so this script cannot read or modify a user's real data.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from app.agent_tools import AGENT_TOOL_DEFINITIONS, AgentToolExecutor
from app.llm import generate_agent_result


PREPARER = AgentToolExecutor(
    admin_client=None,
    user_id="synthetic-smoke-user",
    session_id="synthetic-smoke-session",
    now=lambda: datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc),
)


def execute_synthetic_tool(name: str, arguments: dict) -> dict:
    """Return deterministic tool results without connecting to Supabase."""
    print(json.dumps({"tool_call": name, "arguments": arguments}), flush=True)
    if name == "get_spending_summary":
        return {
            "status": "ok",
            "period": {"start": "2026-07-01", "end": "2026-07-24"},
            "expense_total": "RM520.00",
            "expense_count": 12,
            "categories": [{"name": "Food", "amount": "RM220.00"}],
            "comparison": {
                "previous_total": "RM160.00",
                "difference": "RM60.00",
            },
        }
    if name == "get_budget_status":
        return {
            "status": "ok",
            "monthly_limit": "RM600.00",
            "recorded_spending": "RM520.00",
            "remaining": "RM80.00",
        }
    if name == "get_savings_goals":
        return {
            "status": "ok",
            "goals": [
                {
                    "name": "Laptop",
                    "current_amount": 900,
                    "target_amount": 2000,
                    "deadline": "2026-12-15",
                }
            ],
        }
    if name == "get_upcoming_reminders":
        return {
            "status": "ok",
            "reminders": [
                {
                    "title": "Phone bill",
                    "amount": 60,
                    "due_at": "2026-07-29T20:00:00+08:00",
                }
            ],
        }
    if name == "get_financial_overview":
        return {
            "status": "ok",
            "spending": {
                "expense_total": "RM220.00",
                "categories": [{"name": "Food", "amount": "RM220.00"}],
                "comparison": {
                    "previous_total": "RM160.00",
                    "difference": "RM60.00",
                },
            },
            "budget": {
                "monthly_limit": "RM600.00",
                "recorded_spending": "RM520.00",
                "remaining": "RM80.00",
            },
            "savings": {
                "goals": [
                    {
                        "name": "Laptop",
                        "current_amount": 900,
                        "target_amount": 2000,
                        "deadline": "2026-12-15",
                    }
                ]
            },
            "reminders": {
                "reminders": [
                    {
                        "title": "Phone bill",
                        "amount": 60,
                        "due_at": "2026-07-29T20:00:00+08:00",
                    }
                ]
            },
        }
    if name == "get_report_summary":
        return {
            "status": "ok",
            "income": "RM1000.00",
            "expenses": "RM520.00",
            "net": "RM480.00",
        }
    if name == "prepare_reminder":
        return PREPARER.execute(name, arguments)
    if name == "prepare_report":
        return {
            "status": "confirmation_required",
            "ui_payload": {
                "type": "action",
                "action_id": "00000000-0000-4000-8000-000000000321",
                "action_type": "generate_report",
                "status": "pending",
                "title": "Generate financial report?",
                "description": "Synthetic smoke-test proposal.",
                "confirm_label": "Generate report",
                "arguments": arguments,
                "fields": [],
            },
        }
    return {"status": "not_allowed"}


SCENARIOS = [
    (
        "compare_last_month",
        "Compare with last month",
    ),
    (
        "complex_multi_module",
        "Compare my Food spending with last month, check whether I am over budget, "
        "tell me my Laptop savings-goal progress, and list bills due next week.",
    ),
    (
        "incomplete_reminder",
        "Remind me to pay PTPTN.",
    ),
    (
        "complete_reminder",
        "Every month on the 15th, remind me three days earlier at 8 PM Malaysia time "
        "to pay PTPTN RM150. Show me the details before creating it.",
    ),
    (
        "report_action",
        "Generate my current-month financial report for all categories, but show me "
        "what will happen before you do it.",
    ),
]


def main() -> None:
    for scenario, prompt in SCENARIOS:
        result = generate_agent_result(
            prompt,
            tool_definitions=AGENT_TOOL_DEFINITIONS,
            tool_executor=execute_synthetic_tool,
            reasoning_effort="high",
            max_iterations=3,
        )
        print(
            json.dumps(
                {
                    "scenario": scenario,
                    "model": result.model,
                    "tools": result.tool_names,
                    "ui_type": (result.ui_payload or {}).get("type"),
                    "ui_status": (result.ui_payload or {}).get("status"),
                    "content": result.content,
                },
                ensure_ascii=True,
            )
        )


if __name__ == "__main__":
    main()
