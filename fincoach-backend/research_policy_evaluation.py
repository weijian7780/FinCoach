"""Run the versioned public-question interpretation evaluation against the provider."""

import json
import sys
from pathlib import Path

from app.llm import CoachRequestBudget, generate_structured_result
from app.rag.research_policy import interpret_question


def main() -> int:
    fixture = ("research_policy_unseen_eval.json" if "--unseen" in sys.argv
               else "research_policy_eval.json")
    cases = json.loads((Path(__file__).parent / "tests" / "fixtures" /
                        fixture).read_text(encoding="utf-8"))
    failed = 0
    for case in cases:
        history = [{"role": "user", "content": text} for text in case["history"]]
        plan = interpret_question(
            case["question"], history,
            base_personal=False, base_external=False,
            generate=generate_structured_result,
            budget=CoachRequestBudget.start(),
        )
        checks = {
            "interpreted": plan.interpreted,
            "personal": plan.needs_personal == case["personal"],
            "external": plan.needs_external == case["external"],
            # A personal-only read has no external source freshness decision;
            # the backend date parser still controls its actual read period.
            "scope": not case["external"] or plan.time_scope == case["scope"],
            "period": not case.get("period") or plan.period == case["period"],
            "entities": all(
                expected.casefold() in " ".join(plan.entities).casefold()
                for expected in case.get("entities", [])
            ),
        }
        if not all(checks.values()):
            failed += 1
        print(json.dumps({
            "id": case["id"], "split": case["split"],
            "passed": all(checks.values()),
            "failed_fields": [key for key, okay in checks.items() if not okay],
            "topic": plan.topic, "entities": plan.entities,
        }))
    print(f"RESULT {len(cases) - failed}/{len(cases)} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
