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

    def test_exact_rm_amount_is_parsed_as_a_complete_token(self):
        for query, expected in [
            ("Show transactions for RM1,000", "1000.00"),
            ("Show transactions for RM1,000.25", "1000.25"),
            ("Show transactions for RM25.50", "25.50"),
        ]:
            with self.subTest(query=query):
                result = self.resolve(query)
                self.assertEqual(result.tool_name, "search_transactions")
                self.assertEqual(result.readiness.value, "ready")
                self.assertEqual(result.arguments["amount"], expected)
                self.assertNotIn("category_name", result.arguments)

    def test_malformed_rm_amount_requires_clarification(self):
        for query in [
            "Show transactions for RM25.999",
            "Show transactions for RM1,00",
            "Show transactions for RM25 and RM30",
            # A magnitude suffix (25k) and a signed amount (RM-25) are recognised
            # money tokens the exact-match filter does not support: clarify rather
            # than truncate to RM25 or leak the token into the category filter.
            "Show transactions for RM25k",
            "Show transactions for RM-25",
        ]:
            with self.subTest(query=query):
                result = self.resolve(query)
                self.assertEqual(result.tool_name, "search_transactions")
                self.assertEqual(result.readiness.value, "needs_clarification")
                self.assertEqual(result.invalid_fields, ("amount",))
                self.assertNotIn("amount", result.arguments)

    def test_named_day_ranges_preserve_both_boundaries(self):
        for query, start, end in [
            ("Show spending from 1 July to 15 July 2026", "2026-07-01", "2026-07-15"),
            ("Show spending between 1 July and 15 July 2026", "2026-07-01", "2026-07-15"),
            ("Show spending from July 1 to July 15, 2026", "2026-07-01", "2026-07-15"),
            ("Show spending on 15 July 2026", "2026-07-15", "2026-07-15"),
        ]:
            with self.subTest(query=query):
                result = self.resolve(query)
                self.assertEqual(result.tool_name, "get_spending_summary")
                self.assertEqual(result.readiness.value, "ready")
                self.assertEqual(result.arguments["start_date"], start)
                self.assertEqual(result.arguments["end_date"], end)

    def test_invalid_named_day_range_requires_clarification(self):
        for query in [
            "Show spending from 31 February to 2 March 2026",
            "Show spending from 15 July to 1 July 2026",
            "Show spending from July 1-15, 2026",
        ]:
            with self.subTest(query=query):
                result = self.resolve(query)
                self.assertEqual(result.readiness.value, "needs_clarification")
                self.assertEqual(result.invalid_fields, ("start_date", "end_date"))

    def test_numeric_merchant_and_relative_date_are_distinct_filters(self):
        numeric = self.resolve("Show transactions at 7-Eleven")
        self.assertEqual(numeric.tool_name, "search_transactions")
        self.assertEqual(numeric.arguments.get("text"), "7-Eleven")
        named = self.resolve("Show transactions at In-N-Out")
        self.assertEqual(named.arguments.get("text"), "In-N-Out")
        relative = self.resolve("Transactions from yesterday")
        self.assertEqual(relative.tool_name, "search_transactions")
        self.assertEqual(relative.arguments["start_date"], "2026-08-19")
        self.assertEqual(relative.arguments["end_date"], "2026-08-19")
        self.assertNotIn("text", relative.arguments)

    def test_malay_count_and_merchant_total_keep_the_merchant(self):
        count = self.resolve("berapa banyak transaksi di Grab bulan ini")
        self.assertEqual(count.tool_name, "search_transactions")
        self.assertEqual(count.arguments["result_mode"], "count")
        self.assertEqual(count.arguments["text"], "Grab")
        self.assertEqual(count.arguments["start_date"], "2026-08-01")
        total = self.resolve("berapa saya belanja di Grab bulan ini")
        self.assertEqual(total.tool_name, "search_transactions")
        self.assertEqual(total.arguments["result_mode"], "expense_total")
        self.assertEqual(total.arguments["text"], "Grab")

    def test_income_transaction_type_is_preserved(self):
        income = self.resolve("Show income transactions at Grab")
        self.assertEqual(income.tool_name, "search_transactions")
        self.assertEqual(income.arguments["transaction_type"], "income")
        self.assertEqual(income.arguments["text"], "Grab")
        self.assertNotIn("category_name", income.arguments)
        expense = self.resolve("Show expense transactions at Grab")
        self.assertEqual(expense.arguments["transaction_type"], "expense")

    def test_unsupported_transaction_constraints_clarify(self):
        for query in [
            "Show my first 5 transactions",
            "First 5 transactions",
            "Show transactions not Food",
            "Show transactions excluding Food",
            "Show transactions at Grab and Foodpanda",
            # A second "at <merchant>" is still two merchants, even without a
            # joining "and": keep both or clarify, never silently drop one.
            "Show transactions at Grab at Foodpanda",
        ]:
            with self.subTest(query=query):
                result = self.resolve(query)
                self.assertEqual(result.tool_name, "search_transactions")
                self.assertEqual(result.readiness.value, "needs_clarification")
                self.assertEqual(result.invalid_fields, ("transaction_filter",))
                self.assertEqual(result.arguments, {})

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

    def test_food_spend_shorthand_routes_to_spending_summary_with_category(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        self.assertEqual(route_coach_message("food spend"), CoachingRoute.PERSONAL_FINANCE)
        result = self.resolve("food spend")
        self.assertEqual(result.tool_name, "get_spending_summary")
        self.assertEqual(result.arguments.get("category_name"), "Food")

    def test_hyphenated_savings_goal_routes_to_savings_goals(self):
        result = self.resolve("Show my savings-goal")
        self.assertEqual(result.tool_name, "get_savings_goals")

    def test_which_category_spending_ranking_has_no_category_filter(self):
        result = self.resolve("Which category am I spending the most on?")
        self.assertEqual(result.tool_name, "get_spending_summary")
        self.assertIsNone(result.arguments.get("category_name"))
        self.assertIsNone(result.clarification)

    def test_negative_spend_time_routes_to_casual(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        self.assertEqual(route_coach_message("I spend time with my friends"), CoachingRoute.CASUAL)
        self.assertEqual(route_coach_message("spend hours on homework"), CoachingRoute.CASUAL)
