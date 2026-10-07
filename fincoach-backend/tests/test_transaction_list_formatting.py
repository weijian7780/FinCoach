"""Regression: a transaction list's stated count must match the rows shown, and
count/expense_total modes render their own numbers."""

import unittest

from app.rag.service import _format_fast_verified_read

PERIOD = {"start": "2026-09-01", "end": "2026-09-30"}


def _rows(n):
    return [
        {"date": f"2026-09-{i + 1:02d}", "category": "Food", "amount": f"RM{i + 1}.00"}
        for i in range(n)
    ]


class TransactionListFormatTests(unittest.TestCase):
    def test_stated_count_matches_all_rows_shown(self):
        result = {"status": "ok", "period": PERIOD, "transactions": _rows(10), "total_matched": 10}
        text = _format_fast_verified_read("search_transactions", result)
        self.assertIn("Found 10 matching", text)
        self.assertEqual(text.count("Food"), 10)  # all 10 listed, not just 5

    def test_capped_list_reports_total_and_how_many_shown(self):
        result = {"status": "ok", "period": PERIOD, "transactions": _rows(10), "total_matched": 30}
        text = _format_fast_verified_read("search_transactions", result)
        self.assertIn("Found 30 matching", text)
        self.assertIn("showing the most recent 10", text)
        self.assertEqual(text.count("Food"), 10)

    def test_count_mode_reports_the_count(self):
        result = {"status": "ok", "result_mode": "count", "count": 42, "period": PERIOD}
        text = _format_fast_verified_read("search_transactions", result)
        self.assertIn("42 recorded transaction(s)", text)

    def test_expense_total_mode_reports_the_total(self):
        result = {
            "status": "ok", "result_mode": "expense_total", "expense_total": "RM20.00",
            "expense_count": 2, "period": PERIOD,
        }
        text = _format_fast_verified_read("search_transactions", result)
        self.assertIn("RM20.00", text)
        self.assertIn("2 transaction(s)", text)


if __name__ == "__main__":
    unittest.main()
