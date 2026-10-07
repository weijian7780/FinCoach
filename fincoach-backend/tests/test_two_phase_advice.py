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

SPENDING = {"status": "ok", "expense_total": "RM600.00", "expense_count": 12,
            "period": {"start": "2026-08-01", "end": "2026-08-31"},
            "categories": [{"name": "Food", "amount": "RM300.00"}]}


class TwoPhaseAdviceTests(unittest.TestCase):
    """Verify the two-phase response for deep-advice personal queries.

    Deep-advice queries (containing 'why', 'should', 'how can', etc.)
    now render verified tool data in a deterministic facts block, then
    append number-free LLM commentary. This prevents the numeric guard
    from rejecting the entire response when the LLM paraphrases a figure.
    """

    def setUp(self):
        """Force guard #2 on — it is behind the kill switch by default.

        service.py reads grounding._VALIDATION_ENABLED live, so flipping the
        grounding module attribute is sufficient.
        """
        self._orig_grounding = _grounding_mod._VALIDATION_ENABLED
        _grounding_mod._VALIDATION_ENABLED = True

    def tearDown(self):
        _grounding_mod._VALIDATION_ENABLED = self._orig_grounding

    def test_deep_advice_includes_verified_facts_block(self):
        """A deep question should include deterministic facts from the tool."""
        result = send(
            "Why is my budget low?",
            "You are close to your monthly limit. Consider tracking daily expenses.",
            BUDGET,
        )
        # The facts block from _format_fast_verified_read for get_budget_status
        self.assertIn("Remaining:", result["content"])
        self.assertIn("RM100.00", result["content"])
        self.assertIn("Monthly limit:", result["content"])

    def test_deep_advice_preserves_number_free_commentary(self):
        """LLM commentary without numbers should pass through intact."""
        commentary = "You are close to your monthly limit. Consider tracking daily expenses."
        result = send(
            "Why is my budget low?",
            commentary,
            BUDGET,
        )
        # Both the facts block AND the commentary should be present
        self.assertIn("Remaining:", result["content"])
        self.assertIn("Consider tracking daily expenses", result["content"])

    def test_deep_advice_falls_back_gracefully_when_llm_sneaks_number(self):
        """If the LLM writes an unverifiable number, facts block is preserved."""
        result = send(
            "Why should I reduce spending?",
            "Your recorded spending is RM9999.",
            SPENDING,
        )
        # The facts block should be preserved (user sees their real data)
        self.assertIn("RM600.00", result["content"])
        # The invented RM9999 should NOT appear
        self.assertNotIn("9999", result["content"])
        # Model should be grounding-policy (fallback was triggered)
        self.assertEqual(result["model"], "fincoach-grounding-policy")
        # The safe fallback advice should appear
        self.assertIn("Review the data above", result["content"])

    def test_deep_advice_correct_number_from_tool_passes(self):
        """A correct number that IS in the tool result should pass the guard."""
        result = send(
            "Why is my budget low?",
            "Your remaining budget is very low. Consider reducing spending.",
            BUDGET,
        )
        # Should NOT be the grounding fallback
        self.assertNotEqual(result["model"], "fincoach-grounding-policy")
        # Facts block present
        self.assertIn("RM100.00", result["content"])

    def test_simple_read_still_uses_fast_verified_path(self):
        """A simple question (no deep-advice cue) should NOT use two-phase."""
        result = send(
            "Show my budget",
            "ignored — should not reach LLM",
            BUDGET,
        )
        # Fast verified read renders the template directly
        self.assertIn("Remaining:", result["content"])
        # Model should be fincoach-verified-read, not test (LLM not called)
        self.assertEqual(result["model"], "fincoach-verified-read")

    def test_hypothetical_example_in_commentary_passes(self):
        """A clearly labeled hypothetical amount in commentary should pass."""
        result = send(
            "How can I improve my budget?",
            "For example, setting aside a small amount weekly builds discipline.",
            BUDGET,
        )
        # Should NOT be fallback — no RM figure in commentary at all
        self.assertNotEqual(result["model"], "fincoach-grounding-policy")
        self.assertIn("setting aside a small amount", result["content"])


if __name__ == "__main__":
    unittest.main()
