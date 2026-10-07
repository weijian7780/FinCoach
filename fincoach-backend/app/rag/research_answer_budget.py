"""Absolute stage bounds retain one request clock and finalization margin."""
from dataclasses import replace
from app.config import (
    COACH_FINALIZATION_RESERVE_SECONDS, COACH_RESEARCH_PHASE_SECONDS,
    COACH_RESEARCH_WRITER_SECONDS, COACH_RESEARCH_CORRECTION_SECONDS,
)
from app.llm import CoachRequestBudget, research_answer_reserve_seconds
from app import llm

INITIAL_WRITER_MIN_SECONDS = 20
CORRECTION_MIN_SECONDS = 18
RESEARCH_VERIFIER_SECONDS = 8


def research_work_budget(budget: CoachRequestBudget) -> CoachRequestBudget:
    """Reserve serialization/storage time before any optional model work."""
    return budget.for_stage(max_seconds=110, reserve_after_seconds=COACH_FINALIZATION_RESERVE_SECONDS)


def research_phase_budget(work: CoachRequestBudget) -> CoachRequestBudget:
    """Research cannot move its deadline later when interpretation ends early."""
    child = work.for_stage(max_seconds=COACH_RESEARCH_PHASE_SECONDS,
        reserve_after_seconds=research_answer_reserve_seconds())
    return replace(child, stage_deadline_at=min(child.stage_deadline_at,
        work.started_at + COACH_RESEARCH_PHASE_SECONDS))


def initial_writer_budget(budget: CoachRequestBudget) -> CoachRequestBudget | None:
    remaining = budget.remaining_seconds()
    if remaining < INITIAL_WRITER_MIN_SECONDS + RESEARCH_VERIFIER_SECONDS:
        return None
    # Existing shorter request contracts retain their original writer allocation.
    if llm.COACH_REQUEST_DEADLINE_SECONDS < 120:
        return budget.for_stage(max_seconds=20, reserve_after_seconds=8)
    # Use all four reserved slots when they fit; late evidence retains a check.
    reserve = COACH_RESEARCH_CORRECTION_SECONDS + 2 * RESEARCH_VERIFIER_SECONDS
    if remaining < INITIAL_WRITER_MIN_SECONDS + reserve:
        reserve = RESEARCH_VERIFIER_SECONDS
    return budget.for_stage(max_seconds=COACH_RESEARCH_WRITER_SECONDS,
        reserve_after_seconds=reserve)
