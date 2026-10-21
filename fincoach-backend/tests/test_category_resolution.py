"""Shared category resolver: pure resolution plus executor integration."""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.category_resolution import resolve_category_phrase

NAMES = ["Food", "Public Transport", "Transport", "Entertainment", "Groceries"]


class PureResolverTests(unittest.TestCase):
    def test_trailing_phrase_resolves_full_name(self):
        res = resolve_category_phrase("Food spending July and August", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Food")

    def test_leading_on_phrase_resolves(self):
        res = resolve_category_phrase("spending on Food across July to September", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Food")

    def test_prefers_longest_complete_name(self):
        res = resolve_category_phrase("Public Transport spending July and August", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Public Transport")

    def test_shorter_name_when_only_it_appears(self):
        res = resolve_category_phrase("Transport spending in July", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Transport")

    def test_budget_metric_phrase_resolves(self):
        res = resolve_category_phrase("Food budget July and August", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Food")

    def test_category_before_budget_with_month_resolves(self):
        # "Show my September food budget" — the month must not be read as part of
        # the category, and the category word order (before "budget") still wins.
        res = resolve_category_phrase("Show my September food budget", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Food")

    def test_no_category_requested_is_none(self):
        for message in (
            "Show my budget breakdown",
            "Compare July, August and September",
            "Compare the last three months",
            "How am I doing this month?",
            "am i over budget",
            "am i under budget",
            "am i within budget",
        ):
            res = resolve_category_phrase(message, NAMES)
            self.assertEqual(res.status, "none", message)

    def test_unknown_unmarked_phrase_needs_interpretation_with_suggestion(self):
        # An unfamiliar phrase in a bare category slot is "might be a category":
        # it goes to interpretation (which clarifies when disabled), and still
        # carries a close-match suggestion.
        res = resolve_category_phrase("Foood spending July and August", NAMES)
        self.assertEqual(res.status, "needs_interpretation")
        self.assertEqual(res.suggestion, "Food")

    def test_unknown_unmarked_phrase_without_close_match(self):
        res = resolve_category_phrase("spending on Yachts in July", NAMES)
        self.assertEqual(res.status, "needs_interpretation")
        self.assertIsNone(res.suggestion)

    def test_explicit_unknown_category_is_unresolved(self):
        # An EXPLICIT marker names a category deliberately, so an unknown one is
        # unresolved (clarify), never interpreted.
        res = resolve_category_phrase("spending for category Foood", NAMES)
        self.assertEqual(res.status, "unresolved")
        self.assertEqual(res.suggestion, "Food")

    def test_empty_available_names(self):
        self.assertEqual(
            resolve_category_phrase("Food spending", []).status, "needs_interpretation"
        )

    def test_ranking_queries_bypass_slot_extraction(self):
        for message in (
            "Which category am I spending the most on?",
            "What category do I spend the most on?",
            "Top spending category",
            "Which category has the highest spending?",
        ):
            res = resolve_category_phrase(message, NAMES)
            self.assertEqual(res.status, "none", f"Failed for {message}: status={res.status}, requested={res.requested}")

    def test_hyphenated_category_name_resolves(self):
        names = ["Take-away", "Fast-food", "Groceries"]
        res = resolve_category_phrase("Take-away spending", names)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Take-away")

    def test_iso_date_preserves_category_resolution(self):
        res = resolve_category_phrase("spending from 2026-07-01 to 2026-07-15 on Food", NAMES)
        self.assertEqual(res.status, "resolved")
        self.assertEqual(res.category, "Food")


class DateAwareQuery:
    def __init__(self, rows):
        self.rows = rows
        self._month = None
        self._date_filters = []
        self._single = False
        self._range = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        if column == "month":
            self._month = value
        return self

    def is_(self, *_a, **_k):
        return self

    def gte(self, column, value):
        if column == "transaction_date":
            self._date_filters.append(("gte", value))
        return self

    def lte(self, column, value):
        if column == "transaction_date":
            self._date_filters.append(("lte", value))
        return self

    def lt(self, column, value):
        if column == "transaction_date":
            self._date_filters.append(("lt", value))
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def maybe_single(self):
        self._single = True
        return self

    def _match(self, row):
        if self._month is not None and "month" in row and row.get("month") != self._month:
            return False
        value = row.get("transaction_date")
        for kind, bound in self._date_filters:
            if value is None:
                return False
            if kind == "gte" and not value >= bound:
                return False
            if kind == "lte" and not value <= bound:
                return False
            if kind == "lt" and not value < bound:
                return False
        return True

    def execute(self):
        rows = [row for row in self.rows if self._match(row)]
        if self._range is not None:
            rows = rows[self._range[0]:self._range[1] + 1]
        data = (rows[0] if rows else None) if self._single else rows
        return SimpleNamespace(data=data, error=None)


def _expense(day, amount, category):
    return {
        "id": f"{category}-{day}-{amount}",
        "amount": amount,
        "transaction_date": day,
        "category": {"name": category, "type": "expense"},
    }


class ExecutorCategoryIntegrationTests(unittest.TestCase):
    def test_shorthand_and_ranking_reach_correct_verified_totals(self):
        from datetime import date
        from app.rag.routing import resolve_read_request

        rows = [
            _expense("2026-09-05", 100, "Food"),
            _expense("2026-09-06", 250, "Public Transport"),
        ]
        for question, total, highest in (
            ("show me food spend", "RM100.00", "Food"),
            ("Which category am I spending the most on?", "RM350.00", "Public Transport"),
            ("Which category costs most?", "RM350.00", "Public Transport"),
            ("monthly spending", "RM350.00", "Public Transport"),
        ):
            with self.subTest(question=question):
                request = resolve_read_request(question, [], now=date(2026, 9, 22))
                executor = self.make_executor(question, rows)
                result = executor.execute(request.tool_name, request.arguments)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["expense_total"], total)
                self.assertEqual(result["categories"][0]["name"], highest)

    def make_executor(self, request_text, transactions):
        from app.agent_tools import AgentToolExecutor

        table_rows = {
            "categories": [{"name": name} for name in NAMES],
            "profiles": [{"spending_records_consent": "granted"}],
            "transactions": transactions,
        }
        client = MagicMock()
        client.table.side_effect = lambda name: DateAwareQuery(list(table_rows.get(name, [])))
        return AgentToolExecutor(
            client,
            user_id="verified-user",
            session_id="session-1",
            now=lambda: datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
            request_text=request_text,
        )

    def test_comparison_applies_resolved_category_to_every_month(self):
        executor = self.make_executor(
            "Compare Food spending in July and August",
            [
                _expense("2026-07-05", 300, "Food"),
                _expense("2026-07-06", 90, "Public Transport"),
                _expense("2026-08-05", 250, "Food"),
            ],
        )
        # The router hands over a date-contaminated phrase; the executor fixes it.
        result = executor.execute(
            "get_period_comparison",
            {
                "metric": "spending",
                "periods": ["2026-07", "2026-08"],
                "category_name": "Food In July",
            },
        )
        self.assertEqual(result["status"], "ok")
        july, august = result["periods"]
        self.assertEqual(july["total"], "RM300.00")  # Public Transport excluded
        self.assertEqual(august["total"], "RM250.00")

    def test_comparison_prefers_longest_category_name(self):
        executor = self.make_executor(
            "Compare Public Transport spending July and August",
            [
                _expense("2026-07-05", 40, "Public Transport"),
                _expense("2026-07-06", 300, "Food"),
                _expense("2026-08-05", 55, "Public Transport"),
            ],
        )
        result = executor.execute(
            "get_period_comparison",
            {"metric": "spending", "periods": ["2026-07", "2026-08"]},
        )
        july, august = result["periods"]
        self.assertEqual(july["total"], "RM40.00")
        self.assertEqual(august["total"], "RM55.00")

    def test_unknown_category_clarifies_instead_of_unfiltered(self):
        executor = self.make_executor(
            "Compare grocery spending July and August",  # user's category is 'Groceries'
            [_expense("2026-07-05", 300, "Food")],
        )
        result = executor.execute(
            "get_period_comparison",
            {"metric": "spending", "periods": ["2026-07", "2026-08"]},
        )
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("Groceries", result["message"])

    def test_no_category_runs_unfiltered(self):
        executor = self.make_executor(
            "Compare spending in July and August",
            [
                _expense("2026-07-05", 300, "Food"),
                _expense("2026-07-06", 90, "Public Transport"),
                _expense("2026-08-05", 250, "Food"),
            ],
        )
        result = executor.execute(
            "get_period_comparison",
            {"metric": "spending", "periods": ["2026-07", "2026-08"]},
        )
        july, _august = result["periods"]
        self.assertEqual(july["total"], "RM390.00")  # both categories counted

    def test_budget_breakdown_without_category_is_not_clarified(self):
        executor = self.make_executor(
            "Show my budget breakdown",
            [_expense("2026-07-05", 300, "Food")],
        )
        result = executor.execute("get_budget_status", {"month": "2026-07"})
        self.assertEqual(result["status"], "ok")

    def test_over_budget_status_question_is_not_clarified(self):
        # "am i over budget" is a budget-status question with no category. The
        # word "over" must not be read as an unknown category name.
        from datetime import date
        from app.rag.routing import resolve_read_request

        for question in ("am i over budget", "am i under budget", "am i within budget"):
            with self.subTest(question=question):
                request = resolve_read_request(question, [], now=date(2026, 9, 22))
                self.assertEqual(request.tool_name, "get_budget_status")
                self.assertNotIn("category_name", request.arguments)
                executor = self.make_executor(
                    question, [_expense("2026-09-05", 300, "Food")]
                )
                result = executor.execute(request.tool_name, request.arguments)
                self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
