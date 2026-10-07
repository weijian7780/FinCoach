"""Regression seams use real filtering/pagination rather than no-op query mocks."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_tools import AgentToolExecutor


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.orders = []
        self.start, self.stop = 0, None

    def select(self, *_args): return self
    def maybe_single(self): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self
    def is_(self, key, value):
        self.filters.append(lambda row: row.get(key) is None)
        return self
    def gte(self, key, value):
        self.filters.append(lambda row: row[key] >= value)
        return self
    def lte(self, key, value):
        self.filters.append(lambda row: row[key] <= value)
        return self
    def order(self, key, desc=False):
        self.orders.append((key, desc))
        return self
    def limit(self, count):
        self.stop = count
        return self
    def range(self, start, end):
        self.start, self.stop = start, end + 1
        return self
    def execute(self):
        if isinstance(self.rows, dict): return SimpleNamespace(data=self.rows)
        rows = [row for row in self.rows if all(test(row) for test in self.filters)]
        for key, desc in reversed(self.orders):
            rows.sort(key=lambda row: row[key], reverse=desc)
        return SimpleNamespace(data=rows[self.start:self.stop])


def expense(id, amount, category, day="2026-03-10", owner="u"):
    return {"id": str(id), "amount": amount, "transaction_date": day,
            "user_id": owner, "category": {"name": category, "type": "expense"}}


def executor(rows, limits=None):
    tables = {
        "transactions": rows,
        "categories": [{"name": "Food", "user_id": None}, {"name": "Rent", "user_id": None}],
        "profiles": {"spending_records_consent": "granted"},
        "monthly_budgets": {"limit_amount": 1000},
        "budgets": limits or [],
    }
    client = MagicMock()
    client.table.side_effect = lambda name: Query(tables.get(name, []))
    return AgentToolExecutor(client, user_id="u", session_id="s",
                             now=lambda: datetime(2026, 3, 20, tzinfo=timezone.utc))


class AccuracyToolsTests(unittest.TestCase):
    def test_summary_and_search_include_matching_records_beyond_first_page(self):
        rows = [expense(i, 1, "Food") for i in range(500)]
        rows += [expense("rent", 900, "Rent", "2026-03-01"),
                 expense("foreign", 9999, "Rent", owner="other")]
        tools = executor(rows)
        summary = tools.execute("get_spending_summary", {})
        self.assertEqual(summary["expense_total"], "RM1400.00")
        self.assertEqual(summary["expense_count"], 501)
        rent = tools.execute("get_spending_summary", {"category_name": "Rent"})
        self.assertEqual(rent["expense_total"], "RM900.00")
        found = tools.execute("search_transactions", {"category_name": "Rent"})
        self.assertEqual([row["id"] for row in found["transactions"]], ["rent"])

    def test_overall_remaining_is_independent_of_category_filter(self):
        tools = executor([expense("a", 100, "Food"), expense("b", 800, "Rent")],
                         [{"user_id": "u", "month": "2026-03-01", "amount": 200,
                           "category": {"name": "Food"}}])
        result = tools.execute("get_budget_status", {"category_name": "Food"})
        self.assertEqual(result["remaining"], "RM100.00")
        self.assertEqual(result["recorded_spending"], "RM900.00")
        self.assertEqual(result["selected_category"]["remaining"], "RM100.00")
        self.assertEqual(result["selected_category"]["recorded_spending"], "RM100.00")

    def test_category_without_limit_keeps_category_scope(self):
        result = executor([expense("a", 100, "Food"), expense("b", 800, "Rent")]).execute(
            "get_budget_status", {"category_name": "Food"})
        self.assertEqual(result["selected_category"]["recorded_spending"], "RM100.00")
        self.assertIsNone(result["selected_category"]["limit"])
        self.assertEqual(result["remaining"], "RM100.00")

    def test_unknown_category_is_not_presented_as_zero(self):
        result = executor([]).execute("get_spending_summary", {"category_name": "Foood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("expense_total", result)

    def test_calendar_comparison_excludes_tail_of_january(self):
        tools = executor([expense("jan", 900, "Rent", "2026-01-30"),
                          expense("feb", 100, "Food", "2026-02-05"),
                          expense("mar", 150, "Food", "2026-03-05")])
        result = tools.execute("get_spending_summary", {
            "start_date": "2026-03-01", "end_date": "2026-03-31", "compare_previous_period": True})
        self.assertEqual(result["comparison"]["previous_start"], "2026-02-01")
        self.assertEqual(result["comparison"]["previous_total"], "RM100.00")
        self.assertEqual(result["comparison"]["difference"], "RM50.00")

    def test_partial_period_comparison_keeps_equal_length(self):
        result = executor([]).execute("get_spending_summary", {
            "start_date": "2026-03-10", "end_date": "2026-03-15", "compare_previous_period": True})
        self.assertEqual(result["comparison"]["previous_start"], "2026-03-04")
        self.assertEqual(result["comparison"]["previous_end"], "2026-03-09")

    def test_leap_year_and_january_comparisons(self):
        for start, end, previous in [("2024-03-01", "2024-03-31", "2024-02-01"),
                                      ("2026-01-01", "2026-01-31", "2025-12-01")]:
            with self.subTest(start=start):
                result = executor([]).execute("get_spending_summary", {
                    "start_date": start, "end_date": end, "compare_previous_period": True})
                self.assertEqual(result["comparison"]["previous_start"], previous)
