import unittest
from datetime import date
from app.rag.routing import resolve_read_request


class AccuracyRoutingTests(unittest.TestCase):
    def resolve(self, text, history=None):
        return resolve_read_request(text, history or [], now=date(2026, 8, 20))

    def test_common_period_and_category_filters(self):
        cases = [
            ("How much did I spend on Food this month?", {"start_date": "2026-08-01", "end_date": "2026-08-31", "category_name": "Food"}),
            ("Show my transactions yesterday", {"start_date": "2026-08-19", "end_date": "2026-08-19"}),
            ("Show my spending from 2026-07-01 to 2026-07-15", {"start_date": "2026-07-01", "end_date": "2026-07-15"}),
            ("Plan my next month budget", {"month": "2026-09"}),
            ("Show my budget in July", {"month": "2026-07"}),
            # No period given -> the current Malaysia month is materialised as the
            # default (provenance "default"), so the answer can state the period.
            ("May I see my spending?", {"start_date": "2026-08-01", "end_date": "2026-08-31"}),
            ("Berapa saya belanja untuk Makanan semalam?", {"start_date": "2026-08-19", "end_date": "2026-08-19", "category_name": "Makanan"}),
        ]
        for question, expected in cases:
            with self.subTest(question=question):
                self.assertEqual(self.resolve(question).arguments, expected)

    def test_chained_followups_retain_category_and_tool(self):
        history = []
        for question in ["Show my spending in June", "Only food", "What about July?"]:
            result = self.resolve(question, history)
            history.append({"role": "user", "content": question})
        self.assertEqual(result.tool_name, "get_spending_summary")
        self.assertEqual(result.arguments, {"start_date": "2026-07-01", "end_date": "2026-07-31", "category_name": "Food"})
        budget = self.resolve("What about last month?", [{"role": "user", "content": "Show my budget this month"}])
        self.assertEqual(budget.tool_name, "get_budget_status")
        self.assertEqual(budget.arguments["month"], "2026-07")

    def test_invalid_or_unsupported_period_is_not_silently_defaulted(self):
        for question in ["Show spending from 2026-02-30 to 2026-03-05", "Show spending from 2026-08-20 to 2026-08-01", "Show my spending last fortnight"]:
            with self.subTest(question=question):
                self.assertIsNotNone(self.resolve(question).clarification)

    def test_explicit_topic_switch_drops_old_category(self):
        result = self.resolve("Show my budget this month", [{"role": "user", "content": "Show spending only Food"}])
        self.assertEqual(result.tool_name, "get_budget_status")
        self.assertNotIn("category_name", result.arguments)

    def test_casual_and_education_do_not_inherit_personal_filters(self):
        history = [{"role": "user", "content": "Show spending only Food"}]
        self.assertIsNone(self.resolve("What about PTPTN?", history).tool_name)
        self.assertIsNone(self.resolve("Thanks", history).tool_name)

    def test_savings_topic_change_does_not_inherit_food_spending(self):
        result = self.resolve("What about my savings?", [
            {"role": "user", "content": "Show my spending on Food"},
        ])
        self.assertFalse(result.inherited)
        self.assertIsNone(result.tool_name)
        self.assertNotIn("category_name", result.arguments)
        self.assertIsNotNone(result.clarification)

    def test_unresolved_transaction_reference_requires_clarification(self):
        result = self.resolve("Show me that transaction")
        self.assertIsNotNone(result.clarification)

    def test_malay_savings_topic_change_requires_clarification(self):
        result = self.resolve("Macam mana dengan simpanan saya?", [
            {"role": "user", "content": "Show my spending on Food"},
        ])
        self.assertFalse(result.inherited)
        self.assertIsNone(result.tool_name)
        self.assertNotIn("category_name", result.arguments)
        self.assertIsNotNone(result.clarification)

    def test_malay_unresolved_transaction_reference_requires_clarification(self):
        result = self.resolve("Tunjuk transaksi itu")
        self.assertIsNotNone(result.clarification)

    def test_same_intent_month_and_category_continuation_still_resolves(self):
        history = []
        for question in ["Show my spending on Food in June", "What about July?"]:
            result = self.resolve(question, history)
            history.append({"role": "user", "content": question})
        self.assertTrue(result.inherited)
        self.assertEqual(result.tool_name, "get_spending_summary")
        self.assertEqual(
            result.arguments,
            {"start_date": "2026-07-01", "end_date": "2026-07-31", "category_name": "Food"},
        )
        self.assertIsNone(result.clarification)
