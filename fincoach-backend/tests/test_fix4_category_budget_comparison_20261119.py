"""Fix 4 (2026-11-19): a category budget comparison reads that category's limits.

"Compare my Food budget for July and August" used to compare the overall
monthly budget while labelling it Food. Tested through
AgentToolExecutor.execute so the existing category checks run.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agent_tools import AgentToolExecutor

USER = "verified-user"
OTHER = "other-user"


class _Query:
    """A fake PostgREST query that honours eq/is_ filters and maybe_single."""

    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.single = False

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def is_(self, column, value):
        self.filters.append((column, None if value == "null" else value))
        return self

    def maybe_single(self):
        self.single = True
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        rows = [row for row in self.rows
                if all(row.get(column) == value for column, value in self.filters)]
        data = (rows[0] if rows else None) if self.single else rows
        return SimpleNamespace(data=data, error=None)


def _executor(categories=None, request_text=None):
    tables = {
        "categories": categories or [
            {"id": 1, "name": "Food", "user_id": None},
            {"id": 2, "name": "Transport", "user_id": None},
        ],
        "profiles": [{"id": USER, "spending_records_consent": "granted"}],
        "monthly_budgets": [
            {"user_id": USER, "month": "2026-07-01", "limit_amount": 1500},
            {"user_id": USER, "month": "2026-08-01", "limit_amount": 1400},
        ],
        "budgets": [
            {"user_id": USER, "month": "2026-07-01", "amount": 400, "category": {"name": "Food"}},
            {"user_id": USER, "month": "2026-08-01", "amount": 350, "category": {"name": "Food"}},
            {"user_id": USER, "month": "2026-07-01", "amount": 90, "category": {"name": "Transport"}},
            {"user_id": USER, "month": "2026-08-01", "amount": 80, "category": {"name": "Transport"}},
            {"user_id": OTHER, "month": "2026-07-01", "amount": 999, "category": {"name": "Food"}},
            {"user_id": OTHER, "month": "2026-08-01", "amount": 888, "category": {"name": "Food"}},
        ],
    }
    client = MagicMock()
    client.table.side_effect = lambda name: _Query(list(tables.get(name, [])))
    return AgentToolExecutor(
        client, user_id=USER, session_id="session-1", request_text=request_text,
        now=lambda: datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )


def _compare(executor, **arguments):
    return executor.execute("get_period_comparison", {
        "metric": "budget", "periods": ["2026-07", "2026-08"], **arguments})


def test_category_budget_uses_that_categorys_limits():
    result = _compare(_executor(), category_name="Food")
    assert result["status"] == "ok"
    july, august = result["periods"]
    # Food's own limits: not the overall 1500/1400, not Transport, not the other user.
    assert july["total"] == "RM400.00"
    assert august["total"] == "RM350.00"
    assert july["has_records"] and august["has_records"]
    assert august["change"]["direction"] == "less"


def test_category_name_matches_case_and_spacing_insensitively():
    result = _compare(_executor(), category_name="  food ")
    july, august = result["periods"]
    assert (july["total"], august["total"]) == ("RM400.00", "RM350.00")


def test_category_without_a_limit_in_a_month_is_not_set():
    executor = _executor()
    tables_budgets = [
        {"user_id": USER, "month": "2026-07-01", "amount": 400, "category": {"name": "Food"}},
    ]
    executor.admin_client.table.side_effect = lambda name: _Query(
        tables_budgets if name == "budgets" else [
            {"id": 1, "name": "Food", "user_id": None}] if name == "categories" else [])
    result = _compare(executor, category_name="Food")
    july, august = result["periods"]
    assert july["has_records"] is True and july["total"] == "RM400.00"
    assert august["has_records"] is False


def test_no_category_still_compares_the_overall_monthly_budget():
    result = _compare(_executor())
    july, august = result["periods"]
    assert (july["total"], august["total"]) == ("RM1,500.00", "RM1,400.00")


def test_unknown_category_asks_for_clarification():
    result = _compare(_executor(), category_name="Gadgets")
    assert result["status"] == "needs_clarification"


def test_ambiguous_category_asks_for_clarification():
    categories = [
        {"id": 1, "name": "Food", "user_id": None},
        {"id": 7, "name": "food", "user_id": USER},
    ]
    executor = _executor(categories, request_text="Compare my food budget for July and August")
    result = _compare(executor, category_name="Food")
    assert result["status"] == "needs_clarification"
