"""A calculation or source must answer its own requested part, not a neighbour."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.llm import CoachRequestBudget, LLMResult
from app.rag import research_answer as answer
from app.rag.research_coverage import (
    PartCoverage, calculated_part_ids, plan_without_parts, requested_parts,
)
from app.rag.research_policy import EvidenceAssessment, ResearchDecision, search_part
from app.rag.retrieval import RetrievedChunk
from app.rag.grounding import DISCLAIMER, GroundingClaim
from app.rag import verifier
from test_kb_nonfinance import (
    SAVE_TARGET_LISTED, SAVE_QUESTION, _all_providers_down, _plan, _records_service,
)
from test_kb_reduced_release import _interpret


def test_savings_calculation_does_not_answer_an_unrelated_finance_question(monkeypatch):
    question = "How much can I save toward a RM3000 laptop, and what is PTPTN?"
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"].update(topic="PTPTN", required_facts=["what is PTPTN"],
                             subject_domain="finance", parts=[])
    plan = _plan(payload, question)
    assert calculated_part_ids(plan) == ()
    _all_providers_down(monkeypatch)
    captured = []
    from app.rag import service
    from app.rag.research_policy import EvidenceAssessment, ResearchDecision

    def research(plan, chunks, **kwargs):
        captured.extend(part.label for part in requested_parts(plan))
        return ResearchDecision([], EvidenceAssessment("insufficient"), False, "no_api_key")

    monkeypatch.setattr(service, "run_research_policy", research)
    coach = _records_service(monkeypatch, payload, question)
    content = coach.send_message("s", "m", question)["assistant_message"]["content"]
    assert captured == ["what is PTPTN"]
    assert "monthly contributions" in content


def test_old_single_finance_part_without_a_binding_is_not_assumed_answered():
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"]["parts"] = []
    assert calculated_part_ids(_plan(payload, SAVE_QUESTION)) == ()


def test_explicit_savings_binding_leaves_other_finance_parts_for_research():
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"]["parts"] = [
        {"fact": "how many months to save for the laptop", "domain": "finance", "answer_kind": "savings_target"},
        {"fact": "what is PTPTN", "domain": "finance", "answer_kind": "research"},
    ]
    plan = _plan(payload, "q")
    assert calculated_part_ids(plan) == ("p1",)
    remaining = plan_without_parts(plan, ("p1",))
    assert [(part.id, part.label) for part in requested_parts(remaining)] == [("p2", "what is PTPTN")]


def test_remaining_mixed_part_keeps_its_original_identity_and_entities():
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"].update(subject_domain="mixed", parts=[
        {"fact": "save for a laptop", "domain": "finance", "answer_kind": "savings_target"},
        {"fact": "explain message passing", "domain": "non_finance"},
        {"fact": "eligibility requirements", "domain": "finance", "entities": ["PTPTN"]},
    ])
    plan = _plan(payload, "q")
    remaining = plan_without_parts(plan, calculated_part_ids(plan))
    assert [part.id for part in requested_parts(remaining)] == ["p2", "p3"]
    assert "PTPTN" in search_part(remaining, requested_parts(remaining)[1]).label


def _shared_document_decision():
    quotes = ("Compound interest includes interest on accumulated interest.",
              "Message passing exchanges messages between processes.")
    source = RetrievedChunk(1, "Study notes", "notes.md", None, 0, " ".join(quotes), .8)
    assessment = EvidenceAssessment("sufficient", supported_sources=(1,),
        supported_quotes=tuple((1, quote) for quote in quotes),
        parts=(PartCoverage("p1", "confirmed", (1,), complete=True),
               PartCoverage("p2", "confirmed", (2,), complete=True)))
    return ResearchDecision([source], assessment)


def _mixed_plan():
    return _plan({"route": "financial_education", "public": {
        "topic": "compound interest and message passing", "subject_domain": "mixed", "parts": [
            {"fact": "explain compound interest", "domain": "finance"},
            {"fact": "explain message passing", "domain": "non_finance"},
        ]}}, "Explain compound interest and message passing")


def test_shared_source_citation_cannot_cover_an_unexplained_part(monkeypatch):
    text = "**Insight**\nCompound interest includes interest on accumulated interest [S1]."
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: answer.ResearchDraftCheck(
        True, approved_text=text, diagnostics={"answered_part_ids": ["p1"],
                                               "addressed_part_ids": ["p1"]}))
    result = answer.recover_research_answer(plan=_mixed_plan(), decision=_shared_document_decision(),
        draft=LLMResult(text, "test"), budget=CoachRequestBudget.start(), public_question="q")
    assert result.result.content.endswith(answer._NON_FINANCE_PART_MESSAGES["en"])


def test_semantically_verified_partial_explanation_needs_no_referral(monkeypatch):
    text = "**Insight**\nMessage passing exchanges messages between processes [S1]."
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: answer.ResearchDraftCheck(
        True, approved_text=text, diagnostics={"answered_part_ids": [], "addressed_part_ids": ["p2"]}))
    result = answer.recover_research_answer(plan=_mixed_plan(), decision=_shared_document_decision(),
        draft=LLMResult(text, "test"), budget=CoachRequestBudget.start(), public_question="q")
    assert "learning resources" not in result.result.content


@pytest.mark.parametrize("kind", ["p1", "allocation", "invented"])
def test_invalid_calculation_bindings_are_rejected(kind):
    from app.rag.request_interpretation import IntentProposal
    from pydantic import ValidationError
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"]["parts"][0]["answer_kind"] = kind
    with pytest.raises(ValidationError):
        IntentProposal.model_validate(payload)


def test_a_calculation_cannot_be_bound_to_a_non_finance_part():
    from app.rag.request_interpretation import IntentProposal
    from pydantic import ValidationError
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"].update(subject_domain="non_finance", topic="message passing")
    payload["public"]["parts"][0]["domain"] = "non_finance"
    with pytest.raises(ValidationError):
        IntentProposal.model_validate(payload)


def test_explicit_saving_calculation_with_no_records_is_repaired():
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload.update(route="financial_education", read=None)
    result = _interpret(SAVE_QUESTION, [], payload, SAVE_TARGET_LISTED)
    assert result.failure is None and result.resolved.tool_name == "predict_savings"
    assert len(_interpret.inputs) == 2


def test_mixed_label_repair_cannot_turn_ptptn_into_a_non_finance_topic():
    # A real Gemini reading called two finance topics "mixed". Asking for one
    # part of each domain then made the next reading falsely relabel PTPTN.
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"].update(subject_domain="mixed", required_facts=[], parts=[
        {"fact": "save for the laptop", "domain": "finance"},
        {"fact": "what is PTPTN", "domain": "finance", "entities": ["PTPTN"]},
    ])
    repair = deepcopy(payload)
    repair["public"]["parts"][1]["domain"] = "non_finance"
    result = _interpret("How much can I save for a RM3000 laptop, and what is PTPTN?", [], payload, repair)
    assert result.failure == "read_constraint" and result.proposal is None
    assert "ask them separately" in result.failure_message


def test_financial_search_keeps_original_part_ids_after_removing_other_parts():
    from app.rag.research_policy import financial_search_plan
    payload = deepcopy(SAVE_TARGET_LISTED)
    payload["public"].update(subject_domain="mixed", parts=[
        {"fact": "save for a laptop", "domain": "finance", "answer_kind": "savings_target"},
        {"fact": "explain message passing", "domain": "non_finance"},
        {"fact": "eligibility requirements", "domain": "finance", "entities": ["PTPTN"]},
    ])
    remaining = plan_without_parts(_plan(payload, "q"), ("p1",))
    searched = financial_search_plan(remaining)
    assert [(part.id, part.label) for part in requested_parts(searched)] == [("p3", "eligibility requirements")]
    assert "PTPTN" in search_part(searched, requested_parts(searched)[0]).label


def test_reordering_facts_keeps_the_calculation_bound_to_the_saving_fact():
    payload = deepcopy(SAVE_TARGET_LISTED)
    saving = payload["public"]["parts"][0]
    payload["public"]["parts"] = [
        {"fact": "what is PTPTN", "domain": "finance", "entities": ["PTPTN"]}, saving]
    plan = _plan(payload, "q")
    assert calculated_part_ids(plan) == ("p2",)
    remaining = plan_without_parts(plan, ("p2",))
    assert [(part.id, part.label) for part in requested_parts(remaining)] == [("p1", "what is PTPTN")]


def _check_with_claim_links(monkeypatch, *, rejected=False):
    first = "Compound interest includes interest on accumulated interest [S1]."
    second = "Message passing exchanges messages between processes [S1]."
    text = f"**Insight**\n{first}\n\n{second}\n\n**Educational guidance**\n{DISCLAIMER}"

    def check(claims, *args, **kwargs):
        assert len(claims) == 2
        return verifier.GroundingVerification(
            {1: "supported", 2: "unsupported" if rejected else "supported"},
            {1: 1} if rejected else {1: 1, 2: 1}, requested_scope_covered=False,
            answered_part_ids=(), answered_part_claims=(("p1", (1,)), ("p2", (2,))))

    monkeypatch.setattr(answer, "verify_grounding_claims", check)
    return answer.check_research_draft(text, public_question="Explain compound interest and message passing",
        decision=_shared_document_decision(), budget=CoachRequestBudget.start())


def test_displayed_partial_claims_retain_their_semantic_part_links(monkeypatch):
    checked = _check_with_claim_links(monkeypatch)
    assert checked.diagnostics["answered_part_ids"] == []
    assert checked.diagnostics["addressed_part_ids"] == ["p1", "p2"]
    assert "Message passing" in checked.approved_text


def test_removed_claim_cannot_suppress_its_parts_referral(monkeypatch):
    checked = _check_with_claim_links(monkeypatch, rejected=True)
    assert checked.diagnostics["addressed_part_ids"] == ["p1"]
    assert "Message passing exchanges" not in checked.approved_text


@pytest.mark.parametrize("part_id,expected_error", [("p2", None), ("p6", "invalid_verifier_response")])
def test_existing_verifier_accepts_partial_claim_bindings_only_for_requested_parts(monkeypatch, part_id, expected_error):
    claim = "Message passing exchanges messages between processes."
    payload = dict(claims=[dict(id=1, verdict="supported", source_index=1, scope_relation="preserved")],
        quality_errors=[], requested_scope_covered=False, unanswered_requested_parts=["other details"],
        answered_part_ids=[], part_claim_ids={part_id: [1]})
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)),
                                                       finish_reason="stop")], usage=None)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: response)))
    monkeypatch.setattr(verifier, "_create_verifier_client", lambda **k: client)
    checked = verifier.verify_grounding_claims([GroundingClaim(1, claim, (1,))], [claim], timeout_seconds=5,
        research_context=verifier.ResearchVerificationContext("q", claim, (), enforce_scope=True,
            requested_parts=requested_parts(_mixed_plan()), coverage=_shared_document_decision().assessment.parts))
    assert checked.error_code == expected_error
    if expected_error is None:
        assert checked.answered_part_claims == (("p2", (1,)),)
