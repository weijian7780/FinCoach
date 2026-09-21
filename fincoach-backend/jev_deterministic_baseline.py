"""Repaired deterministic baseline (candidate A) on the action+topic task.

Maps the existing regex router (app/rag/routing.py) + topic detector
(app/rag/query_analysis.py) onto the SAME action/topic vocabulary the Jev
candidate is scored on, then reuses jev_action_eval.score() so the two are
compared on identical metrics.

"Repaired" = the read layer emits EVERY matching read tool instead of only the
first (removing the first-match-wins ceiling in required_read_agent_tool_name),
so a genuine multi-read request like "check my cashflow and make a plan" can
score both. This is the most generous fair form of the deterministic system;
it still cannot infer intent beyond its regexes and has no monthly-cadence or
uncertain-band notion.
"""
from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path

from dotenv import load_dotenv

from jev_action_eval import DEV_CASES, PERSONAL_ACTIONS, load_labels, score, _print_run

load_dotenv()

from app.rag.query_analysis import detect_knowledge_topics
from app.rag import routing as R


def _matching_reads(m: str) -> set[str]:
    """Every read tool whose pattern fires (repaired: no first-match-wins)."""
    reads: set[str] = set()
    if R._CASHFLOW_FORECAST_QUERY.search(m): reads.add("get_cashflow_forecast")
    if R.is_weekly_savings_plan_request(m): reads.add("get_weekly_savings_plan")
    if R._PREDICTION_QUERY.search(m): reads.add("predict_savings")
    if R._PROFILE_QUERY.search(m): reads.add("get_financial_profile")
    if R._REMINDER_REFERENCE.search(m) or R._DEADLINE_QUERY.search(m): reads.add("get_upcoming_reminders")
    if R._SAVINGS_GOAL_QUERY.search(m): reads.add("get_savings_goals")
    # A budget-allocation/method ask is educational, not a budget-status read.
    if R._BUDGET_QUERY.search(m) and not R._BUDGET_ALLOCATION_QUERY.search(m):
        reads.add("get_budget_status")
    # search wins over generic spending summary when the search pattern fires
    if R._TRANSACTION_SEARCH_QUERY.search(m):
        reads.add("search_transactions")
    elif R._TRANSACTION_QUERY.search(m):
        reads.add("get_spending_summary")
    return reads


def deterministic_actions(content: str, history: list[dict] | None):
    m = " ".join(content.strip().split())
    route = R.route_coach_message(m)
    actions: set[str] = set()

    personal_route = route in (R.CoachingRoute.PERSONAL_FINANCE, R.CoachingRoute.COMBINED)
    if personal_route:
        actions |= _matching_reads(m)
    # Follow-up inheritance runs regardless of the bare message's route: the app
    # resolves "and next month?" against history even though it alone reads casual.
    resolved = R.resolve_read_request(content, history or [])
    if resolved.tool_name and (resolved.inherited or personal_route):
        actions.add(resolved.tool_name)
    if personal_route and not actions:  # original ladder's final fallback
        actions.add("get_financial_overview")

    # Confirmation-gated writes are detected route-independently in the app.
    for w in R.required_agent_tool_names(m):
        actions.add(w)

    # Education: education/combined route, or the product-ranking intercept.
    if route in (R.CoachingRoute.FINANCIAL_EDUCATION, R.CoachingRoute.COMBINED):
        actions.add("education")
    elif R.is_product_selection_request(m):
        actions.add("education")

    is_casual = route == R.CoachingRoute.CASUAL and not actions
    if is_casual:
        actions = {"casual"}

    topics = {t.topic.topic_id for t in detect_knowledge_topics(m)}
    uncertain = (not actions) and not is_casual
    return actions, topics, is_casual, uncertain


def build_rows(labels):
    rows = []
    for cid, c in labels.items():
        acts, topics, is_casual, uncertain = deterministic_actions(c["query"], c.get("history"))
        rows.append({
            "id": cid, "category": c["category"], "query": c["query"],
            "exp_actions": set(c["expected_actions"]), "exp_topics": set(c["expected_topics"]),
            "exp_personal": c["requires_personal_records"], "exp_clarify": c["expected_clarification"],
            "got_actions": acts, "got_topics": topics,
            "got_personal": bool(acts & PERSONAL_ACTIONS), "got_uncertain": uncertain,
            "casual_p": 1.0 if is_casual else 0.0,
            "top_actions": [], "param_probs": {},   # no monthly-cadence notion
            "latency_ms": 0.0, "in_tok": None, "out_tok": None, "model": "deterministic",
        })
    return rows


def main():
    ap = ArgumentParser()
    ap.add_argument("--cases", default=str(DEV_CASES))
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    labels = load_labels(args.cases)
    rows = build_rows(labels)
    _print_run(rows, f"deterministic baseline (repaired) — {Path(args.cases).name}")
    s = score(rows)
    s["model"] = "deterministic (regex router, repaired multi-read)"
    print("\n== summary ==")
    for k, v in s.items():
        print(f"  {k}: {v}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"summary": s, "rows": [
            {**r, "exp_actions": sorted(r["exp_actions"]), "got_actions": sorted(r["got_actions"]),
             "exp_topics": sorted(r["exp_topics"]), "got_topics": sorted(r["got_topics"])}
            for r in rows]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
