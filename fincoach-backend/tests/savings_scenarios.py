"""Six made-up record scenarios for the savings estimate, built through the real
``AgentToolExecutor._predict_savings`` with in-memory rows (only Supabase I/O is
replaced). Shared by the unit tests and the live answer trials; holds records,
never questions."""
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.agent_tools import AgentToolExecutor
from test_accuracy_tools import Query

BUILT_IN = ("Food", "Transport", "Entertainment", "Shopping", "Bills", "Income")
CUSTOM_NAME = "Zorblax Hobby Jar"  # a user's own category name: must never leave the tool
# The real tool, captured before any test replaces it on the class.
_REAL_PREDICT = AgentToolExecutor._predict_savings


def _row(id, amount, category, day, kind="expense"):
    return {"id": str(id), "amount": amount, "transaction_date": day, "user_id": "u",
            "category": {"name": category, "type": kind}}


def _executor(*, rows, today, allowance=None, budget=None):
    tables = {
        "profiles": {"id": "u", "monthly_allowance": allowance, "spending_records_consent": "granted"},
        "transactions": rows,
        "categories": [{"id": f"b{i}", "name": name, "user_id": None} for i, name in enumerate(BUILT_IN)]
        + [{"id": "c1", "name": CUSTOM_NAME, "user_id": "u"}],
        "savings_goals": [],
        "monthly_budgets": {"limit_amount": budget} if budget is not None else {},
        "budgets": [],
    }
    client = MagicMock()
    client.table.side_effect = lambda name: Query(tables.get(name, []))
    now = datetime(*today, 12, tzinfo=ZoneInfo("Asia/Kuala_Lumpur"))
    return AgentToolExecutor(client, user_id="u", session_id="s", now=lambda: now)


def one_dominant_payment():
    """Income RM600, one RM800 Entertainment payment and RM52.45 Food in 9 days."""
    rows = [_row("i1", 600, "Income", "2026-11-01", "income"),
            _row("e1", 800, "Entertainment", "2026-11-03"),
            _row("e2", 30.25, "Food", "2026-11-05"), _row("e3", 22.20, "Food", "2026-11-08")]
    return _executor(rows=rows, today=(2026, 11, 9)), {}


def steady_daily_spending():
    """RM20 of Food every day for 10 days against RM500 income."""
    rows = [_row("i1", 500, "Income", "2026-11-01", "income")]
    rows += [_row(f"e{day}", 20, "Food", f"2026-11-{day:02d}") for day in range(1, 11)]
    return _executor(rows=rows, today=(2026, 11, 10)), {}


def surplus():
    """RM2,000 income, RM240 spent over 12 days in Food and Transport."""
    rows = [_row("i1", 2000, "Income", "2026-11-01", "income"),
            _row("e1", 95.50, "Food", "2026-11-02"), _row("e2", 54.50, "Food", "2026-11-09"),
            _row("e3", 90, "Transport", "2026-11-04")]
    return _executor(rows=rows, today=(2026, 11, 12)), {}


def budget_based_no_expenses():
    """No expense records this month or last; a RM900 budget and RM1,200 allowance."""
    return _executor(rows=[], today=(2026, 11, 6), allowance=1200, budget=900), {}


def next_month_prediction():
    """December from November's pace (RM310 over 10 days) and a RM1,000 allowance."""
    rows = [_row("e1", 180, "Food", "2026-11-03"), _row("e2", 130, "Shopping", "2026-11-07")]
    return _executor(rows=rows, today=(2026, 11, 10), allowance=1000), {"month": "2026-12-01"}


def allowance_based_income():
    """No recorded income; RM800 allowance; Food plus a custom category over 5 days."""
    rows = [_row("e1", 100, "Food", "2026-11-02"), _row("e2", 60, CUSTOM_NAME, "2026-11-04")]
    return _executor(rows=rows, today=(2026, 11, 5), allowance=800), {}


SCENARIOS = {
    "one_dominant_payment": one_dominant_payment,
    "steady_daily_spending": steady_daily_spending,
    "surplus": surplus,
    "budget_based_no_expenses": budget_based_no_expenses,
    "next_month_prediction": next_month_prediction,
    "allowance_based_income": allowance_based_income,
}


def predict(name):
    """The real tool result for one scenario."""
    executor, args = SCENARIOS[name]()
    return _REAL_PREDICT(executor, {"include_goals": False, **args})
