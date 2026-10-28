"""Approved evidence reaches the primary writer before fallback is considered."""
import pytest

from app.llm import CoachRequestBudget, LLMResult
from app.rag import research_answer as answer
from app.rag import service
from app.rag.research_answer import ResearchDraftCheck
from app.rag.research_policy import EvidenceAssessment, QuestionPlan, ResearchDecision
from app.rag.retrieval import RetrievedChunk

SOURCE = ("PTPTN is the National Higher Education Fund Corporation. "
          "It provides education loans to eligible Malaysian students.")
QUOTE = "PTPTN is the National Higher Education Fund Corporation."
PLAN = QuestionPlan("ptptn", False, True, "stable", response_language="en")


def _decision(quote=QUOTE, status="sufficient"):
    chunk = RetrievedChunk(1, "PTPTN guidance", "official_ptptn.md", None, 0, SOURCE, 0.8)
    # Corpus-only shape: the source is approved, the literal quotation is only
    # carried in source_quotes, and supported_quotes starts empty.
    return ResearchDecision([chunk], EvidenceAssessment(status, supported_sources=(1,)), source_quotes=(quote,))


def _run(monkeypatch, decision, *, primary, recover=None):
    calls = {"primary": 0}

    def generate(prompt, **kwargs):
        calls["primary"] += 1
        calls["prompt"] = prompt
        if isinstance(primary, Exception):
            raise primary
        return LLMResult(primary, "gemini-test")
    monkeypatch.setattr(service, "generate_result", generate)
    if recover is not None:
        monkeypatch.setattr(service, "recover_research_answer", recover)
    outcome = service._research_explanation_result(plan=PLAN, decision=decision,
                                                   budget=CoachRequestBudget.start(), question="what is ptptn")
    return outcome, calls


def _capture(seen):
    def recover(**kwargs):
        seen.update(kwargs)
        return "captured"
    return recover


def test_recoverable_quotes_reach_the_primary_writer(monkeypatch):
    seen = {}
    outcome, calls = _run(monkeypatch, _decision(), primary="PTPTN provides education loans.",
                          recover=_capture(seen))
    assert calls["primary"] == 1 and QUOTE in calls["prompt"]
    assert seen["draft"].content == "PTPTN provides education loans." and seen["initial_failure"] is None
    # Source validation is kept: the reconstructed quote is tied to its approved source.
    assert seen["decision"].assessment.supported_quotes == ((1, QUOTE),)


def test_quote_not_in_its_source_is_not_approved_and_skips_the_writer(monkeypatch):
    seen = {}
    _, calls = _run(monkeypatch, _decision(quote="PTPTN gives free money to everyone."),
                    primary="unused", recover=_capture(seen))
    assert calls["primary"] == 0 and seen["draft"] is None


def test_no_time_left_skips_the_primary_writer(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "initial_writer_budget", lambda budget: None)
    _, calls = _run(monkeypatch, _decision(), primary="unused", recover=_capture(seen))
    assert calls["primary"] == 0 and seen["draft"] is None


def _valid_check(text):
    return lambda *a, **k: ResearchDraftCheck(True, approved_text=text, diagnostics={})


def test_primary_success_is_the_answer(monkeypatch):
    monkeypatch.setattr(answer, "check_research_draft", _valid_check("PTPTN provides education loans."))
    monkeypatch.setattr(answer, "_generate_research_correction", lambda *a, **k: pytest.fail("no fallback"))
    outcome, calls = _run(monkeypatch, _decision(), primary="PTPTN provides education loans.")
    assert calls["primary"] == 1
    assert outcome.mode == "research_explanation" and "education loans" in outcome.result.content


def test_primary_failure_then_fallback_writes_the_answer(monkeypatch):
    monkeypatch.setattr(answer, "check_research_draft", _valid_check("Fallback: PTPTN provides loans."))
    monkeypatch.setattr(answer, "_generate_research_correction",
                        lambda *a, **k: LLMResult("Fallback: PTPTN provides loans.", "deepseek-test"))
    outcome, calls = _run(monkeypatch, _decision(), primary=TimeoutError())
    assert calls["primary"] == 1
    assert outcome.mode == "research_explanation_recovery" and "Fallback" in outcome.result.content


def test_both_providers_failing_gives_the_unavailable_wording(monkeypatch):
    def fallback(*a, **k):
        raise RuntimeError("Insufficient Balance")
    monkeypatch.setattr(answer, "_generate_research_correction", fallback)
    outcome, calls = _run(monkeypatch, _decision(), primary=TimeoutError())
    assert calls["primary"] == 1
    assert outcome.mode == "research_explanation_unavailable"
    assert outcome.result.content == answer.UNAVAILABLE_MESSAGE


def test_insufficient_evidence_never_calls_a_writer(monkeypatch):
    monkeypatch.setattr(answer, "_generate_research_correction", lambda *a, **k: pytest.fail("no writer"))
    decision = ResearchDecision([], EvidenceAssessment("insufficient"), failure="research_round_limit")
    outcome, calls = _run(monkeypatch, decision, primary="unused")
    assert calls["primary"] == 0
    assert outcome.result.content == answer._INSUFFICIENT_EVIDENCE_MESSAGES["en"]
