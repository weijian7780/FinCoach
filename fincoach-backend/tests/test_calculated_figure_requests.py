"""A figure FinCoach calculates is a result, not a setting, and a savings target
with no surplus still gets advice. Typed fields only; the shapes come from a
real conversation (2026-11-09) with the amounts varied."""
import copy
import random
from types import SimpleNamespace

import pytest

import app.agent_tools as tools
from app.rag import request_interpretation as intent
from app.rag import service
from test_kb_nonfinance import _all_providers_down, _records_service

SHORTFALL = {
    "status": "ok", "month": "2026-10-01", "income_basis": "recorded_income", "income": "RM600.00",
    "projection_basis": "spending_pace", "basis_period": {"start": "2026-10-01", "end": "2026-10-09"},
    "days_elapsed": 9, "days_in_month": 31, "expense_count": 7, "recorded_expenses": "RM852.45",
    "daily_spending_rate": "RM94.72", "projected_month_spending": "RM2,841.50",
    "projected_remaining": "-RM2,241.50", "projected_shortfall": "RM2,241.50", "goal_details": [],
    "projected_saveable": "RM0.00", "is_estimate": True,
}
SURPLUS = {**SHORTFALL, "income": "RM3,000.00", "projected_remaining": "RM158.50",
           "projected_shortfall": "RM0.00", "projected_saveable": "RM158.50"}


def _change_figure(amount="1000", goal="explain"):
    return {"route": "personal_finance", "relation": "follow_up", "goal": goal, "response_language": "en",
            "read": {"operation": "predict_savings", "category": {"decision": "none"}},
            "amounts": [{"amount": amount, "role": "context"}]}


def _saved_target(amount="50"):
    """The reading stored for "Help me save RM50"."""
    return {
        "route": "combined", "relation": "new", "goal": "advise", "response_language": "en",
        "requested_output": "advice",
        "read": {"operation": "predict_savings", "category": {"decision": "none"}},
        "public": {"topic": f"Help saving RM{amount}", "question": f"How can I save RM{amount}?",
                   "framework": "none", "stated_amount": amount, "subject_domain": "finance",
                   "jurisdiction": "Malaysia", "time_scope": "stable",
                   "search_query": "saving money Malaysia practical strategies",
                   "required_facts": [f"ways to save RM{amount}"],
                   "parts": [{"fact": f"help saving a total target of RM{amount}", "domain": "finance",
                              "answer_kind": "savings_target",
                              "search_query": "saving money Malaysia practical strategies"}]},
        "amounts": [{"amount": amount, "role": "target"}],
    }


def _send(monkeypatch, payload, question, *, savings=SHORTFALL, writer=None):
    """One real turn. ``writer`` is what the model writes; None = providers down."""
    _all_providers_down(monkeypatch)
    prompts = []
    if writer is not None:
        def generate(prompt, **_kwargs):
            prompts.append(prompt)
            return SimpleNamespace(content=writer, model="test-writer", prompt_tokens=1, completion_tokens=1,
                                   finish_reason="stop")
        monkeypatch.setattr(service, "generate_result", generate)
    svc = _records_service(monkeypatch, copy.deepcopy(payload), question)
    monkeypatch.setattr(tools.AgentToolExecutor, "_predict_savings", lambda self, raw: dict(savings))
    message = svc.send_message("s", "m", question)["assistant_message"]
    return message["content"], message.get("model"), prompts


# ---- Reading: the interpreter is told the difference -----------------------------------

def test_the_interpreter_is_told_a_calculated_figure_is_not_a_setting():
    assert "is a result, not a setting" in intent.PROMPT
    assert "never a target or budget" in intent.PROMPT


def test_a_stated_amount_on_a_calculated_figure_is_a_valid_reading():
    proposal = intent._normalise_proposal(intent.IntentProposal.model_validate(_change_figure()))
    intent.check_amounts(proposal)
    assert service._listed_target(proposal) is None
    assert service._listed_context_amounts(proposal) == ("1000",)


# ---- Changing a calculated figure: the user's question gets answered --------------------

ANSWER = ("The estimated shortfall is calculated from your income and projected spending, so it cannot be set "
          "directly. Reaching RM1,000 means closing the difference through more income or less spending.\n"
          "Calculation: RM2,241.50 - RM1,000 = RM1,241.50")
QUESTION = "can i change estimated shortfall to rm1000?"


def test_the_answer_explains_the_figure_and_is_not_a_savings_target(monkeypatch):
    content, model, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=ANSWER)
    assert "Your savings target" not in content and "target cannot be reached" not in content
    assert "estimated shortfall: **RM2,241.50**" in content
    assert ANSWER in content
    assert model == "test-writer"


def test_the_writer_is_told_the_amount_is_the_users_not_a_record(monkeypatch):
    _, _, prompts = _send(monkeypatch, _change_figure(), QUESTION, writer=ANSWER)
    assert prompts and "RM1,000" in prompts[-1] and "not a record" in prompts[-1]


@pytest.mark.parametrize("seed", range(25))
def test_any_stated_amount_and_its_exact_difference_survive_the_checks(seed, monkeypatch):
    stated = random.Random(seed).randint(1, 2241)
    difference = 2241.50 - stated
    writer = (f"It is calculated, so it cannot be set to RM{stated:,}.\n"
              f"Calculation: RM2,241.50 - RM{stated:,} = RM{difference:,.2f}")
    content, _, _ = _send(monkeypatch, _change_figure(str(stated)), QUESTION, writer=writer)
    assert writer in content


@pytest.mark.parametrize("writer", [
    "It cannot be set. Cut RM777.77 from food.",
    "It cannot be set.\nCalculation: RM2,241.50 - RM1,000 = RM999.00",
    "It cannot be set.\nCalculation: RM2,241.50 - RM555.00 = RM1,686.50",
    "Your recorded income is RM777.77, so it cannot be set.",
])
def test_any_other_new_or_wrong_amount_drops_the_paragraph(writer, monkeypatch):
    content, _, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=writer)
    assert "estimated shortfall: **RM2,241.50**" in content
    assert "777.77" not in content and "RM999.00" not in content and "RM555.00" not in content


def test_without_a_stated_amount_the_users_number_is_still_not_evidence(monkeypatch):
    payload = {**_change_figure(), "amounts": []}
    content, _, _ = _send(monkeypatch, payload, "why is my shortfall so high? i thought rm1000",
                          writer="It should be RM1,000.")
    assert "RM1,000" not in content


def test_a_paragraph_stating_the_real_shortfall_is_kept(monkeypatch):
    writer = ("The estimated shortfall is RM2,241.50 and it cannot be set directly. Your recorded income of "
              "RM600.00 and projected spending of RM2,841.50 produce it.")
    content, _, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=writer)
    assert writer in content


def test_the_word_estimate_binds_like_estimated(monkeypatch):
    writer = "No, it is calculated, so it cannot be set directly to RM1,000. Your verified estimate is RM2,241.50."
    content, _, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=writer)
    assert writer in content
    wrong = "No, it cannot be set. Your verified estimate is RM999.99."
    content, _, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=wrong)
    assert wrong not in content


@pytest.mark.parametrize("writer", [
    "You have RM2,241.50 left this month.",          # a shortfall is never money left
    "Your estimated savings are RM2,241.50.",        # nor money saved
    "Your shortfall is RM999.99.",                   # nor any other amount
])
def test_the_shortfall_amount_only_counts_as_a_shortfall(writer, monkeypatch):
    content, _, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=writer)
    assert writer not in content


def test_a_show_reading_with_a_stated_amount_still_answers_it(monkeypatch):
    content, _, prompts = _send(monkeypatch, _change_figure(goal="show"), QUESTION, writer=ANSWER)
    assert ANSWER in content
    assert "do not restate them" not in prompts[-1]


def test_a_failed_writer_still_gives_the_verified_figures(monkeypatch):
    content, model, _ = _send(monkeypatch, _change_figure(), QUESTION)
    assert "estimated shortfall: **RM2,241.50**" in content and "Your savings target" not in content
    assert model == "fincoach-verified-read"


# ---- A savings target with no surplus: advice follows the calculated answer ----------------

ADVICE = "Start by pausing your largest non-essential spending this week, then log every expense."
TARGET_QUESTION = "Help me save RM50"


def test_no_surplus_target_keeps_the_calculated_block_and_adds_advice(monkeypatch):
    content, model, _ = _send(monkeypatch, _saved_target(), TARGET_QUESTION, writer=ADVICE)
    assert content.startswith("Your savings target: **RM50**.")
    assert "estimated shortfall: **RM2,241.50**" in content
    assert "no surplus to save this month" in content
    assert content.index("no surplus to save this month") < content.index(ADVICE)
    assert model == "test-writer"


def test_no_surplus_advice_with_a_new_amount_never_removes_the_block(monkeypatch):
    content, _, _ = _send(monkeypatch, _saved_target(), TARGET_QUESTION, writer="Cut RM777.77 from food each week.")
    assert content.startswith("Your savings target: **RM50**.")
    assert "no surplus to save this month" in content and "777.77" not in content


def test_no_surplus_advice_may_name_the_users_own_target(monkeypatch):
    writer = "To reach your RM50 goal, pause non-essential spending first."
    content, model, _ = _send(monkeypatch, _saved_target(), TARGET_QUESTION, writer=writer)
    assert writer in content and model == "test-writer"


def test_no_surplus_with_providers_down_keeps_todays_code_answer(monkeypatch):
    content, model, _ = _send(monkeypatch, _saved_target(), TARGET_QUESTION)
    assert content.startswith("Your savings target: **RM50**.")
    assert "Reducing spending or increasing income would need to come first." in content
    assert model == "fincoach-verified-read"


def test_a_target_with_a_surplus_stays_a_code_answer_with_no_model_call(monkeypatch):
    content, model, prompts = _send(monkeypatch, _saved_target("500"), "Help me save RM500",
                                    savings=SURPLUS, writer="This must not appear.")
    assert "monthly contribution" in content and "This must not appear." not in content
    assert prompts == [] and model == "fincoach-verified-read"
