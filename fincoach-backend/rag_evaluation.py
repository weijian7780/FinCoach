"""Reproducible source-level RAG evaluation (no answer-generation calls).

Dense mode uses local corpus embeddings. Hybrid mode calls the production
retriever and performs read-only knowledge RPCs; fallback is rejected rather
than mislabeled as a hybrid score. Candidate labels are not reviewed evidence.
"""
from argparse import ArgumentParser
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter

from app.config import RETRIEVE_CANDIDATES, RETRIEVE_K, RETRIEVE_SCORE_MARGIN, RETRIEVE_THRESHOLD
from app.rag.evaluation import EvaluationCase, evaluate_rankings

DEFAULT_CASES = Path(__file__).parent / "tests/fixtures/rag_retrieval_cases.json"


def load_cases(path: Path) -> list[EvaluationCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload["cases"]
    cases = []
    for item in payload:
        sources = item.get("expected_sources")
        if sources is None:
            sources = [item["expected_source"]] if item.get("expected_source") else []
        cases.append(EvaluationCase(item["id"], item["query"], tuple(sources),
                                    tuple(item.get("history", [])), item.get("language", "unspecified"),
                                    item.get("label_status", "legacy_unreviewed")))
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Dataset must contain nonempty, unique case IDs")
    return cases


def run_evaluation(cases_path: Path, *, mode: str = "dense", require_reviewed: bool = False) -> dict:
    import numpy as np
    from app.embeddings import embed_texts
    from app.rag.ingestion import load_documents
    from app.rag.retrieval import RetrievedChunk, retrieve, select_retrieved_chunks
    from app.rag.query_analysis import analyze_knowledge_query
    from ingest import CORPUS_DIR, build_chunks

    cases = load_cases(cases_path)
    if require_reviewed and any(case.label_status != "human_reviewed" for case in cases):
        raise ValueError("Final evaluation requires human-reviewed relevance labels")
    chunks = build_chunks(load_documents(CORPUS_DIR))
    known_sources = {chunk.source for chunk in chunks}
    unknown = {source for case in cases for source in case.expected_sources} - known_sources
    if unknown:
        raise ValueError(f"Unknown labelled sources: {sorted(unknown)}")
    corpus_fingerprint = hashlib.sha256(json.dumps(
        [(chunk.source, chunk.chunk_index, chunk.content) for chunk in chunks], ensure_ascii=False
    ).encode()).hexdigest()
    ranked_sources, returned_sources, timings = {}, {}, {}
    setup_start = perf_counter()
    if mode == "dense":
        document_vectors = np.asarray(embed_texts([chunk.content for chunk in chunks]), dtype=np.float32)
    elif mode != "hybrid":
        raise ValueError("mode must be dense or hybrid")
    setup_ms = (perf_counter() - setup_start) * 1000
    for case in cases:
        start = perf_counter()
        if mode == "dense":
            query_vector = np.asarray(embed_texts([case.query])[0], dtype=np.float32)
            scores = query_vector @ document_vectors.T
            indices = np.argsort(-scores, kind="stable")
            ranked_sources[case.case_id] = [chunks[index].source for index in indices]
            candidates = [RetrievedChunk(int(index) + 1, chunks[index].title, chunks[index].source,
                           chunks[index].page, chunks[index].chunk_index, chunks[index].content,
                           float(scores[index])) for index in indices[:max(RETRIEVE_K, RETRIEVE_CANDIDATES)]]
            returned = select_retrieved_chunks(candidates, k=RETRIEVE_K, threshold=RETRIEVE_THRESHOLD,
                                               score_margin=RETRIEVE_SCORE_MARGIN)
        else:
            trace = {}
            analysis = analyze_knowledge_query(case.query, history=list(case.history))
            returned = retrieve(case.query, analysis=analysis, trace=trace)
            if trace.get("mode") != "hybrid":
                raise RuntimeError("Hybrid RPC unavailable: refusing to report fallback as hybrid retrieval")
            ranked_sources[case.case_id] = trace["ranked_sources"]
        timings[case.case_id] = (perf_counter() - start) * 1000
        returned_sources[case.case_id] = [chunk.source or "" for chunk in returned]
    metrics = asdict(evaluate_rankings(cases, ranked_sources, returned_sources))
    for row in metrics["per_case"]:
        row["retrieval_ms"] = timings[row["case_id"]]
    metrics.update({
        "schema_version": 2, "mode": mode, "evaluation_unit": "unique_source_document",
        "ranking_scope": "all_local_dense_chunks" if mode == "dense" else "merged_hybrid_candidate_pool_before_topic_reservation",
        "history_mode": "raw_query_only" if mode == "dense" else "production_topic_inheritance",
        "dataset_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "local_corpus_sha256": corpus_fingerprint,
        "database_corpus_verified": False if mode == "hybrid" else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "label_status": "human_reviewed" if all(c.label_status == "human_reviewed" for c in cases) else "UNREVIEWED_NOT_FINAL",
        "threshold": RETRIEVE_THRESHOLD, "score_margin": RETRIEVE_SCORE_MARGIN,
        "candidate_k": RETRIEVE_CANDIDATES, "returned_k": RETRIEVE_K,
        "setup_ms": setup_ms, "retrieval_ms_p50": float(np.percentile(list(timings.values()), 50)),
        "retrieval_ms_p95": float(np.percentile(list(timings.values()), 95)),
        "latency_note": "Sequential single pass; cold-start effects possible; excludes LLM generation. Modes have different setup costs.",
    })
    return metrics


def write_reports(metrics: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = metrics["per_case"]
    with (output / "per-query.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    lines = ["# RAG retrieval evaluation", "", f"Mode: {metrics['mode']}", f"Labels: **{metrics['label_status']}**", "",
             "| Metric | Value |", "|---|---:|"]
    for key in ("case_count", "precision", "recall", "f1", "precision_at_3", "recall_at_3", "f1_at_3", "mrr", "abstention_accuracy", "retrieval_ms_p50", "retrieval_ms_p95"):
        lines.append(f"| {key} | {metrics[key]} |")
    lines += ["", "Retrieval quality is not answer correctness. See the evaluation protocol for denominators and limitations."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def passes_acceptance(metrics: dict, *, min_hit_at_3: float, min_mrr: float,
                      min_expected_retained: float, max_average_sources: float) -> bool:
    return (metrics["hit_at_3"] >= min_hit_at_3 and metrics["mrr"] >= min_mrr
            and metrics["expected_retained"] >= min_expected_retained
            and metrics["average_returned_sources"] <= max_average_sources)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--mode", choices=("dense", "hybrid"), default="dense")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-reviewed", action="store_true")
    parser.add_argument("--check-acceptance", action="store_true", help="Opt in to legacy development thresholds; not thesis success criteria")
    parser.add_argument("--min-hit-at-3", type=float, default=1.0)
    parser.add_argument("--min-mrr", type=float, default=0.98)
    parser.add_argument("--min-expected-retained", type=float, default=1.0)
    parser.add_argument("--max-average-sources", type=float, default=2.0)
    args = parser.parse_args()
    metrics = run_evaluation(args.cases, mode=args.mode, require_reviewed=args.require_reviewed)
    if args.output:
        write_reports(metrics, args.output)
    print(json.dumps({key: value for key, value in metrics.items() if key != "per_case"}, indent=2))
    if args.check_acceptance and not passes_acceptance(metrics, min_hit_at_3=args.min_hit_at_3,
        min_mrr=args.min_mrr, min_expected_retained=args.min_expected_retained, max_average_sources=args.max_average_sources):
        raise SystemExit("RAG evaluation acceptance criteria failed")
