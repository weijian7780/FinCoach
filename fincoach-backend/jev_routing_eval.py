"""Jev-first routing + topic-selection evaluation (isolated requests).

Each case is ONE isolated system_one request carrying only the message, the
topic registry definitions, and thresholds. No user records, no credentials,
and no cross-case shared state. Ground-truth topics come from the labelled
retrieval fixtures (expected_source -> topic_id).

This measures Jev in isolation; it does not wire Jev into CoachingService and
sends only synthetic benchmark queries. Live user messages still require the
provider-consent disclosure update before any integration.
"""
from __future__ import annotations

import json
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from app.rag.query_analysis import KNOWLEDGE_TOPICS

load_dotenv()

FIXTURES = Path(__file__).parent / "tests/fixtures"
SOURCE_TO_TOPIC = {t.source: t.topic_id for t in KNOWLEDGE_TOPICS}
ROUTE_CRITERIA = {
    "casual": "small talk, greetings, thanks, or non-finance chatter; no advice needed",
    "personal_finance": "about the user's OWN recorded finances (their spending, budget, savings, reminders)",
    "financial_education": "general finance knowledge or definitions, NOT tied to the user's own records",
    "combined": "needs BOTH the user's own records AND general finance knowledge",
    "needs_clarification": "too ambiguous or underspecified to route confidently",
}


def _topic_label(topic) -> str:
    return topic.canonical_terms[0] if topic.canonical_terms else topic.topic_id


def build_questions():
    from typesafe_sdk import Choice, Noul

    questions = {
        "route": Choice(
            instructions="Classify the FinCoach coaching response path for the user message.",
            criteria=dict(ROUTE_CRITERIA),
        )
    }
    for topic in KNOWLEDGE_TOPICS:
        aka = ", ".join(topic.canonical_terms)
        questions[f"topic_{topic.topic_id}"] = Noul(
            instructions=(
                f"Is the user's message about this Malaysian personal-finance topic: "
                f"{_topic_label(topic)} ({aka})? Answer yes only if this specific topic "
                f"is a substantive subject of the message."
            )
        )
    return questions


def load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["cases"] if isinstance(payload, dict) else payload
    out = []
    for item in cases:
        srcs = item.get("expected_sources")
        if srcs is None:
            srcs = [item["expected_source"]] if item.get("expected_source") else []
        expected = {SOURCE_TO_TOPIC[s] for s in srcs if s in SOURCE_TO_TOPIC}
        out.append({
            "id": item["id"],
            "query": item["query"],
            "expected_topics": expected,  # empty set = negative/unanswerable
        })
    return out


def _usage_tokens(resp) -> int | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    ins = getattr(usage, "input_tokens", None)
    outs = getattr(usage, "output_tokens", None)
    if isinstance(ins, int) or isinstance(outs, int):
        return (ins or 0) + (outs or 0)
    return None


def run(cases, *, route_threshold: float, topic_threshold: float, max_topics: int):
    from typesafe_sdk import TypeSafeClient

    questions = build_questions()
    rows = []
    with TypeSafeClient() as client:
        for case in cases:
            t = perf_counter()
            resp = client.system_one(state={"message": case["query"]}, questions=questions)
            latency_ms = (perf_counter() - t) * 1000

            route = resp.choices["route"].choice
            route_conf = float(resp.choices["route"].confidence)
            probs = {
                t_.topic_id: float(resp.nouls[f"topic_{t_.topic_id}"].noul)
                for t_ in KNOWLEDGE_TOPICS
            }
            ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
            selected = {tid for tid, p in ranked if p >= topic_threshold}
            capped = {tid for tid, _ in ranked[:max_topics]} if len(selected) > max_topics else selected
            selected = selected & capped if len(selected) > max_topics else selected

            rows.append({
                "id": case["id"],
                "query": case["query"],
                "expected": case["expected_topics"],
                "route": route,
                "route_conf": route_conf,
                "route_below_gate": route_conf < route_threshold,
                "selected": selected,
                "top_prob": ranked[0][1],
                "top_topic": ranked[0][0],
                "latency_ms": latency_ms,
                "tokens": _usage_tokens(resp),
                "model": getattr(resp, "model", None),
            })
    return rows


def score(rows) -> dict:
    tp = fp = fn = 0
    exact = neg_ok = neg_total = 0
    for r in rows:
        exp, sel = r["expected"], r["selected"]
        tp += len(exp & sel)
        fp += len(sel - exp)
        fn += len(exp - sel)
        if exp == sel:
            exact += 1
        if not exp:
            neg_total += 1
            if not sel:
                neg_ok += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    lat = sorted(r["latency_ms"] for r in rows)
    toks = [r["tokens"] for r in rows if r["tokens"] is not None]
    return {
        "cases": len(rows),
        "topic_precision": round(prec, 4),
        "topic_recall": round(rec, 4),
        "topic_f1": round(f1, 4),
        "exact_set_match": round(exact / len(rows), 4) if rows else 0.0,
        "negatives": neg_total,
        "negative_abstain_ok": neg_ok,
        "route_below_gate_pct": round(sum(r["route_below_gate"] for r in rows) / len(rows), 4) if rows else 0.0,
        "latency_median_ms": round(lat[len(lat) // 2]) if lat else None,
        "latency_p95_ms": round(lat[max(0, int(len(lat) * 0.95) - 1)]) if lat else None,
        "tokens_total": sum(toks) if toks else None,
        "tokens_per_case": round(sum(toks) / len(toks)) if toks else None,
    }


def main():
    ap = ArgumentParser()
    ap.add_argument("--cases", default=str(FIXTURES / "rag_retrieval_cases.json"))
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--route-threshold", type=float, default=0.80)
    ap.add_argument("--topic-threshold", type=float, default=0.70)
    ap.add_argument("--max-topics", type=int, default=3)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    cases = load_cases(Path(args.cases))
    if args.offset:
        cases = cases[args.offset:]
    if args.limit:
        cases = cases[: args.limit]

    rows = run(cases, route_threshold=args.route_threshold,
               topic_threshold=args.topic_threshold, max_topics=args.max_topics)

    print(f"{'id':<16} {'route':<20} {'cf':>5} {'exp':<18} {'selected':<24} {'ms':>5}")
    print("-" * 92)
    for r in rows:
        exp = ",".join(sorted(r["expected"])) or "(none)"
        sel = ",".join(sorted(r["selected"])) or "(none)"
        mark = "OK " if r["expected"] == r["selected"] else "MIS"
        gate = "!" if r["route_below_gate"] else " "
        print(f"{r['id']:<16} {r['route']:<20} {r['route_conf']:>4.2f}{gate} {exp[:17]:<18} {sel[:23]:<24} {r['latency_ms']:>5.0f}  {mark}")

    summary = score(rows)
    models = sorted({r["model"] for r in rows if r.get("model")})
    summary["model"] = models[0] if len(models) == 1 else models
    print("\n== summary ==")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"summary": summary, "rows": [
                {**r, "expected": sorted(r["expected"]), "selected": sorted(r["selected"])}
                for r in rows]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
