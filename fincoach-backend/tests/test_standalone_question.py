"""The user's request survives the pipeline: a standalone question becomes the
requested part, retrieval also searches the plan's own subject words, the writer
answers the requested form, and a gap notice names what is missing."""
import pytest
from pydantic import ValidationError

from app.llm import CoachRequestBudget
from app.rag import prompts
from app.rag import request_interpretation as intent
from app.rag import research_answer as answer
from app.rag import research_policy
from app.rag import service, verifier
from app.rag.grounding import DISCLAIMER
from app.rag.query_analysis import SearchSubquery, analyze_knowledge_query
from app.rag.research_coverage import PartCoverage, requested_parts
from app.rag.research_policy import EvidenceAssessment, ResearchDecision
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import ResearchOutcome
from test_kb_nonfinance import _plan, _public, _recording_retrieve, _semantic, _send
from test_kb_reduced_release import _interpret

WHY = "Why does KWSP exist and why do members contribute to it?"


# ---- Step 2: the standalone question -------------------------------------------------

def test_older_proposal_without_a_question_is_unchanged():
    payload = _public("kwsp", entities=["KWSP"])
    assert intent.IntentProposal.model_validate(payload).public.question is None
    plan = _plan(payload, "why kwsp")
    assert plan.required_facts == () and plan.question == ""
    assert [part.label for part in requested_parts(plan)] == ["kwsp"]  # today's bare-topic fallback


def test_reviewer_repro_why_kwsp_keeps_the_why_as_the_requested_part():
    # Live trace: "why kwsp" was reduced to the bare label "kwsp".
    plan = _plan(_public("kwsp", entities=["KWSP"], question=WHY), "why kwsp")
    assert plan.required_facts == (WHY,)
    assert [part.label for part in requested_parts(plan)] == [WHY]


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_question_counts_as_none(value):
    assert intent.IntentProposal.model_validate(_public("kwsp", question=value)).public.question is None


@pytest.mark.parametrize("value", [123, "x" * 201])
def test_invalid_question_is_rejected(value):
    with pytest.raises(ValidationError):
        intent.IntentProposal.model_validate(_public("kwsp", question=value))


def test_definition_path_stays_first():
    # A bare "what is X" keeps its full definition briefing.
    plan = _plan(_public("ptptn", question="What is PTPTN?"), "what is PTPTN")
    assert plan.definitional and plan.required_facts == intent._DEFINITIONAL_FACTS


def test_explicit_facts_and_parts_keep_their_precedence():
    facts = _plan(_public("kwsp", required_facts=["dividend rate"], question=WHY), "q")
    assert facts.required_facts == ("dividend rate",)
    mixed = _plan(_public("kwsp and recursion", subject_domain="mixed", question=WHY, parts=[
        {"fact": "why KWSP exists", "domain": "finance"}, {"fact": "what recursion is", "domain": "non_finance"}]), "q")
    assert mixed.required_facts == ("why KWSP exists", "what recursion is")


def test_standalone_question_is_de_identified():
    plan = _plan(_public("emergency fund", question="Why keep RM3,000 in an emergency fund? Email me at a@b.com"), "q")
    assert "3,000" not in plan.question and "a@b.com" not in plan.question
    assert all("3,000" not in fact and "a@b.com" not in fact for fact in plan.required_facts)


def test_interpreter_accepts_the_question_field_end_to_end():
    result = _interpret("why kwsp", [], {"route": "financial_education", "relation": "new",
                                         "public": {"topic": "kwsp", "entities": ["KWSP"], "question": WHY}})
    assert result.failure is None and result.public_plan.required_facts == (WHY,)


def test_prompt_asks_for_the_standalone_question():
    assert "public.question" in intent.PROMPT and "keeping what is asked" in intent.PROMPT


# ---- Step 3: retrieval also searches the plan's own subject words ------------------------

def test_subject_searches_are_plain_searches_and_the_question_is_not_searched():
    # Measured: searching the whole standalone question added off-target
    # passages without finding more documents, so only subject words are added.
    plan = _plan(_public("kwsp", entities=["KWSP"], question=WHY), "why kwsp")
    subqueries = service._subject_subqueries(plan)
    assert [s.text for s in subqueries] == ["KWSP"]
    assert all(s.topic_id is None and s.source is None for s in subqueries)  # never a curated-topic rule


def test_curated_topic_search_stays_first_and_is_not_duplicated():
    plan = _plan(_public("PTPTN", entities=["PTPTN"], question="What does PTPTN fund?"), "q")
    base = analyze_knowledge_query(plan.topic)
    analysis = service._plan_retrieval_analysis(plan, base)
    assert analysis.subqueries[:len(base.subqueries)] == base.subqueries
    texts = [" ".join(s.text.casefold().split()) for s in analysis.subqueries]
    assert len(texts) == len(set(texts))


def test_no_extra_searches_when_the_topic_has_none():
    plan = _plan(_public("kwsp", question=WHY), "q")
    empty = analyze_knowledge_query("")
    assert service._plan_retrieval_analysis(plan, empty) is empty


def test_reviewer_repro_non_finance_part_is_searched_by_its_subject(monkeypatch):
    # "explain message passing" scored below the threshold while the bare subject
    # "message passing" finds the document; the part's own subject is now searched.
    from app.rag.research_coverage import plan_without_parts
    plan = _plan(_public("message passing and laptop savings", subject_domain="mixed", parts=[
        {"fact": "explain message passing", "domain": "non_finance", "entities": ["message passing"]},
        {"fact": "how to save for a laptop", "domain": "finance"}]), "q")
    remaining = plan_without_parts(plan, ("p2",))
    calls = _recording_retrieve(monkeypatch, [[]])
    service._retrieve_remaining_parts(remaining, [], ())
    assert "message passing" in calls[0]["subqueries"]
    assert all("laptop" not in text.casefold() for text in calls[0]["subqueries"])


def test_first_retrieval_includes_the_subject_words(monkeypatch):
    calls = _recording_retrieve(monkeypatch, [[]])
    monkeypatch.setattr(research_policy, "assess_evidence",
                        lambda *a, **k: EvidenceAssessment("insufficient", ("p1",)))
    monkeypatch.setattr(research_policy, "research_evidence", lambda *a, **k: ResearchOutcome([], True, "ok"))
    monkeypatch.setattr(research_policy, "extract_passages", lambda *a, **k: {})
    _semantic(monkeypatch, _public("kwsp", entities=["KWSP"], question=WHY, subject_domain="finance"), "why kwsp")
    _send("why kwsp")
    assert calls and "KWSP" in calls[0]["subqueries"] and WHY not in calls[0]["subqueries"]


# ---- Step 4: the writer answers the requested form ----------------------------------------

def test_writer_prompt_answers_the_requested_form_without_unrequested_advice():
    text = prompts.RESEARCH_EXPLANATION_SYSTEM_PROMPT
    assert "reasons for a why question" in text and "Never substitute a definition" in text
    assert "not a reason to add student advice" in text
    assert "Malaysian students" in text  # still the audience


# ---- Step 5: the notice names only what is missing -------------------------------------------

def test_notice_names_the_missing_parts_once():
    notice = answer._partial_notice("q", (WHY, WHY, " "))
    assert notice == f"I couldn't fully confirm and explain: “{WHY}”."


def test_notice_without_named_parts_keeps_the_general_sentence():
    assert answer._partial_notice("q") == "I could not explain all the requested details yet."
    assert answer._partial_notice("q\nResponse language: ms.", ("Kenapa KWSP?",)).startswith(
        "Saya belum dapat mengesahkan")


def test_notice_names_only_the_plans_own_labels():
    from app.rag.research_coverage import RequestedPart
    verification = verifier.GroundingVerification({}, unanswered_requested_parts=(WHY, "free text from a model"))
    assert answer._missing_labels(verification, (RequestedPart("p1", WHY),)) == (WHY,)


def test_checked_partial_answer_names_the_unanswered_part(monkeypatch):
    quote = "KWSP manages mandatory contributions from monthly wages."
    source = RetrievedChunk(1, "KWSP guide", "kwsp.md", None, 0, quote, .8)
    decision = ResearchDecision([source], EvidenceAssessment(
        "partial", supported_sources=(1,), supported_quotes=((1, quote),),
        parts=(PartCoverage("p1", "reported", (1,), complete=False),)),
        diagnostics={"requested_part_labels": [WHY]})
    text = f"**Insight**\nKWSP manages mandatory contributions from monthly wages [S1].\n\n**Educational guidance**\n{DISCLAIMER}"
    monkeypatch.setattr(answer, "verify_grounding_claims", lambda claims, *a, **k: verifier.GroundingVerification(
        {claim.id: "supported" for claim in claims}, {claim.id: 1 for claim in claims},
        requested_scope_covered=False, unanswered_requested_parts=(WHY,), answered_part_ids=()))
    checked = answer.check_research_draft(text, public_question="why kwsp", decision=decision,
                                          budget=CoachRequestBudget.start())
    assert f"I couldn't fully confirm and explain: “{WHY}”." in checked.approved_text
    assert "I could not explain all the requested details yet." not in checked.approved_text
