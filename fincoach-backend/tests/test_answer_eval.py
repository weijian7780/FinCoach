"""Tests for the answer-correctness scorer (app/rag/answer_eval.py).

The load-bearing test is the None-denominator rule: an all-refusal bucket must
report grounding_precision = None, never 1.0. That is the whole reason this layer
exists per the evaluation protocol — a coach that refuses everything must not
score as perfectly grounded.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rag.answer_eval import (
    BUCKETS,
    CORPUS_ANSWERABLE,
    FABRICATED,
    REFUSED,
    SUPPORTED,
    UNANSWERABLE,
    UNSUPPORTED,
    VERDICTS,
    WEB_ANSWERABLE,
    AnswerCase,
    compare_answer_arms,
    score_answer_counts,
)

FIXTURE = Path(__file__).parent / "fixtures" / "answer_eval_cases.json"


def _case(case_id, bucket, *, answerable=True, label="candidate_unreviewed"):
    return AnswerCase(
        case_id=case_id, bucket=bucket, query="q", answerable=answerable,
        label_status=label,
    )


# ---- The None-denominator rule ----------------------------------------------

def test_all_refusals_report_none_grounding_precision_not_one():
    cases = [_case("a", WEB_ANSWERABLE), _case("b", WEB_ANSWERABLE)]
    verdicts = {"a": REFUSED, "b": REFUSED}
    result = score_answer_counts(cases, verdicts)
    web = result["by_bucket"][WEB_ANSWERABLE]
    assert web["answered"] == 0
    assert web["grounding_precision"] is None  # NOT 1.0
    assert web["refusal_rate"] == 1.0


def test_grounding_precision_is_supported_over_answered():
    cases = [_case(c, CORPUS_ANSWERABLE) for c in ("a", "b", "c", "d")]
    # 2 supported, 1 unsupported, 1 refused -> answered = 3, precision = 2/3
    verdicts = {"a": SUPPORTED, "b": SUPPORTED, "c": UNSUPPORTED, "d": REFUSED}
    corpus = score_answer_counts(cases, verdicts)["by_bucket"][CORPUS_ANSWERABLE]
    assert corpus["answered"] == 3
    assert corpus["grounding_precision"] == pytest.approx(2 / 3)
    assert corpus["refusal_rate"] == pytest.approx(1 / 4)


def test_fabricated_is_counted_separately_as_the_task7_gate():
    cases = [_case(c, WEB_ANSWERABLE) for c in ("a", "b")]
    verdicts = {"a": FABRICATED, "b": SUPPORTED}
    web = score_answer_counts(cases, verdicts)["by_bucket"][WEB_ANSWERABLE]
    assert web["fabricated"] == 1
    assert web["fabrication_rate"] == pytest.approx(0.5)
    # fabricated counts as answered, so precision = 1 supported / 2 answered
    assert web["grounding_precision"] == pytest.approx(0.5)


# ---- Contract: counts partition, errors are not empty successes -------------

def test_counts_partition_the_total():
    cases = [_case(c, CORPUS_ANSWERABLE) for c in ("a", "b", "c", "d")]
    verdicts = {"a": SUPPORTED, "b": UNSUPPORTED, "c": FABRICATED, "d": REFUSED}
    overall = score_answer_counts(cases, verdicts)["overall"]
    assert (
        overall["supported"] + overall["unsupported"]
        + overall["fabricated"] + overall["refused"]
        == overall["total"] == 4
    )


def test_missing_verdict_raises_not_silently_scored():
    cases = [_case("a", WEB_ANSWERABLE), _case("b", WEB_ANSWERABLE)]
    with pytest.raises(ValueError, match="Missing verdicts"):
        score_answer_counts(cases, {"a": SUPPORTED})


def test_unknown_verdict_raises():
    cases = [_case("a", WEB_ANSWERABLE)]
    with pytest.raises(ValueError, match="Unknown verdicts"):
        score_answer_counts(cases, {"a": "looks_ok"})


def test_unknown_bucket_raises():
    cases = [_case("a", "made_up_bucket")]
    with pytest.raises(ValueError, match="unknown bucket"):
        score_answer_counts(cases, {"a": SUPPORTED})


def test_duplicate_case_ids_raise():
    cases = [_case("a", WEB_ANSWERABLE), _case("a", CORPUS_ANSWERABLE)]
    with pytest.raises(ValueError, match="unique"):
        score_answer_counts(cases, {"a": SUPPORTED})


def test_label_status_is_unreviewed_unless_every_case_reviewed():
    reviewed = score_answer_counts(
        [_case("a", WEB_ANSWERABLE, label="human_reviewed")], {"a": SUPPORTED}
    )
    assert reviewed["label_status"] == "human_reviewed"
    mixed = score_answer_counts(
        [
            _case("a", WEB_ANSWERABLE, label="human_reviewed"),
            _case("b", WEB_ANSWERABLE, label="candidate_unreviewed"),
        ],
        {"a": SUPPORTED, "b": SUPPORTED},
    )
    assert mixed["label_status"] == "UNREVIEWED_NOT_FINAL"


# ---- Arm comparison (Task 7 table) ------------------------------------------

def test_compare_arms_diffs_against_legacy_and_keeps_none_deltas():
    cases = [_case("a", WEB_ANSWERABLE), _case("b", WEB_ANSWERABLE)]
    arms = {
        "legacy@256": score_answer_counts(cases, {"a": REFUSED, "b": REFUSED}),
        "evidence@1536": score_answer_counts(cases, {"a": SUPPORTED, "b": REFUSED}),
    }
    table = compare_answer_arms(arms)
    assert table["baseline"] == "legacy@256"
    web = table["arms"]["evidence@1536"][WEB_ANSWERABLE]
    assert web["supported_delta"] == 1
    # legacy answered nothing (precision None) -> delta stays None, not fabricated
    assert web["grounding_precision_delta"] is None


def test_compare_arms_without_baseline_raises():
    cases = [_case("a", WEB_ANSWERABLE)]
    arms = {"evidence@1536": score_answer_counts(cases, {"a": SUPPORTED})}
    with pytest.raises(ValueError, match="no legacy baseline"):
        compare_answer_arms(arms)


# ---- Fixture scaffold integrity ---------------------------------------------

def test_fixture_loads_and_every_case_is_unreviewed_with_a_valid_bucket():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids)), "case IDs must be unique"
    assert {c["bucket"] for c in cases} == set(BUCKETS), "all three buckets present"
    # Scaffold must not masquerade as reviewed data.
    assert all(c["label_status"] == "candidate_unreviewed" for c in cases)
    # Unanswerable cases must be flagged answerable=false (refusal is correct).
    for c in cases:
        if c["bucket"] == UNANSWERABLE:
            assert c["answerable"] is False


def test_fixture_rows_build_valid_answer_cases():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = [
        AnswerCase(
            case_id=c["case_id"], bucket=c["bucket"], query=c["query"],
            language=c.get("language", "unspecified"),
            answerable=c.get("answerable", True),
            must_include_facts=tuple(c.get("must_include_facts", ())),
            acceptable_sources=tuple(c.get("acceptable_sources", ())),
            label_status=c.get("label_status", "candidate_unreviewed"),
        )
        for c in payload["cases"]
    ]
    # A dummy all-refused pass must score without error and never invent precision.
    result = score_answer_counts(cases, {c.case_id: REFUSED for c in cases})
    assert result["overall"]["grounding_precision"] is None
    assert result["label_status"] == "UNREVIEWED_NOT_FINAL"
