"""Displayed coverage follows required claims, not every sentence in a draft."""
from dataclasses import replace
from unittest.mock import patch

import pytest

from app import llm
from app.llm import AgentLLMResult, CoachRequestBudget
from app.rag import research_answer as answer
from app.rag.grounding import DISCLAIMER
from app.rag.research_coverage import PartCoverage
from app.rag.research_policy import EvidenceAssessment, QuestionPlan, ResearchDecision
from app.rag.retrieval import RetrievedChunk
from app.rag.verifier import GroundingVerification


QUESTION = "What is a reserve fund?"
FACT = "A reserve fund is money held for future needs."
EXTRA = "Some people keep it in a separate container."


def evidence(*, complete=True, second_part=False):
    source = RetrievedChunk(1, "Fixture", "fixture", None, 0, FACT, .8)
    parts = (PartCoverage("p1", "confirmed", (1,), complete=complete),)
    labels = [QUESTION]
    if second_part:
        parts += (PartCoverage("p2", "confirmed", (1,), complete=True),)
        labels.append("Where is it kept?")
    return ResearchDecision([source], EvidenceAssessment(
        "sufficient" if complete else "partial", supported_sources=(1,),
        supported_quotes=((1, FACT),), parts=parts),
        diagnostics={"requested_part_labels": labels})


def draft():
    return (f"**Insight**\n{FACT[:-1]} [S1].\n\n{EXTRA[:-1]} [S1].\n\n"
            f"**Educational guidance**\n{DISCLAIMER}")


def verdict(*, mappings=(("p1", (1,)),), answered=("p1",)):
    return GroundingVerification(
        {1: "supported", 2: "unsupported"}, {1: 1},
        requested_scope_covered=True, answered_part_ids=answered,
        answered_part_claims=mappings)


def check(result=None, decision=None):
    with patch.object(answer, "verify_grounding_claims", return_value=result or verdict()):
        return answer.check_research_draft(
            draft(), public_question=QUESTION, decision=decision or evidence(),
            budget=CoachRequestBudget.start())


def test_optional_rejection_keeps_complete_answer_without_notice_or_rewrite():
    # Exercise final delivery too: a rejected aside must not spend a rewrite
    # or append a warning when every required positive claim survived.
    with (patch.object(answer, "verify_grounding_claims", return_value=verdict()),
          patch.object(answer, "_generate_research_correction") as rewrite):
        outcome = answer.recover_research_answer(
            plan=QuestionPlan("reserve fund", False, True, "stable"),
            decision=evidence(), draft=AgentLLMResult(draft(), "primary"),
            budget=CoachRequestBudget.start(), public_question=QUESTION)
    rewrite.assert_not_called()
    assert outcome.diagnostics["complete"] is True
    assert outcome.diagnostics["answered_part_ids"] == ["p1"]
    assert "money held for future needs" in outcome.result.content
    assert "separate container" not in outcome.result.content
    assert "could not" not in outcome.result.content and "couldn't" not in outcome.result.content


@pytest.mark.parametrize("result,decision", [
    (verdict(), evidence(complete=False)),
    (verdict(answered=()), evidence()),
    (verdict(mappings=()), evidence()),
    (verdict(mappings=(("p1", (1, 2)),)), evidence()),
])
def test_partial_or_unmapped_part_cannot_be_promoted_after_removal(result, decision):
    checked = check(result, decision)
    assert not checked.is_valid
    assert checked.diagnostics["answered_part_ids"] == []
    assert checked.diagnostics["requested_scope_covered"] is False
    assert checked.diagnostics["unanswered_requested_parts"] == [QUESTION]
    assert f"“{QUESTION}”" in checked.approved_text


def test_removing_required_part_names_only_that_part():
    checked = check(verdict(mappings=(("p1", (1,)), ("p2", (2,))),
                            answered=("p1", "p2")), evidence(second_part=True))
    assert not checked.is_valid
    assert checked.diagnostics["answered_part_ids"] == ["p1"]
    assert checked.diagnostics["unanswered_requested_parts"] == ["Where is it kept?"]
    assert "“Where is it kept?”" in checked.approved_text
    assert f"“{QUESTION}”" not in checked.approved_text


def test_quality_failure_is_not_cleared_by_optional_removal():
    checked = check(replace(verdict(), quality_errors=("incomplete_supported_answer",)))
    assert not checked.is_valid
    assert checked.diagnostics["requested_scope_covered"] is False


def test_no_surviving_positive_claim_is_not_an_answer():
    checked = check(GroundingVerification({1: "unsupported", 2: "unsupported"}))
    assert not checked.is_valid and checked.approved_text is None


def test_legacy_decision_without_public_labels_does_not_display_part_ids():
    checked = check(verdict(mappings=()), replace(evidence(), diagnostics={}))
    assert not checked.is_valid
    assert "I could not explain all the requested details yet." in checked.approved_text
    assert "p1" not in checked.approved_text


@pytest.mark.parametrize("required_claims,complete", [((1,), True), ((1, 2), False)])
def test_numeric_rejection_overrides_semantic_support_for_required_claims(required_claims, complete):
    # The semantic checker accepts both claims, but the local numeric guard
    # removes the invented amount. Only an optional amount may be discarded
    # without losing completeness.
    text = draft().replace(EXTRA[:-1], "The reserve amount is RM500")
    result = GroundingVerification(
        {1: "supported", 2: "supported"}, {1: 1, 2: 1},
        requested_scope_covered=True, answered_part_ids=("p1",),
        answered_part_claims=(("p1", required_claims),))
    with patch.object(answer, "verify_grounding_claims", return_value=result):
        checked = answer.check_research_draft(text, public_question=QUESTION,
            decision=evidence(), budget=CoachRequestBudget.start())
    assert checked.is_valid is complete
    assert checked.diagnostics["numeric_rejected_claim_count"] == 1
    assert "RM500" not in checked.approved_text
    assert ("couldn't" in checked.approved_text) is not complete


@pytest.mark.parametrize("session", [None, object()])
def test_correction_can_use_primary_with_actual_generator_signature(monkeypatch, session):
    # Run through the actual generate_result signature/provider selection.
    # Mocking generate_result itself would hide an unsupported keyword argument.
    budget = replace(CoachRequestBudget.start(), provider_session=session)
    providers = [llm._Provider("primary", "https://primary.invalid", "fixture", "primary"),
                 llm._Provider("fallback", "https://fallback.invalid", "fixture", "fallback")]
    monkeypatch.setattr(llm, "_providers", lambda: providers)
    result = llm.LLMResult("Corrected explanation", "primary")
    with patch.object(llm, "_generate_with_provider", return_value=result) as generate:
        assert answer._generate_research_correction(
            "rewrite", budget=budget, system_prompt="Explain") is result
    assert generate.call_count == 1
    assert generate.call_args.args[1].role == "primary"
    assert generate.call_args.kwargs["timeout_seconds"] <= budget.remaining_seconds() + 1


def test_correction_keeps_existing_failover_within_stage_budget(monkeypatch):
    budget = CoachRequestBudget.start().for_stage(stage_name="answer_recovery", max_seconds=18)
    providers = [llm._Provider("primary", "https://primary.invalid", "fixture", "primary"),
                 llm._Provider("fallback", "https://fallback.invalid", "fixture", "fallback")]
    monkeypatch.setattr(llm, "_providers", lambda: providers)
    result = llm.LLMResult("Corrected explanation", "fallback")
    with patch.object(llm, "_generate_with_provider", side_effect=[TimeoutError(), result]) as generate:
        assert answer._generate_research_correction(
            "rewrite", budget=budget, system_prompt="Explain") is result
    assert [call.args[1].role for call in generate.call_args_list] == ["primary", "fallback"]
    assert all(call.kwargs["timeout_seconds"] <= 18 for call in generate.call_args_list)
