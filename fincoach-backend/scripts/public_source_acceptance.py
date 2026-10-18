"""Explicitly authorized real public acceptance. Run inside the Desktop probe process."""
import json
import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.research_recovery_probe import run_public_probe
from app.rag.public_source_store import PublicSourceStore
from app.rag.web_research import ResearchOutcome


def save(directory, name, result):
    target = directory / (name + ".json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    temporary.replace(target)
    print(json.dumps({"case": name, "complete": result["complete_answer"],
        "elapsed_ms": result["elapsed_ms"], "parts": result["part_coverage"],
        "answer": result["answer"], "reuse": result["source_reuse"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='/tmp/public-source-acceptance')
    args = parser.parse_args()
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    variants = ["how do i apply STR, what document do i need",
        "How do I apply for Sumbangan Tunai Rahmah, and what supporting documents are needed?",
        "How do I apply for Sumbangan Tunai Rahmah, and which documents are required for married applicants?"]
    results = []
    with TemporaryDirectory(prefix="fincoach-acceptance-") as root:
        for i, question in enumerate(variants):
            for j in range(2):
                store = PublicSourceStore(Path(root) / f"cold-{i}-{j}")
                result = run_public_probe(question, warmup=i == j == 0, source_store=store)
                save(directory, f"str-cold-{i}-{j}", result)
                results.append(result)
                if i == j == 0:
                    warm_store = store
        warm = run_public_probe(variants[0], source_store=warm_store)
        save(directory, "str-warm", warm)
        results.append(warm)
        # A simulated fetch outage uses already fetched fresh public pages;
        # interpretation/writer/verifier remain real. Never label this a live outage.
        with patch("app.rag.web_research.extract_passages", return_value={}), \
             patch("app.rag.research_gap_batch.research_evidence", return_value=ResearchOutcome(reason="simulated_fetch_outage")), \
             patch("app.rag.research_policy.research_evidence", return_value=ResearchOutcome(reason="simulated_fetch_outage")):
            outage = run_public_probe(variants[0], source_store=warm_store)
        outage["simulated_public_fetch_outage"] = True
        save(directory, "str-simulated-fetch-outage", outage)
        for name, question in [
            ("akpk", "How do I apply for AKPK's Debt Management Programme, who is eligible, and what documents do I need?"),
            ("epf", "How do I apply for EPF education withdrawal, who qualifies, and what documents do I need?"),
            ("sara", "How do I apply for SARA assistance? Explain the eligibility and application process in English.")]:
            result = run_public_probe(question)
            save(directory, name, result)
            results.append(result)
    passed = all(r['complete_answer'] for r in results) and outage['complete_answer']
    (directory/'gate.json').write_text(json.dumps(dict(automatic_coverage_gate=passed,
        manual_category_citation_review_required=True, deploy_authorized_by_results=False)))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
