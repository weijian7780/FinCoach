"""Non-destructive production-container smoke test for bounded Coach actions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.llm import AgentLLMResult, LLMResult
from app.rag.prompts import build_casual_prompt
from app.rag.service import CoachingService
from app.supabase_client import get_supabase


def _repository(content: str) -> MagicMock:
    repository = MagicMock(user_id="bounded-action-smoke-user")
    repository.require_session.return_value = {
        "id": "smoke-session",
        "title": "New conversation",
    }
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {
        "id": "smoke-message",
        "session_id": "smoke-session",
        "user_id": "bounded-action-smoke-user",
        "role": "user",
        "content": content,
    }
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = (
        lambda **kwargs: kwargs["assistant_payload"]
    )
    return repository


def _send(content: str) -> dict:
    return CoachingService(_repository(content), MagicMock()).send_message(
        "smoke-session",
        "smoke-message",
        content,
    )["assistant_message"]


def _reminder_count() -> int:
    response = (
        get_supabase()
        .table("reminders")
        .select("id", count="exact", head=True)
        .execute()
    )
    return int(response.count or 0)


def main() -> None:
    reminder_count_before = _reminder_count()
    results: list[dict] = []

    ambiguous_cases = {
        "pay bill": "Pay bill",
        "pay wifi bill": "Pay wifi bill",
        "settle rent": "Settle rent",
        "pay PTPTN": "Pay PTPTN",
        "bayar bil": "Bayar bil",
    }
    for content, expected_title in ambiguous_cases.items():
        with (
            patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError(
                    "Ambiguous payment commands must not reach casual chat."
                ),
            ),
            patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError(
                    "Ambiguous payment commands must use deterministic clarification."
                ),
            ),
        ):
            assistant = _send(content)
        ui_payload = assistant["ui_payload"]
        assert ui_payload["field"] == "confirm_reminder_intent"
        assert ui_payload["draft"]["title"] == expected_title
        assert [option["value"] for option in ui_payload["options"]] == [
            "create_reminder",
            "not_now",
        ]
        results.append(
            {
                "scenario": content,
                "result": "intent_confirmation",
                "title": expected_title,
            }
        )

    with patch(
        "app.rag.service.generate_result",
        return_value=LLMResult(
            "Sure! I'll set a reminder for tomorrow at 9 PM.",
            "synthetic-provider",
        ),
    ):
        assistant = _send("hello coach")
    assert "not created" in assistant["content"].lower()
    assert assistant["ui_payload"] == {}
    results.append(
        {
            "scenario": "unsupported_free_chat_claim",
            "result": "blocked",
        }
    )

    history_prompt = build_casual_prompt(
        "What should I do next?",
        [
            {
                "role": "assistant",
                "content": "I set a reminder for tomorrow at 9 PM.",
                "status": "completed",
                "ui_payload": {},
            }
        ],
        12,
    )
    assert "I set a reminder" not in history_prompt
    assert "unverified app-action claim omitted" in history_prompt.lower()
    results.append(
        {
            "scenario": "old_false_claim_in_history",
            "result": "omitted",
        }
    )

    captured_tools: dict[str, set[str]] = {}

    def _capture_read_tools(_prompt: str, **kwargs) -> AgentLLMResult:
        captured_tools["read"] = {
            item["function"]["name"]
            for item in kwargs["tool_definitions"]
        }
        return AgentLLMResult("Read-only result.", "synthetic-provider")

    with patch(
        "app.rag.service.generate_agent_result",
        side_effect=_capture_read_tools,
    ):
        _send("Show my Food budget status")
    assert "prepare_reminder" not in captured_tools["read"]
    assert "prepare_report" not in captured_tools["read"]
    results.append(
        {
            "scenario": "ordinary_budget_question",
            "result": "read_only_tools",
        }
    )

    def _capture_reminder_tools(_prompt: str, **kwargs) -> AgentLLMResult:
        captured_tools["reminder"] = {
            item["function"]["name"]
            for item in kwargs["tool_definitions"]
        }
        return AgentLLMResult(
            "Review the reminder details.",
            "synthetic-provider",
            ui_payload={
                "type": "clarification",
                "action_type": "create_reminder",
            },
        )

    with patch(
        "app.rag.service.generate_agent_result",
        side_effect=_capture_reminder_tools,
    ):
        _send("Remind me to pay rent tomorrow at 8 PM")
    assert "prepare_reminder" in captured_tools["reminder"]
    assert "prepare_report" not in captured_tools["reminder"]
    results.append(
        {
            "scenario": "explicit_reminder",
            "result": "reminder_tool_only",
        }
    )

    def _capture_report_tools(_prompt: str, **kwargs) -> AgentLLMResult:
        captured_tools["report"] = {
            item["function"]["name"]
            for item in kwargs["tool_definitions"]
        }
        return AgentLLMResult(
            "Review the report details.",
            "synthetic-provider",
            ui_payload={
                "type": "clarification",
                "action_type": "generate_report",
            },
        )

    with patch(
        "app.rag.service.generate_agent_result",
        side_effect=_capture_report_tools,
    ):
        _send("Generate my current-month financial report")
    assert "prepare_report" in captured_tools["report"]
    assert "prepare_reminder" not in captured_tools["report"]
    results.append(
        {
            "scenario": "explicit_report",
            "result": "report_tool_only",
        }
    )

    with (
        patch("app.rag.service.COACH_WRITE_ACTIONS_ENABLED", False),
        patch(
            "app.rag.service.generate_result",
            side_effect=AssertionError(
                "The disabled path must not call a provider."
            ),
        ),
        patch(
            "app.rag.service.generate_agent_result",
            side_effect=AssertionError(
                "The disabled path must not call an agent provider."
            ),
        ),
    ):
        assistant = _send("Remind me to pay rent tomorrow at 8 PM")
    assert "disabled" in assistant["content"].lower()
    assert assistant["ui_payload"] == {}
    results.append(
        {
            "scenario": "emergency_kill_switch",
            "result": "write_blocked",
        }
    )

    reminder_count_after = _reminder_count()
    assert reminder_count_after == reminder_count_before
    print(
        json.dumps(
            {
                "status": "passed",
                "scenario_count": len(results),
                "reminder_count_before": reminder_count_before,
                "reminder_count_after": reminder_count_after,
                "results": results,
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
