"""Re-query ONLY the revised education Noul across all 67 cases; reuse every
other cached prediction. Valid because system_one questions are independent —
a question's answer does not depend on which other questions share the call.

Reports education hit/miss flips (improvements AND regressions) at pos=0.70,
then re-scores the full set with the spliced predictions.
"""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from jev_action_eval import ACTION_QUESTIONS, DEV_CASES, _history_text, _load_expected_cadence

load_dotenv()

import os
PREDS_IN = Path(os.environ.get("REQ_PREDS_IN", "jev_action_preds.json"))
PREDS_OUT = Path(os.environ.get("REQ_PREDS_OUT", "jev_action_preds_eduB.json"))
POS = 0.70


def main():
    from typesafe_sdk import Noul, TypeSafeClient

    dev = json.loads(DEV_CASES.read_text(encoding="utf-8"))["cases"]
    _load_expected_cadence(dev)
    by_id = {c["id"]: c for c in dev}
    preds = json.loads(PREDS_IN.read_text(encoding="utf-8"))["preds"]

    edu_q = {"act_education": Noul(instructions=ACTION_QUESTIONS["education"])}
    flips = []
    lat = []
    with TypeSafeClient() as client:
        for p in preds:
            case = by_id[p["id"]]
            state = {"message": p["query"]}
            hist = _history_text(case)
            if hist:
                state["recent_conversation"] = hist
            t = perf_counter()
            resp = client.system_one(state=state, questions=edu_q)
            lat.append((perf_counter() - t) * 1000)
            new_edu = float(resp.nouls["act_education"].noul)
            old_edu = p["act_probs"]["education"]

            exp_edu = "education" in p["exp_actions"]
            old_hit = (old_edu >= POS) == exp_edu
            new_hit = (new_edu >= POS) == exp_edu
            if old_hit != new_hit or abs(new_edu - old_edu) >= 0.15:
                flips.append({
                    "id": p["id"], "exp_edu": exp_edu,
                    "old": round(old_edu, 2), "new": round(new_edu, 2),
                    "kind": "IMPROVED" if (new_hit and not old_hit)
                            else "REGRESSED" if (old_hit and not new_hit)
                            else "shifted",
                    "query": p["query"][:50],
                })
            # splice ONLY education; everything else stays as cached
            p["act_probs"]["education"] = new_edu

    PREDS_OUT.write_text(json.dumps({"preds": preds}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"re-queried education on {len(preds)} cases; median {sorted(lat)[len(lat)//2]:.0f}ms\n")
    print("== education flips (hit/miss change or |delta|>=0.15) ==")
    for f in sorted(flips, key=lambda x: {"REGRESSED": 0, "IMPROVED": 1, "shifted": 2}[x["kind"]]):
        tag = {"exp_edu": "edu+" if f["exp_edu"] else "edu-"}["exp_edu"]
        print(f"  {f['kind']:<9} {tag:<5} {f['id']:<24} {f['old']:.2f}->{f['new']:.2f}  | {f['query']}")
    imp = sum(f["kind"] == "IMPROVED" for f in flips)
    reg = sum(f["kind"] == "REGRESSED" for f in flips)
    print(f"\n  improved: {imp}   regressed: {reg}   other shifts: {len(flips)-imp-reg}")
    print(f"\nwrote {PREDS_OUT}\nnow: python jev_action_eval.py --preds-in {PREDS_OUT} --sweep")


if __name__ == "__main__":
    main()
