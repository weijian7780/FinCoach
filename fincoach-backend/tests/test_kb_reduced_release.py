"""Reduced release: document titles and follow-ups, safe retry, failure wording,
concept/institution assessment. No non-finance scope layer."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import llm
from app.rag import document_titles as titles
from app.rag import request_interpretation as intent
from app.rag import research_answer as answer
from app.rag import retrieval
from app.rag import service
from app.rag.research_policy import EvidenceAssessment, QuestionPlan, ResearchDecision, assess_evidence
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import _safe_error


def _public(topic, **public):
    return {"route": "financial_education", "public": {"topic": topic, **public}}


# ---- Document titles ---------------------------------------------------------

@pytest.mark.parametrize("stored,cleaned", [
    ("a1 group (1) (1)", "a1 group"), ("a1 group (1) (1).md", "a1 group"),
    ("Budget 2026.pdf", "budget 2026"), ("Savings_Guide - Copy (2)", "savings guide"),
])
def test_only_file_name_leftovers_are_removed(stored, cleaned):
    assert titles.clean_document_title(stored) == cleaned


DOCS = (("up_a1.md", "a1 group (1) (1)"), ("official_epf.md", "EPF basics"),
        ("up_budget.md", "Budget"), ("up_budget26.md", "Budget 2026"))


@pytest.mark.parametrize("text,expected", [
    ("what is a1 group", ["up_a1.md"]), ("summarise the a1 group assignment", ["up_a1.md"]),
    ("what is a group", []), ("what is a1", []), ("explain budget 2026", ["up_budget26.md"]),
])
def test_whole_cleaned_title_with_word_boundaries(text, expected):
    assert [m.source for m in titles.resolve_document_titles(text, DOCS)] == expected


def test_catalogue_sources_are_excluded_and_shared_titles_are_both_returned():
    assert titles.resolve_document_titles("epf basics", DOCS, excluded_sources=frozenset({"official_epf.md"})) == ()
    docs = (("a.md", "a1 group"), ("b.md", "a1 group (1)"))
    assert {m.source for m in titles.resolve_document_titles("what is a1 group", docs)} == {"a.md", "b.md"}


@pytest.mark.parametrize("topic,expected", [
    ("a1 group", True), ("the a1 group document", True), ("amortisation in a1 group", False),
    ("a1 group deliverables", False),
])
def test_topic_is_the_document_only_when_nothing_else_is_asked(topic, expected):
    match = titles.resolve_document_titles("a1 group", (("up_a1.md", "a1 group (1) (1)"),))[0]
    assert titles.topic_is_document(topic, match) is expected


# ---- Retrieval of a named document ---------------------------------------------

class _Query:
    def __init__(self, rows):
        self.rows, self.filters = rows, {}

    def select(self, *a):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, n):
        return self

    def execute(self):
        return SimpleNamespace(data=[r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())])


class _Client:
    def __init__(self, rows, fail=False):
        self.rows, self.fail = rows, fail

    def table(self, name):
        if self.fail:
            raise ConnectionError("down")
        return _Query(self.rows)

    def rpc(self, name, params):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[]))


def _row(chunk_id, source, vector, index=0):
    return {"id": chunk_id, "title": "a1 group (1) (1)", "content": f"section {index}", "source": source,
            "page_number": None, "chunk_index": index, "embedding": json.dumps(vector)}


def test_named_document_bypasses_the_general_cutoff(monkeypatch):
    rows = [_row(1, "up_a1.md", [0.2, 0.98, 0]), _row(2, "up_a1.md", [0.3, 0.95, 0], 1), _row(3, "x.md", [0.9, 0.1, 0])]
    monkeypatch.setattr(retrieval, "get_supabase", lambda: _Client(rows))
    monkeypatch.setattr(retrieval, "embed_texts", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    chunks = retrieval.retrieve("a1 group", title_sources=("up_a1.md",))
    assert [c.id for c in chunks] == [2, 1] and all(c.match_reason == "title" for c in chunks)


def test_general_search_keeps_its_threshold(monkeypatch):
    monkeypatch.setattr(retrieval, "get_supabase", lambda: _Client([]))
    monkeypatch.setattr(retrieval, "embed_texts", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    monkeypatch.setattr(retrieval, "_hybrid_candidates", lambda *a: [RetrievedChunk(9, "t", "s", None, 0, "c", 0.30)])
    assert retrieval.retrieve("message passing") == []


def test_published_titles_are_deduplicated_and_failures_degrade(monkeypatch):
    monkeypatch.setattr(retrieval, "_title_cache", None)
    rows = [{"source": "up_a1.md", "title": "a1 group"}] * 2
    monkeypatch.setattr(retrieval, "get_supabase", lambda: _Client(rows))
    assert retrieval.published_document_titles() == (("up_a1.md", "a1 group"),)
    monkeypatch.setattr(retrieval, "_title_cache", None)
    monkeypatch.setattr(retrieval, "get_supabase", lambda: _Client([], fail=True))
    assert retrieval.published_document_titles() == ()


# ---- Evidence assessment wording ---------------------------------------------

def _assessor_prompt(plan, chunks):
    prompts = []
    assess_evidence(plan, chunks, generate=lambda p, **k: prompts.append(p) or SimpleNamespace(content="x"))
    return prompts[0]


def _corpus(match_reason=None):
    return [RetrievedChunk(1, "a1 group", "up_a1.md", None, 0, "Assignment text " * 5, 0.3, match_reason=match_reason)]


def test_concept_definition_does_not_demand_an_institution():
    prompt = _assessor_prompt(QuestionPlan("compound interest", False, True, "stable", definitional=True,
                                           subject_kind="other"), _corpus())
    assert "Do not require an institution's identity" in prompt
    assert "require the institution's identity/full" not in prompt


def test_agency_definition_keeps_the_institution_wording():
    prompt = _assessor_prompt(QuestionPlan("AKPK", False, True, "stable", definitional=True,
                                           subject_kind="agency"), _corpus())
    assert "require the institution's identity/full" in prompt


def test_named_document_subject_versus_named_source():
    about = _assessor_prompt(QuestionPlan("a1 group", False, True, "stable", definitional=True,
                                          document_subject=True), _corpus("title"))
    assert "asking what it is asks what this document is about" in about and "This is a bare definition" not in about
    inside = _assessor_prompt(QuestionPlan("amortisation", False, True, "stable", definitional=True,
                                           subject_kind="other"), _corpus("title"))
    assert "as the place to look" in inside and "This is a bare definition of a concept" in inside


# ---- Failure wording ---------------------------------------------------------

@pytest.mark.parametrize("language", ("en", "ms", "zh", "ta"))
@pytest.mark.parametrize("failure,table", [
    ("auth_error", answer._TEMPORARY_FAILURE_MESSAGES), ("search_failed", answer._TEMPORARY_FAILURE_MESSAGES),
    ("research_round_limit", answer._INSUFFICIENT_EVIDENCE_MESSAGES),
    ("extraction_failed", answer._INSUFFICIENT_EVIDENCE_MESSAGES), (None, answer._INSUFFICIENT_EVIDENCE_MESSAGES),
])
def test_failure_wording_by_cause(language, failure, table):
    message = answer.no_evidence_message(QuestionPlan("x", False, True, "stable", response_language=language), failure)
    assert message == table[language] and "key" not in message.lower()


@pytest.mark.parametrize("name,code", [
    ("ForbiddenError", "auth_error"), ("InvalidAPIKeyError", "auth_error"), ("UsageLimitExceededError", "quota"),
    ("BadRequestError", "search_failed"),
])
def test_tavily_error_classes(name, code):
    assert _safe_error(type(name, (Exception,), {})()) == code


# ---- Retry -------------------------------------------------------------------

def _assistant(proposal, *, status=None, anchor="2026-10-20", message_id="a", retry_of=None, document=None):
    context = {"version": 1, "anchor_date": anchor, "proposal": proposal}
    if retry_of:
        context["retry_of"] = retry_of
    if document:
        context["document_title"] = document
    payload = {"intent_context": context}
    if status:
        payload["research_outcome"] = {"status": status}
    return {"id": message_id, "role": "assistant", "content": "reply", "status": "completed", "ui_payload": payload}


def _interpret(question, history, *outputs, documents=()):
    prompts, queue = [], iter(outputs)

    def generate(prompt, *, validate, **kwargs):
        prompts.append(prompt)
        output = next(queue)
        if isinstance(output, Exception):
            raise output
        return validate(json.dumps(output))
    result = intent.interpret_request(question, history, today=date(2026, 10, 24),
                                      budget=llm.CoachRequestBudget.start(), generate=generate,
                                      published_documents=documents)
    _interpret.inputs = [json.loads(p.split("INPUT DATA:\n", 1)[1]) for p in prompts]
    return result


RETRY = {"route": "casual", "relation": "retry"}
MESSAGE_PASSING = _public("message passing")


def test_try_again_replays_the_previous_question_with_its_outcome():
    history = [{"id": "u1", "role": "user", "content": "what is message passing"},
               _assistant(MESSAGE_PASSING, status="insufficient")]
    result = _interpret("try again", history, RETRY)
    assert result.proposal.public.topic == "message passing" and result.public_plan.definitional
    assert result.context["anchor_date"] == "2026-10-20" and result.context["retry_of"] == "what is message passing"
    assert _interpret.inputs[0]["context"][-1]["outcome"] == "unresolved"


def test_retry_never_replays_an_app_action():
    previous = {"route": "personal_finance", "read": {"operation": "get_upcoming_reminders",
                "category": {"decision": "none"}, "period": {"kind": "default"}},
                "actions": [{"kind": "create_reminder", "title": "Pay rent"}]}
    result = _interpret("try again", [{"id": "u1", "role": "user", "content": "remind me"}, _assistant(previous)], RETRY)
    assert result.proposal.actions == [] and result.resolved.tool_name == "get_upcoming_reminders"


def test_retry_with_no_earlier_question_says_so():
    result = _interpret("try again", [], RETRY)
    assert result.proposal is None
    assert result.failure_message == intent._RETRY_NO_REQUEST_MESSAGES["en"]


def test_retry_of_an_action_only_request_is_explained_and_not_executed(monkeypatch):
    monkeypatch.setattr(intent, "COACH_WRITE_ACTIONS_ENABLED", False)
    history = [{"id": "u1", "role": "user", "content": "remind me to pay rent"},
               _assistant({"route": "personal_finance", "actions": [{"kind": "create_reminder", "title": "Pay rent"}]})]
    result = _interpret("try again", history, RETRY)
    assert result.proposal is None
    assert result.failure_message == "Creating reminders through the coach is currently unavailable."


def test_chained_retry_keeps_the_original_wording():
    history = [{"id": "u1", "role": "user", "content": "what is message passing"}, _assistant(MESSAGE_PASSING, message_id="a1"),
               {"id": "u2", "role": "user", "content": "try again"},
               _assistant(MESSAGE_PASSING, message_id="a2", retry_of="what is message passing")]
    assert _interpret("try again", history, RETRY).public_plan.original_question == "what is message passing"


def test_retry_targets_a_failed_latest_request():
    history = [{"id": "u1", "role": "user", "content": "what is ptptn"}, _assistant(_public("ptptn"), message_id="a1"),
               {"id": "u2", "role": "user", "content": "what is epf", "status": "failed"}]
    result = _interpret("try again", history, RETRY, _public("epf"))
    assert result.proposal.public.topic == "epf" and _interpret.inputs[1]["current_message"] == "what is epf"


def test_retry_after_an_outage_reply_reinterprets_that_question():
    history = [{"id": "u1", "role": "user", "content": "what is ptptn"}, _assistant(_public("ptptn"), message_id="a1"),
               {"id": "u2", "role": "user", "content": "what is epf"},
               {"id": "a2", "role": "assistant", "status": "completed", "content": "...", "ui_payload": {}}]
    assert _interpret("try again", history, RETRY, _public("epf")).proposal.public.topic == "epf"


def test_retry_reinterpretation_outage_stays_an_outage():
    result = _interpret("try again", [{"id": "u1", "role": "user", "content": "what is epf", "status": "failed"}],
                        RETRY, TimeoutError())
    assert result.proposal is None and result.failure == "interpretation_unavailable"


# ---- Interpreter context: documents ------------------------------------------

def test_published_titles_and_previous_document_reach_the_interpreter():
    history = [{"id": "u1", "role": "user", "content": "what is a1 group"},
               _assistant(_public("a1 group"), document="a1 group")]
    _interpret("what is assigment overview", history, _public("a1 group assignment overview"), documents=("a1 group",))
    data = _interpret.inputs[0]
    assert data["published_documents"] == ["a1 group"]
    assert [c for c in data["context"] if c["role"] == "accepted_context"][-1]["document"] == "a1 group"


def test_previous_document_is_a_named_input_and_a_continuation_is_carried():
    history = [{"id": "u1", "role": "user", "content": "what is a1 group"},
               _assistant(_public("a1 group"), document="a1 group")]
    result = _interpret("what is assigment overview", history,
                        {**_public("assignment overview", continues_document=True), "relation": "follow_up"})
    assert _interpret.inputs[0]["previous_document"] == "a1 group"
    assert result.context["continued_document"] == "a1 group"


def test_follow_up_relation_after_a_document_answer_continues_it():
    # Live output: relation=follow_up but continues_document left false.
    history = [{"id": "u1", "role": "user", "content": "what is a1 group"},
               _assistant(_public("a1 group"), document="a1 group")]
    result = _interpret("what is assigment overview", history,
                        {**_public("assigment overview"), "relation": "follow_up"})
    assert result.context["continued_document"] == "a1 group"


def test_new_subject_after_a_document_carries_nothing():
    history = [{"id": "u1", "role": "user", "content": "what is a1 group"},
               _assistant(_public("a1 group"), document="a1 group")]
    result = _interpret("what is BNPL", history, _public("bnpl"))
    assert "continued_document" not in result.context


def test_no_previous_document_means_no_continuation_even_if_flagged():
    result = _interpret("what is the overview", [], _public("overview", continues_document=True))
    assert _interpret.inputs[0]["previous_document"] is None and "continued_document" not in result.context


def test_older_stored_proposal_still_loads():
    assert intent.load_proposal(_public("ptptn")).public.verify_current is False


# ---- Service -------------------------------------------------------------------

def _semantic(monkeypatch, payload, question):
    p = intent._normalise_proposal(intent.IntentProposal.model_validate(payload))
    semantic = intent.InterpretedRequest(p, intent.compile_read(p, date(2026, 10, 24)), intent._public_plan(p, question),
                                         context={"version": 1, "anchor_date": "2026-10-24", "proposal": p.model_dump()})
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", lambda *a, **k: semantic)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: pytest.fail("no answer model expected"))


def _send(text):
    repository = MagicMock(user_id="u")
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    return service.CoachingService(repository, MagicMock()).send_message("s", "m", text)["assistant_message"]


def _policy(monkeypatch, seen, failure="research_round_limit"):
    def policy(plan, chunks, **kwargs):
        seen.update(plan=plan, web=kwargs["web_enabled"])
        return ResearchDecision([], EvidenceAssessment("insufficient"), failure=failure)
    monkeypatch.setattr(service, "run_research_policy", policy)


A1 = (("up_a1.md", "a1 group (1) (1)"),)
GUIDE = (("up_smg.md", "Student Money Guide"),)


def test_ambiguous_titles_ask_in_plain_text(monkeypatch):
    _semantic(monkeypatch, _public("a1 group"), "what is a1 group")
    monkeypatch.setattr(service, "published_document_titles", lambda: (("a.md", "a1 group"), ("b.md", "a1 group (1)")))
    monkeypatch.setattr(service, "run_research_policy", lambda *a, **k: pytest.fail("must ask first"))
    message = _send("what is a1 group")
    assert "Which one do you mean?" in message["content"] and (message.get("ui_payload") or {}).get("type") is None


def test_what_is_a_named_document_asks_what_it_covers_and_saves_its_identity(monkeypatch):
    seen, sources = {}, []
    monkeypatch.setattr(service, "published_document_titles", lambda: A1)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: sources.append(k.get("title_sources")) or [])
    _policy(monkeypatch, seen, failure="search_disabled")
    _semantic(monkeypatch, _public("a1 group"), "what is a1 group")
    message = _send("what is a1 group")
    assert sources == [("up_a1.md",)] and seen["web"] is False and seen["plan"].document_subject
    assert seen["plan"].required_facts == ("what this document is about and what it covers",)
    assert message["content"] == answer._INSUFFICIENT_EVIDENCE_MESSAGES["en"]
    assert message["ui_payload"]["intent_context"]["document_title"] == "a1 group"


def test_catalogue_topics_win_over_titles(monkeypatch):
    sources = []
    monkeypatch.setattr(service, "published_document_titles", lambda: (("up_ptptn.md", "ptptn"),))
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: sources.append(k.get("title_sources")) or [])
    _policy(monkeypatch, {})
    _semantic(monkeypatch, _public("ptptn"), "what is ptptn")
    _send("what is ptptn")
    assert sources == [()]


def test_term_inside_a_named_document_keeps_its_question_and_web(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "published_document_titles", lambda: GUIDE)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    _policy(monkeypatch, seen)
    _semantic(monkeypatch, _public("amortisation in student money guide"), "What is amortisation in Student Money Guide?")
    _send("What is amortisation in Student Money Guide?")
    assert seen["web"] is True and not seen["plan"].document_subject and seen["plan"].definitional


def test_follow_up_naming_the_document_pins_it(monkeypatch):
    seen, sources = {}, []
    monkeypatch.setattr(service, "published_document_titles", lambda: A1)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: sources.append(k.get("title_sources")) or [])
    _policy(monkeypatch, seen)
    _semantic(monkeypatch, {**_public("a1 group assignment overview"), "relation": "follow_up"},
              "what is assigment overview")
    _send("what is assigment overview")
    assert sources == [("up_a1.md",)] and not seen["plan"].document_subject


def _semantic_with_context(monkeypatch, payload, question, context_extra):
    p = intent._normalise_proposal(intent.IntentProposal.model_validate(payload))
    semantic = intent.InterpretedRequest(p, intent.compile_read(p, date(2026, 10, 24)), intent._public_plan(p, question),
                                         context={"version": 1, "anchor_date": "2026-10-24", "proposal": p.model_dump(),
                                                  **context_extra})
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", lambda *a, **k: semantic)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: pytest.fail("no answer model expected"))


def test_continued_document_is_pinned_and_answered_from_it(monkeypatch):
    seen, sources = {}, []
    monkeypatch.setattr(service, "published_document_titles", lambda: A1)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: sources.append(k.get("title_sources")) or [])
    _policy(monkeypatch, seen, failure="search_disabled")
    _semantic_with_context(monkeypatch, {**_public("assigment overview", continues_document=True),
                                         "relation": "follow_up"},
                           "what is assigment overview", {"continued_document": "a1 group"})
    message = _send("what is assigment overview")
    assert sources == [("up_a1.md",)] and seen["web"] is False and seen["plan"].document_subject
    assert seen["plan"].required_facts == ("what the document says about assigment overview",)
    assert message["ui_payload"]["intent_context"]["document_title"] == "a1 group"
    assert message["content"] == answer._INSUFFICIENT_EVIDENCE_MESSAGES["en"]


def test_document_summary_without_requested_facts_asks_what_it_covers(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "published_document_titles", lambda: A1)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    _policy(monkeypatch, seen, failure="search_disabled")
    _semantic(monkeypatch, _public("a1 group"), "summarise the a1 group document")
    _send("summarise the a1 group document")
    assert seen["plan"].required_facts == ("what this document is about and what it covers",)


def test_checker_exempts_the_fixed_english_disclaimer_from_language_checks():
    from app.rag import verifier
    import inspect
    assert "never a mismatch" in inspect.getsource(verifier)


def test_research_prompt_forbids_assuming_the_user_is_the_documents_audience():
    from app.rag.prompts import RESEARCH_EXPLANATION_SYSTEM_PROMPT as prompt
    assert "Never assume the user is its audience" in prompt and "'your group'" in prompt


def test_summary_uses_the_document_but_current_checks_keep_research(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "published_document_titles", lambda: GUIDE)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    _policy(monkeypatch, seen)
    _semantic(monkeypatch, _public("student money guide"), "Summarise Student Money Guide.")
    _send("Summarise Student Money Guide.")
    assert seen["web"] is False
    for extra, question in ((dict(verify_current=True), "Is Student Money Guide still accurate under current rules?"),
                            (dict(explicit_search=True), "Check Student Money Guide; search official sources.")):
        _semantic(monkeypatch, _public("student money guide", time_scope="current", **extra), question)
        _send(question)
        assert seen["web"] is True and seen["plan"].time_scope == "current"


# ---- Retry keeps the resolved document context --------------------------------

def _doc_turns():
    """Document question, then an unnamed follow-up resolved against it."""
    return [{"id": "u1", "role": "user", "content": "what is a1 group"},
            _assistant(_public("a1 group"), message_id="a1", document="a1 group"),
            {"id": "u2", "role": "user", "content": "what is assigment overview"},
            _assistant({**_public("assignment overview"), "relation": "follow_up"}, message_id="a2",
                       document="a1 group")]


def test_retry_of_a_document_follow_up_keeps_its_document():
    result = _interpret("try again", _doc_turns(), RETRY)
    assert result.proposal.public.topic == "assignment overview"
    assert result.context["continued_document"] == "a1 group"
    assert result.context["retry_of"] == "what is assigment overview"


def test_second_retry_still_keeps_the_document_and_original_wording():
    history = _doc_turns() + [
        {"id": "u3", "role": "user", "content": "try again"},
        _assistant({**_public("assignment overview"), "relation": "follow_up"}, message_id="a3",
                   document="a1 group", retry_of="what is assigment overview")]
    result = _interpret("try again", history, RETRY)
    assert result.context["continued_document"] == "a1 group"
    assert result.context["retry_of"] == "what is assigment overview"


def test_retry_of_a_failed_follow_up_reinterprets_it_with_the_document():
    history = _doc_turns()[:2] + [{"id": "u2", "role": "user", "content": "what is assigment overview",
                                   "status": "failed"}]
    result = _interpret("try again", history, RETRY,
                        {**_public("assignment overview", continues_document=True), "relation": "follow_up"})
    assert _interpret.inputs[1]["previous_document"] == "a1 group"
    assert result.context["continued_document"] == "a1 group"


def test_retry_after_an_explicit_topic_change_has_no_document():
    history = _doc_turns()[:2] + [{"id": "u2", "role": "user", "content": "what is BNPL"},
                                  _assistant(_public("bnpl"), message_id="a2")]
    result = _interpret("try again", history, RETRY)
    assert result.proposal.public.topic == "bnpl" and "continued_document" not in result.context


def test_retry_of_an_action_turn_after_a_document_never_repeats_the_action():
    action = {"route": "personal_finance", "actions": [{"kind": "create_reminder", "title": "Submit report"}]}
    history = _doc_turns()[:2] + [{"id": "u2", "role": "user", "content": "remind me to submit the report"},
                                  _assistant(action, message_id="a2")]
    result = _interpret("try again", history, RETRY)
    assert result.proposal is None
    assert result.failure_message == intent._RETRY_ACTION_UNAVAILABLE_MESSAGES["create_reminder"]["en"]


def test_retried_document_is_pinned_only_while_still_published(monkeypatch):
    for published, expected in ((A1, [("up_a1.md",)]), ((), [()])):
        sources = []
        monkeypatch.setattr(service, "published_document_titles", lambda published=published: published)
        monkeypatch.setattr(service, "retrieve", lambda *a, **k: sources.append(k.get("title_sources")) or [])
        _policy(monkeypatch, {}, failure="search_disabled")
        _semantic_with_context(monkeypatch, {**_public("assignment overview"), "relation": "follow_up"},
                               "what is assigment overview", {"continued_document": "a1 group",
                                                              "retry_of": "what is assigment overview"})
        _send("try again")
        assert sources == expected


# ---- Unrequested gap notes are not missing information ------------------------

def _covered_decision():
    from app.rag.research_coverage import PartCoverage
    text = "The guide explains how to budget for tuition fees each semester."
    chunk = RetrievedChunk(1, "Student Money Guide", "up_smg.md", None, 0, text, 0.8)
    return ResearchDecision([chunk], EvidenceAssessment(
        "sufficient", supported_sources=(1,), supported_quotes=((1, text),),
        parts=(PartCoverage("p1", "direct", (1,), complete=True),)), source_quotes=(text,))


def _draft(*insight):
    from app.rag.grounding import DISCLAIMER
    return "**Insight**\n" + "\n".join(insight) + f"\n\n**Educational guidance**\n{DISCLAIMER}"


def _check(text, verdict):
    from unittest.mock import patch
    from app.rag.verifier import GroundingVerification

    def verifier(claims, *a, **k):
        return GroundingVerification({c.id: verdict(c.text) for c in claims},
                                     {c.id: c.cited_indices[0] for c in claims if c.cited_indices})
    with patch.object(answer, "verify_grounding_claims", side_effect=verifier):
        return answer.check_research_draft(text, public_question="summarise Student Money Guide",
                                           decision=_covered_decision(), budget=llm.CoachRequestBudget.start())


def test_unrequested_naming_gap_is_dropped_without_a_partial_caveat():
    result = _check(_draft("The guide explains how to budget for tuition fees each semester [S1].",
                           "I haven't confirmed why the guide has this title."), lambda text: "supported")
    assert result.diagnostics["unrelated_notice_count"] == 1  # the note path was exercised
    assert result.is_valid
    assert "tuition fees" in result.approved_text
    assert "why the guide has this title" not in result.approved_text
    assert "could not explain" not in result.approved_text
    assert "requested details removed during verification" not in (
        result.diagnostics.get("unanswered_requested_parts") or [])


def test_a_genuinely_unsupported_claim_still_keeps_the_caveat():
    result = _check(_draft("The guide explains how to budget for tuition fees each semester [S1].",
                           "The guide guarantees a RM500 bursary to every reader [S1]."),
                    lambda text: "unsupported" if "bursary" in text else "supported")
    assert not result.is_valid and result.approved_text
    assert "could not explain all the requested details" in result.approved_text


def test_writer_is_told_not_to_invent_unrequested_gaps():
    from app.rag.prompts import RESEARCH_EXPLANATION_SYSTEM_PROMPT as prompt
    assert "Report a gap only for something the user asked" in prompt
