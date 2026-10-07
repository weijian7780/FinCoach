"""Target contracts for the category-parser refactor (deliberately red first).

Run with ``python -m pytest tests/test_category_interpretation_contract.py -q``.
These are expectations, not snapshots of today's wrong behavior. No xfail hides
missing behavior. Only the external database/provider boundaries are replaced;
the resolver, router, executor, and financial aggregation remain production code.
"""

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agent_tools import AgentToolExecutor
from app.category_resolution import resolve_category_phrase
from app.rag.routing import resolve_read_request


CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "category_interpretation_cases.json")
    .read_text(encoding="utf-8")
)
CASES = CORPUS["cases"]
NOW = date.fromisoformat(CORPUS["anchor_date"])
USER_ID = "category-contract-owner"
RECORD_TABLES = {"transactions", "monthly_budgets", "budgets", "reports", "savings_goals", "reminders"}


class StoredQuery:
    """Read-only PostgREST boundary double; filters affect the returned rows.

    Log execution, not query construction. Seed another owner's rows so a
    missing owner predicate contaminates totals and fails real assertions.
    Unknown query operations fail loudly instead of becoming permissive no-ops.
    """

    def __init__(self, store, table):
        self.store, self.table_name = store, table
        self.filters, self.orders = [], []
        self.bounds = None
        self.row_limit = None
        self.single = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def is_(self, field, value):
        self.filters.append(("eq", field, None if value == "null" else value))
        return self

    def gte(self, field, value):
        self.filters.append(("gte", field, value))
        return self

    def lte(self, field, value):
        self.filters.append(("lte", field, value))
        return self

    def lt(self, field, value):
        self.filters.append(("lt", field, value))
        return self

    def order(self, field, *, desc=False):
        self.orders.append((field, desc))
        return self

    def range(self, start, end):
        self.bounds = (start, end)
        return self

    def limit(self, value):
        self.row_limit = value
        return self

    def maybe_single(self):
        self.single = True
        return self

    def execute(self):
        self.store.executed.append(self)
        rows = deepcopy(self.store.rows.get(self.table_name, []))
        for op, field, expected in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(field) == expected]
            else:
                rows = [row for row in rows if row.get(field) is not None]
                if op == "gte":
                    rows = [row for row in rows if row[field] >= expected]
                elif op == "lte":
                    rows = [row for row in rows if row[field] <= expected]
                elif op == "lt":
                    rows = [row for row in rows if row[field] < expected]
        for field, desc in reversed(self.orders):
            rows.sort(key=lambda row: row.get(field, ""), reverse=desc)
        if self.bounds is not None:
            start, end = self.bounds
            rows = rows[start:end + 1]
        if self.row_limit is not None:
            rows = rows[:self.row_limit]
        data = (rows[0] if rows else None) if self.single else rows
        return SimpleNamespace(data=data, error=None)


class StoredClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def table(self, name):
        return StoredQuery(self, name)


def stored_rows(names, *, consent="granted"):
    """Independent, hand-sized financial examples; no production expectations.

    Default September: Food 100 + Transport 250 = 350; monthly cap 700.
    August: Food 60 + Transport 140 = 200. May: Food 33. Extra named
    categories deliberately have distinct amounts to expose wrong matching.
    """
    categories = [
        {"id": index, "name": name, "type": "expense", "user_id": None}
        for index, name in enumerate(names, 1)
    ]
    amounts = {"Food": "100", "Transport": "250", "Public Transport": "25",
               "Take-away": "15", "Food & Drink": "20", "Food and Drink": "30",
               "Drink": "40", "May": "7", "Now": "8", "Monthly": "9"}
    transactions = []
    for category in categories:
        if category["name"] in amounts:
            transactions.append({
                "id": f"sep-{category['id']}", "user_id": USER_ID,
                "category_id": category["id"], "category": category,
                "amount": amounts[category["name"]], "transaction_date": "2026-09-05",
                "source": "manual", "description": "Fixture expense",
            })
        for name, day, amount in (("Food", "2026-08-05", "60"),
                                  ("Transport", "2026-08-05", "140"),
                                  ("Food", "2026-05-05", "33")):
            if category["name"] == name:
                transactions.append({
                    "id": f"{day}-{category['id']}", "user_id": USER_ID,
                    "category_id": category["id"], "category": category,
                    "amount": amount, "transaction_date": day,
                    "source": "manual", "description": "Earlier fixture expense",
                })
    food = next((item for item in categories if item["name"] == "Food"), None)
    # Income must not be counted as expense; another owner's expense must not
    # enter a read at all. Both are in-period and deliberately large.
    transactions.extend([
        {"id": "salary", "user_id": USER_ID, "category_id": 900,
         "category": {"name": "Salary", "type": "income"}, "amount": "900",
         "transaction_date": "2026-09-05", "source": "manual", "description": "Income"},
        {"id": "other-owner", "user_id": "other-owner", "category_id": 901,
         "category": {"name": "Food", "type": "expense"}, "amount": "9999",
         "transaction_date": "2026-09-05", "source": "manual", "description": "Private"},
    ])
    return {
        "categories": categories + [{"id": 902, "name": "Secret", "type": "expense", "user_id": "other-owner"}],
        "profiles": [{"id": USER_ID, "spending_records_consent": consent, "monthly_allowance": "900"}],
        "transactions": transactions,
        "monthly_budgets": [{"user_id": USER_ID, "month": "2026-09-01", "limit_amount": "700"}],
        "budgets": ([{"user_id": USER_ID, "month": "2026-09-01", "category_id": food["id"],
                      "amount": "200", "category": food}] if food else []),
    }


def make_executor(text, names=None, *, consent="granted"):
    client = StoredClient(stored_rows(CORPUS["default_catalog"] if names is None else names, consent=consent))
    executor = AgentToolExecutor(
        client, user_id=USER_ID, session_id="category-contract-session",
        request_text=text, now=lambda: datetime(2026, 9, 22, 10, tzinfo=timezone.utc),
    )
    return executor, client


def value_at(result, path):
    """Read a public result field, including list indices, for literal assertions."""
    for part in path.split("."):
        result = result[int(part)] if isinstance(result, list) else result[part]
    return result


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_category_decision_boundary(case):
    """False category assertions, lost names, and ambiguity must be observable."""
    result = resolve_category_phrase(case["text"], case.get("catalog", CORPUS["default_catalog"]))
    assert (result.status, result.category) == (case["decision"], case["category"])
    if "suggestion" in case:
        assert result.suggestion == case["suggestion"]


@pytest.mark.parametrize("case", [case for case in CASES if "read" in case], ids=lambda case: case["id"])
def test_routed_read_totals_and_query_boundary_without_interpretation(case):
    """The future disabled-mode fallback must clarify before financial reads.

    This runs today's real router -> executor boundary. It does not invent an AI
    adapter or patch in a resolution that the production service cannot carry.
    Cases requiring interpretation therefore expect clarification in this suite.
    """
    want = case["read"]
    request = resolve_read_request(case["text"], [], now=NOW)
    assert request.tool_name == want["tool"]
    executor, client = make_executor(case["text"], case.get("catalog"))
    if request.clarification:
        result = {"status": "needs_clarification", "message": request.clarification}
    else:
        result = executor.execute(request.tool_name, request.arguments)
    if want["status"] == "needs_clarification":
        assert not [q.table_name for q in client.executed if q.table_name in RECORD_TABLES], "Clarification must precede financial reads"
    assert result["status"] == want["status"], result
    assert any(q.table_name == "transactions" for q in client.executed) == want["transactions_read"]
    for path, expected in want.get("values", {}).items():
        assert value_at(result, path) == expected, (path, result)
    for path, expected in want.get("lengths", {}).items():
        assert len(value_at(result, path)) == expected


TOOL_CASES = [
    ("get_budget_status", {"month": "2026-09"}, {"selected_category.recorded_spending": "RM100.00"}),
    ("get_spending_summary", {}, {"expense_total": "RM100.00"}),
    ("search_transactions", {}, {"transactions.0.amount": "RM100.00"}),
    ("get_report_summary", {"start_date": "2026-09-01", "end_date": "2026-09-30"}, {"spending.expense_total": "RM100.00"}),
    ("get_financial_overview", {"month": "2026-09"}, {"spending.expense_total": "RM100.00"}),
    ("get_period_comparison", {"metric": "spending", "periods": ["2026-08", "2026-09"]}, {"periods.0.total": "RM60.00", "periods.1.total": "RM100.00"}),
    ("get_category_budget_recommendation", {"month": "2026-09"}, {"candidate.name": "Transport", "historical_amount": "RM140.00", "target_month_category_spending": "RM250.00"}),
]


@pytest.mark.parametrize("tool,args,values", TOOL_CASES, ids=[row[0] for row in TOOL_CASES])
def test_every_category_read_preserves_a_real_filter(tool, args, values):
    # Food already has a saved limit, so the recommender correctly short-circuits
    # without transactions. Use unbudgeted Transport to exercise its read path.
    category = "Transport" if tool == "get_category_budget_recommendation" else "Food"
    executor, client = make_executor(f"show spending for {category}")
    result = executor.execute(tool, args)
    assert result["status"] == "ok", result
    assert any(q.table_name == "transactions" for q in client.executed)
    for path, expected in values.items():
        assert value_at(result, path) == expected, (tool, path, result)


@pytest.mark.parametrize("tool,args,_values", TOOL_CASES, ids=[row[0] for row in TOOL_CASES])
def test_every_category_read_blocks_an_explicit_unknown_before_records(tool, args, _values):
    executor, client = make_executor("show spending for category Yachts")
    result = executor.execute(tool, args)
    assert not [q.table_name for q in client.executed if q.table_name in RECORD_TABLES]
    assert result["status"] == "needs_clarification", result


@pytest.mark.parametrize("tool,args,_values", TOOL_CASES, ids=[row[0] for row in TOOL_CASES])
def test_every_category_read_blocks_duplicate_names_before_records(tool, args, _values):
    executor, client = make_executor("show spending on Food", ["Food", "Transport", "Food"])
    result = executor.execute(tool, args)
    assert not [q.table_name for q in client.executed if q.table_name in RECORD_TABLES]
    assert result["status"] == "needs_clarification", result


@pytest.mark.parametrize("tool,args,_values", TOOL_CASES, ids=[row[0] for row in TOOL_CASES])
def test_category_resolution_cannot_bypass_transaction_consent(tool, args, _values):
    executor, client = make_executor("show spending for Food", consent="denied")
    result = executor.execute(tool, args)
    assert not [q for q in client.executed if q.table_name == "transactions"]
    if tool == "get_budget_status":
        assert result["spending_permission_required"] is True
        assert result["recorded_spending"] is None
    elif tool == "get_financial_overview":
        assert result["spending"]["status"] == "permission_required"
    else:
        assert result["status"] == "permission_required"


@pytest.mark.parametrize("research_enabled", [False, True], ids=["research-off", "research-on"])
def test_clear_personal_read_does_not_call_an_interpreter(monkeypatch, research_enabled):
    """Measure actual provider-boundary calls, not the final response-mode label.

    Research-enabled currently calls an interpreter even for a simple personal
    read. Keep that failing expectation visible so 'fast_verified_read' cannot
    be mistaken for proof of zero model calls before formatting.
    """
    from app.rag import service

    question = "Show my Food spending in September 2026"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "message", "content": question}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    client = StoredClient(stored_rows(CORPUS["default_catalog"]))
    model_calls = []

    def unexpected_model_call(*_args, **_kwargs):
        model_calls.append("called")
        # The interpreter catches provider failures. The call count below still
        # exposes unnecessary work even if the service recovers successfully.
        raise AssertionError("A clear record read must not need a model")

    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", research_enabled)
    monkeypatch.setattr(service, "generate_structured_result", unexpected_model_call)
    monkeypatch.setattr(service, "generate_result", unexpected_model_call)
    monkeypatch.setattr(service, "generate_agent_result", unexpected_model_call)
    monkeypatch.setattr(service, "retrieve", lambda *_args, **_kwargs: [])
    result = service.CoachingService(repository, client).send_message("session", "message", question)
    answer = result["assistant_message"]["content"]
    assert "RM100.00" in answer, answer
    assert "RM350.00" not in answer, answer
    assert any(q.table_name == "transactions" for q in client.executed)
    assert model_calls == [], "The clear read invoked a model before rendering its verified result"
