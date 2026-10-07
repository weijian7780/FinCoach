import unittest
from unittest.mock import MagicMock, patch
from app.rag.service import CoachingService
from app.rag import grounding as _grounding_mod
from app.llm import AgentLLMResult


def send(question, answer, tool_result, history=None):
    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Audit"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": question}
    repo.list_messages.return_value = history or []
    repo.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    with patch("app.rag.service.AgentToolExecutor.execute", return_value=tool_result), patch(
        "app.rag.service.generate_result", return_value=AgentLLMResult(content=answer, model="test")
    ), patch("app.rag.service.retrieve", return_value=[]):
        return CoachingService(repo, MagicMock()).send_message("s", "m", question)["assistant_message"]


BUDGET = {"status": "ok", "month": "2026-08-01", "monthly_limit": "RM1000.00",
          "recorded_spending": "RM900.00", "remaining": "RM100.00"}


class AccuracyGroundingTests(unittest.TestCase):
    def setUp(self):
        """Force guard #2 on — it is behind the kill switch by default.

        service.py reads grounding._VALIDATION_ENABLED live (single source of
        truth), so flipping the grounding module attribute is sufficient.
        """
        self._orig_grounding = _grounding_mod._VALIDATION_ENABLED
        _grounding_mod._VALIDATION_ENABLED = True

    def tearDown(self):
        _grounding_mod._VALIDATION_ENABLED = self._orig_grounding
    def test_user_input_is_not_evidence_for_recorded_amount(self):
        result = send("Why is my budget remaining RM9999?", "Your verified remaining budget is RM9999.", BUDGET)
        self.assertNotIn("9999", result["content"])

    def test_history_is_not_evidence_for_recorded_amount(self):
        result = send("Why should I reduce spending?", "Your recorded spending is RM9999.",
                      {"status": "ok", "expense_total": "RM600.00"},
                      [{"role": "assistant", "content": "Your spending is RM9999."}])
        self.assertNotIn("9999", result["content"])

    def test_amount_present_in_wrong_field_is_rejected(self):
        result = send("Why is my budget low?", "Your remaining budget is RM1000.00.", BUDGET)
        self.assertEqual(result["model"], "fincoach-grounding-policy")

    def test_correct_recorded_balance_is_preserved(self):
        answer = "Your remaining budget is RM100.00."
        result = send("Why is my budget low?", answer, BUDGET)
        self.assertIn("RM100.00", result["content"])
        self.assertIn(answer, result["content"])

    def test_hypothetical_example_is_not_a_recorded_claim(self):
        answer = "For example, saving RM50 each month can build a habit."
        result = send("Why should I save?", answer, BUDGET)
        self.assertIn(answer, result["content"])

    def test_example_cannot_whitelist_same_amount_in_recorded_claim(self):
        answer = "For example, saving RM9999 is ambitious. Your recorded spending is RM9999."
        result = send("Why should I reduce spending?", answer, {"status": "ok", "expense_total": "RM600.00"})
        self.assertEqual(result["model"], "fincoach-grounding-policy")

    def test_failed_tool_is_not_rendered_as_zero(self):
        result = send("Show my spending", "", {"status": "invalid_arguments", "message": "Invalid period."})
        self.assertNotIn("RM0", result["content"])
        self.assertIn("Invalid period", result["content"])
