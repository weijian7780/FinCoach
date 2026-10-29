"""Regressions for general public questions, harmless metadata and bounded reuse."""
import json
import pytest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.llm import CoachRequestBudget
from app.rag import research_policy as policy
from app.rag import web_research as web
from app.rag.retrieval import RetrievedChunk


def source(text="Submit the application using the official portal."):
    return RetrievedChunk(1, "Official instructions", "official", None, 0, text, .8,
                          source_type="web", url="https://www.ptptn.gov.my/apply", tier=1,
                          confidence="established")


def test_named_agency_role_is_general_despite_previous_programme():
    proposed = policy.QuestionPlan("ICU JPM role in SARA", False, True, "stable",
        entities=("ICU JPM",), required_facts=("SARA eligibility",), original_question="ICU, JPM do for?")
    normalized = policy._normalize_question_scope(proposed, proposed.original_question)
    assert normalized.scope == "general"
    assert "SARA" not in normalized.topic
    assert all("SARA" not in fact for fact in normalized.required_facts)
    assert not normalized.definitional


def test_explicit_programme_reference_keeps_contextual_scope():
    proposed = policy.QuestionPlan("ICU JPM role in SARA", False, True, "stable", entities=("ICU JPM",))
    result = policy._normalize_question_scope(proposed, "What does ICU JPM do for SARA?")
    assert result.scope == "contextual" and "SARA" in result.topic


def test_new_named_programme_does_not_inherit_previous_programme():
    proposed = policy.QuestionPlan("AKPK application process", False, True, "current",
        entities=("STR", "AKPK"), required_facts=("application steps", "documents"), scope="contextual")
    result = policy._normalize_question_scope(proposed, "How do I apply for STR and what documents?")
    assert result.scope == "general" and result.entities == ("STR",)
    assert "AKPK" not in result.topic and "STR" in result.topic


def test_malay_agency_role_preserves_language():
    proposed = policy.QuestionPlan("ICU JPM role in SARA", False, True, "stable", entities=("ICU JPM",), response_language="ms")
    result = policy._normalize_question_scope(proposed, "Apakah fungsi ICU JPM?")
    assert result.response_language == "ms" and "SARA" not in result.topic


def test_pronoun_role_followup_retains_public_reference():
    proposed = policy.QuestionPlan("ICU JPM role in SARA", False, True, "stable", entities=("ICU JPM",))
    result = policy._normalize_question_scope(proposed, "What does it do for that programme?")
    assert result.scope == "contextual" and "SARA" in result.topic


def test_long_missing_label_preserves_exact_support():
    chunk = source()
    payload = dict(status="partial", missing=["required application documents " * 8],
        conflicting=False, jurisdiction_matches=True, period_matches=True,
        support=[dict(source_id=1, quote=chunk.content)])
    model = MagicMock(return_value=SimpleNamespace(content=json.dumps(payload)))
    diagnostics = {}
    result = policy.assess_evidence(policy.QuestionPlan("application", False, True, "current"),
        [chunk], generate=model, diagnostics=diagnostics)
    assert result.supported_quotes == ((1, chunk.content),)
    assert result.failure is None and result.status == "partial"
    assert model.call_count == 1 and diagnostics["local_repairs"] == 1


def test_insufficient_coverage_does_not_erase_valid_positive_support():
    chunk = source()
    payload = dict(status="insufficient", missing=["documents"], conflicting=False,
        jurisdiction_matches=True, period_matches=True, support=[dict(source_id=1, quote=chunk.content)])
    result = policy.assess_evidence(policy.QuestionPlan("application", False, True, "current"),
        [chunk], generate=lambda *a, **k: SimpleNamespace(content=json.dumps(payload)))
    assert result.status == "partial" and result.supported_quotes == ((1, chunk.content),)


def test_empty_evidence_reserve_uses_otherwise_idle_time():
    from app import llm
    with patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60):
        assert llm.research_answer_reserve_seconds(has_evidence=False) == 20
        assert llm.research_answer_reserve_seconds(has_evidence=True) == 30


def test_full_page_reused_for_a_new_window_without_paid_extraction():
    import sys
    cache = web.WebResearchCache()
    raw = "Application steps\nApply through the official portal.\n\nDocuments\nProvide an identity card and transcript."
    client = MagicMock()
    client.extract.return_value = {"results": [{"url": source().url, "raw_content": raw}]}
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **k: client)}):
        web.extract_passages([source().url], api_key="test", query="application", cache=cache, complete_context=True)
        result = web.extract_passages([source().url], api_key="test", query="documents", cache=cache, complete_context=True)
    assert "identity card" in result[source().url]
    assert client.extract.call_count == 1 and cache.extract_calls == 1


def test_source_call_caps_apply_before_dispatch():
    import sys
    cache = web.WebResearchCache(search_calls=3, extract_calls=4)
    client = MagicMock()
    assert web._search_pass(client, "new query", caged=True, max_results=4, timeout=5, cache=cache) == []
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **k: client)}):
        assert web.extract_passages([source().url], api_key="test", cache=cache) == {}
    client.search.assert_not_called()
    client.extract.assert_not_called()


def test_last_empty_evidence_window_is_assessed_before_failure():
    from app.rag.web_research import ResearchOutcome
    chunk = source()
    assessed = [policy.EvidenceAssessment("insufficient", ("application",))] * 4 + [
        policy.EvidenceAssessment("sufficient", supported_sources=(1,), supported_quotes=((1, chunk.content),))]
    with (patch.object(policy, "assess_evidence", side_effect=assessed),
          patch.object(policy, "research_evidence", return_value=ResearchOutcome([chunk], True, "ok")) as search,
          patch.object(policy, "extract_passages", side_effect=[
              {chunk.url: chunk.content + " Follow the portal instructions."},
              {chunk.url: chunk.content + " Read the complete application guidance."}])):
        result = policy.run_research_policy(policy.QuestionPlan("application", False, True, "current", entities=("PTPTN",)),
            [], generate=MagicMock(), budget=CoachRequestBudget.start(), api_key="test", web_enabled=True,
            max_results=4, timeout=8)
    assert result.assessment.supported_quotes
    assert result.diagnostics["empty_evidence_recovery_used"] == 1
    assert search.call_count <= 3 and result.diagnostics["assessment_calls"] <= 6


def test_scope_incomplete_draft_retains_verified_partial_for_rewrite():
    from app.rag import research_answer as answer_module
    from app.rag.grounding import DISCLAIMER
    from app.rag.verifier import GroundingVerification
    chunk = source()
    decision = policy.ResearchDecision([chunk], policy.EvidenceAssessment("sufficient",
        supported_sources=(1,), supported_quotes=((1, chunk.content),)))
    draft = f"**Insight**\nApply using the portal [S1].\n\n**Recommended action**\nSubmit through the portal [S1].\n\n**Educational guidance**\n{DISCLAIMER}"
    def verify(claims, *_a, **_k):
        return GroundingVerification({c.id: "supported" for c in claims}, {c.id: 1 for c in claims},
            requested_scope_covered=False, unanswered_requested_parts=("documents",))
    with patch.object(answer_module, "verify_grounding_claims", side_effect=verify):
        result = answer_module.check_research_draft(draft, public_question="How do I apply and what documents?",
            decision=decision, budget=CoachRequestBudget.start())
    assert not result.is_valid and result.approved_text
    assert result.diagnostics["requested_scope_covered"] is False
    assert "documents" in result.diagnostics["unanswered_requested_parts"]


def test_late_initial_explanation_keeps_five_seconds_for_verification():
    from app import llm
    from app.rag import service
    chunk = source()
    decision = policy.ResearchDecision([chunk], policy.EvidenceAssessment("partial",
        supported_sources=(1,), supported_quotes=((1, chunk.content),)))
    with (patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "monotonic", return_value=40),
          patch.object(service, "generate_result", return_value=SimpleNamespace(content="draft")) as generate,
          patch.object(service, "recover_research_answer")):
        service._research_explanation_result(plan=policy.QuestionPlan("application", False, True, "current"),
            decision=decision, budget=CoachRequestBudget(0), question="How do I apply?")
        assert generate.call_args is None  # G=20 plus V=8 cannot fit 20 remaining seconds.


def test_early_source_completion_gives_primary_a_larger_explanation_window():
    from app import llm
    from app.rag import service
    chunk = source()
    decision = policy.ResearchDecision([chunk], policy.EvidenceAssessment("sufficient",
        supported_sources=(1,), supported_quotes=((1, chunk.content),)))
    with (patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "monotonic", return_value=20),
          patch.object(service, "generate_result", return_value=SimpleNamespace(content="draft")) as generate,
          patch.object(service, "recover_research_answer")):
        service._research_explanation_result(plan=policy.QuestionPlan("benefit", False, True, "current"),
            decision=decision, budget=CoachRequestBudget(0), question="How do I apply?")
        stage = generate.call_args.kwargs["budget"]
        assert stage.started_at == 0 and stage.remaining_seconds() == 20


def test_public_discovery_is_not_biased_to_unrelated_finance_hosts():
    client = MagicMock()
    client.search.return_value = {"results": []}
    web._search_pass(client, "public institution role Malaysia", caged=True, max_results=4,
                     timeout=5, public_policy=True)
    assert not client.search.call_args.kwargs.get("include_domains")


def test_related_agencies_do_not_create_an_unrequested_comparison():
    chunk = source("You can apply for the benefit through the official portal.")
    question = policy.QuestionPlan("benefit application", False, True, "current",
        entities=("Tax agency", "Finance ministry"), original_question="How do I apply for this benefit?")
    payload = dict(status="sufficient", missing=[], conflicting=False, jurisdiction_matches=True,
                   period_matches=True, support=[dict(source_id=1, quote=chunk.content)])
    result = policy.assess_evidence(question, [chunk],
        generate=lambda *a, **k: SimpleNamespace(content=json.dumps(payload)))
    assert result.status == "sufficient" and not result.missing


def test_discovery_includes_sibling_official_subdomains():
    institution = policy.QuestionPlan("application", False, True, "current", entities=("AKPK",))
    portal = replace(source("AKPK application portal."), url="https://dm.akpk.org.my/application")
    assert policy._discovery_domains(institution, [portal]) == ("akpk.org.my",)


def test_local_window_failure_can_use_the_remaining_search_slot():
    from app.rag.web_research import ResearchOutcome
    chunk = source()
    approvals = [policy.EvidenceAssessment("insufficient", ("application",))] * 2 + [
        policy.EvidenceAssessment("sufficient", supported_sources=(1,), supported_quotes=((1, chunk.content),))]
    outcomes = [ResearchOutcome([chunk], True, "ok"), ResearchOutcome([], True, "no_results"),
                ResearchOutcome([replace(chunk, content=chunk.content + " Read the form guidance.")], True, "ok")]
    with (patch.object(policy, "assess_evidence", side_effect=approvals),
          patch.object(policy, "research_evidence", side_effect=outcomes),
          patch.object(policy, "extract_passages", return_value={chunk.url: chunk.content})):
        result = policy.run_research_policy(policy.QuestionPlan("application", False, True, "current", entities=("PTPTN",)),
            [], generate=MagicMock(), budget=CoachRequestBudget.start(), api_key="test", web_enabled=True,
            max_results=4, timeout=8)
    assert result.assessment.supported_quotes and result.diagnostics["empty_evidence_recovery_used"] == 1


def test_english_gap_finds_malay_document_section_on_cached_page():
    raw = ("## Benefit programme\n\nGeneral benefit programme application instructions.\n\n"
           + "General information. " * 110 + "\n\n"
           + "## Dokumen sokongan\n\nPemohon berkahwin: sijil perkahwinan dan kad pengenalan.\n\n"
           + "Footer navigation. " * 110)
    selected = web._complete_page_window(raw, "supporting documents for married applicants",
                                         subject_query="benefit programme")
    assert "sijil perkahwinan" in selected


@pytest.mark.parametrize("question", ["What does ICU JPM do? Explain in English.",
                                     "What is the role of ICU JPM in Malaysia?"])
def test_language_and_jurisdiction_are_not_programme_context(question):
    proposed = policy.QuestionPlan("ICU JPM role in SARA", False, True, "stable",
        entities=("ICU JPM",), required_facts=("SARA eligibility",), response_language="en")
    normalized = policy._normalize_question_scope(proposed, question)
    assert normalized.scope == "general" and "SARA" not in normalized.topic


def test_explicit_comparison_retains_referenced_institution():
    proposed = policy.QuestionPlan("Compare STR with AKPK", False, True, "current",
        entities=("STR", "AKPK"), required_facts=("Compare STR and AKPK purposes",), scope="contextual")
    normalized = policy._normalize_question_scope(proposed, "How does STR compare with it?")
    assert normalized.entities == ("STR", "AKPK") and normalized.required_facts


def test_what_does_requirement_question_is_not_an_agency_role():
    proposed = policy.QuestionPlan("Programme application documents", False, True, "current",
        entities=("AKPK",), required_facts=("documents required",))
    result = policy._normalize_question_scope(proposed, "What does AKPK need from me?")
    assert result.topic == proposed.topic and result.required_facts == proposed.required_facts


def test_late_initial_draft_uses_remaining_time_for_verification():
    from app import llm
    from app.rag import research_answer as module
    from app.rag.grounding import DISCLAIMER
    chunk = source()
    decision = policy.ResearchDecision([chunk], policy.EvidenceAssessment("sufficient",
        supported_sources=(1,), supported_quotes=((1, chunk.content),)))
    draft = llm.LLMResult(f"**Insight**\nApply online [S1].\n\n**Recommended action**\nSubmit via the portal [S1].\n\n**Educational guidance**\n{DISCLAIMER}", "primary")
    def checking(text, **kw):
        assert kw["budget"].started_at == 0
        assert kw["budget"].timeout_for("verifier") > 0
        return module.ResearchDraftCheck(True, approved_text=text)
    with (patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "monotonic", return_value=52),
          patch.object(module, "check_research_draft", side_effect=checking),
          patch.object(module, "_generate_research_correction") as rewrite):
        result = module.recover_research_answer(plan=policy.QuestionPlan("application", False, True, "current"),
            decision=decision, draft=draft, budget=CoachRequestBudget(0), public_question="How do I apply?")
    assert result.mode == "research_explanation"
    rewrite.assert_not_called()


def test_long_scope_label_does_not_discard_valid_claim_verdicts():
    from app.rag import verifier
    from app.rag.grounding import GroundingClaim
    payload = {"claims": [{"id": 1, "verdict": "supported", "source_index": 1, "scope_relation": "preserved"}],
        "quality_errors": [], "requested_scope_covered": False,
        "unanswered_requested_parts": ["complete supporting documents for all eligible applicant categories " * 3]}
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[
        SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    with patch.object(verifier, "_create_verifier_client", return_value=client):
        result = verifier.verify_grounding_claims([GroundingClaim(1, "Apply online.", (1,))],
            ["Apply online."], timeout_seconds=5, research_context=verifier.ResearchVerificationContext(
                "How do I apply and what documents?", "Apply online.", (), enforce_scope=True))
    assert result.error_code is None and result.verdicts == {1: "supported"}
    assert result.unanswered_requested_parts and len(result.unanswered_requested_parts[0]) <= 100


def test_scope_is_incomplete_after_rejected_deadline_is_removed():
    from app.rag import research_answer as module
    from app.rag.verifier import GroundingVerification
    from app.rag.grounding import DISCLAIMER
    chunk = source("Apply through the portal within 12 months.")
    decision = policy.ResearchDecision([chunk], policy.EvidenceAssessment("sufficient",
        supported_sources=(1,), supported_quotes=((1, chunk.content),)))
    draft = f"**Insight**\nApply through the portal [S1].\n\n**Recommended action**\nUse the portal [S1].\n\nApply within 24 months [S1].\n\n**Educational guidance**\n{DISCLAIMER}"
    def verify(claims, *_a, **_k):
        return GroundingVerification({c.id: "supported" for c in claims}, {c.id: 1 for c in claims},
                                     requested_scope_covered=True)
    with patch.object(module, "verify_grounding_claims", side_effect=verify):
        result = module.check_research_draft(draft, public_question="How do I apply and what deadline?",
            decision=decision, budget=CoachRequestBudget.start())
    assert result.approved_text and "24 months" not in result.approved_text
    assert result.diagnostics["requested_scope_covered"] is False
    assert result.diagnostics["unanswered_requested_parts"]
