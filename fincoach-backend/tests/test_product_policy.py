"""Research answers: the checker judges product steering by meaning, not words.

The sentences here are test data only; the application holds no phrase list.
"""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.llm import CoachRequestBudget, LLMResult
from app.rag import research_answer as answer
from app.rag import research_policy, service, verifier
from app.rag.grounding import DISCLAIMER, GroundingClaim, contains_specific_product_recommendation
from app.rag.research_coverage import PartCoverage, RequestedPart
from app.rag.research_policy import EvidenceAssessment, ResearchDecision
from app.rag.retrieval import RetrievedChunk
from app.rag.verifier import GroundingVerification, ResearchVerificationContext
from test_kb_nonfinance import _public, _semantic, _send

ORDINARY = "Investors can buy stock through a broker [S1]."
OTHER = "A stock is a share of ownership in a company [S1]."
STEERING = "Open an account with Acme Securities to buy stocks [S1]."
SOURCE = "A stock is a share of ownership in a company. Investors can buy stock through a broker."


def _draft(*sentences):
    return "**Insight**\n" + "\n\n".join(sentences) + f"\n\n**Educational guidance**\n{DISCLAIMER}"


def _decision():
    assessment = EvidenceAssessment("sufficient", supported_sources=(1,), supported_quotes=((1, SOURCE),),
                                    parts=(PartCoverage("p1", "confirmed", (1,), complete=True),))
    return ResearchDecision([RetrievedChunk(1, "Stocks", "stocks.md", None, 0, SOURCE, .8)], assessment)


def _verified(claim_count, verdict=None, claim_ids=(), entity=None, part_claims=None):
    ids = range(1, claim_count + 1)
    return GroundingVerification(
        {i: "supported" for i in ids}, {i: 1 for i in ids}, requested_scope_covered=True,
        answered_part_ids=("p1",), answered_part_claims=part_claims or (("p1", tuple(ids)),),
        product_verdict=verdict, product_claim_ids=tuple(claim_ids), product_entity=entity)


def _check(monkeypatch, draft, verification, recheck=("uncertain", (), None)):
    seen = {}

    def fake(claims, references, **kwargs):
        seen["context"] = kwargs["research_context"]
        return verification

    def fake_recheck(question, draft_text, claims, reason, **kwargs):
        seen.setdefault("rechecks", []).append(reason)
        return recheck
    monkeypatch.setattr(answer, "verify_grounding_claims", fake)
    monkeypatch.setattr(answer, "recheck_product_policy", fake_recheck)
    checked = answer.check_research_draft(draft, public_question="how to buy stock", decision=_decision(),
                                          budget=CoachRequestBudget.start())
    return checked, seen


# ---- The failure being fixed: ordinary wording ----------------------------------------

def test_old_filter_really_does_flag_this_ordinary_sentence():
    # Documents why the switch is needed; the old filter stays for other routes.
    assert contains_specific_product_recommendation(ORDINARY)


def test_ordinary_wording_passes_when_the_checker_allows_it(monkeypatch):
    checked, seen = _check(monkeypatch, _draft(ORDINARY), _verified(1, "allowed"))
    assert checked.is_valid and "through a broker" in checked.approved_text
    assert seen["context"].assess_product_policy
    assert checked.diagnostics["product_policy"] == {
        "verdict": "allowed", "first_verdict": "allowed", "decided_by": "checker", "claim_count": 0,
        "old_filter_flagged": True}


# ---- A recommendation: remove the sentence, keep the rest -----------------------------

def test_steering_sentence_is_removed_and_the_rest_kept(monkeypatch):
    verification = _verified(2, "recommendation", (2,), "Acme Securities", (("p1", (1,)),))
    checked, _ = _check(monkeypatch, _draft(OTHER, STEERING), verification)
    assert checked.is_valid
    assert "share of ownership" in checked.approved_text and "Acme" not in checked.approved_text


def test_removal_that_leaves_the_part_incomplete_is_not_valid(monkeypatch):
    verification = _verified(2, "recommendation", (2,), "Acme Securities", (("p1", (1, 2)),))
    checked, _ = _check(monkeypatch, _draft(OTHER, STEERING), verification)
    assert not checked.is_valid and checked.error_codes == ("product_recommendation",)
    assert "Acme" not in (checked.approved_text or "")


def test_recommendation_with_no_sentence_is_rechecked_and_removed_when_it_names_the_product(monkeypatch):
    checked, seen = _check(monkeypatch, _draft(STEERING), _verified(1, "recommendation", (), "Acme Securities"),
                           recheck=("recommendation", (1,), "Acme Securities"))
    assert not checked.is_valid and checked.error_codes == ("product_recommendation",)
    assert checked.approved_text is None
    assert len(seen["rechecks"]) == 1 and "does not identify" in seen["rechecks"][0]
    assert checked.diagnostics["product_policy"]["first_verdict"] == "uncertain"
    assert checked.diagnostics["product_policy"]["decided_by"] == "recheck"


def test_recommendation_with_no_sentence_is_kept_when_the_recheck_finds_none(monkeypatch):
    checked, seen = _check(monkeypatch, _draft(STEERING), _verified(1, "recommendation", (), "Acme Securities"))
    assert checked.is_valid and len(seen["rechecks"]) == 1
    assert checked.diagnostics["product_policy"]["verdict"] == "allowed"
    assert checked.diagnostics["product_policy"]["decided_by"] == "recheck_uncertain"


def test_all_sentences_steering_leaves_nothing_to_ship(monkeypatch):
    checked, _ = _check(monkeypatch, _draft(STEERING), _verified(1, "recommendation", (1,), "Acme Securities"))
    assert not checked.is_valid and checked.approved_text is None


# ---- No usable verdict: never worse than today ----------------------------------------

@pytest.mark.parametrize("verdict", ["uncertain", "invalid", None])
def test_without_a_verdict_the_checker_is_asked_again_not_the_old_filter(monkeypatch, verdict):
    # The old word filter flags this ordinary sentence, but no longer decides.
    assert contains_specific_product_recommendation(ORDINARY)
    checked, seen = _check(monkeypatch, _draft(ORDINARY), _verified(1, verdict))
    assert checked.is_valid and len(seen["rechecks"]) == 1
    assert checked.diagnostics["product_policy"]["decided_by"] == "recheck_uncertain"


@pytest.mark.parametrize("verdict", ["uncertain", "invalid", None])
def test_without_a_verdict_a_recheck_can_still_remove_steering(monkeypatch, verdict):
    checked, _ = _check(monkeypatch, _draft(OTHER, STEERING), _verified(2, verdict, part_claims=(("p1", (1,)),)),
                        recheck=("recommendation", (2,), "Acme Securities"))
    assert checked.is_valid and "Acme" not in checked.approved_text


@pytest.mark.parametrize("outcome", ["unavailable", "invalid", "allowed"])
def test_an_unusable_recheck_keeps_the_answer(monkeypatch, outcome):
    checked, _ = _check(monkeypatch, _draft(ORDINARY), _verified(1, "uncertain"), recheck=(outcome, (), None))
    assert checked.is_valid


@pytest.mark.parametrize("verdict", ["uncertain", "invalid", None])
def test_without_a_verdict_the_old_filter_decides_and_can_pass(monkeypatch, verdict):
    checked, _ = _check(monkeypatch, _draft(OTHER), _verified(1, verdict))
    assert checked.is_valid


def test_checker_crash_ships_nothing_unchecked(monkeypatch):
    def crash(*a, **k):
        raise TimeoutError
    monkeypatch.setattr(answer, "verify_grounding_claims", crash)
    checked = answer.check_research_draft(_draft(ORDINARY), public_question="q", decision=_decision(),
                                          budget=CoachRequestBudget.start())
    assert not checked.is_valid and checked.error_codes == ("verifier_unavailable",)


def test_draft_with_no_claims_cannot_bypass_the_check(monkeypatch):
    monkeypatch.setattr(answer, "verify_grounding_claims", lambda *a, **k: pytest.fail("no checker call"))
    checked = answer.check_research_draft(f"**Insight**\n\n**Educational guidance**\n{DISCLAIMER}",
                                          public_question="q", decision=_decision(),
                                          budget=CoachRequestBudget.start())
    assert not checked.is_valid and "no_claims" in checked.error_codes


# ---- Both drafts are checked ----------------------------------------------------------

def test_rewritten_draft_gets_its_own_verdict(monkeypatch):
    verdicts = iter([_verified(1, "recommendation", (), "Acme Securities"), _verified(1, "allowed")])
    calls = []

    def fake(claims, references, **kwargs):
        calls.append(kwargs["research_context"].draft)
        return next(verdicts)
    monkeypatch.setattr(answer, "verify_grounding_claims", fake)
    monkeypatch.setattr(answer, "recheck_product_policy",
                        lambda *a, **k: ("recommendation", (1,), "Acme Securities"))
    monkeypatch.setattr(answer, "_generate_research_correction",
                        lambda *a, **k: LLMResult(_draft(ORDINARY), "gemini"))
    outcome = answer.recover_research_answer(
        plan=research_policy.QuestionPlan("stocks", False, True, "stable"), decision=_decision(),
        draft=LLMResult(_draft(STEERING), "gemini"), budget=CoachRequestBudget.start(), public_question="q")
    assert len(calls) == 2 and "Acme" in calls[0] and "broker" in calls[1]
    assert outcome.mode == "research_explanation_recovery" and "through a broker" in outcome.result.content


# ---- The checker's reply ---------------------------------------------------------------

def _context():
    return ResearchVerificationContext("how to buy stock", _draft(ORDINARY), (), (), assess_product_policy=True,
                                       requested_parts=(RequestedPart("p1", "how to buy stock"),),
                                       coverage=_decision().assessment.parts)


def _reply(monkeypatch, policy, *, context=None, **extra):
    payload = dict(claims=[dict(id=1, verdict="supported", source_index=1, scope_relation="preserved")],
                   quality_errors=[], requested_scope_covered=True, unanswered_requested_parts=[],
                   answered_part_ids=["p1"], part_claim_ids={"p1": [1]}, **extra)
    if policy is not ...:
        payload["product_policy"] = policy
    prompts = []

    def create(**kwargs):
        prompts.append(kwargs["messages"][-1]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)),
                                                        finish_reason="stop")], usage=None)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(verifier, "_create_verifier_client", lambda **k: client)
    result = verifier.verify_grounding_claims(
        [GroundingClaim(1, "Investors can buy stock through a broker.", (1,))], [SOURCE], timeout_seconds=5,
        research_context=context or _context())
    return result, prompts[0]


def test_valid_allowed_reply_is_read(monkeypatch):
    result, prompt = _reply(monkeypatch, {"verdict": "allowed", "claim_ids": [], "named_entity": None})
    assert result.product_verdict == "allowed" and not result.error_code
    assert '"product_policy"' in prompt


def test_valid_recommendation_reply_is_read(monkeypatch):
    result, _ = _reply(monkeypatch, {"verdict": "recommendation", "claim_ids": [1], "named_entity": "Acme"},
                       context=replace(_context(), draft=_draft(STEERING)))
    assert (result.product_verdict, result.product_claim_ids, result.product_entity) == ("recommendation", (1,), "Acme")


@pytest.mark.parametrize("policy", [
    ..., "allowed", {"verdict": "maybe"},
])
def test_badly_formed_verdict_does_not_fail_good_claims(monkeypatch, policy):
    result, _ = _reply(monkeypatch, policy)
    assert result.product_verdict == "invalid"
    assert result.error_code is None and result.verdicts == {1: "supported"}


@pytest.mark.parametrize("entity", [None, "", "   "])
def test_recommendation_that_names_nothing_is_only_uncertain(monkeypatch, entity):
    # Steering is toward a particular name; a product type alone is not one.
    result, _ = _reply(monkeypatch, {"verdict": "recommendation", "claim_ids": [1], "named_entity": entity})
    assert result.product_verdict == "uncertain" and result.product_claim_ids == ()


def test_other_checker_callers_are_unchanged(monkeypatch):
    context = ResearchVerificationContext("q", "d", (), (), requested_parts=(RequestedPart("p1", "q"),),
                                          coverage=_decision().assessment.parts)
    result, prompt = _reply(monkeypatch, ..., context=context)
    assert result.product_verdict is None and '"product_policy"' not in prompt


def test_checker_repair_keeps_the_verdict(monkeypatch):
    first = _verified(1, "recommendation", (1,), "Acme")
    assert verifier._keep_product_verdict(_verified(1, "allowed"), first).product_verdict == "recommendation"
    assert verifier._keep_product_verdict(_verified(1, "allowed"), _verified(1, "invalid")).product_verdict == "allowed"
    assert verifier._keep_product_verdict(_verified(1, "allowed"), _verified(1, None)).product_verdict == "allowed"


# ---- The complete path through the service ---------------------------------------------

def _research_turn(monkeypatch, verification):
    question = "how to buy stock"
    chunk = RetrievedChunk(1, "Stocks", "stocks.md", None, 0, SOURCE, .8)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(research_policy, "assess_evidence", lambda *a, **k: _decision().assessment)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: LLMResult(_draft(ORDINARY), "gemini"))
    monkeypatch.setattr(answer, "verify_grounding_claims", lambda *a, **k: verification)
    monkeypatch.setattr(answer, "recheck_product_policy", lambda *a, **k: ("uncertain", (), None))
    monkeypatch.setattr(answer, "_generate_research_correction",
                        lambda *a, **k: LLMResult(_draft(ORDINARY), "gemini"))
    _semantic(monkeypatch, _public("buying stock", subject_domain="finance"), question)
    return _send(question)


def test_reviewer_repro_how_to_buy_stock_reaches_the_user(monkeypatch):
    # Reproduced in the app: every later gate must honour the checker's verdict,
    # or an approved answer is replaced by the canned product redirect.
    message = _research_turn(monkeypatch, _verified(1, "allowed"))
    assert "through a broker" in message["content"]
    assert message["model"] != "fincoach-product-policy"


def test_unusable_verdict_on_ordinary_wording_reaches_the_user_after_one_recheck(monkeypatch):
    message = _research_turn(monkeypatch, _verified(1, "uncertain"))
    assert "through a broker" in message["content"]
