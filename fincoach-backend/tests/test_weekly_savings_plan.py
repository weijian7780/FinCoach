"""Weekly plans exercise routing, real financial reads, arithmetic and reply guards."""

import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.rag import grounding
from app.rag.routing import resolve_read_request
from tests.test_savings_prediction import coach_reply, prediction_executor


NOW = datetime(2026, 9, 21, 12, tzinfo=ZoneInfo("Asia/Kuala_Lumpur"))
QUESTION = "Make me a weekly saving plan"


def goal(**changes):
    return {"id": 1, "user_id": "u", "name": "saga car", "target_amount": 46000,
            "current_amount": 600, "deadline": "2026-09-30",
            "created_at": "2026-09-01", **changes}


def executor(**changes):
    return prediction_executor(now=NOW, goals=[goal()], **changes)


class WeeklySavingsPlanTests(unittest.TestCase):
    def test_weekly_requests_select_planning_instead_of_goal_lookup(self):
        for question in (QUESTION, "Make me a weekly savings plan", "Plan my savings weekly",
                         "How much can I save each week?", "Pelan simpanan mingguan saya"):
            with self.subTest(question=question):
                resolved = resolve_read_request(question, [], now=NOW)
                self.assertEqual(resolved.tool_name, "get_weekly_savings_plan")
                self.assertIsNone(resolved.clarification)
        self.assertEqual(resolve_read_request("Show my savings goals", []).tool_name,
                         "get_savings_goals")
        self.assertIsNone(resolve_read_request("What is a savings plan?", []).tool_name)

    def test_plan_month_and_followup_are_preserved(self):
        first = resolve_read_request(QUESTION + " for October 2026", [], now=NOW)
        self.assertEqual(first.arguments, {"month": "2026-10"})
        followup = resolve_read_request("What about next month?", [
            {"role": "user", "content": QUESTION},
        ], now=NOW)
        self.assertEqual(followup.tool_name, "get_weekly_savings_plan")
        self.assertEqual(followup.arguments, {"month": "2026-10"})

    def test_reads_current_owner_records_and_calculates_shared_schedule(self):
        tools = prediction_executor(now=NOW, goals=[goal(), goal(user_id="other", name="private")])
        plan = tools.execute("get_weekly_savings_plan", {})
        self.assertEqual(plan["status"], "ok")
        self.assertEqual(plan["forecast"]["income"], "RM1200.00")
        self.assertEqual(plan["forecast"]["recorded_expenses"], "RM300.00")
        # 300 / 21 * 30 = 428.57 spending; 771.43 / 30 * 7 = 180.00 weekly.
        self.assertEqual(plan["weekly_saveable"], "RM180.00")
        self.assertEqual(plan["schedule"], [
            {"date": "2026-09-28", "amount": "RM180.00"},
            {"date": "2026-09-30", "amount": "RM51.42"},
        ])
        self.assertEqual(len(plan["goals"]), 1)
        saved = plan["goals"][0]
        self.assertEqual(saved["current_amount"], "RM600.00")
        self.assertEqual(saved["remaining_to_goal"], "RM45400.00")
        self.assertEqual(saved["contributions_remaining"], 2)
        self.assertEqual(saved["required_per_contribution"], "RM22700.00")
        self.assertTrue(saved["exceeds_estimated_pace"])
        self.assertTrue({"profiles", "transactions", "savings_goals"}.issubset(
            {call.args[0] for call in tools.admin_client.table.call_args_list}))

    def test_full_reply_cannot_repeat_false_missing_data_or_fake_goal_progress(self):
        for validation_enabled in (False, True):
            with self.subTest(validation_enabled=validation_enabled), patch.object(
                grounding, "_VALIDATION_ENABLED", validation_enabled
            ):
                reply = coach_reply(QUESTION, executor(), generated=(
                    "Without verified income or spending data, I cannot calculate a weekly amount. "
                    "You have RM0.00 saved [get_savings_goals]."
                ))
                self.assertEqual(reply["model"], "fincoach-verified-read")
                for expected in ("RM1200.00", "RM300.00", "RM600.00", "RM22700.00",
                                 "RM180.00", "2026-09-28", "2026-09-30"):
                    self.assertIn(expected, reply["content"])
                self.assertNotIn("Without verified", reply["content"])
                self.assertNotIn("[get_savings_goals]", reply["content"])
                self.assertIn("shared", reply["content"].lower())
                self.assertIn("deadline", reply["content"].lower())

    def test_missing_income_keeps_goal_requirement_without_inventing_affordability(self):
        plan = executor(allowance=None).execute("get_weekly_savings_plan", {})
        self.assertIsNone(plan["weekly_saveable"])
        self.assertEqual(plan["forecast"]["missing_fields"], ["income"])
        self.assertEqual(plan["goals"][0]["required_per_contribution"], "RM22700.00")
        reply = coach_reply(QUESTION, executor(allowance=None))
        self.assertIn("RM22700.00", reply["content"])
        self.assertIn("allowance", reply["content"].lower())
        self.assertNotIn("RM0.00", reply["content"])

    def test_consent_stops_spending_reads_and_planning(self):
        tools = executor(consent="denied")
        plan = tools.execute("get_weekly_savings_plan", {})
        self.assertEqual(plan["status"], "permission_required")
        self.assertNotIn("transactions", [call.args[0] for call in tools.admin_client.table.call_args_list])

    def test_deficit_never_recommends_funding_goals(self):
        reply = coach_reply(QUESTION, executor(allowance=200))
        self.assertIn("shortfall", reply["content"].lower())
        self.assertIn("No surplus", reply["content"])
        self.assertNotIn("2026-09-28:", reply["content"])

    def test_deadline_edge_cases_do_not_divide_by_zero_or_fabricate_dates(self):
        for changes, expected in (({"deadline": None}, "no_deadline"),
                                  ({"deadline": "2026-09-20"}, "overdue"),
                                  ({"deadline": "2026-09-21"}, "due_today"),
                                  ({"current_amount": 46000}, "completed")):
            with self.subTest(changes=changes):
                plan = prediction_executor(now=NOW, goals=[goal(**changes)]).execute(
                    "get_weekly_savings_plan", {})
                self.assertEqual(plan["goals"][0]["status"], expected)
                self.assertIsNone(plan["goals"][0]["required_per_contribution"])

    def test_goal_requirements_round_up_but_final_payment_is_capped(self):
        plan = prediction_executor(now=NOW, goals=[goal(target_amount=100, current_amount=0,
                                                      deadline="2026-10-06")]).execute(
            "get_weekly_savings_plan", {})
        self.assertEqual(plan["goals"][0]["required_per_contribution"], "RM33.34")
        self.assertEqual(plan["goals"][0]["final_contribution"], "RM33.32")

        tiny = prediction_executor(now=NOW, goals=[goal(target_amount=100, current_amount=99.99,
                                                      deadline="2027-09-21")]).execute(
            "get_weekly_savings_plan", {})["goals"][0]
        self.assertEqual(tiny["contributions_remaining"], 1)
        self.assertEqual(tiny["final_contribution"], "RM0.01")

    def test_missing_spending_does_not_assume_zero_and_budget_fallback_is_labelled(self):
        missing = executor(transactions=[]).execute("get_weekly_savings_plan", {})
        self.assertIsNone(missing["weekly_saveable"])
        self.assertEqual(missing["forecast"]["missing_fields"], ["spending"])
        reply = coach_reply(QUESTION, executor(transactions=[], budgets=[{
            "user_id": "u", "month": "2026-09-01", "limit_amount": 700,
        }]))
        self.assertIn("budget-based estimate", reply["content"])
        self.assertIn("RM116.66", reply["content"])

    def test_future_month_has_a_full_schedule_and_past_plans_are_rejected(self):
        tools = executor()
        future = tools.execute("get_weekly_savings_plan", {"month": "2026-10"})
        self.assertEqual([entry["date"] for entry in future["schedule"]],
                         ["2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28", "2026-10-31"])
        self.assertEqual(tools.execute("get_weekly_savings_plan", {"month": "2026-08"})["status"],
                         "needs_clarification")


if __name__ == "__main__":
    unittest.main()
