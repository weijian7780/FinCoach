from dataclasses import replace
from types import SimpleNamespace
import json
import logging
import pytest
from app.llm import CoachRequestBudget, LLMResult
from app.rag import research_answer as answer
from app.rag.research_coverage import RequestedPart
from app.rag.research_policy import EvidenceAssessment, ResearchDecision
from test_research_evidence_handoff import PLAN, _decision


@pytest.mark.parametrize("lang", ["en","ms","zh","ta"])
@pytest.mark.parametrize("code,expected", [
    ("product_recommendation","product_steering"),("unsupported_number","no_evidence"),
    ("no_supported_facts","no_evidence"),("verifier_timeout","technical"),
    ("answer_output_truncated","unusable_draft"),("future_unmapped_code","unknown")])
def test_final_display_and_logged_reason(monkeypatch,caplog,lang,code,expected):
    monkeypatch.setattr(answer,"check_research_draft",lambda *a,**k:answer.ResearchDraftCheck(False,(code,)))
    def failed_rewrite(*a,**k): raise TimeoutError()
    monkeypatch.setattr(answer,"_generate_research_correction",failed_rewrite)
    with caplog.at_level(logging.INFO,logger="uvicorn.error"):
        outcome=answer.recover_research_answer(plan=replace(PLAN,response_language=lang),
            decision=_decision(),draft=LLMResult("draft","test"),budget=CoachRequestBudget.start(),public_question="test")
    table={"product_steering":answer._PRODUCT_MESSAGES,"no_evidence":answer._INSUFFICIENT_EVIDENCE_MESSAGES,
        "technical":answer._RETRY_MESSAGES,"unusable_draft":answer._RETRY_MESSAGES,"unknown":answer._UNKNOWN_MESSAGES}[expected]
    assert outcome.result.content==table[lang]
    assert outcome.diagnostics["reply_reason"]==expected
    assert outcome.diagnostics["cause_codes"]==[code]
    assert outcome.diagnostics["terminal_reason"]=="recovery_generation_unavailable"
    events=[json.loads(r.getMessage()) for r in caplog.records if 'coach_answer_recovery' in r.getMessage()]
    assert events[-1]["reply_reason"]==expected


def test_known_reasons_have_unique_membership():
    categories=answer._FAILURE_CODES
    assert sum(map(len,categories.values()))==len(set().union(*categories.values()))
    for reason,codes in categories.items():
        for code in codes:
            assert answer._failure_reply("en",(),(code,))[0]==reason


@pytest.mark.parametrize("failure,reason",[("extraction_failed","no_evidence"),("timeout","technical")])
def test_early_no_evidence_keeps_source_reason(failure,reason):
    outcome=answer.recover_research_answer(plan=PLAN,decision=ResearchDecision([],EvidenceAssessment("insufficient"),failure=failure),
        draft=None,budget=CoachRequestBudget.start(),public_question="question")
    assert outcome.result.content==answer.no_evidence_message(PLAN,failure)
    assert outcome.diagnostics["reply_reason"]==reason


def test_failed_correction_keeps_checked_content(monkeypatch):
    monkeypatch.setattr(answer,"check_research_draft",lambda *a,**k:answer.ResearchDraftCheck(False,("unsupported_number",),
        approved_text="Verified part [S1].",diagnostics={"approved_claim_count":1}))
    def offline(*a,**k): raise TimeoutError()
    monkeypatch.setattr(answer,"_generate_research_correction",offline)
    outcome=answer.recover_research_answer(plan=PLAN,decision=_decision(),draft=LLMResult("draft","model"),
        budget=CoachRequestBudget.start(),public_question="question")
    assert outcome.result.content=="Verified part [S1]."
    assert outcome.diagnostics["reply_reason"]=="partial"


def test_plan_labels_survive_missing_verifier_wording():
    parts=(RequestedPart("p1","Eligibility"),RequestedPart("p2","Deadline"))
    check=SimpleNamespace(unanswered_requested_parts=("untrusted wording",),answered_part_ids=("p1",))
    assert answer._missing_labels(check,parts)==("Deadline",)
    assert answer._missing_labels(check,(RequestedPart("p2","p2"),))==()
