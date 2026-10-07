"""Service-level wiring for LLM-offered choice cards (flag on/off + selection).

The pure parsing/validation lives in test_coach_choices.py; these tests exercise
CoachingService.send_message: emission behind the flag, flag-off inertness, and
that tapping a saved choice routes its query through the normal read path.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.llm import AgentLLMResult, LLMResult
from app.rag.coach_choices import build_choices_payload

_OPEN = "<<<FINCOACH_CHOICES>>>"
_CLOSE = "<<<END_FINCOACH_CHOICES>>>"
_ANSWER_WITH_BLOCK = (
    "PTPTN is the national higher-education loan.\n\n"
    f"{_OPEN}\n"
    '{"choices": [{"label": "Repayment options", "query": "How do I repay PTPTN?"},'
    ' {"label": "Check my balance", "query": "How much PTPTN do I still owe?"}]}\n'
    f"{_CLOSE}"
)


def _education_repository():
    repository = MagicMock(user_id="verified-user")
    repository.require_session.return_value = {"id": "session-1", "title": "New conversation"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {
        "id": "message-1", "session_id": "session-1", "user_id": "verified-user",
        "role": "user", "content": "What is PTPTN?",
    }
    repository.list_messages.return_value = [
        {"id": "message-1", "role": "user", "content": "What is PTPTN?"},
    ]
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    return repository


class ChoiceEmissionTests(unittest.TestCase):
    def _run(self, *, flag: bool):
        from app.rag.service import CoachingService

        repository = _education_repository()
        with (
            patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", False),
            patch("app.rag.service.COACH_LLM_CHOICES_ENABLED", flag),
            patch("app.rag.service.retrieve", return_value=[]),
            patch(
                "app.rag.service.generate_result",
                return_value=LLMResult(content=_ANSWER_WITH_BLOCK, model="test"),
            ),
            patch(
                "app.rag.service._ground_educational_answer",
                side_effect=lambda result, **_kwargs: (result, False, False),
            ),
        ):
            return CoachingService(repository, MagicMock()).send_message(
                "session-1", "message-1", "What is PTPTN?"
            )["assistant_message"]

    def test_flag_on_strips_block_and_attaches_choice_payload(self):
        message = self._run(flag=True)
        content = message["content"]
        self.assertIn("PTPTN is the national higher-education loan.", content)
        # Raw metadata never surfaces in the visible answer.
        self.assertNotIn(_OPEN, content)
        self.assertNotIn(_CLOSE, content)
        self.assertNotIn("query", content)
        payload = message["ui_payload"]
        self.assertEqual(payload["type"], "coach_choices")
        self.assertEqual([o["id"] for o in payload["options"]], ["c1", "c2"])
        self.assertEqual(payload["options"][0]["query"], "How do I repay PTPTN?")
        # A choice card replaces deterministic chips for this turn.
        self.assertNotIn("follow_ups", payload)

    def test_flag_off_leaves_block_untouched_and_offers_no_choice_cards(self):
        message = self._run(flag=False)
        # With the flag off the choice logic is inert; nothing strips the block
        # and no coach_choices payload is produced.
        self.assertNotEqual(message.get("ui_payload", {}).get("type"), "coach_choices")


class ChoiceSelectionTests(unittest.TestCase):
    def test_tapping_a_saved_choice_routes_its_query_as_a_new_read(self):
        from app.rag.service import CoachingService

        options = [
            {"id": "c1", "label": "Food this month",
             "query": "How much did I spend on Food this month?"},
        ]
        saved = {
            "id": "assist-1",
            "session_id": "session-1",
            "ui_payload": build_choices_payload(options, origin_message_id="user-0"),
        }

        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {"id": "session-1", "title": "Chat"}
        repository.require_interaction_message.return_value = saved
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-2", "session_id": "session-1", "user_id": "verified-user",
            "role": "user", "content": "How much did I spend on Food this month?",
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]

        execute = MagicMock(return_value={"status": "ok", "expense_total": "RM0.00", "expense_count": 0})
        with (
            patch("app.rag.service.COACH_LLM_CHOICES_ENABLED", True),
            patch("app.rag.service.AgentToolExecutor.execute", execute),
            patch("app.rag.service.retrieve", return_value=[]),
            patch(
                "app.rag.service.generate_result",
                return_value=LLMResult(content="You spent RM0.00 on Food.", model="test"),
            ),
            patch(
                "app.rag.service.generate_agent_result",
                return_value=AgentLLMResult(content="You spent RM0.00 on Food.", model="test"),
            ),
        ):
            CoachingService(repository, MagicMock()).send_message(
                "session-1", "message-2",
                "How much did I spend on Food this month?",
                interaction_reply={"assistant_message_id": "assist-1", "value": "c1"},
            )

        # The tapped choice ran the saved query through the normal read path.
        self.assertTrue(execute.called)
        self.assertEqual(execute.call_args[0][0], "get_spending_summary")

    def test_invalid_option_id_does_not_crash(self):
        from app.rag.service import CoachingService

        saved = {
            "id": "assist-1",
            "session_id": "session-1",
            "ui_payload": build_choices_payload(
                [{"id": "c1", "label": "A", "query": "How much did I spend this month?"}],
                origin_message_id="user-0",
            ),
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {"id": "session-1", "title": "Chat"}
        repository.require_interaction_message.return_value = saved
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-3", "session_id": "session-1", "user_id": "verified-user",
            "role": "user", "content": "pick",
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]

        with (
            patch("app.rag.service.COACH_LLM_CHOICES_ENABLED", True),
            patch("app.rag.service.AgentToolExecutor.execute",
                  return_value={"status": "ok", "expense_total": "RM0.00", "expense_count": 0}),
            patch("app.rag.service.retrieve", return_value=[]),
            patch("app.rag.service.generate_result",
                  return_value=LLMResult(content="ok", model="test")),
            patch("app.rag.service.generate_agent_result",
                  return_value=AgentLLMResult(content="ok", model="test")),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1", "message-3", "pick",
                interaction_reply={"assistant_message_id": "assist-1", "value": "c9"},
            )
        # An unresolved option id must not raise; it falls back to normal handling.
        self.assertIn("assistant_message", result)


if __name__ == "__main__":
    unittest.main()
