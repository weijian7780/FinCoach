"""Meaning and evidence completeness survive the real assessment/delivery chain."""
import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.llm import CoachRequestBudget, LLMResult
from app.rag import request_interpretation as intent
from app.rag import research_answer as answer
from app.rag import research_policy as policy
from app.rag import verifier
from app.rag.grounding import DISCLAIMER
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import classify_tier


QUESTION = "What is cash flow?"
FACT = "Cash flow is the movement of money into and out of a business."
BANK_URL = "https://www.maybank2u.com.my/education/cash-flow"


def interpreted(message, **public):
    payload = {"route": "financial_education", "public": {
        "topic": "cash flow", "question": QUESTION, "definitional": True, **public}}

    def generate(prompt, *, validate, **kwargs):
        return validate(json.dumps(payload))

    return intent.interpret_request(message, [], today=date(2026, 10, 29),
        budget=CoachRequestBudget.start(), generate=generate)


@pytest.mark.parametrize("question", [
    "what is cash flow", "cash flow is what", "cash flow tu apa", "现金流是什么意思？",
])
def test_semantic_definition_handles_equivalent_wording(question):
    result = interpreted(question)
    assert result.failure is None
    assert result.public_plan.definitional
    assert result.public_plan.time_scope == "stable"
    assert result.public_plan.required_facts == policy._DEFINITIONAL_FACTS


def test_semantic_nondefinition_is_not_overridden_by_an_english_opener():
    result = interpreted("Explain why cash flow matters", definitional=False,
        question="Why does cash flow matter?",
        required_facts=["why cash flow matters"])
    assert result.failure is None
    assert not result.public_plan.definitional
    assert result.public_plan.required_facts == ("why cash flow matters",)


@pytest.mark.parametrize("fields", [
    {"time_scope": "current"}, {"time_scope": "historical", "period": "2023"},
    {"verify_current": True}, {"explicit_search": True},
])
def test_definition_label_cannot_erase_an_explicit_evidence_constraint(fields):
    result = interpreted("Explain the requested rule", required_facts=["requested rule"], **fields)
    assert result.failure is None
    assert not result.public_plan.definitional
    assert result.public_plan.required_facts == ("requested rule",)


def test_legacy_research_interpreter_also_uses_the_semantic_definition_label():
    payload = dict(topic="cash flow", needs_personal=False, needs_external=True,
                   time_scope="stable", definitional=True)
    result = policy.interpret_question("cash flow tu apa", [], base_personal=False,
        base_external=True, generate=lambda *a, **k: LLMResult(json.dumps(payload), "fixture"))
    assert result.interpreted and result.definitional


def plan(**fields):
    return replace(policy.QuestionPlan("cash flow", False, True, "stable",
        required_facts=(QUESTION,), original_question="cash flow is what", part_tracking=True), **fields)


def source(url=BANK_URL, text=FACT):
    return RetrievedChunk(1, "Cash flow education", "fixture", None, 0, text, .8,
        source_type="web", url=url, tier=classify_tier(url), confidence="reported")


def assessment(p, sources, *, requirement="explanatory", complete=True, quote=FACT):
    payload = dict(status="sufficient", missing=[], conflicting=False,
        jurisdiction_matches=True, period_matches=True,
        support=[dict(source_id=1, quote=quote)],
        coverage=[dict(part_id="p1", status="reported", support_indices=[1],
            resolution="direct", complete=complete, evidence_requirement=requirement)])
    return policy.assess_evidence(p, sources,
        generate=lambda *a, **k: LLMResult(json.dumps(payload), "fixture"),
        budget=CoachRequestBudget.start())


def checked_answer(p, sources, assessed):
    decision = policy.ResearchDecision(sources, assessed,
        diagnostics={"requested_part_labels": [QUESTION]})
    payload = dict(claims=[dict(id=1, verdict="supported", source_index=1, scope_relation="preserved")],
        quality_errors=[], requested_scope_covered=True, unanswered_requested_parts=[],
        answered_part_ids=["p1"], part_claim_ids={"p1": [1]})
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(usage=None,
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(payload)))])
    draft = LLMResult(f"**Insight**\n{FACT[:-1]} [S1].\n\n**Educational guidance**\n{DISCLAIMER}", "fixture")
    with (patch.object(verifier, "_create_verifier_client", return_value=client),
          patch.object(answer, "_generate_research_correction", side_effect=TimeoutError) as rewrite):
        result = answer.recover_research_answer(plan=p, decision=decision, draft=draft,
            budget=CoachRequestBudget.start(), public_question=QUESTION)
    return result, rewrite


@pytest.mark.parametrize("url", [
    BANK_URL, "https://www.cimb.com.my/education/cash-flow",
    "https://finance.example.edu/cash-flow", "https://www.cnbc.com/cash-flow",
])
def test_supported_education_is_complete_without_official_confirmation_or_rewrite(url):
    # Same bug as the saved chat: the model answers p1, all facts are verified,
    # and a bank/academic/publisher explains the concept. Source authority must
    # not turn this into an unanswered question during delivery.
    p, sources = plan(), [source(url)]
    assessed = assessment(p, sources)
    result, rewrite = checked_answer(p, sources, assessed)
    assert assessed.status == "sufficient"
    assert assessed.parts[0].status == "reported"  # No false first-party promotion.
    assert assessed.parts[0].complete
    assert result.diagnostics["complete"] is True
    assert result.diagnostics["answered_part_ids"] == ["p1"]
    assert result.diagnostics["unanswered_requested_parts"] == []
    assert "movement of money" in result.result.content
    assert "couldn't fully confirm" not in result.result.content
    rewrite.assert_not_called()


def test_genuinely_partial_education_still_discloses_the_gap():
    p, sources = plan(), [source()]
    assessed = assessment(p, sources, complete=False)
    result, _ = checked_answer(p, sources, assessed)
    assert not assessed.parts[0].complete
    assert result.diagnostics["complete"] is False
    assert "couldn't fully confirm" in result.result.content


def test_institutional_requirement_still_needs_authority_or_corroboration():
    text = "Example programme applicants must provide their identity card."
    p = plan(topic="Example programme", required_facts=("required documents",))
    assessed = assessment(p, [source(text=text)], requirement="authoritative", quote=text)
    assert assessed.supported_quotes == ((1, text),)
    assert assessed.parts[0].status == "reported"
    assert not assessed.parts[0].complete


@pytest.mark.parametrize("fields", [
    {"time_scope": "current"}, {"time_scope": "historical", "period": "2023"},
    {"verify_current": True}, {"period": "2026"},
])
def test_explanatory_label_cannot_relax_time_or_current_verification(fields):
    assessed = assessment(plan(**fields), [source()])
    assert assessed.supported_quotes
    assert not assessed.parts[0].complete
    assert assessed.parts[0].evidence_requirement == "authoritative"


@pytest.mark.parametrize("url,text", [
    (BANK_URL, "Cash flow is mentioned in this article."),
    ("https://unknown.example/finance", FACT),
    ("https://reddit.com/r/finance", FACT),
])
def test_explanatory_label_cannot_authorize_invented_quotes_or_unapproved_sources(url, text):
    assessed = assessment(plan(), [source(url, text)])
    assert not assessed.supported_quotes
    assert not any(part.complete for part in assessed.parts)


def test_mixed_definition_and_requirement_keep_separate_evidence_standards():
    text = FACT + " Example programme applicants must provide an identity card."
    payload = dict(status="sufficient", missing=[], conflicting=False,
        jurisdiction_matches=True, period_matches=True,
        support=[dict(source_id=1, quote=text)], coverage=[
            dict(part_id="p1", status="reported", support_indices=[1], resolution="direct",
                 complete=True, evidence_requirement="explanatory"),
            dict(part_id="p2", status="reported", support_indices=[1], resolution="direct",
                 complete=True, evidence_requirement="authoritative")])
    assessed = policy.assess_evidence(plan(required_facts=(QUESTION, "Example required documents")),
        [source(text=text)], generate=lambda *a, **k: LLMResult(json.dumps(payload), "fixture"))
    assert assessed.parts[0].complete and not assessed.parts[1].complete
    assert assessed.missing == ("Example required documents",)
