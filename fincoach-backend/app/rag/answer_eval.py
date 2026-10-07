"""Answer-correctness scoring — the separate test layer named in the evaluation
protocol (`docs/rag-evaluation-protocol.md`, "Financial answer correctness is a
separate test layer").

This is NOT retrieval scoring. `app/rag/evaluation.py` scores whether the right
source DOCUMENTS were retrieved. This module scores whether the generated ANSWER
is grounded — the metric that decides whether `evidence` mode beats `legacy`
(evidence-validation plan, Task 1 / Task 7).

Pure and offline: no models, no network, no database. It takes recorded cases +
one verdict per case and rolls them into raw counts and `None`-safe rates. The
verdicts themselves come from human review (the answer key — Task 1b) or a
reviewed offline judge; producing them is not this module's job.

Four verdicts partition every answered case:
  * ``supported``   — the answer's claims are entailed by cited sources.
  * ``unsupported`` — the answer made a claim not grounded in a source, but did
                      not invent a specific fact (vague / off-target / weakly
                      grounded).
  * ``fabricated``  — the answer stated a made-up number, product name, policy,
                      or citation. This is the invariant-#2 breach and is
                      counted on its own because Task 7 adopts `evidence` only
                      if fabricated counts do NOT rise vs `legacy`.
  * ``refused``     — the answer declined / said "insufficient evidence" and made
                      no substantive claim.

Denominator rule (carried from the retrieval protocol): a refusal must NEVER
score as perfect grounding. ``grounding_precision`` is ``None`` — undefined, not
``1.0`` — when a bucket answered nothing (all refusals). Precision over an empty
answer set is meaningless, and reporting it as 1.0 would reward a coach that
refuses everything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---- Buckets: what kind of question, hence what correct behavior looks like --
CORPUS_ANSWERABLE = "corpus_answerable"   # answer is in the local corpus
WEB_ANSWERABLE = "web_answerable"         # needs web research (not in corpus)
UNANSWERABLE = "unanswerable"             # nothing can answer it; refusal is correct
BUCKETS = (CORPUS_ANSWERABLE, WEB_ANSWERABLE, UNANSWERABLE)

# ---- Verdicts: one per answered case, partitioning ---------------------------
SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
FABRICATED = "fabricated"
REFUSED = "refused"
VERDICTS = (SUPPORTED, UNSUPPORTED, FABRICATED, REFUSED)

# Everything that is not a refusal is an "answer" the coach committed to.
_ANSWERED = (SUPPORTED, UNSUPPORTED, FABRICATED)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AnswerCase:
    """One held-out question plus the reviewer's answer key.

    ``must_include_facts`` / ``acceptable_sources`` are the gold label a human
    fills in (Task 1b); they are not consumed by the count rollup here but travel
    with the case so the scorer's inputs are auditable and the fixture doubles as
    the review template.
    """

    case_id: str
    bucket: str
    query: str
    language: str = "unspecified"
    answerable: bool = True
    must_include_facts: tuple[str, ...] = ()
    acceptable_sources: tuple[str, ...] = ()
    label_status: str = "candidate_unreviewed"


@dataclass(frozen=True)
class BucketCounts:
    total: int
    supported: int
    unsupported: int
    fabricated: int
    refused: int

    @property
    def answered(self) -> int:
        return self.supported + self.unsupported + self.fabricated

    @property
    def grounding_precision(self) -> float | None:
        """supported / answered — ``None`` when the bucket answered nothing."""
        return self.supported / self.answered if self.answered else None

    @property
    def refusal_rate(self) -> float | None:
        return self.refused / self.total if self.total else None

    @property
    def fabrication_rate(self) -> float | None:
        """fabricated / total — the Task 7 gate metric (must not rise)."""
        return self.fabricated / self.total if self.total else None

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "supported": self.supported,
            "unsupported": self.unsupported,
            "fabricated": self.fabricated,
            "refused": self.refused,
            "answered": self.answered,
            "grounding_precision": self.grounding_precision,
            "refusal_rate": self.refusal_rate,
            "fabrication_rate": self.fabrication_rate,
        }


def _count_bucket(verdicts: list[str]) -> BucketCounts:
    return BucketCounts(
        total=len(verdicts),
        supported=verdicts.count(SUPPORTED),
        unsupported=verdicts.count(UNSUPPORTED),
        fabricated=verdicts.count(FABRICATED),
        refused=verdicts.count(REFUSED),
    )


def score_answer_counts(cases: list[AnswerCase], verdicts: dict[str, str]) -> dict:
    """Roll one arm's per-case verdicts into per-bucket + overall counts/rates.

    ``verdicts`` maps ``case_id -> verdict``. Every case must have a verdict:
    a missing result is an error, never an empty success (same rule the retrieval
    harness enforces). Rates use ``None`` where the denominator is zero, so a
    bucket of all-refusals reports ``grounding_precision = None``, not ``1.0``.
    """
    if not cases:
        raise ValueError("at least one answer case is required")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("answer case IDs must be unique")
    for case in cases:
        if case.bucket not in BUCKETS:
            raise ValueError(f"{case.case_id}: unknown bucket {case.bucket!r}")
    missing = [case.case_id for case in cases if case.case_id not in verdicts]
    if missing:
        raise ValueError(f"Missing verdicts for {missing}; errors are not empty results")
    bad = {cid: v for cid, v in verdicts.items() if v not in VERDICTS}
    if bad:
        raise ValueError(f"Unknown verdicts {bad}; allowed: {VERDICTS}")

    by_bucket: dict[str, list[str]] = {bucket: [] for bucket in BUCKETS}
    for case in cases:
        by_bucket[case.bucket].append(verdicts[case.case_id])
    all_verdicts = [verdicts[case.case_id] for case in cases]

    label_status = (
        "human_reviewed"
        if cases and all(c.label_status == "human_reviewed" for c in cases)
        else "UNREVIEWED_NOT_FINAL"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluation_unit": "generated_answer",
        "label_status": label_status,
        "case_count": len(cases),
        "overall": _count_bucket(all_verdicts).as_dict(),
        "by_bucket": {
            bucket: _count_bucket(by_bucket[bucket]).as_dict() for bucket in BUCKETS
        },
    }


def compare_answer_arms(metrics_by_arm: dict[str, dict]) -> dict:
    """Diff each arm against the ``legacy`` arm — the Task 7 comparison table.

    Expects the dict returned by ``score_answer_counts`` per arm, keyed by arm
    name (e.g. ``legacy@256``, ``legacy@1536``, ``evidence@1536``). A ``legacy``
    or ``legacy@256`` arm is the baseline; every other arm is diffed against it.
    ``None`` grounding precision (all-refusal bucket) yields a ``None`` delta —
    never a fabricated 0.0.
    """
    baseline_key = next(
        (k for k in ("legacy", "legacy@256") if k in metrics_by_arm),
        None,
    )
    if baseline_key is None:
        raise ValueError("no legacy baseline arm found (expected 'legacy' or 'legacy@256')")
    base = metrics_by_arm[baseline_key]

    def _delta(a: float | None, b: float | None) -> float | None:
        return a - b if (a is not None and b is not None) else None

    table: dict[str, dict] = {}
    for arm, metrics in metrics_by_arm.items():
        if arm == baseline_key:
            continue
        row: dict[str, dict] = {}
        for bucket in (*BUCKETS, "_overall_key"):
            key = "overall" if bucket == "_overall_key" else bucket
            b = base["overall"] if bucket == "_overall_key" else base["by_bucket"][bucket]
            m = metrics["overall"] if bucket == "_overall_key" else metrics["by_bucket"][bucket]
            row[key] = {
                "supported_delta": m["supported"] - b["supported"],
                "fabricated_delta": m["fabricated"] - b["fabricated"],
                "refused_delta": m["refused"] - b["refused"],
                "grounding_precision_delta": _delta(
                    m["grounding_precision"], b["grounding_precision"]
                ),
            }
        table[arm] = row
    return {"baseline": baseline_key, "arms": table}
