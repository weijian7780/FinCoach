"""Document-level retrieval metrics, independent of models or databases.

Rankings are deduplicated by source before applying k=3. P@3 has a fixed
three-slot denominator; final-context precision uses actual returned sources.
Macro P/R/F1 cover answerable cases; negative cases have separate abstention
accuracy and contribute false positives to micro precision.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    query: str
    expected_sources: tuple[str, ...]
    history: tuple[dict, ...] = ()
    language: str = "unspecified"
    label_status: str = "legacy_unreviewed"


@dataclass(frozen=True)
class EvaluationResult:
    case_count: int
    hit_at_1: float
    hit_at_3: float
    mrr: float
    expected_retained: float
    average_returned_sources: float
    source_coverage_at_3: float
    precision_at_3: float
    recall_at_3: float
    f1_at_3: float
    precision: float
    recall: float
    f1: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    answerable_count: int
    unanswerable_count: int
    abstention_accuracy: float | None
    per_case: tuple[dict, ...]


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def _f1(precision, recall):
    return _ratio(2 * precision * recall, precision + recall)


def evaluate_rankings(cases: list[EvaluationCase], ranked_sources: dict[str, list[str]],
                      returned_sources: dict[str, list[str]]) -> EvaluationResult:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("evaluation case IDs must be unique")
    rows = []
    for case in cases:
        if case.case_id not in ranked_sources or case.case_id not in returned_sources:
            raise ValueError(f"Missing retrieval result for {case.case_id}; errors are not empty results")
        ranked = list(dict.fromkeys(ranked_sources[case.case_id]))
        returned = list(dict.fromkeys(returned_sources[case.case_id]))
        expected = set(case.expected_sources)
        top = ranked[:3]
        true_positive = len(expected.intersection(returned))
        p, r = _ratio(true_positive, len(returned)), _ratio(true_positive, len(expected))
        top_tp = len(expected.intersection(top))
        p3, r3 = top_tp / 3, _ratio(top_tp, len(expected))
        rank = next((i for i, source in enumerate(top, 1) if source in expected), None)
        rows.append({
            "case_id": case.case_id, "query": case.query, "language": case.language,
            "label_status": case.label_status, "answerable": bool(expected),
            "expected_sources": sorted(expected), "ranked_sources": ranked,
            "returned_sources": returned, "true_positives": true_positive,
            "false_positives": len(returned) - true_positive,
            "false_negatives": len(expected) - true_positive,
            "precision": p if expected else None, "recall": r if expected else None,
            "f1": _f1(p, r) if expected else None,
            "precision_at_3": p3 if expected else None,
            "recall_at_3": r3 if expected else None,
            "f1_at_3": _f1(p3, r3) if expected else None,
            "hit_at_1": float(bool(top and top[0] in expected)),
            "hit_at_3": float(rank is not None), "mrr_at_3": 1 / rank if rank else 0.0,
            "expected_retained": float(expected.issubset(returned)) if expected else None,
            "abstained_correctly": not returned if not expected else None,
            "top_3_true_positives": top_tp,
        })
    positives = [row for row in rows if row["answerable"]]
    negatives = [row for row in rows if not row["answerable"]]
    def mean(key): return _ratio(sum(row[key] for row in positives), len(positives))
    tp = sum(row["true_positives"] for row in rows)
    mp = _ratio(tp, sum(len(row["returned_sources"]) for row in rows))
    mr = _ratio(tp, sum(len(row["expected_sources"]) for row in rows))
    return EvaluationResult(
        case_count=len(rows), hit_at_1=mean("hit_at_1"), hit_at_3=mean("hit_at_3"),
        mrr=mean("mrr_at_3"), expected_retained=mean("expected_retained"),
        average_returned_sources=sum(len(row["returned_sources"]) for row in rows) / len(rows),
        source_coverage_at_3=_ratio(sum(row["top_3_true_positives"] for row in positives), sum(len(row["expected_sources"]) for row in positives)),
        precision_at_3=mean("precision_at_3"), recall_at_3=mean("recall_at_3"), f1_at_3=mean("f1_at_3"),
        precision=mean("precision"), recall=mean("recall"), f1=mean("f1"),
        micro_precision=mp, micro_recall=mr, micro_f1=_f1(mp, mr),
        answerable_count=len(positives), unanswerable_count=len(negatives),
        abstention_accuracy=(sum(row["abstained_correctly"] for row in negatives) / len(negatives) if negatives else None),
        per_case=tuple(rows),
    )
