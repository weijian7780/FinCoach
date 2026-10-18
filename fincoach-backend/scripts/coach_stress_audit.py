"""Reproducible Coach audit with synthetic records; never connects to Supabase.

Run from the backend: .venv/Scripts/python scripts/coach_stress_audit.py
This is an audit, not an acceptance suite: failures remain visible in JSON and
the process returns 1 when any contract fails. It does not change application
code, environment files, or a user's records. The external database/provider
boundaries are doubles; routing, tools, formatter and service are real code.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app import config
from app.agent_tools import AgentToolExecutor
from app.rag import grounding
from app.rag.routing import resolve_read_request
from app.rag.service import _format_fast_verified_read
from test_category_interpretation_contract import StoredClient, stored_rows, USER_ID, RECORD_TABLES
from test_accuracy_grounding import send, BUDGET

NOW = date(2026, 9, 28)
CHECKS = []


def record(name, passed, expected, actual, family):
    CHECKS.append({"name": name, "family": family, "passed": bool(passed),
                   "expected": expected, "actual": actual})


def fixture(consent="granted"):
    data = stored_rows(["Food", "Transport"], consent=consent)
    food, transport = data["categories"][:2]
    salary = {"id": 900, "name": "Salary", "type": "income", "user_id": None}
    data["categories"].append(salary)
    data["transactions"] = []

    def add(key, day, amount, merchant, category=food, owner=USER_ID):
        data["transactions"].append({
            "id": key, "user_id": owner, "category_id": category["id"],
            "category": category, "transaction_date": day, "amount": str(amount),
            "description": merchant, "source": "manual",
        })

    # More than one database page and more than the tool's maximum list limit.
    for i in range(125):
        add(f"grab-{i:03}", f"2026-09-{i % 25 + 1:02}", "25.00", "Grab", food)
    add("grab-income", "2026-09-26", "500", "Grab", salary)
    add("seven", "2026-09-27", "12.50", "7-Eleven")
    add("panda", "2026-09-27", "40", "Foodpanda")
    add("bus", "2026-09-28", "10", "Bus", transport)
    add("july-early", "2026-07-10", "20", "Grab")
    add("july-late", "2026-07-20", "80", "Grab")
    add("other-owner", "2026-09-28", "9999", "Grab", owner="other-owner")
    return data


def read(query, *, consent="granted", history=None):
    request = resolve_read_request(query, history or [], now=NOW)
    client = StoredClient(fixture(consent))
    executor = AgentToolExecutor(
        client, user_id=USER_ID, session_id="synthetic-stress-audit",
        request_text=query, now=lambda: datetime(2026, 9, 28, 10, tzinfo=timezone.utc),
    )
    if request.clarification:
        result = {"status": "needs_clarification", "message": request.clarification}
    elif request.tool_name:
        result = executor.execute(request.tool_name, request.arguments)
    else:
        result = {"status": "no_read_tool"}
    return request, result, client


def evidence(request, result):
    return {"tool": request.tool_name, "arguments": request.arguments, "result": result}


def exact(query, field, expected, family="tool"):
    request, result, _ = read(query)
    actual = result.get(field)
    record(query, result.get("status") == "ok" and actual == expected,
           {field: expected}, evidence(request, result), family)


def run():
    exact("how many transactions at Grab", "count", 126)
    exact("how much did I spend at Grab", "expense_total", "RM3125.00")
    exact("how many Food transactions at Grab", "count", 125)
    exact("how much did I spend at Grab on Food", "expense_total", "RM3125.00")
    exact("transactions from July", "total_matched", 2)
    exact("transactions from yesterday", "total_matched", 2, "date_filter")
    exact("show transactions at 7-Eleven", "total_matched", 1, "merchant_filter")
    exact("show income transactions at Grab", "total_matched", 1, "type_filter")
    exact("berapa banyak transaksi di Grab bulan ini", "count", 126, "language")
    exact("berapa saya belanja di Grab bulan ini", "expense_total", "RM3125.00", "language")
    exact("show spending from 1 July to 15 July 2026", "expense_total", "RM20.00", "date_filter")

    request, result, _ = read("show transactions for RM1,000")
    record("thousands separator preserves amount",
           request.arguments.get("amount") == "1000.00" or result.get("status") == "needs_clarification",
           "amount 1000.00 or clarification, never 1.00", evidence(request, result), "amount_parsing")
    request, result, _ = read("show transactions for RM25.999")
    record("malformed precision is not silently truncated",
           result.get("status") in {"needs_clarification", "invalid_arguments"},
           "reject/clarify malformed money, never exact-match 25.00", evidence(request, result), "amount_parsing")

    # Cross-product checks all asserted filters against independent row values.
    # This evaluates filter composition, not just status=ok or the tool name.
    for verb in ["show", "list", "find", ""]:
        for count in [1, 5, 10, 50]:
            for category in ["", "Food"]:
                query = f"{verb} my last {count} {category} transactions at Grab for RM25".strip()
                request, result, _ = read(query)
                rows = result.get("transactions", [])
                valid = (result.get("status") == "ok" and len(rows) == count
                         and result.get("total_matched") == 125
                         and all(r["description"] == "Grab" and r["amount"] == "RM25.00"
                                 and r["category"] == "Food" for r in rows))
                record(query, valid, {"displayed": count, "total": 125, "amount": "RM25.00"},
                       {"tool": request.tool_name, "args": request.arguments,
                        "status": result.get("status"), "displayed": len(rows),
                        "total": result.get("total_matched")}, "composition")

    request, result, _ = read("show my last 10 transactions at Grab")
    rendered = _format_fast_verified_read(request.tool_name, result)
    record("merchant list without a period searches all dates, lists 10, reports all 128",
           rendered.count(": Food RM") + rendered.count(": Salary RM") == 10
           and "Found 128" in rendered and "most recent 10" in rendered
           and "across all dates" in rendered,
           "128 matched across all dates (incl. 2 July) / 10 displayed", rendered, "formatting")

    for query, predicate in [
        ("show my first 5 transactions", lambda r: all(x["date"] == "2026-09-01" for x in r.get("transactions", [])) and len(r.get("transactions", [])) == 5),
        ("show transactions not Food", lambda r: bool(r.get("transactions")) and all(x["category"] != "Food" for x in r["transactions"])),
        ("show transactions at Grab and Foodpanda", lambda r: r.get("total_matched") == 127),
    ]:
        request, result, _ = read(query)
        record(query, result.get("status") == "needs_clarification" or predicate(result),
               "Honor all constraints, or clarify unsupported/ambiguous request",
               evidence(request, result), "constraint_preservation")

    for query in ["show transactions under RM25", "top 5 transactions", "show Food and Transport transactions"]:
        request, result, client = read(query)
        financial_reads = [q.table_name for q in client.executed if q.table_name in RECORD_TABLES]
        record(query, result.get("status") == "needs_clarification" and not financial_reads,
               "clarify before reading financial records", {"result": result, "reads": financial_reads}, "safe_clarification")

    for query in ["how many transactions at Grab", "how much did I spend at Grab", "show transactions at Grab"]:
        request, result, client = read(query, consent="denied")
        financial_reads = [q.table_name for q in client.executed if q.table_name in RECORD_TABLES]
        record(query + " [consent denied]", result.get("status") != "ok" and not financial_reads,
               "deny and execute zero financial reads", {"result": result, "reads": financial_reads}, "consent")

    # Spending-record consent does not forbid reading the user's saved budget
    # limits. The protected values are transaction-derived spending/remaining.
    request, result, client = read("am i over budget", consent="denied")
    financial_reads = [q.table_name for q in client.executed if q.table_name in RECORD_TABLES]
    record("budget with spending consent denied",
           "transactions" not in financial_reads and result.get("recorded_spending") is None
           and result.get("remaining") is None and result.get("spending_permission_required") is True,
           "budget limits allowed; spending/remaining unavailable; zero transaction reads",
           {"result": result, "reads": financial_reads}, "consent")

    request, result, client = read("how many transactions at Grab")
    txn_queries = [q for q in client.executed if q.table_name == "transactions"]
    record("owner scoping on every pagination query",
           len(txn_queries) >= 2 and all(("eq", "user_id", USER_ID) in q.filters for q in txn_queries)
           and result.get("count") == 126,
           "all pages owner-filtered; other owner's 9999 excluded",
           {"pages": len(txn_queries), "count": result.get("count")}, "ownership")

    for query in ["am i over budget", "remaining budget", "still within my budget", "exceeded my budget"]:
        request, result, _ = read(query)
        record(query, request.tool_name == "get_budget_status" and result.get("status") == "ok"
               and not request.arguments.get("category_name"), "whole-month budget, no false category",
               {"tool": request.tool_name, "args": request.arguments, "status": result.get("status")}, "budget")

    # Inject known bad provider drafts to exercise the real service's guard.
    # This measures containment of hallucinations, NOT live-model accuracy.
    drafts = ["Your remaining budget is RM9999.", "Your remaining budget is RM1000.00."]
    modes = [("actual_local_config", grounding._VALIDATION_ENABLED), ("validation_enabled", True)]
    for label, enabled in modes:
        with patch.object(grounding, "_VALIDATION_ENABLED", enabled):
            for draft in drafts:
                output = send("Why is my budget low?", draft, deepcopy(BUDGET))
                record(label + ": reject " + draft, draft not in output["content"],
                       "remove fabricated amount / wrong-field amount; retain verified RM100",
                       {"content": output["content"], "model": output["model"]}, "grounding")
            correct = "Your remaining budget is RM100.00."
            output = send("Why is my budget low?", correct, deepcopy(BUDGET))
            record(label + ": preserve correct advice", correct in output["content"], correct,
                   output["content"], "grounding")

    # Provider failure and malformed result must never become invented balances.
    output = send("Show my spending", "", {"status": "invalid_arguments", "message": "Invalid period."})
    record("failed tool is not a zero balance", "RM0" not in output["content"] and "Invalid period" in output["content"],
           "honest tool failure", output["content"], "failure_handling")

    report = {
        "anchor_date": NOW.isoformat(), "scope": "offline synthetic DB/provider boundaries; real application functions",
        "flags": {"answer_validation": grounding._VALIDATION_ENABLED,
                  "research_policy": config.COACH_RESEARCH_POLICY_ENABLED,
                  "grounding_mode": config.COACH_GROUNDING_MODE},
        "summary": {"checks": len(CHECKS), "passed": sum(c["passed"] for c in CHECKS),
                    "failed": sum(not c["passed"] for c in CHECKS)},
        "checks": CHECKS,
    }
    if "--stdout-json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return int(report["summary"]["failed"] > 0)
    output_path = ROOT / "evaluation-results" / "coach-stress-audit-2026-09-28.json"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"]))
    for check in CHECKS:
        if not check["passed"]:
            print("FAIL: " + check["name"])
    print("Evidence: " + str(output_path))
    return int(report["summary"]["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(run())
