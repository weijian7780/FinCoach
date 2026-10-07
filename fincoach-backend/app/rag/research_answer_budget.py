"""Absolute stage bounds retain one request clock and finalization margin."""
from dataclasses import replace
from app.config import (
    COACH_FINALIZATION_RESERVE_SECONDS,
    COACH_RESEARCH_PHASE_SECONDS,
    COACH_RESEARCH_WRITER_SECONDS,
    COACH_RESEARCH_CORRECTION_SECONDS,
    COACH_RESEARCH_ANSWER_RESERVE_SECONDS,
)
from app.llm import CoachRequestBudget, research_answer_reserve_seconds
from app import llm

RESEARCH_VERIFIER_SECONDS = 5.0


def research_work_budget(budget: CoachRequestBudget) -> CoachRequestBudget:
    """Reserve serialization/storage time before any optional model work."""
    child = budget.for_stage(
        max_seconds=llm.COACH_REQUEST_DEADLINE_SECONDS - COACH_FINALIZATION_RESERVE_SECONDS,
        reserve_after_seconds=COACH_FINALIZATION_RESERVE_SECONDS,
        stage_name="model_work",
    )
    work_deadline = budget.started_at + (llm.COACH_REQUEST_DEADLINE_SECONDS - COACH_FINALIZATION_RESERVE_SECONDS)
    target_deadline = min(child.stage_deadline_at, work_deadline) if child.stage_deadline_at is not None else work_deadline
    return replace(child, stage_deadline_at=target_deadline)


def research_phase_budget(work: CoachRequestBudget) -> CoachRequestBudget:
    """Research cannot move its deadline later when interpretation ends early."""
    child = work.for_stage(
        max_seconds=COACH_RESEARCH_PHASE_SECONDS,
        reserve_after_seconds=COACH_RESEARCH_ANSWER_RESERVE_SECONDS,
        stage_name="research_phase",
    )
    abs_research_deadline = work.started_at + COACH_RESEARCH_PHASE_SECONDS
    target_deadline = min(child.stage_deadline_at, abs_research_deadline) if child.stage_deadline_at is not None else abs_research_deadline
    return replace(child, stage_deadline_at=target_deadline)


def initial_writer_budget(work: CoachRequestBudget) -> CoachRequestBudget | None:
    remaining = work.remaining_seconds()
    if remaining < COACH_RESEARCH_WRITER_SECONDS + RESEARCH_VERIFIER_SECONDS:
        return None
    # Reserve for downstream checks and correction:
    # Full correction path: 15s correction + 2 * 5s checks = 25s reserve.
    # At research second 75 (40s left in work): 10s correction + 2 * 5s checks = 20s reserve.
    if remaining >= COACH_RESEARCH_WRITER_SECONDS + COACH_RESEARCH_CORRECTION_SECONDS + 2 * RESEARCH_VERIFIER_SECONDS:
        reserve = COACH_RESEARCH_CORRECTION_SECONDS + 2 * RESEARCH_VERIFIER_SECONDS
    elif remaining >= COACH_RESEARCH_WRITER_SECONDS + 10 + 2 * RESEARCH_VERIFIER_SECONDS:
        reserve = 10 + 2 * RESEARCH_VERIFIER_SECONDS
    else:
        reserve = RESEARCH_VERIFIER_SECONDS
    return work.for_stage(
        max_seconds=COACH_RESEARCH_WRITER_SECONDS,
        reserve_after_seconds=reserve,
        stage_name="research_writer",
    )


def correction_budget(work: CoachRequestBudget) -> CoachRequestBudget | None:
    remaining = work.remaining_seconds()
    if remaining < 5.0 + RESEARCH_VERIFIER_SECONDS:
        return None
    return work.for_stage(
        max_seconds=COACH_RESEARCH_CORRECTION_SECONDS,
        reserve_after_seconds=RESEARCH_VERIFIER_SECONDS,
        stage_name="research_correction",
    )
