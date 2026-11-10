"""A figure FinCoach calculates is a result, not a setting, and a savings target
with no surplus still gets advice. Typed fields only; the shapes come from a
real conversation (2026-11-09) with the amounts varied. Since 2026-11-10 the
writer names every amount as a {{field}} and code fills it in (the fields
themselves are tested in test_savings_explanation.py)."""
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

ANSWER = ("No, the estimated shortfall is worked out from your income and spending, so it can't be set to "
          "{{stated_amount}} directly. To bring it down to {{stated_amount}}, the month's spending would need "
          "to be {{shortfall_minus_stated_amount}} lower, or your income that much higher.")
QUESTION = "can i change estimated shortfall to rm1000?"
WORKING = "Calculation: RM600.00 - RM2,841.50 = **-RM2,241.50**"


def test_the_answer_explains_the_figure_and_is_not_a_savings_target(monkeypatch):
    content, model, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=ANSWER)
    assert content.startswith("No, the estimated shortfall is worked out")
    assert "can't be set to RM1,000.00 directly" in content and "RM1,241.50 lower" in content
    assert "Your savings target" not in content and "{{" not in content
    assert content.rstrip().splitlines()[-2] == WORKING      # the code-written working comes last
    assert model == "test-writer"


def test_the_writer_is_told_the_amount_is_the_users_not_a_record(monkeypatch):
    _, _, prompts = _send(monkeypatch, _change_figure(), QUESTION, writer=ANSWER)
    assert len(prompts) == 1                                 # one writer call, no extra call
    assert ("stated_amount: an amount the user wrote in this message (their own words, not a record) "
            "= RM1,000.00") in prompts[0]
    assert "shortfall_minus_stated_amount:" in prompts[0] and "= RM1,241.50" in prompts[0]


@pytest.mark.parametrize("seed", range(25))
def test_any_stated_amount_gets_its_exact_gap_from_code(seed, monkeypatch):
    stated = random.Random(seed).randint(1, 2241)
    writer = "It is calculated, so it cannot be set to {{stated_amount}}; the gap is {{shortfall_minus_stated_amount}}."
    content, _, _ = _send(monkeypatch, _change_figure(str(stated)), QUESTION, writer=writer)
    assert f"cannot be set to RM{stated:,.2f}; the gap is RM{2241.50 - stated:,.2f}." in content


@pytest.mark.parametrize("writer", [
    "It cannot be set. Cut RM777.77 from food.",                       # a typed amount
    "It cannot be set; the gap is 1,241.50.",                          # typed, no currency sign
    "It cannot be set. Spend 300 less on food.",                       # a bare typed number
    "Your income is {{bank_balance}}.",                                # a field that does not exist
    "It cannot be set to {stated_amount}.",                            # a broken placeholder
])
def test_any_typed_amount_or_unknown_field_gives_the_code_figures(writer, monkeypatch):
    content, model, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=writer)
    assert "estimated shortfall: **RM2,241.50**" in content and model == "fincoach-verified-read"
    assert "777.77" not in content and "bank_balance" not in content and "Spend 300" not in content


def test_without_a_stated_amount_there_is_no_stated_field(monkeypatch):
    payload = {**_change_figure(), "amounts": []}
    content, model, _ = _send(monkeypatch, payload, "why is my shortfall so high? i thought rm1000",
                              writer="It should be {{stated_amount}}.")
    assert "RM1,000" not in content and model == "fincoach-verified-read"


def test_the_real_shortfall_named_by_field_is_kept(monkeypatch):
    writer = ("The estimated shortfall is {{estimated_shortfall}}: your income of {{income}} against projected "
              "spending of {{projected_spending}}.")
    content, _, _ = _send(monkeypatch, _change_figure(), QUESTION, writer=writer)
    assert ("The estimated shortfall is RM2,241.50: your income of RM600.00 against projected spending of "
            "RM2,841.50.") in content


def test_a_show_reading_with_a_stated_amount_still_answers_it(monkeypatch):
    content, _, prompts = _send(monkeypatch, _change_figure(goal="show"), QUESTION, writer=ANSWER)
    assert content.startswith("No, the estimated shortfall")
    assert "do not restate them" not in prompts[-1]


def test_a_failed_writer_still_gives_the_verified_figures(monkeypatch):
    content, model, _ = _send(monkeypatch, _change_figure(), QUESTION)
    assert "estimated shortfall: **RM2,241.50**" in content and "Your savings target" not in content
    assert model == "fincoach-verified-read"


# ---- A savings target with no surplus: the writer answers it ----------------------------

ADVICE = ("**Insight**\nYour spending is already above your income, so saving {{target}} first needs "
          "{{needed_to_save_target}} less spending this month at this pace.\n\n**Recommended action**\n"
          "Pause your largest non-essential spending this week, then log every expense.\n\n"
          "**Educational guidance**\nThis is educational guidance, not licensed financial advice.")
TARGET_QUESTION = "Help me save RM50"


def test_no_surplus_target_is_answered_by_the_writer_with_the_working_in_insight(monkeypatch):
    content, model, prompts = _send(monkeypatch, _saved_target(), TARGET_QUESTION, writer=ADVICE)
    assert content.startswith("**Insight**\nYour spending is already above your income, so saving RM50.00")
    assert "RM2,291.50 less spending" in content                   # 50 + 2,241.50, worked out by code
    assert content.index(WORKING) < content.index("**Recommended action**")
    assert content.rstrip().endswith("not licensed financial advice.")
    assert "Your savings target" not in content and "no surplus" not in content
    assert model == "test-writer" and len(prompts) == 1


def test_no_surplus_advice_with_a_typed_amount_gives_the_target_and_figures(monkeypatch):
    content, model, _ = _send(monkeypatch, _saved_target(), TARGET_QUESTION,
                              writer="Cut RM777.77 from food each week.")
    assert content.startswith("Your savings target: **RM50**.")
    assert "estimated shortfall: **RM2,241.50**" in content and "777.77" not in content
    assert model == "fincoach-verified-read"


def test_no_surplus_with_providers_down_shows_the_target_and_figures_only(monkeypatch):
    content, model, _ = _send(monkeypatch, _saved_target(), TARGET_QUESTION)
    facts = service._format_fast_verified_read("predict_savings", SHORTFALL)
    assert content == f"Your savings target: **RM50**.\n\n{facts}"
    assert model == "fincoach-verified-read"


def test_a_target_with_a_surplus_stays_a_code_answer_with_no_model_call(monkeypatch):
    content, model, prompts = _send(monkeypatch, _saved_target("500"), "Help me save RM500",
                                    savings=SURPLUS, writer="This must not appear.")
    assert "monthly contribution" in content and "This must not appear." not in content
    assert prompts == [] and model == "fincoach-verified-read"
