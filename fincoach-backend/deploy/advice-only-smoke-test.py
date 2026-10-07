"""Non-destructive production smoke test for advice-only AI Coaching."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.config import COACH_WRITE_ACTIONS_ENABLED
from app.llm import AgentLLMResult, LLMResult
from app.rag.service import CoachingService
from app.supabase_client import get_supabase


def _repository(content: str) -> MagicMock:
    repository = MagicMock(user_id="advice-only-smoke-user")
    repository.require_session.return_value = {
        "id": "smoke-session",
        "title": "New conversation",
    }
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {
        "id": "smoke-message",
        "session_id": "smoke-session",
        "user_id": "advice-only-smoke-user",
        "role": "user",
        "content": content,
    }
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = (
        lambda **kwargs: kwargs["assistant_payload"]
    )
    return repository


def _send(
    content: str,
    *,
    interaction_reply: dict[str, str] | None = None,
) -> dict:
    return CoachingService(_repository(content), MagicMock()).send_message(
        "smoke-session",
        "smoke-message",
        content,
        interaction_reply=interaction_reply,
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
    assert COACH_WRITE_ACTIONS_ENABLED is False
    reminder_count_before = _reminder_count()
    results: list[dict] = []

    for content in [
        "pay bill",
        "Remind me to pay rent tomorrow at 8 PM",
        "Generate my current-month financial report",
    ]:
        with (
            patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError(
                    "Recognised actions must not call a chat provider."
                ),
            ),
            patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError(
                    "Recognised actions must not call an agent provider."
                ),
            ),
        ):
            assistant = _send(content)
        assert "disabled" in assistant["content"].lower()
        assert assistant["ui_payload"] == {}
        results.append({"scenario": content, "result": "write_blocked"})

    for content in ["pay billl", "wifi"]:
        with patch(
            "app.rag.service.generate_result",
            return_value=LLMResult(
                "Let me know the amount and I can help you plan or "
                "set a reminder.",
                "synthetic-provider",
            ),
        ):
            assistant = _send(content)
        assert "advice-only" in assistant["content"].lower()
        assert "cannot create" in assistant["content"].lower()
        assert "alerts" in assistant["content"].lower()
        assert assistant["ui_payload"] == {}
        results.append({"scenario": content, "result": "offer_replaced"})

    captured_names: set[str] = set()

    def _read_only_result(_prompt: str, **kwargs) -> AgentLLMResult:
        captured_names.update(
            item["function"]["name"]
            for item in kwargs["tool_definitions"]
        )
        return AgentLLMResult("Read-only budget result.", "synthetic-provider")

    with patch(
        "app.rag.service.generate_agent_result",
        side_effect=_read_only_result,
    ):
        assistant = _send("Show my Food budget status")
    assert "prepare_reminder" not in captured_names
    assert "prepare_report" not in captured_names
    assert assistant["ui_payload"] == {}
    results.append(
        {
            "scenario": "ordinary_budget_question",
            "result": "read_only_tools",
        }
    )

    with patch.object(
        CoachingService,
        "_resume_interaction",
        side_effect=AssertionError(
            "Advice-only mode must reject old action cards."
        ),
    ):
        assistant = _send(
            "Confirm",
            interaction_reply={
                "interaction_id": "old-action-card",
                "field": "confirm",
                "value": "confirm",
            },
        )
    assert "disabled" in assistant["content"].lower()
    assert assistant["ui_payload"] == {}
    results.append(
        {
            "scenario": "old_confirmation_card",
            "result": "write_blocked",
        }
    )

    reminder_count_after = _reminder_count()
    assert reminder_count_after == reminder_count_before
    print(
        json.dumps(
            {
                "status": "passed",
                "write_actions_enabled": COACH_WRITE_ACTIONS_ENABLED,
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
