"""Non-finance questions: published knowledge first, then a referral without web
research; mixed questions get a short referral note; retry messages by cause."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import llm
from app.llm import LLMResult
from app.rag import request_interpretation as intent
from app.rag import research_answer as answer
from app.rag import research_policy
from app.rag import service
from app.rag.research_answer import ResearchDraftCheck
from app.rag.research_coverage import PartCoverage
from app.rag.research_policy import EvidenceAssessment, QuestionPlan, ResearchDecision
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import ResearchOutcome
from test_kb_reduced_release import RETRY, _assistant, _interpret

REFERRAL = "I don't have enough information to answer this topic. Please refer to learning resources on the subject."


def _public(topic, **public):
    return {"route": "financial_education", "public": {"topic": topic, **public}}


def _plan(payload, question="q"):
    p = intent._normalise_proposal(intent.IntentProposal.model_validate(payload))
    return intent._public_plan(p, question)


# ---- Interpreter label ----------------------------------------------------------

@pytest.mark.parametrize("payload,scope", [
    (_public("message passing", subject_domain="non_finance"), "non_finance"),
    (_public("ptptn", subject_domain="finance"), "finance"),
    (_public("tuition fees", subject_domain="finance"), "finance"),
    (_public("message passing and laptop savings", subject_domain="mixed",
             parts=[{"fact": "what message passing is", "domain": "non_finance"},
                    {"fact": "how to save for a laptop", "domain": "finance"}]), "mixed"),
    (_public("ptptn"), "unknown"),  # older stored proposal / no label
])
def test_scope_label_reaches_the_plan(payload, scope):
    assert _plan(payload).finance_scope == scope


def test_planning_a_stated_amount_is_never_wholly_non_finance():
    plan = _plan({**_public("laptop", subject_domain="non_finance", framework="allocation", stated_amount="3000"),
                  "goal": "plan"})
    assert plan.finance_scope == "finance"


# ---- Service: knowledge base first, then referral without web -----------------

def _semantic(monkeypatch, payload, question):
    p = intent._normalise_proposal(intent.IntentProposal.model_validate(payload))
    semantic = intent.InterpretedRequest(p, intent.compile_read(p, date(2026, 10, 25)), intent._public_plan(p, question),
                                         context={"version": 1, "anchor_date": "2026-10-25", "proposal": p.model_dump()})
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", lambda *a, **k: semantic)


def _send(text):
    repository = MagicMock(user_id="u")
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    return service.CoachingService(repository, MagicMock()).send_message("s", "m", text)["assistant_message"]


def _count_web(monkeypatch):
    calls = {"search": 0, "extract": 0}

    def search(*a, **k):
        calls["search"] += 1
        return ResearchOutcome([], True, "ok")

    def extract(*a, **k):
        calls["extract"] += 1
        return {}
    monkeypatch.setattr(research_policy, "research_evidence", search)
    monkeypatch.setattr(research_policy, "extract_passages", extract)
    return calls


def test_unsupported_non_finance_question_gets_the_referral_and_zero_web_calls(monkeypatch):
    calls = _count_web(monkeypatch)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(research_policy, "assess_evidence",
                        lambda *a, **k: EvidenceAssessment("insufficient", ("what message passing is",)))
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: pytest.fail("no writer for no evidence"))
    _semantic(monkeypatch, _public("message passing", subject_domain="non_finance"), "what is message passing")
    message = _send("what is message passing")
    assert calls == {"search": 0, "extract": 0}
    assert message["content"] == REFERRAL


def test_non_finance_question_with_published_evidence_is_answered(monkeypatch):
    calls = _count_web(monkeypatch)
    text = "The assignment brief requires message passing with no shared mutable state."
    chunk = RetrievedChunk(1, "a1 group", "up_a1.md", None, 0, text, 0.6)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(research_policy, "assess_evidence", lambda *a, **k: EvidenceAssessment(
        "sufficient", supported_sources=(1,), supported_quotes=((1, text),),
        parts=(PartCoverage("p1", "direct", (1,), complete=True),)))
    monkeypatch.setattr(service, "generate_result",
                        lambda *a, **k: LLMResult("**Insight**\nThe brief requires message passing [S1].", "gemini"))
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: ResearchDraftCheck(
        True, approved_text="**Insight**\nThe brief requires message passing [S1].", diagnostics={}))
    _semantic(monkeypatch, _public("message passing in the assignment", subject_domain="non_finance"),
              "does the assignment use message passing")
    message = _send("does the assignment use message passing")
    assert calls == {"search": 0, "extract": 0}
    assert "requires message passing" in message["content"] and REFERRAL not in message["content"]


@pytest.mark.parametrize("scope", ["finance", None])
def test_finance_and_unlabelled_questions_keep_web_research(monkeypatch, scope):
    seen = {}
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "run_research_policy", lambda plan, chunks, **k: seen.update(web=k["web_enabled"])
                        or ResearchDecision([], EvidenceAssessment("insufficient"), failure="research_round_limit"))
    extra = {"subject_domain": scope} if scope else {}
    _semantic(monkeypatch, _public("ptptn repayment", **extra), "how does ptptn repayment work")
    message = _send("how does ptptn repayment work")
    assert seen["web"] is True
    assert message["content"] == answer._INSUFFICIENT_EVIDENCE_MESSAGES["en"]


def test_technical_failure_beats_the_referral(monkeypatch):
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "run_research_policy", lambda *a, **k: ResearchDecision(
        [], EvidenceAssessment("insufficient"), failure="assessment_unavailable"))
    _semantic(monkeypatch, _public("message passing", subject_domain="non_finance"), "what is message passing")
    assert _send("what is message passing")["content"] == answer._TEMPORARY_FAILURE_MESSAGES["en"]


@pytest.mark.parametrize("language", ["en", "ms", "zh", "ta"])
def test_referral_in_every_supported_language(language):
    plan = QuestionPlan("x", False, True, "stable", response_language=language, finance_scope="non_finance")
    assert answer.no_evidence_message(plan, "search_disabled") == answer._OUT_OF_SCOPE_MESSAGES[language]


# ---- Retry messages by cause ------------------------------------------------------

def _action_history(kind, title="x"):
    return [{"id": "u1", "role": "user", "content": "do it"},
            _assistant({"route": "personal_finance", "actions": [{"kind": kind, "title": title}]})]


@pytest.mark.parametrize("kind,text", [
    ("create_reminder", "Creating reminders through the coach is currently unavailable."),
    ("generate_report", "Creating reports through the coach is currently unavailable."),
])
def test_blocked_action_retry_names_the_unavailable_action(monkeypatch, kind, text):
    monkeypatch.setattr(intent, "COACH_WRITE_ACTIONS_ENABLED", False)
    result = _interpret("try again", _action_history(kind), RETRY)
    assert result.proposal is None and result.failure_message == text


def test_action_retry_with_writes_enabled_still_never_executes(monkeypatch):
    monkeypatch.setattr(intent, "COACH_WRITE_ACTIONS_ENABLED", True)
    result = _interpret("try again", _action_history("create_reminder"), RETRY)
    assert result.proposal is None
    assert result.failure_message == intent._RETRY_ACTION_NOT_REPEATED_MESSAGES["en"]


def test_missing_earlier_question_and_blocked_action_differ(monkeypatch):
    monkeypatch.setattr(intent, "COACH_WRITE_ACTIONS_ENABLED", False)
    missing = _interpret("try again", [], RETRY).failure_message
    blocked = _interpret("try again", _action_history("create_reminder"), RETRY).failure_message
    assert missing == intent._RETRY_NO_REQUEST_MESSAGES["en"] and missing != blocked


def test_answer_retry_still_repeats_the_question():
    history = [{"id": "u1", "role": "user", "content": "what is message passing"},
               _assistant(_public("message passing", subject_domain="non_finance"))]
    result = _interpret("try again", history, RETRY)
    assert result.proposal.public.topic == "message passing" and result.public_plan.finance_scope == "non_finance"


# ---- Mixed questions: what actually leaves FinCoach --------------------------------

def _outbound(plan, assessment):
    """Run the real research policy; record every web search and extraction."""
    from unittest.mock import patch
    calls = []

    def search(query, **kwargs):
        calls.append(f"{query} || {kwargs.get('subject_query') or ''}")
        return ResearchOutcome([], True, "ok")

    def extract(urls, **kwargs):
        calls.append(f"{kwargs.get('query') or ''} || {kwargs.get('subject_query') or ''}")
        return {}
    with (patch.object(research_policy, "research_evidence", side_effect=search),
          patch.object(research_policy, "extract_passages", side_effect=extract),
          patch.object(research_policy, "assess_evidence", return_value=assessment)):
        research_policy.run_research_policy(plan, [], generate=MagicMock(), budget=llm.CoachRequestBudget.start(),
                                            api_key="test", web_enabled=True, max_results=4, timeout=4)
    return calls


def test_finance_only_question_search_is_unchanged():
    facts = ["eligibility requirements"]
    plan = _plan(_public("PTPTN eligibility", subject_domain="finance", required_facts=facts), "PTPTN eligibility?")
    assert research_policy.financial_search_plan(plan) is plan


# ---- Mixed questions with explicit parts ---------------------------------------------

def _part(fact, domain, *entities):
    return {"fact": fact, "domain": domain, "entities": list(entities)}


def _mixed(topic, *parts, **extra):
    return _public(topic, subject_domain="mixed", parts=list(parts), **extra)


def test_reviewer_repro_what_is_ptptn_and_message_passing_blocks_only_message_passing():
    # Reproduced bug: shared words ("what", "is") flipped which part was blocked.
    plan = _plan(_mixed("PTPTN and message passing",
                        _part("what PTPTN is", "finance", "PTPTN"),
                        _part("definition of message passing", "non_finance")),
                 "What is PTPTN, and what is message passing?")
    from app.rag.research_coverage import non_finance_part_ids, web_research_parts
    assert non_finance_part_ids(plan) == ("p2",)
    assert [part.id for part in web_research_parts(plan)] == ["p1"]
    calls = _outbound(plan, EvidenceAssessment("insufficient", ("what PTPTN is", "definition of message passing")))
    assert calls
    for call in calls:
        assert "ptptn" in call.casefold(), call
        assert "message" not in call.casefold() and "passing" not in call.casefold(), call


def test_reviewers_laptop_question_searches_only_the_finance_part():
    plan = _plan(_mixed("message passing and laptop savings",
                        _part("what message passing is", "non_finance"),
                        _part("how to save for a laptop", "finance")),
                 "Explain message passing and how to save for a laptop")
    calls = _outbound(plan, EvidenceAssessment("insufficient", ("what message passing is", "how to save for a laptop")))
    assert calls
    for call in calls:
        assert "laptop" in call.casefold(), call
        assert "message" not in call.casefold() and "passing" not in call.casefold(), call


def test_finance_entity_is_kept_when_its_part_label_omits_it():
    plan = _plan(_mixed("PTPTN eligibility and message passing",
                        _part("eligibility requirements", "finance", "PTPTN"),
                        _part("what message passing is", "non_finance")))
    calls = _outbound(plan, EvidenceAssessment("insufficient", ("eligibility requirements",)))
    assert calls
    for call in calls:
        assert "ptptn" in call.casefold() and "message" not in call.casefold(), call


def test_assessor_gap_text_is_never_searched_for_a_mixed_question():
    plan = _plan(_mixed("PTPTN and message passing",
                        _part("what PTPTN is", "finance", "PTPTN"),
                        _part("definition of message passing", "non_finance")))
    calls = _outbound(plan, EvidenceAssessment("insufficient", ("message passing in distributed systems",)))
    assert all("message" not in call.casefold() for call in calls)


def test_no_web_search_once_the_finance_part_is_answered():
    plan = _plan(_mixed("message passing and laptop savings",
                        _part("what message passing is", "non_finance"),
                        _part("how to save for a laptop", "finance")))
    answered = EvidenceAssessment("partial", ("what message passing is",), supported_sources=(1,),
                                  parts=(PartCoverage("p1", "missing"),
                                         PartCoverage("p2", "direct", (1,), complete=True)))
    assert _outbound(plan, answered) == []


def test_reviewer_repro_mixed_note_works_without_separate_required_facts():
    # Reproduced bug: with the recorded empty required_facts shape no part was
    # found and the referral note vanished. Parts now carry their own facts.
    plan = _plan(_mixed("PTPTN eligibility requirements and message passing",
                        _part("PTPTN eligibility requirements", "finance", "PTPTN"),
                        _part("what is message passing", "non_finance")))
    assert plan.required_facts and plan.part_domains == ("finance", "non_finance")
    uncovered = (PartCoverage("p1", "direct", (1,), complete=True), PartCoverage("p2", "missing"))
    assert answer.non_finance_part_note(plan, uncovered) == answer._NON_FINANCE_PART_MESSAGES["en"]
    covered = (PartCoverage("p1", "direct", (1,), complete=True), PartCoverage("p2", "direct", (1,), complete=True))
    assert answer.non_finance_part_note(plan, covered) is None


def test_mixed_question_is_not_collapsed_into_one_definition():
    plan = _plan(_mixed("PTPTN and message passing",
                        _part("what PTPTN is", "finance", "PTPTN"),
                        _part("definition of message passing", "non_finance")),
                 "What is PTPTN, and what is message passing?")
    assert not plan.definitional and len(plan.required_facts) == 2


def test_mixed_question_keeps_web_research_for_its_finance_part(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "run_research_policy", lambda plan, chunks, **k: seen.update(web=k["web_enabled"])
                        or ResearchDecision([], EvidenceAssessment("insufficient"), failure="research_round_limit"))
    _semantic(monkeypatch, _mixed("message passing and laptop savings",
                                  _part("what message passing is", "non_finance"),
                                  _part("how to save for a laptop", "finance")),
              "explain message passing and how to save for a laptop")
    _send("explain message passing and how to save for a laptop")
    assert seen["web"] is True


# ---- Incomplete mixed interpretations: repair once, then clarify ------------------------

INCOMPLETE = {"route": "financial_education", "public": {
    "topic": "PTPTN eligibility requirements and message passing", "subject_domain": "mixed"}}
COMPLETE = _mixed("PTPTN eligibility requirements and message passing",
                  _part("PTPTN eligibility requirements", "finance", "PTPTN"),
                  _part("what is message passing", "non_finance"))


def test_incomplete_mixed_reading_is_repaired_by_one_more_interpretation():
    result = _interpret("What are PTPTN eligibility requirements, and what is message passing?", [],
                        INCOMPLETE, COMPLETE)
    assert len(_interpret.inputs) == 2  # the original reading plus exactly one repair
    assert result.public_plan.part_domains == ("finance", "non_finance")


@pytest.mark.parametrize("repair", [INCOMPLETE, TimeoutError()])
def test_unrepairable_mixed_reading_asks_to_split_the_question_without_guessing(repair):
    result = _interpret("What are PTPTN eligibility requirements, and what is message passing?", [],
                        INCOMPLETE, repair)
    assert result.proposal is None and result.failure == "read_constraint"
    assert result.failure_message == intent._SPLIT_QUESTION_MESSAGES["en"]


def test_one_sided_parts_count_as_incomplete():
    proposal = intent.IntentProposal.model_validate(_mixed("x", _part("a", "finance"), _part("b", "finance")))
    assert intent._incomplete_mixed(proposal) and not intent._complete_mixed_parts(proposal)


def test_live_shape_combined_without_a_records_read_is_the_public_route():
    raw = {"route": "combined", "relation": "new", "read": None, "goal": "explain",
           "public": {"topic": "PTPTN eligibility requirements and message passing", "subject_domain": "mixed",
                      "parts": [_part("PTPTN eligibility requirements", "finance", "PTPTN"),
                                _part("what is message passing", "non_finance")]},
           "response_language": "en", "requested_output": "summary"}
    proposal = intent._normalise_proposal(intent.IntentProposal.model_validate(raw))
    assert proposal.route == "financial_education"


# ---- Repair must keep both labelled parts; same wording never merges parts ------------

FINANCE_ONLY_REPAIR = _public("PTPTN eligibility requirements and message passing", subject_domain="finance",
                              required_facts=["PTPTN eligibility requirements", "what is message passing"])
ONE_SIDED_REPAIR = _mixed("PTPTN eligibility requirements and message passing",
                          _part("PTPTN eligibility requirements", "finance", "PTPTN"),
                          _part("what is message passing", "finance"))


@pytest.mark.parametrize("repair", [FINANCE_ONLY_REPAIR, ONE_SIDED_REPAIR])
def test_reviewer_repro_a_repair_that_drops_the_non_finance_label_is_not_accepted(repair):
    # Reproduced bug: the repair answered "finance only", was accepted, and then
    # "message passing" was searched. It must lead to the split-question reply.
    result = _interpret("What are PTPTN eligibility requirements, and what is message passing?", [],
                        INCOMPLETE, repair)
    assert len(_interpret.inputs) == 2
    assert result.proposal is None and result.public_plan is None
    assert result.failure_message == intent._SPLIT_QUESTION_MESSAGES["en"]


SAME_WORDING = _mixed("PTPTN and university admission eligibility",
                      _part("eligibility requirements", "finance", "PTPTN"),
                      _part("eligibility requirements", "non_finance", "university admission"))


def test_reviewer_repro_same_worded_parts_keep_their_own_ids_and_domains():
    from app.rag.research_coverage import non_finance_part_ids, requested_parts, web_research_parts
    plan = _plan(SAME_WORDING, "What are the eligibility requirements for PTPTN and for university admission?")
    parts = requested_parts(plan)
    assert [part.id for part in parts] == ["p1", "p2"]
    assert parts[0].label != parts[1].label  # entity-qualified for the evidence check
    assert non_finance_part_ids(plan) == ("p2",)
    assert [part.id for part in web_research_parts(plan)] == ["p1"]


def test_same_worded_non_finance_part_never_reaches_web_search():
    plan = _plan(SAME_WORDING, "What are the eligibility requirements for PTPTN and for university admission?")
    calls = _outbound(plan, EvidenceAssessment("insufficient", ("PTPTN eligibility requirements",
                                                                "university admission eligibility requirements")))
    assert calls
    for call in calls:
        assert "ptptn" in call.casefold(), call
        assert "university" not in call.casefold() and "admission" not in call.casefold(), call


def test_same_worded_non_finance_part_gets_the_referral_note():
    plan = _plan(SAME_WORDING)
    uncovered = (PartCoverage("p1", "direct", (1,), complete=True), PartCoverage("p2", "missing"))
    assert answer.non_finance_part_note(plan, uncovered) == answer._NON_FINANCE_PART_MESSAGES["en"]


def test_identical_parts_without_entities_still_stay_separate():
    from app.rag.research_coverage import non_finance_part_ids, requested_parts, web_research_parts
    plan = _plan(_mixed("eligibility", _part("eligibility requirements", "finance"),
                        _part("eligibility requirements", "non_finance")))
    assert [part.id for part in requested_parts(plan)] == ["p1", "p2"]
    assert non_finance_part_ids(plan) == ("p2",)
    assert [part.id for part in web_research_parts(plan)] == ["p1"]
