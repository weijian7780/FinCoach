"""Approved 2026-10-31: a typed savings target on a records-only reading, and
money shown with separators and the sign before the currency. Typed fields and
shared parsers only; randomised to show nothing is tied to one amount."""
import random
from datetime import date
from decimal import Decimal

import pytest

from app.agent_tools import _money
from app.rag import request_interpretation as intent
from app.rag import service
from app.rag.grounding import _numeric_values
from app.rag.research_answer import _verified_calculations
from test_kb_nonfinance import _records_service, _all_providers_down

COMPATIBLE = sorted(intent._TARGET_READS)
INCOMPATIBLE = ["get_spending_summary", "search_transactions", "get_budget_status", "get_upcoming_reminders"]


def _records_only(value, operation, role="target", **read_extra):
    return {"route": "personal_finance", "relation": "new", "goal": "plan", "response_language": "en",
            "read": {"operation": operation, "category": {"decision": "none"}, **read_extra},
            "amounts": [{"amount": value, "role": role}]}


def _normalised(payload):
    return intent._normalise_proposal(intent.IntentProposal.model_validate(payload))


@pytest.mark.parametrize("seed", range(60))
def test_a_records_only_target_with_a_compatible_read_is_accepted(seed):
    rng = random.Random(seed)
    amount = str(rng.randint(1, 1_000_000))
    proposal = _normalised(_records_only(amount, rng.choice(COMPATIBLE)))
    intent.check_amounts(proposal)
    intent.compile_read(proposal, date(2026, 10, 31))
    assert service._listed_target(proposal) == amount


@pytest.mark.parametrize("operation", INCOMPATIBLE)
def test_a_records_only_target_with_an_incompatible_read_is_still_rejected(operation):
    extra = {"result_mode": "list"} if operation == "search_transactions" else {}
    with pytest.raises(intent.ProposalRejected):
        intent.check_amounts(_normalised(_records_only("3000", operation, **extra)))


def test_a_budget_still_needs_a_research_part():
    with pytest.raises(intent.ProposalRejected):
        intent.check_amounts(_normalised(_records_only("1500", "predict_savings", role="budget")))


def test_two_records_only_targets_are_not_guessed():
    payload = _records_only("3000", "predict_savings")
    payload["amounts"].append({"amount": "500", "role": "target"})
    with pytest.raises(intent.ProposalRejected):
        intent.check_amounts(_normalised(payload))


@pytest.mark.parametrize("seed", range(20))
def test_a_target_put_on_a_records_read_is_cleared_from_it(seed):
    amount = str(random.Random(seed).randint(1, 100_000))
    proposal = _normalised(_records_only(amount, "predict_savings", amount=amount))
    assert proposal.read.amount is None
    intent.check_amounts(proposal)
    intent.compile_read(proposal, date(2026, 10, 31))


def test_target_is_a_valid_meaning_for_a_repair_on_a_records_only_reading():
    proposal = _normalised(_records_only("3000", "predict_savings"))
    assert intent._amount_meaning(proposal, "3000") == "target"


# ---- The records answer keeps its own content; the plan joins it ---------------------

def _send_records_only(monkeypatch, advice=""):
    _all_providers_down(monkeypatch)
    original = service._records_answer

    def records_answer(**kwargs):
        result, mode, origin, facts = original(**kwargs)
        if advice:
            facts = service._format_fast_verified_read(kwargs["tool_name"], kwargs["tool_result"])
            result = service.replace(result, content=f"{facts}\n\n{advice}")
        return result, mode, origin, facts
    monkeypatch.setattr(service, "_records_answer", records_answer)
    question = "i want reach rm10000"
    svc = _records_service(monkeypatch, _records_only("10000", "predict_savings"), question)
    return svc.send_message("s", "m", question)["assistant_message"]["content"]


def test_records_only_target_answer_gives_the_target_facts_and_plan(monkeypatch):
    content = _send_records_only(monkeypatch)
    assert content.startswith("Your savings target: **RM10,000**.")
    assert "estimated savings" in content and "monthly contribution" in content


def test_requested_advice_in_the_records_answer_is_kept_after_the_plan(monkeypatch):
    advice = "Review your largest spending category first."
    content = _send_records_only(monkeypatch, advice=advice)
    assert advice in content and "monthly contribution" in content
    assert content.index("monthly contribution") < content.index(advice)


# ---- Money display ------------------------------------------------------------------------

def test_money_has_separators_and_the_sign_before_the_currency():
    assert _money("5027.25") == "RM5,027.25"
    assert _money("-5027.25") == "-RM5,027.25"
    assert _money(0) == "RM0.00"
    assert _money("999.5") == "RM999.50"


@pytest.mark.parametrize("seed", range(100))
def test_any_money_value_round_trips_through_every_parser(seed):
    rng = random.Random(seed)
    value = Decimal(rng.randint(-10_000_000, 10_000_000)) / 100
    shown = _money(value)
    assert service._money_decimal(shown) == value                      # coach money parser
    assert _numeric_values(shown) == _numeric_values(f"RM{abs(value)}")  # grounding parser (magnitude)
    assert shown.startswith("-RM") == (value < 0)


def test_calculations_written_with_separators_still_verify():
    allowed = _numeric_values("RM600.00 RM5,627.25")
    assert _verified_calculations("RM5,627.25 - RM600.00 = RM5,027.25", allowed) == {"rm:5027.25"}


def _send_with_model_advice(monkeypatch, advice):
    """The records answer as the real path builds it: verified facts written
    by code, then a model-written advice paragraph ("mixed" provenance)."""
    _all_providers_down(monkeypatch)

    def records_answer(**kwargs):
        facts = service._format_fast_verified_read(kwargs["tool_name"], kwargs["tool_result"])
        result = service.AgentLLMResult(content=f"{facts}\n\n{advice}", model="gemini",
                                        tool_names=(kwargs["tool_name"],),
                                        tool_results=({"name": kwargs["tool_name"], "result": kwargs["tool_result"]},))
        return result, "two_phase_advice", "mixed", facts
    monkeypatch.setattr(service, "_records_answer", records_answer)
    question = "i want reach rm10000"
    svc = _records_service(monkeypatch, _records_only("10000", "predict_savings"), question)
    return svc.send_message("s", "m", question)["assistant_message"]["content"]


def test_reviewer_repro_plan_survives_the_number_check_of_model_advice(monkeypatch):
    # Reproduced with real providers: the code-written plan was counted as model
    # text, failed the number check, and the reply fell back to bare facts.
    advice = "Review your largest spending category first."
    content = _send_with_model_advice(monkeypatch, advice)
    assert "monthly contribution" in content and advice in content


def test_unverifiable_model_advice_never_removes_the_plan(monkeypatch):
    content = _send_with_model_advice(monkeypatch, "Cut RM777.77 from dining every week.")
    assert "monthly contribution" in content and "RM777.77" not in content
    assert content.startswith("Your savings target: **RM10,000**.")
