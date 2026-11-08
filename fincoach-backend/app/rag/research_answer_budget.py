"""Absolute stage bounds retain one request clock and finalization margin."""
from dataclasses import replace
from app.config import (
    COACH_FINALIZATION_RESERVE_SECONDS, COACH_RESEARCH_PHASE_SECONDS,
    COACH_RESEARCH_WRITER_SECONDS, COACH_RESEARCH_CORRECTION_SECONDS,
)
from app.llm import CoachRequestBudget, research_answer_reserve_seconds
from app import llm

INITIAL_WRITER_MIN_SECONDS = 20
# Previous two normal cohorts: writer medians 9.816/12.933s, checker
# medians 5.324/6.247s. Round up the slower medians for rewrite admission.
CORRECTION_MIN_SECONDS = 13
RESEARCH_CHECKER_ESTIMATE_SECONDS = 7


def research_work_budget(budget: CoachRequestBudget) -> CoachRequestBudget:
    """Reserve serialization/storage time before any optional model work."""
    # Anchor the reserve to the ORIGINAL deadline, not the time this function
    # happens to run. Reapplying it must not subtract another five seconds.
    deadline = budget.started_at + llm.COACH_REQUEST_DEADLINE_SECONDS - COACH_FINALIZATION_RESERVE_SECONDS
    return replace(budget, stage_deadline_at=min(deadline, budget.stage_deadline_at)
                   if budget.stage_deadline_at is not None else deadline)


def research_phase_budget(work: CoachRequestBudget) -> CoachRequestBudget:
    """Research cannot move its deadline later when interpretation ends early."""
    child = work.for_stage(max_seconds=COACH_RESEARCH_PHASE_SECONDS,
        reserve_after_seconds=research_answer_reserve_seconds())
    return replace(child, stage_deadline_at=min(child.stage_deadline_at,
        work.started_at + COACH_RESEARCH_PHASE_SECONDS))


def initial_writer_budget(budget: CoachRequestBudget) -> CoachRequestBudget | None:
    remaining = budget.remaining_seconds()
    if remaining < INITIAL_WRITER_MIN_SECONDS + RESEARCH_CHECKER_ESTIMATE_SECONDS:
        return None
    return budget.for_stage(max_seconds=COACH_RESEARCH_WRITER_SECONDS,
        reserve_after_seconds=RESEARCH_CHECKER_ESTIMATE_SECONDS)


def correction_writer_budget(budget: CoachRequestBudget) -> CoachRequestBudget | None:
    """Admit a rewrite only when measured writer and checker times both fit."""
    if budget.remaining_seconds() < CORRECTION_MIN_SECONDS + RESEARCH_CHECKER_ESTIMATE_SECONDS:
        return None
    return budget.for_stage(stage_name='answer_recovery', max_seconds=COACH_RESEARCH_CORRECTION_SECONDS,
                            reserve_after_seconds=RESEARCH_CHECKER_ESTIMATE_SECONDS)
