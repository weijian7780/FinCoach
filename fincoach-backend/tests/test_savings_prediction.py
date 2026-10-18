"""Savings forecasts use real tool arithmetic and the complete coaching guard path."""

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.agent_tools import AgentToolExecutor
from app.llm import AgentLLMResult
from app.rag.grounding import normalise_and_validate_numeric_claims
from app.rag.routing import resolve_read_request
from app.rag.service import CoachingService, _verified_tool_context
from tests.test_accuracy_tools import Query, expense


NOW = datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Asia/Kuala_Lumpur"))


def prediction_executor(*, transactions=None, allowance=1200, consent="granted",
                        goals=None, budgets=None, now=NOW):
    """Replace only Supabase I/O; keep ownership, dates, and pagination filters real."""
    tables = {
        "profiles": [{"id": "u", "monthly_allowance": allowance,
                      "spending_records_consent": consent}],
        "transactions": transactions if transactions is not None else [
            expense("food", 300, "Food", "2026-09-10"),
        ],
        "savings_goals": goals or [],
        "monthly_budgets": budgets or [],
        "budgets": [],
    }
    client = MagicMock()
    client.table.side_effect = lambda name: Query(tables.get(name, []))
    return AgentToolExecutor(client, user_id="u", session_id="s", now=lambda: now)


def coach_reply(question, executor, *, generated=None):
    # History persistence and provider calls are external boundaries. The actual
    # router, executor, formatting, numeric guard, and completion payload all run.
    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Savings"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": question}
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    with (
        patch("app.rag.service.AgentToolExecutor", return_value=executor),
        patch("app.rag.service.generate_result", return_value=AgentLLMResult(
            content=generated or "", model="test-provider")),
        patch("app.rag.service.retrieve", return_value=[]),
        patch("app.rag.service.datetime", wraps=datetime) as clock,
        patch("app.rag.service.resolve_read_request", side_effect=lambda *args, **kwargs: resolve_read_request(*args, **{**kwargs, "now": NOW.date()})),
    ):
        # The executor already uses September fixtures; give the real router
        # the same clock so this test does not change meaning each calendar month.
        clock.now.return_value = NOW
        return CoachingService(repo, executor.admin_client).send_message(
            "s", "m", question,
        )["assistant_message"]


class SavingsPredictionRoutingTests(unittest.TestCase):
    def test_prediction_wording_selects_the_savings_tool(self):
        for question in (
            "predict money saving", "Forecast my savings", "Estimate my savings",
            "Why is my savings prediction low?", "How much money can I save?",
        ):
            with self.subTest(question=question):
                self.assertEqual(resolve_read_request(question, []).tool_name, "predict_savings")

    def test_explicit_cashflow_stays_with_the_cashflow_tool(self):
        self.assertEqual(resolve_read_request("Forecast my cash flow", []).tool_name,
                         "get_cashflow_forecast")

    def test_prediction_honours_the_requested_calendar_month(self):
        for question, month in (
            ("Predict my savings next month", "2026-10"),
            ("Predict my savings last month", "2026-08"),
            ("Predict my savings for October 2026", "2026-10"),
            ("Predict my savings from 2026-10-01 to 2026-10-31", "2026-10"),
        ):
            with self.subTest(question=question):
                result = resolve_read_request(question, [], now=date(2026, 9, 15))
                self.assertEqual(result.arguments, {"month": month})

    def test_prediction_followup_changes_the_target_month(self):
        result = resolve_read_request("What about next month?", [
            {"role": "user", "content": "How much can I save this month?"},
        ], now=date(2026, 9, 15))
        self.assertEqual(result.tool_name, "predict_savings")
        self.assertEqual(result.arguments, {"month": "2026-10"})

    def test_partial_month_is_not_silently_treated_as_a_full_month(self):
        result = resolve_read_request(
            "Predict my savings from 2026-10-05 to 2026-10-15", [], now=date(2026, 9, 15),
        )
        self.assertIsNotNone(result.clarification)


class SavingsPredictionToolTests(unittest.TestCase):
    def test_projection_excludes_other_users_and_future_dated_expenses(self):
        executor = prediction_executor(transactions=[
            expense("food", 300, "Food", "2026-09-10"),
            expense("future", 500, "Food", "2026-09-20"),
            expense("private", 9999, "Food", "2026-09-10", owner="someone-else"),
        ])
        result = executor.execute("predict_savings", {"month": "2026-09"})
        self.assertEqual(result["recorded_expenses"], "RM300.00")
        self.assertEqual(result["projected_month_spending"], "RM600.00")
        self.assertEqual(result["projected_saveable"], "RM600.00")

    def test_recorded_income_is_not_added_to_the_same_monthly_allowance(self):
        income = expense("income", 1500, "Income", "2026-09-01")
        income["category"]["type"] = "income"
        result = prediction_executor(transactions=[
            income, expense("food", 300, "Food", "2026-09-10"),
        ]).execute("predict_savings", {"month": "2026-09"})
        self.assertEqual(result["income"], "RM1500.00")
        self.assertEqual(result["projected_saveable"], "RM900.00")

    def test_unfinished_goals_are_destinations_for_savings_not_immediate_expenses(self):
        result = prediction_executor(goals=[{
            "user_id": "u", "name": "Laptop", "target_amount": 10000,
            "current_amount": 500, "deadline": "2027-09-01", "created_at": "2026-01-01",
        }]).execute("predict_savings", {"month": "2026-09"})
        self.assertEqual(result["projected_saveable"], "RM600.00")
        self.assertEqual(result["goal_details"][0]["remaining_to_goal"], "RM9500.00")

    def test_future_month_uses_observed_spending_instead_of_empty_future_records(self):
        result = prediction_executor().execute("predict_savings", {"month": "2026-10"})
        self.assertEqual(result["month"], "2026-10-01")
        self.assertEqual(result["projected_month_spending"], "RM620.00")
        self.assertEqual(result["projected_saveable"], "RM580.00")

    def test_empty_current_month_uses_previous_month_history(self):
        result = prediction_executor(transactions=[
            expense("august", 310, "Food", "2026-08-10"),
        ]).execute("predict_savings", {"month": "2026-09"})
        self.assertEqual(result["projected_month_spending"], "RM300.00")
        self.assertEqual(result["projected_saveable"], "RM900.00")

    def test_no_spending_history_uses_an_explicit_budget_scenario(self):
        result = prediction_executor(transactions=[], budgets=[{
            "user_id": "u", "month": "2026-09-01", "limit_amount": 700,
        }]).execute("predict_savings", {"month": "2026-09"})
        self.assertEqual(result["projected_month_spending"], "RM700.00")
        self.assertEqual(result["projected_saveable"], "RM500.00")
        self.assertEqual(result.get("projection_basis"), "monthly_budget")

    def test_missing_income_is_not_replaced_with_zero(self):
        result = prediction_executor(allowance=None).execute("predict_savings", {})
        self.assertEqual(result["status"], "needs_data")
        self.assertIn("income", result["missing_fields"])
        self.assertIn("allowance", result["message"].lower())

    def test_missing_expenses_and_budget_are_not_evidence_of_zero_spending(self):
        result = prediction_executor(transactions=[]).execute("predict_savings", {})
        self.assertEqual(result["status"], "needs_data")
        self.assertIn("spending", result["missing_fields"])

    def test_explicit_zero_income_is_known_and_deficit_is_not_negative_savings(self):
        result = prediction_executor(allowance=0).execute("predict_savings", {})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["projected_remaining"], "RM-600.00")
        self.assertEqual(result["projected_saveable"], "RM0.00")

    def test_spending_access_is_required(self):
        result = prediction_executor(consent="denied").execute("predict_savings", {})
        self.assertEqual(result["status"], "permission_required")
        self.assertNotIn("projected_saveable", result)


from app.rag import grounding as _grounding_mod

_SAVED_VALIDATION_FLAG = _grounding_mod._VALIDATION_ENABLED


def setUpModule():
    # These tests exercise guard #2 (the numeric claim path), which is behind
    # the COACH_ANSWER_VALIDATION kill switch (default off in production).
    # service.py reads grounding._VALIDATION_ENABLED live, so flipping the
    # module attribute is sufficient.
    _grounding_mod._VALIDATION_ENABLED = True


def tearDownModule():
    _grounding_mod._VALIDATION_ENABLED = _SAVED_VALIDATION_FLAG


class SavingsPredictionReplyTests(unittest.TestCase):
    def test_exact_reported_question_returns_the_calculated_prediction(self):
        reply = coach_reply("predict money saving", prediction_executor())
        self.assertIn("RM600.00", reply["content"])
        self.assertIn("15 days", reply["content"])
        self.assertIn("estimate", reply["content"].lower())
        self.assertNotIn("could not verify", reply["content"])

    def test_next_month_answer_names_the_target_and_the_observed_period(self):
        reply = coach_reply("Predict my savings for October 2026", prediction_executor())
        self.assertIn("RM580.00", reply["content"])
        self.assertIn("2026-10", reply["content"])
        self.assertIn("2026-09", reply["content"])

    def test_unverified_model_amount_recovers_using_the_existing_prediction(self):
        reply = coach_reply("Why can I save so little this month?", prediction_executor(),
                            generated="Your estimated savings are RM9999.00.")
        self.assertIn("RM600.00", reply["content"])
        self.assertNotIn("9999", reply["content"])
        self.assertNotIn("Please ask for a verified", reply["content"])

    def test_invented_duration_cannot_pass_using_an_unrelated_tool_number(self):
        reply = coach_reply("Why can I save so little this month?", prediction_executor(),
                            generated="Your savings estimate uses 99 days of spending.")
        self.assertIn("RM600.00", reply["content"])
        self.assertNotIn("99 days", reply["content"])

    def test_valid_model_projection_with_calculation_remains_usable(self):
        content = ("Estimated savings: RM600.00.\n"
                   "Calculation: RM1200.00 - RM600.00 = RM600.00\n"
                   "This estimate uses 15 days of recorded expenses.")
        reply = coach_reply("Why can I save so little this month?", prediction_executor(), generated=content)
        # Deep advice includes a deterministic facts block before valid model
        # commentary. Check that both survive numeric grounding.
        self.assertIn("For 2026-09, estimated savings: **RM600.00**.", reply["content"])
        self.assertTrue(reply["content"].endswith("\n\n" + content))
        self.assertEqual(reply["model"], "test-provider")

    def test_deficit_answer_explains_shortfall_instead_of_promising_savings(self):
        reply = coach_reply("predict money saving", prediction_executor(allowance=200))
        self.assertIn("shortfall", reply["content"].lower())
        self.assertIn("RM400.00", reply["content"])
        self.assertNotIn("could not verify", reply["content"])

    def test_missing_income_asks_only_for_the_missing_input(self):
        reply = coach_reply("predict money saving", prediction_executor(allowance=None))
        self.assertIn("allowance", reply["content"].lower())
        self.assertNotIn("RM0", reply["content"])
        self.assertNotIn("verified budget", reply["content"])


class PredictionNumericEvidenceTests(unittest.TestCase):
    def test_typed_day_fields_support_duration_claims_without_whitelisting_any_number(self):
        tool_result = prediction_executor().execute("predict_savings", {})
        result = AgentLLMResult(content="", model="test", tool_results=(
            {"name": "predict_savings", "result": tool_result},
        ))
        evidence = _verified_tool_context(result)
        self.assertEqual(normalise_and_validate_numeric_claims("Based on 15 days.", evidence),
                         "Based on 15 days.")
        self.assertIsNone(normalise_and_validate_numeric_claims("Based on 600 days.", evidence))

    def test_singular_plural_and_malay_duration_units_match(self):
        for text in ("Based on 1 day.", "Based on 1 days.", "Berdasarkan 1 hari."):
            with self.subTest(text=text):
                self.assertEqual(normalise_and_validate_numeric_claims(text, "1 days"), text)

    def test_a_negative_amount_still_requires_evidence(self):
        self.assertIsNone(normalise_and_validate_numeric_claims(
            "Your estimated remaining funds are RM-9999.00.", "RM1200.00 RM600.00",
        ))

    def test_verified_arithmetic_allows_a_derived_amount(self):
        text = "Calculation: RM1200.00 - RM650.00 = RM550.00"
        self.assertEqual(normalise_and_validate_numeric_claims(text, "RM1200.00 RM650.00"), text)

    def test_arithmetic_does_not_ignore_the_operator_or_unknown_inputs(self):
        for text in (
            "Calculation: RM1200.00 + RM650.00 = RM550.00",
            "Calculation: RM1200.00 - RM100.00 = RM1100.00",
            "Calculation: RM1200.00 * RM650.00 = RM1850.00",
        ):
            with self.subTest(text=text):
                self.assertIsNone(normalise_and_validate_numeric_claims(text, "RM1200.00 RM650.00"))


if __name__ == "__main__":
    unittest.main()
