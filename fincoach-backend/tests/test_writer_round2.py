"""Round-two attribution, reply-space and word-limit regressions."""
from dataclasses import replace
import json
from types import SimpleNamespace as NS

import pytest

from app.llm import CoachRequestBudget
from app.rag import research_answer as answer, verifier
from app.rag.grounding import DISCLAIMER, GroundingClaim
from app.rag.research_policy import EvidenceAssessment, ResearchDecision
from app.rag.retrieval import RetrievedChunk
from app.rag.service import _strip_source_markers
from app.rag.verifier import GroundingVerification, ResearchVerificationContext
from test_writer_fixes import response, setup, verdict


def decision(text="Investors may visit the office.", title="Bursa Malaysia"):
    return ResearchDecision([RetrievedChunk(1, title, "guide.md", None, 0, text, .9)],
        EvidenceAssessment("sufficient", supported_sources=(1,), supported_quotes=((1, text),)))


def draft(text):
    return f"**Insight**\n{text}\n\n**Educational guidance**\n{DISCLAIMER}"


def allow(monkeypatch):
    seen = []
    def fake(claims, references, **kwargs):
        seen.append((claims, kwargs))
        return GroundingVerification({c.id: "supported" for c in claims}, {c.id: 1 for c in claims},
            product_verdict="allowed", requested_scope_covered=True)
    monkeypatch.setattr(answer, "verify_grounding_claims", fake)
    return seen


@pytest.mark.parametrize("text, expected", [
    ("According to [S1], investors may visit the office.", "According to Bursa Malaysia, investors may visit the office."),
    ("Menurut [S1], pelabur boleh datang ke pejabat.", "Menurut Bursa Malaysia, pelabur boleh datang ke pejabat."),
    ("[S1] describes visiting the office.", "Bursa Malaysia describes visiting the office."),
])
def test_attribution_survives_check_and_display(monkeypatch, text, expected):
    seen = allow(monkeypatch)
    result = answer.check_research_draft(draft(text), public_question="Explain", decision=decision(),
                                         budget=CoachRequestBudget.start())
    assert result.is_valid
    assert expected in _strip_source_markers(result.approved_text)
    assert expected in seen[0][0][0].text
    assert "[S1]" in result.approved_text


@pytest.mark.parametrize("text", ["Investors may visit the office [S1].", "Investors may visit the office. [S1]"])
def test_trailing_marker_keeps_ordinary_prose(monkeypatch, text):
    allow(monkeypatch)
    result = answer.check_research_draft(draft(text), public_question="Explain", decision=decision(),
                                         budget=CoachRequestBudget.start())
    assert result.is_valid
    assert _strip_source_markers(result.approved_text) == draft("Investors may visit the office.")


def test_inline_title_is_not_permission_for_unsupported_claim(monkeypatch):
    monkeypatch.setattr(answer, "verify_grounding_claims", lambda *a, **k:
        GroundingVerification({1: "unsupported"}, product_verdict="allowed"))
    result = answer.check_research_draft(draft("According to [S1], returns are guaranteed."),
        public_question="Explain", decision=decision(), budget=CoachRequestBudget.start())
    assert not result.is_valid and result.approved_text is None


def test_title_falls_back_to_source_metadata(monkeypatch):
    allow(monkeypatch)
    result = answer.check_research_draft(draft("According to [S1], investors may visit the office."),
        public_question="Explain", decision=decision(title=None), budget=CoachRequestBudget.start())
    assert "According to guide.md," in _strip_source_markers(result.approved_text)


def test_long_answer_and_more_than_twenty_claims_with_500_setting(monkeypatch):
    monkeypatch.setattr(answer, "COACH_RESEARCH_MAX_WORDS", 500)
    seen = allow(monkeypatch)
    text = "\n".join("Investors may visit the office to discuss their account [S1]." for _ in range(25))
    result = answer.check_research_draft(draft(text), public_question="Explain", decision=decision(),
                                         budget=CoachRequestBudget.start())
    assert result.is_valid and len(seen[0][0]) == 25
    assert seen[0][1]["max_tokens"] >= 25 * 120 + 600


def test_checker_token_budget_is_scaled_and_capped():
    assert answer.research_verifier_max_tokens(7) > 1500
    assert answer.research_verifier_max_tokens(30) >= 30 * 120 + 600
    assert answer.research_verifier_max_tokens(100) == 6000


@pytest.mark.parametrize("setting, words, rejected", [(200, 201, True), (500, 301, False), (500, 501, True)])
def test_configured_word_boundary(monkeypatch, setting, words, rejected):
    monkeypatch.setattr(answer, "COACH_RESEARCH_MAX_WORDS", setting)
    allow(monkeypatch)
    # One complete sentence; count includes the mandatory disclaimer, as in production.
    body = "Investors " + "carefully " * (words - len(DISCLAIMER.split()) - 4) + "review their accounts [S1]."
    result = answer.check_research_draft(draft(body), public_question="Explain", decision=decision(),
                                         budget=CoachRequestBudget.start())
    assert ("answer_too_long" in result.error_codes) is rejected


def test_caller_can_reserve_words_below_setting(monkeypatch):
    monkeypatch.setattr(answer, "COACH_RESEARCH_MAX_WORDS", 500)
    allow(monkeypatch)
    text = "Investors " + "carefully " * 220 + "review their accounts [S1]."
    result = answer.check_research_draft(draft(text), public_question="Explain", decision=decision(),
        budget=CoachRequestBudget.start(), max_words=200)
    assert "answer_too_long" in result.error_codes


def test_malformed_research_reply_with_five_seconds_left_can_retry(monkeypatch):
    clock = [0.0]
    calls, timeouts = setup(monkeypatch, [])
    monkeypatch.setattr(verifier, "monotonic", lambda: clock[0])
    def factory(**options):
        timeouts.append(options["timeout_seconds"])
        def create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                clock[0] += options["timeout_seconds"] - 5.1
                return response("{")
            clock[0] += .2
            payload = {**verdict(), "quality_errors": []}
            payload["claims"][0]["scope_relation"] = "preserved"
            return response(payload)
        return NS(chat=NS(completions=NS(create=create)))
    monkeypatch.setattr(verifier, "_create_verifier_client", factory)
    result = verifier.verify_grounding_claims([GroundingClaim(1, "A fact.", (1,))], ["A fact."],
        timeout_seconds=10, research_context=ResearchVerificationContext("q", "d", ()))
    assert result.all_supported
    assert len(calls) == 2 and [c["model"] for c in calls] == ["nemotron-test", "nemotron-test"]
    assert timeouts[0] == 10 and timeouts[1] >= 5
    assert clock[0] < 10


def test_research_valid_rejection_does_not_spend_reserve(monkeypatch):
    calls, timeouts = setup(monkeypatch, [response({**verdict("unsupported"), "quality_errors": []})])
    result = verifier.verify_grounding_claims([GroundingClaim(1, "A fact.", (1,))], ["A fact."],
        timeout_seconds=10, research_context=ResearchVerificationContext("q", "d", ()))
    assert result.verdicts == {1: "unsupported"} and len(calls) == 1
    assert timeouts[0] == 10


def test_scaled_claim_cap_still_bounds_long_answers(monkeypatch):
    monkeypatch.setattr(answer, "COACH_RESEARCH_MAX_WORDS", 500)
    allow(monkeypatch)
    text = "\n".join("Investors may visit the office [S1]." for _ in range(31))
    result = answer.check_research_draft(draft(text), public_question="Explain", decision=decision(),
                                         budget=CoachRequestBudget.start())
    assert "too_many_claims" in result.error_codes


def test_checker_accepts_a_part_supported_by_over_twenty_claims(monkeypatch):
    from app.rag.research_coverage import RequestedPart, PartCoverage
    claims = [GroundingClaim(i, "Investors may visit the office.", (1,)) for i in range(1, 26)]
    payload = {"claims": [{"id": c.id, "verdict": "supported", "source_index": 1,
                           "scope_relation": "preserved"} for c in claims],
               "quality_errors": [], "requested_scope_covered": True,
               "unanswered_requested_parts": [], "answered_part_ids": ["p1"],
               "part_claim_ids": {"p1": [c.id for c in claims]}}
    calls, _ = setup(monkeypatch, [response(payload)])
    context = ResearchVerificationContext("q", "d", (), requested_parts=(RequestedPart("p1", "q"),),
        coverage=(PartCoverage("p1", "confirmed", (1,), complete=True),))
    result = verifier.verify_grounding_claims(claims, ["Investors may visit the office."],
        timeout_seconds=10, research_context=context)
    assert result.all_supported and len(result.answered_part_claims[0][1]) == 25
    assert len(calls) == 1


@pytest.mark.parametrize("limit,target", [(200, 150), (500, 300)])
def test_setting_controls_both_prompts(monkeypatch, limit, target):
    import runpy
    from app import config
    monkeypatch.setattr(config, "COACH_RESEARCH_MAX_WORDS", limit)
    prompts = runpy.run_path(str(__import__("pathlib").Path(answer.__file__).with_name("prompts.py")))
    expected = f"about {target} words, never more than {limit}"
    assert expected in prompts["RESEARCH_EXPLANATION_SYSTEM_PROMPT"]
    assert expected in prompts["build_research_recovery_prompt"]("q", decision())


def test_config_default_and_compose_value(monkeypatch):
    import runpy
    from app import config
    monkeypatch.delenv("COACH_RESEARCH_MAX_WORDS", raising=False)
    assert runpy.run_path(config.__file__)["COACH_RESEARCH_MAX_WORDS"] == 200
    monkeypatch.setenv("COACH_RESEARCH_MAX_WORDS", "500")
    assert runpy.run_path(config.__file__)["COACH_RESEARCH_MAX_WORDS"] == 500


def test_named_source_is_counted_in_display_word_limit(monkeypatch):
    monkeypatch.setattr(answer, "COACH_RESEARCH_MAX_WORDS", 200)
    allow(monkeypatch)
    result = answer.check_research_draft(draft("According to [S1], investors may visit the office."),
        public_question="Explain", decision=decision(title="Source " * 201), budget=CoachRequestBudget.start())
    assert "answer_too_long" in result.error_codes
