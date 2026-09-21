"""Jev multi-label ACTION + topic detection eval (isolated requests).

Tests the "independent Noul per action" candidate: one system_one call per case
asks a yes/no Noul for each supported action, a yes/no Noul for each knowledge
topic, plus a positive-evidence casual Noul. Python combines the answers into a
delivered task set and compares against human ground truth.

Measures (primary first):
  - task_set_recall   : did we detect every requested action? (the key metric)
  - task_set_precision: did we avoid extra unwanted actions?
  - task_exact        : full set matched exactly
  - topic P/R         : topic detection (parent/child sets allowed by labels)
  - personal_access   : requires_personal_records predicted correctly
  - unneeded_clarify / missed_clarify
  - latency, input/output tokens (separately)

This is isolated evaluation only. No CoachingService wiring, no personal data
sent, validator untouched. Action detection is a NEW task here, not assumed.
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
DEV_CASES = FIXTURES / "jev_action_dev_cases.json"

# id -> expected monthly-cadence bool, for scoring parameter resolution apart
# from intent. Populated from the dataset at load time.
_EXP_CADENCE: dict[str, bool] = {}


def _load_expected_cadence(cases):
    for c in cases:
        if "expected_monthly_cadence" in c:
            _EXP_CADENCE[c["id"]] = bool(c["expected_monthly_cadence"])


def load_labels(path):
    """Return {case_id: case} from the versioned label dataset.

    Scoring joins predictions to THESE labels by id — never to the labels
    frozen inside a predictions file — so a label edit takes effect on replay
    without re-querying Jev, and predictions stay pure model output.
    """
    cases = json.loads(Path(path).read_text(encoding="utf-8"))["cases"]
    _load_expected_cadence(cases)
    return {c["id"]: c for c in cases}

# Personal (owner-scoped) actions — firing any implies requires_personal_records.
PERSONAL_ACTIONS = {
    "get_spending_summary", "get_budget_status", "get_savings_goals",
    "get_weekly_savings_plan", "predict_savings", "get_cashflow_forecast",
    "get_financial_overview", "get_financial_profile", "get_upcoming_reminders",
    "search_transactions", "prepare_reminder", "prepare_report",
}

# Action-detection questions. Phrased as "requested as an OUTPUT, not merely
# mentioned as the basis for something else" to separate output from mention.
ACTION_QUESTIONS = {
    "get_spending_summary": "Is the user asking to see how much they have spent, or a summary of their own recorded expenses/transactions?",
    "get_budget_status": "Is the user asking whether they are over/under budget, or to see their own budget status?",
    "get_savings_goals": "Is the user asking to see their own savings goals or goal progress?",
    "get_weekly_savings_plan": "Is the user asking to create or revise a personal savings plan (a schedule of contribution amounts)? Include requests with no specified contribution frequency. Exclude definitions of what a savings plan is, viewing goal progress, a prediction alone, and explicitly declined plans.",
    "predict_savings": "Is the user requesting, as an output, a prediction/estimate of how much they will save in future?",
    "get_cashflow_forecast": "Is the user requesting, as an output, a cashflow forecast of whether their money lasts until month end (NOT merely using cashflow as the basis for another plan)?",
    "get_financial_overview": "Is the user asking for a broad overview of their overall finances or what to prioritise first?",
    "get_financial_profile": "Is the user asking about their own financial profile, income source, or coaching settings?",
    "get_upcoming_reminders": "Is the user asking to see their existing upcoming bills/reminders (NOT to create a new one)?",
    "search_transactions": "Is the user asking to find/search/list specific individual transactions?",
    "prepare_reminder": "Is the user asking to create/set a NEW reminder or alert (NOT merely to view existing ones, and not while declining one)?",
    "prepare_report": "Is the user asking to generate/create/download a NEW report or PDF (not while declining one)?",
    # eduB (frozen dev baseline). eduB2 (contrasting-examples) is preserved only
    # as jev_action_preds_eduB2.json for comparison, not used as the candidate.
    "education": (
        "Does the user want general financial knowledge or guidance about a financial concept, product, scheme, or rule: "
        "an explanation, definition, how-to, or advice (for example how it works, whether it helps or is worthwhile, "
        "whether it is safe, or how to use or avoid it)? "
        "Answer yes for general 'how do I / can X help / is X safe / how to avoid' questions about finance topics. "
        "Answer no if the request is only about the user's own recorded figures, or is purely an action such as creating a reminder or generating a report."
    ),
}
CASUAL_QUESTION = "Is this message purely small talk, a greeting, thanks, or non-finance chit-chat with no financial request?"

# Parameter question, scored SEPARATELY from intent. The handler only supports
# weekly cadence; an explicit monthly request must be caught so Python can
# clarify rather than silently returning a weekly plan.
PARAM_QUESTIONS = {
    "plan_monthly_cadence": "If the user is asking for a savings plan, are they explicitly requesting MONTHLY contributions (contribute once per month), as opposed to weekly, another cadence, or no stated cadence? 'For next month' describes the planning period, not the cadence — answer no for that.",
}


def _topic_label(t) -> str:
    return t.canonical_terms[0] if t.canonical_terms else t.topic_id


def build_questions():
    from typesafe_sdk import Noul

    q = {f"act_{name}": Noul(instructions=text) for name, text in ACTION_QUESTIONS.items()}
    q["casual"] = Noul(instructions=CASUAL_QUESTION)
    for name, text in PARAM_QUESTIONS.items():
        q[f"param_{name}"] = Noul(instructions=text)
    for t in KNOWLEDGE_TOPICS:
        q[f"topic_{t.topic_id}"] = Noul(instructions=(
            f"Is the user's message substantively about this Malaysian personal-finance topic: "
            f"{_topic_label(t)} ({', '.join(t.canonical_terms)})?"
        ))
    return q


def _history_text(case, char_limit=4000) -> str:
    turns = case.get("history", [])
    if not turns:
        return ""
    text = "\n".join(f"{m['role']}: {m['content']}" for m in turns)
    return text[-char_limit:]


def decide(act_probs, topic_probs, casual_p, *, pos: float, neg: float, max_actions: int):
    """Combine independent Noul probabilities into a delivered task set + flags.

    Pure function of raw probabilities so thresholds can be swept OFFLINE over
    the same saved predictions. `pos` accepts an action/topic; `neg` is the
    ceiling for a confident NO — anything in (neg, pos) is an uncertain band and,
    for actions, contributes to a clarification signal rather than a decision.
    """
    accepted = {name: p for name, p in act_probs.items() if p >= pos}
    # Education is a real action Noul; it is accepted on its own evidence only.
    # No automatic topic->education promotion (topic = relevant info, not intent).
    uncertain_actions = {name for name, p in act_probs.items() if neg < p < pos}
    topics = {tid for tid, p in topic_probs.items() if p >= pos}

    # Cap to the most probable actions when more clear the bar than the handler
    # limit; keep the strongest so precision is not sunk by a long tail.
    if len(accepted) > max_actions:
        accepted = dict(sorted(accepted.items(), key=lambda kv: kv[1], reverse=True)[:max_actions])
    actions = set(accepted)

    # Positive-evidence casual: casual only with its OWN support AND nothing
    # financial fired. Absence of actions alone never implies casual.
    is_casual = casual_p >= pos and not actions and not topics
    if is_casual:
        actions = {"casual"}

    # Uncertain -> clarification candidate: no confident action, not casual.
    # An uncertain-band action (something half-detected) strengthens the signal.
    uncertain = (not actions and not is_casual) or bool(uncertain_actions and not actions)

    requires_personal = bool(actions & PERSONAL_ACTIONS)
    return {
        "actions": actions, "topics": topics, "casual": is_casual,
        "uncertain": uncertain, "requires_personal": requires_personal,
        "casual_p": casual_p,
        "top_actions": sorted(act_probs.items(), key=lambda kv: kv[1], reverse=True)[:4],
    }


def query(cases):
    """One live Jev call per case. Saves ALL raw action/topic/casual
    probabilities so thresholds can be swept offline without re-querying."""
    from typesafe_sdk import TypeSafeClient
    questions = build_questions()
    preds = []
    with TypeSafeClient() as client:
        for case in cases:
            state = {"message": case["query"]}
            hist = _history_text(case)
            if hist:
                state["recent_conversation"] = hist
            t = perf_counter()
            resp = client.system_one(state=state, questions=questions)
            latency_ms = (perf_counter() - t) * 1000
            u = getattr(resp, "usage", None)
            preds.append({
                "id": case["id"], "category": case["category"], "query": case["query"],
                "exp_actions": list(case["expected_actions"]),
                "exp_topics": list(case["expected_topics"]),
                "exp_personal": case["requires_personal_records"],
                "exp_clarify": case["expected_clarification"],
                "act_probs": {name: float(resp.nouls[f"act_{name}"].noul) for name in ACTION_QUESTIONS},
                "topic_probs": {t_.topic_id: float(resp.nouls[f"topic_{t_.topic_id}"].noul) for t_ in KNOWLEDGE_TOPICS},
                "param_probs": {name: float(resp.nouls[f"param_{name}"].noul) for name in PARAM_QUESTIONS},
                "casual_p": float(resp.nouls["casual"].noul),
                "latency_ms": latency_ms,
                "in_tok": getattr(u, "input_tokens", None), "out_tok": getattr(u, "output_tokens", None),
                "model": getattr(resp, "model", None),
            })
    return preds


def apply(preds, labels, *, pos, neg, max_actions):
    """Join raw predictions to the versioned LABELS by case id, then decide at
    the given thresholds. Pure/offline — no network. Expected labels come from
    `labels` (the dataset), NOT from any exp_* frozen in the predictions file.
    """
    pred_ids = {p["id"] for p in preds}
    label_ids = set(labels)
    missing = pred_ids - label_ids
    if missing:
        raise ValueError(f"predictions reference case ids absent from label dataset: {sorted(missing)}")
    rows = []
    for p in preds:
        c = labels[p["id"]]
        d = decide(p["act_probs"], p["topic_probs"], p["casual_p"],
                   pos=pos, neg=neg, max_actions=max_actions)
        rows.append({
            "id": p["id"], "category": c["category"], "query": c["query"],
            "exp_actions": set(c["expected_actions"]), "exp_topics": set(c["expected_topics"]),
            "exp_personal": c["requires_personal_records"], "exp_clarify": c["expected_clarification"],
            "got_actions": d["actions"], "got_topics": d["topics"],
            "got_personal": d["requires_personal"], "got_uncertain": d["uncertain"],
            "casual_p": d["casual_p"], "top_actions": d["top_actions"],
            "param_probs": p.get("param_probs", {}),
            "latency_ms": p["latency_ms"], "in_tok": p["in_tok"], "out_tok": p["out_tok"],
            "model": p["model"],
        })
    return rows


def score(rows, *, param_pos=0.70):
    tp=fp=fn=0; exact=0; ttp=tfp=tfn=0
    personal_ok=0; unneeded_clar=0; missed_clar=0
    for r in rows:
        ea, ga = r["exp_actions"], r["got_actions"]
        tp+=len(ea&ga); fp+=len(ga-ea); fn+=len(ea-ga)
        if ea==ga: exact+=1
        et, gt = r["exp_topics"], r["got_topics"]
        ttp+=len(et&gt); tfp+=len(gt-et); tfn+=len(et-gt)
        if r["got_personal"]==r["exp_personal"]: personal_ok+=1
        # Clarify is predicted when EITHER nothing confident fired (uncertain)
        # OR an accepted plan carries an unsupported monthly cadence.
        monthly = r.get("param_probs", {}).get("plan_monthly_cadence", 0.0) >= param_pos
        plan_fired = "get_weekly_savings_plan" in r["got_actions"]
        pred_clar = r["got_uncertain"] or (plan_fired and monthly)
        if pred_clar and not r["exp_clarify"]: unneeded_clar+=1
        if not pred_clar and r["exp_clarify"]: missed_clar+=1
    # Cadence parameter accuracy, scored ONLY on labelled plan cases, independent
    # of intent — a correct plan classification must not hide a wrong schedule.
    cad_total=cad_ok=0
    for r in rows:
        exp_m=_EXP_CADENCE.get(r["id"])
        if exp_m is None: continue
        got_m=r.get("param_probs", {}).get("plan_monthly_cadence", 0.0) >= param_pos
        cad_total+=1; cad_ok+=(got_m==exp_m)
    def pr(a,b): return round(a/b,4) if b else 0.0
    lat=sorted(r["latency_ms"] for r in rows)
    intok=[r["in_tok"] for r in rows if r["in_tok"] is not None]
    outtok=[r["out_tok"] for r in rows if r["out_tok"] is not None]
    return {
        "cases": len(rows),
        "task_recall": pr(tp,tp+fn), "task_precision": pr(tp,tp+fp),
        "task_exact": pr(exact,len(rows)),
        "topic_recall": pr(ttp,ttp+tfn), "topic_precision": pr(ttp,ttp+tfp),
        "personal_access_acc": pr(personal_ok,len(rows)),
        "cadence_acc": pr(cad_ok,cad_total), "cadence_cases": cad_total,
        "unneeded_clarify": unneeded_clar, "missed_clarify": missed_clar,
        "latency_median_ms": round(lat[len(lat)//2]) if lat else None,
        "latency_p95_ms": round(lat[max(0,int(len(lat)*0.95)-1)]) if lat else None,
        "in_tok_total": sum(intok) if intok else None,
        "out_tok_total": sum(outtok) if outtok else None,
        "tok_per_case": round((sum(intok)+sum(outtok))/len(rows)) if intok and outtok else None,
    }


SMOKE_IDS = [
    "multi-plan-predict-en",   # multi-action, the first-match-wins bug
    "comb-plan-compound-en",   # combined: plan + education, topic=compound_interest
    "plan-weekly-ms",          # Malay single action
    "neg-explain-noplan-en",   # negation: must NOT fire plan
    "cashflow-basis-en",       # output-vs-mention: cashflow is basis only
    "edu-akpk-saya-ms",        # Malay 'saya' must not force personal read
    "casual-joke-en",          # positive casual
    "amb-help-en",             # ambiguous -> clarify
]


def _print_run(rows, label):
    print(f"\n### {label}")
    print(f"{'id':<22} {'exp_actions':<32} {'got_actions':<32} {'ms':>5}")
    print("-"*100)
    for r in rows:
        ea=",".join(sorted(r["exp_actions"])) or "(none)"
        ga=",".join(sorted(r["got_actions"])) or "(none)"
        mark="OK " if r["exp_actions"]==r["got_actions"] else "MIS"
        print(f"{r['id']:<22} {ea[:31]:<32} {ga[:31]:<32} {r['latency_ms']:>5.0f}  {mark}")
        if r["exp_actions"]!=r["got_actions"]:
            tops=", ".join(f"{n}={p:.2f}" for n,p in r["top_actions"])
            print(f"{'':<22}   top: {tops}  casual_p={r['casual_p']:.2f}")


def main():
    ap=ArgumentParser()
    ap.add_argument("--cases", default=str(DEV_CASES))
    ap.add_argument("--smoke", action="store_true", help="run only the 8 representative cases")
    ap.add_argument("--pos", type=float, default=0.70)
    ap.add_argument("--neg", type=float, default=0.40)
    ap.add_argument("--max-actions", type=int, default=4)
    ap.add_argument("--sweep", action="store_true", help="offline threshold sweep over one query run")
    ap.add_argument("--preds-out", default="", help="save raw predictions for offline reuse")
    ap.add_argument("--preds-in", default="", help="load raw predictions instead of querying Jev")
    ap.add_argument("--json-out", default="")
    args=ap.parse_args()

    # Labels (incl. cadence) always come from the versioned dataset and are
    # joined to predictions by id. This is the single source of truth for
    # scoring, so a label edit takes effect on replay without re-querying.
    labels = load_labels(args.cases)

    if args.preds_in:
        preds=json.loads(Path(args.preds_in).read_text(encoding="utf-8"))["preds"]
    else:
        payload=json.loads(Path(args.cases).read_text(encoding="utf-8"))
        cases=payload["cases"]
        if args.smoke:
            by_id={c["id"]:c for c in cases}
            cases=[by_id[i] for i in SMOKE_IDS if i in by_id]
        preds=query(cases)

    if args.preds_out:
        Path(args.preds_out).write_text(json.dumps({"preds":preds}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote raw predictions: {args.preds_out}")

    if args.sweep:
        print(f"\n== offline threshold sweep ({len(preds)} cases, one query run) ==")
        print(f"{'pos':>4} {'neg':>4} {'t_rec':>6} {'t_prec':>7} {'exact':>6} {'top_rec':>7} {'top_prec':>8} {'pers':>5} {'unneed_clar':>11} {'miss_clar':>9}")
        for pos in (0.60, 0.70, 0.80):
            neg = round(1.0 - pos, 2)
            rows=apply(preds, labels, pos=pos, neg=neg, max_actions=args.max_actions)
            s=score(rows)
            print(f"{pos:>4.2f} {neg:>4.2f} {s['task_recall']:>6.3f} {s['task_precision']:>7.3f} "
                  f"{s['task_exact']:>6.3f} {s['topic_recall']:>7.3f} {s['topic_precision']:>8.3f} "
                  f"{s['personal_access_acc']:>5.3f} {s['unneeded_clarify']:>11} {s['missed_clarify']:>9}")
        return

    rows=apply(preds, labels, pos=args.pos, neg=args.neg, max_actions=args.max_actions)
    _print_run(rows, f"pos={args.pos} neg={args.neg}")
    s=score(rows)
    models=sorted({r['model'] for r in rows if r.get('model')})
    s['model']=models[0] if len(models)==1 else models
    print("\n== summary ==")
    for k,v in s.items(): print(f"  {k}: {v}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"summary":s,"rows":[
            {**r,"exp_actions":sorted(r["exp_actions"]),"got_actions":sorted(r["got_actions"]),
             "exp_topics":sorted(r["exp_topics"]),"got_topics":sorted(r["got_topics"]),
             "top_actions":[[n,round(p,3)] for n,p in r["top_actions"]]} for r in rows]},
            ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"\nwrote {args.json_out}")


if __name__=="__main__":
    main()
