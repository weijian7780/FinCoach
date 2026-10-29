"""Non-finance questions: published knowledge first, then a referral without web
research; mixed questions get a short referral note; retry messages by cause."""
import json
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

# ---- An amount on a read that cannot filter by amount (recorded live readings) ---------

LAPTOP_QUESTION = "explain message passing and how much should I save each month for a RM3000 laptop"
# Gemini's rejected reading on the live backend, 2026-10-25 (run 4 of 12).
LIVE_PRICE_ON_READ = {
    "route": "combined", "relation": "new",
    "read": {"operation": "predict_savings", "category": {"decision": "none", "name": None, "built_in": None},
             "amount": "3000"},
    "public": {"topic": "message passing", "subject_domain": "non_finance",
               "parts": [{"fact": "explain message passing", "domain": "non_finance"},
                         {"fact": "how much should I save each month for a RM3000 laptop", "domain": "finance"}]},
    "response_language": "en", "requested_output": "advice", "goal": "explain"}
# An accepted live reading of the same question: the price is the planned target.
LAPTOP_TARGET = {
    **LIVE_PRICE_ON_READ,
    "read": {"operation": "predict_savings", "category": {"decision": "none"}},
    "public": {**LIVE_PRICE_ON_READ["public"], "subject_domain": "mixed", "stated_amount": "3000"}}
LAPTOP_PRICE_DROPPED = {**LAPTOP_TARGET, "public": {**LAPTOP_TARGET["public"], "stated_amount": None}}

# Reviewer's counterexample: RM50 is a transaction filter on the wrong operation.
RM50_QUESTION = "summarise my RM50 transactions and explain compound interest"
RM50_ON_SUMMARY = {
    "route": "combined", "relation": "new", "goal": "explain",
    "read": {"operation": "get_spending_summary", "category": {"decision": "none"}, "amount": "50",
             "result_mode": "expense_total"},
    "public": {"topic": "compound interest", "subject_domain": "finance"}}
RM50_AS_FILTER = {**RM50_ON_SUMMARY, "read": {
    "operation": "search_transactions", "category": {"decision": "none"}, "amount": "50",
    "result_mode": "expense_total"}}
RM50_DROPPED = {**RM50_ON_SUMMARY, "read": {"operation": "get_spending_summary", "category": {"decision": "none"},
                                            "result_mode": "expense_total"}}

# Finance-only laptop question, as Gemini reads it on live (4 of 5 runs).
SAVE_QUESTION = "how much should I save each month for a RM3000 laptop"
SAVE_PRICE_ON_READ = {"route": "personal_finance", "relation": "new", "goal": "plan",
                      "read": {"operation": "predict_savings", "category": {"decision": "none"}, "amount": "3000"},
                      "public": None, "response_language": "en", "requested_output": "advice"}
SAVE_TARGET = {"route": "combined", "relation": "new", "goal": "plan",
               "read": {"operation": "predict_savings", "category": {"decision": "none"}},
               "public": {"topic": "saving for a laptop", "subject_domain": "finance", "stated_amount": "3000"},
               "response_language": "en", "requested_output": "advice"}
SAVE_PRICE_DROPPED = {**SAVE_PRICE_ON_READ, "read": {"operation": "predict_savings", "category": {"decision": "none"}}}
ASK_RM3000 = ("Is RM3,000 a price or savings target you are planning for, or should I look for transactions "
              "of RM3,000? Please tell me which.")


def test_reviewer_repro_misplaced_laptop_price_is_re_read_and_kept_as_the_target():
    # Reproduced bug: "Transaction filters require search_transactions" ended the
    # turn with "I couldn't understand this request reliably this time".
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_TARGET)
    assert len(_interpret.inputs) == 2  # the original reading plus exactly one repair
    assert result.failure is None and result.proposal.public.stated_amount == "3000"
    assert result.resolved.tool_name == "predict_savings" and "amount" not in result.resolved.arguments
    assert result.public_plan.part_domains == ("non_finance", "finance")


def test_amount_repair_instruction_precedes_the_input_data():
    prompts = []

    def generate(prompt, *, validate, **kwargs):
        prompts.append(prompt)
        return validate(json.dumps(LIVE_PRICE_ON_READ if len(prompts) == 1 else LAPTOP_TARGET))
    intent.interpret_request(LAPTOP_QUESTION, [], today=date(2026, 10, 24), budget=llm.CoachRequestBudget.start(),
                             generate=generate)
    head, data = prompts[1].split("\nINPUT DATA:\n", 1)
    assert "REPAIR:" in head and "predict_savings" in head and "REPAIR" not in data


def test_reviewer_counterexample_rm50_filter_is_never_dropped():
    # Moving every misplaced amount would have summarised ALL of the month's transactions.
    result = _interpret(RM50_QUESTION, [], RM50_ON_SUMMARY, RM50_DROPPED)
    assert result.proposal is None and result.failure == "read_constraint"
    assert result.failure_message == intent._AMOUNT_MEANING_MESSAGES["en"].format(amount="50")


def test_rm50_repaired_as_a_transaction_filter_keeps_the_filter():
    result = _interpret(RM50_QUESTION, [], RM50_ON_SUMMARY, RM50_AS_FILTER)
    assert result.failure is None
    assert result.resolved.tool_name == "search_transactions" and result.resolved.arguments["amount"] == "50"


def test_rm50_still_misplaced_after_repair_asks_instead_of_guessing():
    result = _interpret(RM50_QUESTION, [], RM50_ON_SUMMARY, RM50_ON_SUMMARY)
    assert len(_interpret.inputs) == 2 and result.failure == "read_constraint"


def test_amount_kept_both_as_filter_and_target_is_ambiguous():
    both = {**RM50_AS_FILTER, "public": {**RM50_ON_SUMMARY["public"], "stated_amount": "50"}}
    assert _interpret(RM50_QUESTION, [], RM50_ON_SUMMARY, both).failure == "read_constraint"


def test_finance_only_laptop_question_keeps_the_rm3000_target():
    result = _interpret(SAVE_QUESTION, [], SAVE_PRICE_ON_READ, SAVE_TARGET)
    assert result.failure is None and result.proposal.public.stated_amount == "3000"
    assert result.resolved.tool_name == "predict_savings"


@pytest.mark.parametrize("repair", [SAVE_PRICE_DROPPED, TimeoutError()])
def test_finance_only_laptop_price_is_never_silently_discarded(repair):
    result = _interpret(SAVE_QUESTION, [], SAVE_PRICE_ON_READ, repair)
    assert result.proposal is None and result.failure == "read_constraint"
    assert result.failure_message == ASK_RM3000


def test_mixed_repair_that_drops_the_price_asks_instead():
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_PRICE_DROPPED)
    assert result.failure == "read_constraint" and result.failure_message == ASK_RM3000


def test_valid_first_reading_is_not_re_read():
    result = _interpret(SAVE_QUESTION, [], SAVE_TARGET)
    assert len(_interpret.inputs) == 1 and result.failure is None


def test_invalid_amount_keeps_the_existing_rejection():
    bad = {**SAVE_PRICE_ON_READ, "read": {**SAVE_PRICE_ON_READ["read"], "amount": "-3000"}}
    result = _interpret(SAVE_QUESTION, [], bad)
    assert len(_interpret.inputs) == 1 and result.failure == "interpretation_unavailable"


def test_reading_with_both_part_labels_is_mixed_even_when_labelled_non_finance():
    plan = _plan({**LAPTOP_TARGET, "public": {**LAPTOP_TARGET["public"], "subject_domain": "non_finance"}})
    assert plan.finance_scope == "mixed" and plan.part_domains == ("non_finance", "finance")


def test_repaired_laptop_reading_never_sends_message_passing_to_web_search():
    plan = _plan(LAPTOP_TARGET, LAPTOP_QUESTION)
    calls = _outbound(plan, EvidenceAssessment("insufficient", ("explain message passing",
                                                                "how much should I save each month for a laptop")))
    assert calls
    for call in calls:
        assert "laptop" in call.casefold(), call
        assert "message" not in call.casefold() and "passing" not in call.casefold(), call


def test_transaction_amount_filter_is_unchanged():
    result = _interpret("show my RM50 transactions", [], {
        "route": "personal_finance", "relation": "new", "goal": "show",
        "read": {"operation": "search_transactions", "category": {"decision": "none"}, "amount": "50"}})
    assert len(_interpret.inputs) == 1 and result.resolved.arguments["amount"] == "50"


@pytest.mark.parametrize("repair", [
    # Allocation would split RM3,000 50/30/20 as if it were income.
    {"route": "financial_education", "relation": "new", "goal": "plan",
     "public": {"topic": "saving for a laptop", "framework": "allocation", "stated_amount": "3000"}},
    # No records read: the normaliser makes "plan a stated amount" allocation too.
    {"route": "financial_education", "relation": "new", "goal": "plan",
     "public": {"topic": "saving for a laptop", "stated_amount": "3000"}},
])
def test_repaired_price_is_never_treated_as_an_amount_to_allocate(repair):
    result = _interpret(SAVE_QUESTION, [], SAVE_PRICE_ON_READ, repair)
    assert result.proposal is None and result.failure_message == ASK_RM3000


def test_rm50_filter_with_a_different_stated_amount_is_not_accepted():
    other = {**RM50_AS_FILTER, "public": {**RM50_ON_SUMMARY["public"], "stated_amount": "75"}}
    assert _interpret(RM50_QUESTION, [], RM50_ON_SUMMARY, other).failure == "read_constraint"


def test_rm50_repaired_as_a_target_on_a_spending_summary_is_not_accepted():
    # A spending summary with "RM50" as a target would again summarise ALL transactions.
    as_target = {**RM50_DROPPED, "public": {**RM50_ON_SUMMARY["public"], "stated_amount": "50"}}
    result = _interpret(RM50_QUESTION, [], RM50_ON_SUMMARY, as_target)
    assert result.proposal is None and result.failure == "read_constraint"


# ---- Requirements set before a repair hold for every later reading ---------------------

SPLIT = intent._SPLIT_QUESTION_MESSAGES["en"]
# A finance-only reading of the mixed laptop question (message passing is gone).
LAPTOP_FINANCE_ONLY = {**SAVE_TARGET}
# Mixed but unlabelled: it keeps RM3,000 as the target, then needs the parts repair.
LAPTOP_TARGET_UNLABELLED = {**LAPTOP_TARGET, "public": {"topic": "message passing and laptop savings",
                                                        "subject_domain": "mixed", "stated_amount": "3000"}}


def test_reviewer_repro_amount_repair_that_drops_the_non_finance_part_asks_instead():
    # Reproduced bug: the amount repair answered finance-only and was accepted, so
    # the message-passing part disappeared.
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_FINANCE_ONLY)
    assert result.proposal is None and result.failure_message == SPLIT


def test_amount_repair_then_parts_repair_that_drops_message_passing_asks_instead():
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_TARGET_UNLABELLED, LAPTOP_FINANCE_ONLY)
    assert len(_interpret.inputs) == 3 and result.proposal is None and result.failure_message == SPLIT


def test_reviewer_repro_parts_repair_that_loses_the_repaired_price_asks_instead():
    # Reproduced bug: the amount repair kept RM3,000, the parts repair added the
    # labels but dropped it, and the result was still accepted.
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_TARGET_UNLABELLED, LAPTOP_PRICE_DROPPED)
    assert len(_interpret.inputs) == 3
    assert result.proposal is None and result.failure_message == ASK_RM3000


def test_parts_repair_that_turns_the_target_into_a_filter_asks_instead():
    as_filter = {**LAPTOP_TARGET, "read": {"operation": "search_transactions", "category": {"decision": "none"},
                                           "amount": "3000"},
                 "public": {**LAPTOP_TARGET["public"], "stated_amount": None}}
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_TARGET_UNLABELLED, as_filter)
    assert result.proposal is None and result.failure_message == ASK_RM3000


def test_both_repairs_keeping_every_requirement_are_accepted():
    result = _interpret(LAPTOP_QUESTION, [], LIVE_PRICE_ON_READ, LAPTOP_TARGET_UNLABELLED, LAPTOP_TARGET)
    assert len(_interpret.inputs) == 3 and result.failure is None
    assert result.proposal.public.stated_amount == "3000"
    assert result.public_plan.part_domains == ("non_finance", "finance")


def test_finance_only_question_has_no_parts_requirement():
    # The finance-only laptop question never had a non-finance part to keep.
    result = _interpret(SAVE_QUESTION, [], SAVE_PRICE_ON_READ, SAVE_TARGET)
    assert result.failure is None


# ---- Typed amount meanings on the first reading -----------------------------------------

TARGET_3000 = [{"amount": "3000", "role": "target"}]
SAVE_TARGET_LISTED = {**SAVE_TARGET, "public": {**SAVE_TARGET["public"], "parts": [
                        {"fact": "monthly saving capacity and time to reach the laptop target", "domain": "finance",
                         "answer_kind": "savings_target"}]},
                      "amounts": TARGET_3000}
LAPTOP_TARGET_LISTED = {**LAPTOP_TARGET, "public": {**LAPTOP_TARGET["public"], "parts": [
                          LAPTOP_TARGET["public"]["parts"][0],
                          {**LAPTOP_TARGET["public"]["parts"][1], "answer_kind": "savings_target"}]},
                        "amounts": TARGET_3000}
# Gemini's first reading on 2026-10-25 (mixed run 5): the laptop price as income to split.
LAPTOP_PRICE_AS_INCOME = {**LAPTOP_TARGET, "public": {**LAPTOP_TARGET["public"], "framework": "allocation"},
                          "amounts": TARGET_3000}


def test_reviewer_repro_price_is_never_split_as_income():
    # Correctness bug: framework=allocation would split RM3,000 50/30/20 as if it were income.
    result = _interpret(LAPTOP_QUESTION, [], LAPTOP_PRICE_AS_INCOME, LAPTOP_TARGET_LISTED)
    assert len(_interpret.inputs) == 2 and result.failure is None
    assert result.proposal.public.framework == "none" and result.proposal.public.stated_amount == "3000"


def test_price_as_income_that_cannot_be_repaired_asks_instead():
    result = _interpret(LAPTOP_QUESTION, [], LAPTOP_PRICE_AS_INCOME, LAPTOP_PRICE_AS_INCOME)
    assert result.proposal is None and result.failure_message == ASK_RM3000


SAVE_NO_PUBLIC_LISTED = {**SAVE_PRICE_DROPPED, "amounts": TARGET_3000}  # target listed, no public plan
# A live reading (2026-10-25): RM3,000 listed as the target, stated_amount left empty.
LIVE_TARGET_UNPLACED = {"route": "combined", "relation": "new", "goal": "plan", "response_language": "en",
                        "read": {"operation": "predict_savings", "category": {"decision": "none"}},
                        "public": {"topic": "message passing", "subject_domain": "mixed",
                                   "parts": [{"fact": "explain message passing", "domain": "non_finance"},
                                             {"fact": "how much should I save each month for a laptop",
                                              "domain": "finance", "entities": [], "answer_kind": "savings_target"}]},
                        "amounts": TARGET_3000}


def test_reviewer_live_shape_listed_target_is_placed_from_the_reading_itself():
    result = _interpret(LAPTOP_QUESTION, [], LIVE_TARGET_UNPLACED)
    assert len(_interpret.inputs) == 1 and result.failure is None
    assert result.proposal.public.stated_amount == "3000" and result.proposal.public.framework == "none"
    assert result.public_plan.part_domains == ("non_finance", "finance")


def test_listed_target_on_a_read_that_cannot_filter_moves_to_the_target():
    on_read = {**LIVE_PRICE_ON_READ, "amounts": TARGET_3000}
    result = _interpret(LAPTOP_QUESTION, [], on_read)
    assert len(_interpret.inputs) == 1 and result.failure is None
    assert result.proposal.read.amount is None and result.proposal.public.stated_amount == "3000"


def test_amount_listed_as_a_filter_is_never_moved():
    on_read = {**LIVE_PRICE_ON_READ, "amounts": [{"amount": "3000", "role": "filter"}]}
    result = _interpret(LAPTOP_QUESTION, [], on_read, LAPTOP_TARGET_LISTED)
    assert result.proposal is None and result.failure_message == ASK_RM3000  # meaning changed: ask


def test_listed_budget_is_never_moved():
    budget = {"route": "financial_education", "relation": "new", "goal": "plan",
              "public": {"topic": "budget plan"}, "amounts": [{"amount": "1500", "role": "budget"}]}
    result = _interpret("Create a budget plan for RM1500.", [], budget, TimeoutError())
    assert result.proposal is None and "RM1,500" in result.failure_message


def test_listed_target_without_a_public_plan_is_re_read():
    result = _interpret(SAVE_QUESTION, [], SAVE_NO_PUBLIC_LISTED, SAVE_TARGET_LISTED)
    assert len(_interpret.inputs) == 2 and result.proposal.public.stated_amount == "3000"


def test_re_read_that_still_omits_the_listed_price_asks_instead():
    result = _interpret(SAVE_QUESTION, [], SAVE_NO_PUBLIC_LISTED, SAVE_PRICE_DROPPED)
    assert result.proposal is None and result.failure_message == ASK_RM3000


def test_records_read_with_a_public_plan_is_the_combined_route():
    labelled_personal = {**SAVE_TARGET_LISTED, "route": "personal_finance"}
    result = _interpret(SAVE_QUESTION, [], labelled_personal)
    assert result.failure is None and result.proposal.route == "combined"


def test_misplaced_goal_filter_is_re_read_on_the_primary_provider():
    # Live rejection: "This operation cannot filter a goal" (goal_name='laptop' on predict_savings).
    goal_filter = {**SAVE_TARGET_LISTED, "read": {"operation": "predict_savings", "category": {"decision": "none"},
                                                  "goal_name": "laptop"}}
    prompts, outputs = [], iter([goal_filter, SAVE_TARGET_LISTED])

    def generate(prompt, *, validate, **kwargs):
        prompts.append(prompt)
        return validate(json.dumps(next(outputs)))
    result = intent.interpret_request(SAVE_QUESTION, [], today=date(2026, 10, 24),
                                      budget=llm.CoachRequestBudget.start(), generate=generate)
    assert len(prompts) == 2 and result.failure is None
    head, data = prompts[1].split("\nINPUT DATA:\n", 1)
    assert "This operation cannot filter a goal" in head and "REPAIR" not in data


def test_goal_filter_repair_must_keep_the_listed_target():
    goal_filter = {**SAVE_TARGET_LISTED, "read": {"operation": "predict_savings", "category": {"decision": "none"},
                                                  "goal_name": "laptop"}}
    as_budget = {**SAVE_TARGET_LISTED, "amounts": [{"amount": "3000", "role": "budget"}]}
    result = _interpret(SAVE_QUESTION, [], goal_filter, as_budget)
    assert result.proposal is None and result.failure_message == ASK_RM3000


def test_goal_filter_repair_must_keep_the_non_finance_part():
    goal_filter = {**LAPTOP_TARGET_LISTED, "read": {"operation": "predict_savings", "category": {"decision": "none"},
                                                    "goal_name": "laptop"}}
    result = _interpret(LAPTOP_QUESTION, [], goal_filter, SAVE_TARGET_LISTED)
    assert result.proposal is None and result.failure_message == SPLIT


def test_unrepairable_rule_without_amounts_keeps_the_existing_outcome():
    goal_filter = {**SAVE_TARGET, "public": None, "route": "personal_finance",
                   "read": {"operation": "predict_savings", "category": {"decision": "none"}, "goal_name": "laptop"}}
    result = _interpret(SAVE_QUESTION, [], goal_filter, TimeoutError())
    assert result.failure == "interpretation_unavailable"


def test_budget_to_split_still_uses_the_allocation_framework():
    plan = {"route": "financial_education", "relation": "new", "goal": "plan",
            "public": {"topic": "budget plan", "framework": "allocation", "stated_amount": "1500"},
            "amounts": [{"amount": "1500", "role": "budget"}]}
    result = _interpret("Create a budget plan for RM1500.", [], plan)
    assert len(_interpret.inputs) == 1 and result.proposal.public.framework == "allocation"


def test_a_target_is_never_defaulted_to_allocation():
    target = {"route": "financial_education", "relation": "new", "goal": "plan",
              "public": {"topic": "saving for a laptop", "stated_amount": "3000"}, "amounts": TARGET_3000}
    proposal = intent._normalise_proposal(intent.IntentProposal.model_validate(target))
    assert proposal.public.framework == "none"


def test_amount_with_two_roles_is_rejected():
    two = {**SAVE_TARGET_LISTED, "amounts": [{"amount": "3000", "role": "target"}, {"amount": "3000", "role": "budget"}]}
    with pytest.raises(intent.ProposalRejected):
        intent.check_amounts(intent.IntentProposal.model_validate(two))


def test_context_amount_needs_no_placement():
    mention = {**SAVE_TARGET_LISTED, "amounts": [*TARGET_3000, {"amount": "50", "role": "context"}]}
    intent.check_amounts(intent.IntentProposal.model_validate(mention))


# ---- The target stays in the final answer --------------------------------------------------

def test_answer_keeps_the_target_as_a_target():
    proposal = intent.IntentProposal.model_validate(SAVE_TARGET_LISTED)
    text = service._with_stated_target("For 2026-10, estimated savings: **RM538.33**.", proposal)
    assert text.startswith("Your savings target: **RM3,000**.\n\n")
    assert service._with_stated_target(text, proposal) == text  # never twice


def test_budget_amount_gets_no_target_line():
    budget = intent.IntentProposal.model_validate({
        "route": "financial_education", "relation": "new", "goal": "plan",
        "public": {"topic": "budget plan", "framework": "allocation", "stated_amount": "1500"},
        "amounts": [{"amount": "1500", "role": "budget"}]})
    assert service._with_stated_target("answer", budget) == "answer"


def test_complete_answer_from_the_service_states_the_target(monkeypatch):
    calls = _count_web(monkeypatch)
    text = "Set aside an affordable savings amount after receiving your allowance."
    chunk = RetrievedChunk(1, "Saving basics", "saving.md", None, 0, text, 0.6)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(research_policy, "assess_evidence", lambda *a, **k: EvidenceAssessment(
        "sufficient", supported_sources=(1,), supported_quotes=((1, text),),
        parts=(PartCoverage("p1", "direct", (1,), complete=True),)))
    draft = "**Insight**\nSet aside an affordable amount first [S1]."
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: LLMResult(draft, "gemini"))
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: ResearchDraftCheck(
        True, approved_text=draft, diagnostics={}))
    target = {"route": "financial_education", "relation": "new", "goal": "plan",
              "public": {"topic": "saving for a laptop", "subject_domain": "finance", "stated_amount": "3000"},
              "amounts": TARGET_3000}
    _semantic(monkeypatch, target, "how should I save for a RM3000 laptop")
    message = _send("how should I save for a RM3000 laptop")
    assert message["content"].startswith("Your savings target: **RM3,000**.")
    assert "50/30/20" not in message["content"] and "Set aside" in message["content"]


# Live readings (2026-10-25): message passing as the public topic, the laptop as the records plan.
LIVE_TOPIC_AND_RECORDS = {"route": "combined", "relation": "new", "goal": "plan", "response_language": "en",
                          "read": {"operation": "predict_savings", "category": {"decision": "none"}},
                          "public": {"topic": "message passing", "subject_domain": "non_finance"},
                          "amounts": TARGET_3000}


def test_reviewer_live_shape_target_never_turns_message_passing_into_finance():
    # Leak risk: the stated amount flipped the message-passing topic to finance,
    # which would have sent "message passing" to web search.
    result = _interpret(LAPTOP_QUESTION, [], LIVE_TOPIC_AND_RECORDS)
    assert result.failure is None and result.public_plan.finance_scope == "non_finance"
    assert result.resolved.tool_name == "predict_savings" and result.proposal.public.stated_amount == "3000"
    assert service._non_finance(result.public_plan)  # the service turns web search off for it


def test_target_beside_a_non_finance_topic_without_records_needs_its_parts():
    no_records = {**LIVE_TOPIC_AND_RECORDS, "route": "financial_education", "read": None}
    result = _interpret(LAPTOP_QUESTION, [], no_records, TimeoutError())
    assert result.proposal is None and result.failure_message == SPLIT


# ---- The savings plan for a target comes from verified records ----------------------------

SAVINGS_RESULT = {
    "status": "ok", "month": "2026-10-01", "income": "RM900.00", "projected_month_spending": "RM361.67",
    "projected_remaining": "RM538.33", "projected_saveable": "RM538.33", "recorded_expenses": "RM350.00",
    "days_elapsed": 30, "basis_period": {"start": "2026-09-01", "end": "2026-09-30"},
    "income_basis": "monthly_allowance"}
PLAN_6 = ("To reach your savings target of **RM3,000** with your estimated savings of **RM538.33** a month, "
          "you would need about **6 monthly contributions** (RM3,000 ÷ RM538.33 ≈ 5.57, rounded up). This "
          "assumes you start from zero and your saving capacity stays the same; existing savings and any "
          "deadline are not included.")


def _record(**changes):
    return ({"name": "predict_savings", "result": {**SAVINGS_RESULT, **changes}},)


def test_target_plan_is_calculated_from_the_verified_savings_estimate():
    plan = service._target_plan("3000", _record(), "en")
    facts = service._format_fast_verified_read("predict_savings", SAVINGS_RESULT)
    assert plan == (PLAN_6, facts)
    assert service._target_block("3000", plan, "en") == f"Your savings target: **RM3,000**.\n\n{facts}\n\n{PLAN_6}"


def test_no_surplus_says_the_target_cannot_be_reached_from_current_capacity():
    text, _ = service._target_plan("3000", _record(projected_remaining="-RM40.00", projected_saveable="RM0.00",
                                                   projected_shortfall="RM40.00"), "en")
    assert "no surplus to save this month, so the RM3,000 target cannot be reached" in text


def test_target_is_rounded_up_to_whole_contributions():
    assert "about **6 monthly contributions** (RM3,000 ÷ RM500.00 ≈ 6.00" in service._target_plan(
        "3000", _record(projected_saveable="RM500.00"), "en")[0]
    assert "about **1 monthly contribution** (" in service._target_plan(
        "3000", _record(projected_saveable="RM4,000.00"), "en")[0]


def test_without_a_verified_savings_estimate_there_is_no_plan():
    assert service._target_plan("3000", (), "en") is None
    assert service._target_plan("3000", ({"name": "predict_savings", "result": {"status": "error"}},), "en") is None


def test_answer_without_a_plan_still_states_the_target_and_a_budget_never_does():
    target = intent.IntentProposal.model_validate(SAVE_TARGET_LISTED)
    assert service._with_stated_target("answer", target) == "Your savings target: **RM3,000**.\n\nanswer"
    budget = intent.IntentProposal.model_validate({
        "route": "financial_education", "relation": "new", "goal": "plan",
        "public": {"topic": "budget plan", "framework": "allocation", "stated_amount": "1500"},
        "amounts": [{"amount": "1500", "role": "budget"}]})
    assert service._with_stated_target("answer", budget) == "answer"


# ---- Part IDs: what the calculation answers, and what remains to explain ----------------

def test_calculation_answers_the_single_finance_part_by_its_part_id():
    from app.rag.research_coverage import calculated_part_ids
    assert calculated_part_ids(_plan(LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)) == ("p2",)
    assert calculated_part_ids(_plan(SAVE_TARGET_LISTED, SAVE_QUESTION)) == ("p1",)
    assert calculated_part_ids(_plan(LIVE_TOPIC_AND_RECORDS, LAPTOP_QUESTION)) == ()  # non-finance topic


def test_only_the_bound_finance_part_is_answered():
    from app.rag.research_coverage import calculated_part_ids
    two = {**LIVE_TARGET_UNPLACED, "public": {**LIVE_TARGET_UNPLACED["public"], "parts": [
        *LIVE_TARGET_UNPLACED["public"]["parts"], {"fact": "what is PTPTN", "domain": "finance", "entities": ["PTPTN"]}]}}
    assert calculated_part_ids(_plan(two, LAPTOP_QUESTION)) == ("p2",)


def test_remaining_plan_holds_only_the_unanswered_part():
    from app.rag.research_coverage import plan_without_parts, requested_parts
    plan = _plan(LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    remaining = plan_without_parts(plan, ("p2",))
    assert remaining.required_facts == ("explain message passing",)
    assert remaining.part_domains == ("non_finance",) and remaining.finance_scope == "non_finance"
    assert remaining.needs_personal and "laptop" not in remaining.topic.casefold()
    assert [part.id for part in requested_parts(remaining)] == ["p1"]
    assert service._non_finance(remaining)  # no web search for it
    assert plan_without_parts(plan, ()) is plan
    assert plan_without_parts(_plan(SAVE_TARGET_LISTED, SAVE_QUESTION), ("p1",)) is None


def test_referral_follows_the_final_answer_coverage():
    from app.rag.research_coverage import plan_without_parts
    remaining = plan_without_parts(_plan(LIVE_TARGET_UNPLACED, LAPTOP_QUESTION), ("p2",))
    assert answer.non_finance_part_note(remaining, ()) == answer._NON_FINANCE_PART_MESSAGES["en"]
    assert answer.non_finance_part_note(remaining, ("p1",)) is None
    # A plain non-finance question keeps its existing behaviour (no extra note).
    assert answer.non_finance_part_note(_plan(_public("message passing", subject_domain="non_finance")), ()) is None


# ---- Complete answers through the service ------------------------------------------------

def _fail(*_args, **_kwargs):
    raise RuntimeError("provider unavailable")


def _records_service(monkeypatch, payload, question):
    from test_category_interpretation_contract import StoredClient, stored_rows, USER_ID
    _semantic(monkeypatch, payload, question)
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    return service.CoachingService(repository, StoredClient(stored_rows(["Food", "Transport"])))


def _all_providers_down(monkeypatch):
    web = []
    for name in ("generate_structured_result", "generate_result", "generate_agent_result", "generate_fallback_result"):
        monkeypatch.setattr(service, name, _fail)
    monkeypatch.setattr(llm, "generate_result", _fail)
    monkeypatch.setattr(answer, "_generate_research_correction", _fail)
    monkeypatch.setattr(research_policy, "research_evidence",
                        lambda *a, **k: web.append(a) or ResearchOutcome([], False, "auth_error"))
    monkeypatch.setattr(research_policy, "extract_passages", lambda *a, **k: web.append(a) or {})
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    return web


def test_finance_only_target_is_one_code_written_answer_without_research(monkeypatch):
    web = _all_providers_down(monkeypatch)
    svc = _records_service(monkeypatch, SAVE_TARGET_LISTED, SAVE_QUESTION)
    message = svc.send_message("s", "m", SAVE_QUESTION)["assistant_message"]
    facts = service._format_fast_verified_read("predict_savings", SAVINGS_RESULT)
    assert message["content"] == f"Your savings target: **RM3,000**.\n\n{facts}\n\n{PLAN_6}"
    assert web == []  # the answered part is never researched


@pytest.mark.parametrize("payload", [LIVE_TARGET_UNPLACED, LIVE_TOPIC_AND_RECORDS])
def test_outage_keeps_the_calculation_and_refers_only_the_unanswered_non_finance_part(monkeypatch, payload):
    web = _all_providers_down(monkeypatch)
    svc = _records_service(monkeypatch, payload, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert content.startswith("Your savings target: **RM3,000**.") and PLAN_6 in content
    assert content.rstrip().endswith("Please refer to learning resources on the subject.")
    assert "Please try again" not in content and "confirmed" not in content
    assert web == []  # only the non-finance part remained: knowledge base only


def _document_supported(monkeypatch, answered_ids, shown=None, addressed_ids=()):
    """Message passing found in a published document; the checker reports which
    parts the explanation shown to the user actually answers."""
    prompts = []
    text = "The assignment brief requires message passing with no shared mutable state."
    chunk = RetrievedChunk(1, "a1 group", "up_a1.md", None, 0, text, 0.6)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(research_policy, "research_evidence", lambda *a, **k: pytest.fail("no web search"))
    monkeypatch.setattr(research_policy, "assess_evidence", lambda *a, **k: EvidenceAssessment(
        "sufficient", supported_sources=(1,), supported_quotes=((1, text),),
        parts=(PartCoverage("p1", "direct", (1,), complete=True),)))
    draft = "**Insight**\nThe brief requires message passing with no shared mutable state [S1]."

    def writer(prompt, *a, **k):
        prompts.append(prompt)
        return LLMResult(draft, "gemini")
    monkeypatch.setattr(service, "generate_result", writer)
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: ResearchDraftCheck(
        True, approved_text=shown or draft, diagnostics={"answered_part_ids": list(answered_ids),
                                                       "addressed_part_ids": list(addressed_ids)}))
    return prompts


def test_document_supported_part_is_explained_with_the_calculation_and_no_referral(monkeypatch):
    prompts = _document_supported(monkeypatch, ["p1"])
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert content.startswith("Your savings target: **RM3,000**.") and PLAN_6 in content
    assert "requires message passing" in content
    assert "learning resources" not in content
    # The writer was asked about the remaining part only, never the laptop.
    assert prompts and all("laptop" not in prompt.casefold() for prompt in prompts)


def test_found_document_that_the_shown_answer_does_not_use_is_referred(monkeypatch):
    # The document was found and assessed, but the checked text shown to the
    # user does not use it: finding a document alone never covers the part.
    _document_supported(monkeypatch, [], shown="**Insight**\nI haven't established the requested details yet.")
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert PLAN_6 in content
    assert content.rstrip().endswith(answer._NON_FINANCE_PART_MESSAGES["en"])


def test_partly_explained_part_gets_no_referral(monkeypatch):
    # The checker did not judge the part complete, but the shown text explains
    # it from its own cited document: the partial notice covers the gap.
    _document_supported(monkeypatch, [], addressed_ids=["p1"])
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert "requires message passing" in content and "learning resources" not in content


def test_unsupported_remaining_part_gets_one_referral(monkeypatch):
    _all_providers_down(monkeypatch)
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert content.count("learning resources") == 1
    assert content.endswith(answer._NON_FINANCE_PART_MESSAGES["en"])


# ---- Calculate, then search for the unanswered parts, then assemble ------------------------

A1_TEXT = "Functional programming concepts include message passing with no shared mutable state."
A1_CHUNK = RetrievedChunk(7, "a1 group", "up_a1.md", None, 0, A1_TEXT, 0.48)
PTPTN_TEXT = "PTPTN manages higher education loans and collects loan repayments."
PTPTN_CHUNK = RetrievedChunk(8, "PTPTN guidance", "official_ptptn_loan_guidance.md", None, 0, PTPTN_TEXT, 0.6)
LAPTOP_AND_PTPTN = {**SAVE_TARGET_LISTED, "public": {
    "topic": "laptop savings and PTPTN", "subject_domain": "finance", "stated_amount": "3000", "parts": [
        {"fact": "monthly saving capacity and time to reach the laptop target", "domain": "finance",
         "answer_kind": "savings_target"},
        {"fact": "what is PTPTN", "domain": "finance", "entities": ["PTPTN"], "answer_kind": "research"}]}}
PTPTN_QUESTION = "How much can I save toward a RM3000 laptop, and what is PTPTN?"


def _recording_retrieve(monkeypatch, results):
    """retrieve() stand-in: records the topic and rebuilt subqueries of each call
    and answers from ``results`` by call number (the whole question first)."""
    calls = []

    def fake(topic, *, analysis=None, title_sources=()):
        calls.append({"topic": topic, "subqueries": [s.text for s in analysis.subqueries],
                      "topic_ids": [s.topic_id for s in analysis.subqueries], "titles": title_sources})
        found = results[len(calls) - 1] if len(calls) <= len(results) else []
        if isinstance(found, Exception):
            raise found
        return list(found)
    monkeypatch.setattr(service, "retrieve", fake)
    return calls


def _assess_from(monkeypatch, quote_chunk):
    """The evidence check sees what retrieval supplied; it supports the remaining
    part only when that part's own source is among the chunks it receives."""
    seen = []

    def assess(plan, chunks, *a, **k):
        seen.append([chunk.title for chunk in chunks])
        if any(chunk.id == quote_chunk.id for chunk in chunks):
            return EvidenceAssessment("sufficient", supported_sources=(1,), supported_quotes=((1, quote_chunk.content),),
                                      parts=(PartCoverage(requested_parts_of(plan)[0], "confirmed", (1,), complete=True),))
        return EvidenceAssessment("insufficient", (requested_parts_of(plan)[0],))
    monkeypatch.setattr(research_policy, "assess_evidence", assess)
    return seen


def requested_parts_of(plan):
    from app.rag.research_coverage import requested_parts
    return [part.id for part in requested_parts(plan)]


def _writer_and_checker(monkeypatch, text, part_id):
    draft = f"**Insight**\n{text} [S1]."
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: LLMResult(draft, "gemini"))
    monkeypatch.setattr(answer, "check_research_draft", lambda *a, **k: ResearchDraftCheck(
        True, approved_text=draft, diagnostics={"answered_part_ids": [part_id], "addressed_part_ids": [part_id]}))


def test_laptop_only_is_calculated_with_no_second_search_and_no_research(monkeypatch):
    web = _all_providers_down(monkeypatch)
    calls = _recording_retrieve(monkeypatch, [[]])
    monkeypatch.setattr(service, "run_research_policy", lambda *a, **k: pytest.fail("no research for an answered part"))
    svc = _records_service(monkeypatch, SAVE_TARGET_LISTED, SAVE_QUESTION)
    content = svc.send_message("s", "m", SAVE_QUESTION)["assistant_message"]["content"]
    assert PLAN_6 in content and len(calls) <= 1 and web == []


def test_remaining_message_passing_part_is_searched_with_rebuilt_instructions(monkeypatch):
    # Reproduced gap: the whole-question topic ("message passing and laptop
    # savings") found nothing, and the remaining part was never searched itself.
    calls = _recording_retrieve(monkeypatch, [[], [A1_CHUNK]])
    seen = _assess_from(monkeypatch, A1_CHUNK)
    monkeypatch.setattr(research_policy, "research_evidence", lambda *a, **k: pytest.fail("no web search"))
    _writer_and_checker(monkeypatch, "The brief lists message passing with no shared mutable state", "p1")
    question = LAPTOP_QUESTION
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, question)
    content = svc.send_message("s", "m", question)["assistant_message"]["content"]
    assert len(calls) == 2
    assert calls[1]["subqueries"] == ["explain message passing"]  # rebuilt, not the old topic
    assert "laptop" not in calls[1]["topic"].casefold()
    assert seen and "a1 group" in seen[-1]
    assert PLAN_6 in content and "message passing with no shared mutable state" in content
    assert "learning resources" not in content


def test_remaining_ptptn_part_is_searched_and_researched_without_the_laptop(monkeypatch):
    calls = _recording_retrieve(monkeypatch, [[], [PTPTN_CHUNK]])
    searched = []
    monkeypatch.setattr(research_policy, "research_evidence",
                        lambda query, **k: searched.append(query) or ResearchOutcome([], True, "ok"))
    monkeypatch.setattr(research_policy, "extract_passages", lambda *a, **k: {})
    _assess_from(monkeypatch, PTPTN_CHUNK)
    _writer_and_checker(monkeypatch, "PTPTN manages higher education loans", "p2")
    svc = _records_service(monkeypatch, LAPTOP_AND_PTPTN, PTPTN_QUESTION)
    content = svc.send_message("s", "m", PTPTN_QUESTION)["assistant_message"]["content"]
    assert len(calls) == 2 and calls[1]["topic_ids"][0] == "ptptn"  # the known PTPTN topic first
    assert all("laptop" not in text.casefold() for text in calls[1]["subqueries"])
    assert all("laptop" not in query.casefold() for query in searched)
    assert PLAN_6 in content and "PTPTN manages higher education loans" in content


def test_missing_evidence_for_the_remaining_part_gives_one_honest_referral(monkeypatch):
    _all_providers_down(monkeypatch)
    calls = _recording_retrieve(monkeypatch, [[], []])
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert len(calls) == 2 and PLAN_6 in content
    assert content.count("learning resources") == 1


def test_failed_second_search_keeps_the_evidence_already_found(monkeypatch):
    calls = _recording_retrieve(monkeypatch, [[A1_CHUNK], RuntimeError("database unavailable")])
    seen = _assess_from(monkeypatch, A1_CHUNK)
    monkeypatch.setattr(research_policy, "research_evidence", lambda *a, **k: pytest.fail("no web search"))
    _writer_and_checker(monkeypatch, "The brief lists message passing with no shared mutable state", "p1")
    svc = _records_service(monkeypatch, LIVE_TARGET_UNPLACED, LAPTOP_QUESTION)
    content = svc.send_message("s", "m", LAPTOP_QUESTION)["assistant_message"]["content"]
    assert len(calls) == 2 and "a1 group" in seen[-1]
    assert PLAN_6 in content and "learning resources" not in content


def test_named_document_context_is_kept_for_the_second_search(monkeypatch):
    from app.rag.research_coverage import plan_without_parts
    plan = plan_without_parts(_plan(LIVE_TARGET_UNPLACED, LAPTOP_QUESTION), ("p2",))
    calls = _recording_retrieve(monkeypatch, [[A1_CHUNK]])
    service._retrieve_remaining_parts(plan, [], ("up_a1.md",))
    assert calls[0]["titles"] == ("up_a1.md",)
