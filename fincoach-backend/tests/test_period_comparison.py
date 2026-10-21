"""Multi-period comparison: routing parse, tool computation, and formatting."""

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.rag.routing import (
    is_multi_period_comparison,
    parse_comparison_request,
    required_read_agent_tool_name,
)

NOW = date(2026, 9, 22)  # September 2026 is the in-progress current month


class ComparisonRoutingTests(unittest.TestCase):
    def test_trailing_year_applies_to_the_whole_month_list(self):
        parsed = parse_comparison_request(
            "Compare my spending in July and September 2025", now=NOW
        )
        self.assertEqual(parsed["periods"], ["2025-07", "2025-09"])

    def test_trailing_year_applies_to_the_whole_month_range(self):
        parsed = parse_comparison_request(
            "Compare my spending from January to March 2025", now=NOW
        )
        self.assertEqual(parsed["periods"], ["2025-01", "2025-02", "2025-03"])

    def test_cross_year_range_respects_its_explicit_endpoint(self):
        for text in (
            "Compare spending November to February 2025",
            "Compare spending November 2024 to February",
        ):
            with self.subTest(text=text):
                parsed = parse_comparison_request(text, now=NOW)
                self.assertEqual(parsed["periods"], ["2024-11", "2024-12", "2025-01", "2025-02"])

    def test_too_many_months_require_clarification_instead_of_truncation(self):
        from app.rag.routing import ReadReadiness, resolve_read_request

        for text in (
            "Compare my spending for the last 13 months",
            "Compare my spending for the last 100 months",
            "Compare this month with the previous twelve",
            "Compare January 2025 to February 2026 spending",
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "12"):
                    parse_comparison_request(text, now=NOW)
                resolved = resolve_read_request(text, [], now=NOW)
                self.assertEqual(resolved.readiness, ReadReadiness.NEEDS_CLARIFICATION)
                self.assertNotIn("periods", resolved.arguments)

    def test_relative_month_period_is_not_used_as_a_category(self):
        parsed = parse_comparison_request(
            "Compare my spending for the last three months", now=NOW
        )
        self.assertIsNone(parsed["category_name"])
        parsed = parse_comparison_request(
            "Compare my spending on Food for the last three months", now=NOW
        )
        self.assertEqual(parsed["category_name"], "Food")

    def test_named_month_list_resolves_to_calendar_months(self):
        parsed = parse_comparison_request(
            "Compare July, August and September spending", now=NOW
        )
        assert parsed is not None
        self.assertEqual(parsed["metric"], "spending")
        self.assertEqual(parsed["periods"], ["2026-07", "2026-08", "2026-09"])

    def test_month_range_is_expanded_inclusive(self):
        parsed = parse_comparison_request("Compare spending July to September", now=NOW)
        assert parsed is not None
        self.assertEqual(parsed["periods"], ["2026-07", "2026-08", "2026-09"])

    def test_two_nonconsecutive_named_months(self):
        parsed = parse_comparison_request("Compare June with September", now=NOW)
        assert parsed is not None
        self.assertEqual(parsed["periods"], ["2026-06", "2026-09"])

    def test_last_n_months_are_completed_months(self):
        parsed = parse_comparison_request("Compare the last three months", now=NOW)
        assert parsed is not None
        # Six/three completed months exclude the in-progress current month.
        self.assertEqual(parsed["periods"], ["2026-06", "2026-07", "2026-08"])

    def test_this_month_with_previous_n_includes_current(self):
        parsed = parse_comparison_request(
            "Compare this month with the previous three", now=NOW
        )
        assert parsed is not None
        self.assertEqual(parsed["periods"], ["2026-06", "2026-07", "2026-08", "2026-09"])

    def test_cross_year_named_months(self):
        parsed = parse_comparison_request("Compare December and January", now=NOW)
        assert parsed is not None
        self.assertEqual(parsed["periods"], ["2025-12", "2026-01"])

    def test_explicit_baseline_month(self):
        parsed = parse_comparison_request(
            "Compare July, August and September against July", now=NOW
        )
        assert parsed is not None
        self.assertEqual(parsed["baseline"], "2026-07")

    def test_single_compare_is_not_multi_period(self):
        self.assertIsNone(parse_comparison_request("Compare with last month", now=NOW))
        self.assertFalse(is_multi_period_comparison("Compare with last month", now=NOW))

    def test_single_named_month_with_compare_asks_for_more(self):
        # A comparison is clearly meant but only one month resolves.
        with self.assertRaises(ValueError):
            parse_comparison_request("Compare July spending", now=NOW)
        # The tool selector still claims it so a clarification can be raised.
        self.assertTrue(is_multi_period_comparison("Compare July spending", now=NOW))

    def test_tool_selection_prefers_period_comparison(self):
        from app.rag.routing import CoachingRoute

        self.assertEqual(
            required_read_agent_tool_name(
                "Compare July, August and September spending",
                CoachingRoute.PERSONAL_FINANCE,
            ),
            "get_period_comparison",
        )


class DateAwareQuery:
    """A Supabase query stub that honours transaction_date and month filters."""

    def __init__(self, rows):
        self.rows = rows
        self._eq: dict[str, object] = {}
        self._date_filters: list[tuple[str, str]] = []
        self._single = False
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._eq[column] = value
        return self

    def is_(self, column, _value):
        self._eq[column] = None
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

    def _matches(self, row):
        if "month" in self._eq and row.get("month") != self._eq["month"]:
            return False
        date_value = row.get("transaction_date")
        for kind, bound in self._date_filters:
            if date_value is None:
                return False
            if kind == "gte" and not date_value >= bound:
                return False
            if kind == "lte" and not date_value <= bound:
                return False
            if kind == "lt" and not date_value < bound:
                return False
        return True

    def execute(self):
        rows = [row for row in self.rows if self._matches(row)]
        if self._range is not None:
            rows = rows[self._range[0]:self._range[1] + 1]
        data = (rows[0] if rows else None) if self._single else rows
        return SimpleNamespace(data=data, error=None)


def _expense(month_day: str, amount, category="Food"):
    return {
        "id": f"{category}-{month_day}-{amount}",
        "amount": amount,
        "transaction_date": month_day,
        "category": {"name": category, "type": "expense"},
    }


class ComparisonToolTests(unittest.TestCase):
    def make_executor(self, table_rows):
        from unittest.mock import MagicMock

        from app.agent_tools import AgentToolExecutor

        table_rows.setdefault("categories", [{"name": "Food"}, {"name": "Coffee"}])
        table_rows.setdefault(
            "profiles", [{"spending_records_consent": "granted"}]
        )
        client = MagicMock()

        def table(name):
            return DateAwareQuery(list(table_rows.get(name, [])))

        client.table.side_effect = table
        executor = AgentToolExecutor(
            client,
            user_id="verified-user",
            session_id="session-1",
            now=lambda: datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
        )
        return executor

    def test_spending_totals_and_consecutive_changes(self):
        executor = self.make_executor(
            {
                "transactions": [
                    _expense("2026-07-05", 400),
                    _expense("2026-07-20", 200),
                    _expense("2026-08-10", 540),
                    _expense("2026-09-01", 320),
                ]
            }
        )
        result = executor._period_comparison(
            {"metric": "spending", "periods": ["2026-07", "2026-08", "2026-09"]}
        )
        self.assertEqual(result["status"], "ok")
        july, august, september = result["periods"]

        self.assertEqual(july["total"], "RM600.00")
        self.assertIsNone(july["change"])  # first listed month is the baseline

        self.assertEqual(august["total"], "RM540.00")
        self.assertEqual(august["change"]["direction"], "less")
        self.assertEqual(august["change"]["amount"], "RM60.00")
        self.assertEqual(august["change"]["percent"], "10")

        # September is the in-progress month: its change is withheld.
        self.assertTrue(september["incomplete"])
        self.assertEqual(september["recorded_through"], "2026-09-22")
        self.assertTrue(september["change"]["withheld"])

    def test_fixed_baseline_month(self):
        executor = self.make_executor(
            {
                "transactions": [
                    _expense("2026-06-05", 800),
                    _expense("2026-07-05", 600),
                    _expense("2026-08-05", 400),
                ]
            }
        )
        result = executor._period_comparison(
            {
                "metric": "spending",
                "periods": ["2026-07", "2026-08"],
                "baseline": "2026-06",
            }
        )
        july, august = result["periods"]
        # Both compare against June (800), not against each other.
        self.assertEqual(july["change"]["baseline_month"], "2026-06")
        self.assertEqual(july["change"]["amount"], "RM200.00")
        self.assertEqual(august["change"]["baseline_month"], "2026-06")
        self.assertEqual(august["change"]["amount"], "RM400.00")

    def test_missing_records_are_distinguished_from_activity(self):
        executor = self.make_executor(
            {"transactions": [_expense("2026-07-05", 300)]}
        )
        result = executor._period_comparison(
            {"metric": "spending", "periods": ["2026-07", "2026-08"]}
        )
        july, august = result["periods"]
        self.assertTrue(july["has_records"])
        self.assertFalse(august["has_records"])
        self.assertEqual(august["total"], "RM0.00")

    def test_category_filter_applies_to_every_month(self):
        executor = self.make_executor(
            {
                "transactions": [
                    _expense("2026-07-05", 300, category="Food"),
                    _expense("2026-07-06", 90, category="Coffee"),
                    _expense("2026-08-05", 250, category="Food"),
                ]
            }
        )
        result = executor._period_comparison(
            {
                "metric": "spending",
                "periods": ["2026-07", "2026-08"],
                "category_name": "Food",
            }
        )
        july, august = result["periods"]
        self.assertEqual(july["total"], "RM300.00")  # Coffee excluded
        self.assertEqual(august["total"], "RM250.00")

    def test_zero_baseline_avoids_percentage(self):
        executor = self.make_executor(
            {"transactions": [_expense("2026-08-05", 120)]}
        )
        result = executor._period_comparison(
            {"metric": "spending", "periods": ["2026-07", "2026-08"]}
        )
        _july, august = result["periods"]
        # July has no spending (baseline 0): report the amount, no percentage.
        self.assertEqual(august["change"]["amount"], "RM120.00")
        self.assertIsNone(august["change"]["percent"])

    def test_budget_metric_compares_monthly_limits(self):
        executor = self.make_executor(
            {
                "monthly_budgets": [
                    {"month": "2026-07-01", "limit_amount": 600},
                    {"month": "2026-08-01", "limit_amount": 500},
                ]
            }
        )
        result = executor._period_comparison(
            {"metric": "budget", "periods": ["2026-07", "2026-08"]}
        )
        july, august = result["periods"]
        self.assertEqual(july["total"], "RM600.00")
        self.assertEqual(august["total"], "RM500.00")
        self.assertEqual(august["change"]["direction"], "less")

    def test_requires_two_months(self):
        executor = self.make_executor({"transactions": []})
        result = executor._period_comparison(
            {"metric": "spending", "periods": ["2026-07"]}
        )
        self.assertEqual(result["status"], "invalid_arguments")


class ComparisonFormatTests(unittest.TestCase):
    def _build(self):
        from app.rag.service import _format_period_comparison

        result = {
            "status": "ok",
            "metric": "spending",
            "category_name": "Food",
            "baseline": "consecutive",
            "range": {"start": "2026-07", "end": "2026-09"},
            "periods": [
                {
                    "month": "2026-07", "label": "July 2026", "total": "RM600.00",
                    "has_records": True, "incomplete": False, "recorded_through": None,
                    "change": None,
                },
                {
                    "month": "2026-08", "label": "August 2026", "total": "RM540.00",
                    "has_records": True, "incomplete": False, "recorded_through": None,
                    "change": {"withheld": False, "baseline_month": "2026-07",
                               "amount": "RM60.00", "direction": "less", "percent": "10"},
                },
                {
                    "month": "2026-09", "label": "September 2026", "total": "RM320.00",
                    "has_records": True, "incomplete": True,
                    "recorded_through": "2026-09-22", "change": {"withheld": True},
                },
            ],
        }
        return _format_period_comparison(result)

    def test_header_baseline_and_entries(self):
        text = self._build()
        self.assertIn("Spending comparison", text)
        self.assertIn("Food only.", text)
        self.assertIn("Changes are against the previous listed month.", text)
        self.assertIn("**July 2026 — RM600.00**", text)
        self.assertIn("Baseline.", text)
        self.assertIn("RM60.00 less · 10% decrease", text)

    def test_incomplete_month_is_flagged_and_withheld(self):
        text = self._build()
        self.assertIn("Month in progress", text)
        self.assertIn("Full-month change withheld until the month ends.", text)


if __name__ == "__main__":
    unittest.main()
