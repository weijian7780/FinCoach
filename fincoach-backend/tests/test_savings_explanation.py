"""Savings estimate answers (2026-11-10): code does the maths, the writer writes
every sentence, and every money amount is a {{field}} that code fills in.

The six record scenarios are built through the real predict_savings code with
in-memory rows (tests/savings_scenarios.py) and checked against hand-worked
figures. No trial question appears here."""
import ast
import copy
import json
import random
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agent_tools as tools
from app.rag import service
from savings_scenarios import CUSTOM_NAME, predict
from test_kb_nonfinance import _all_providers_down, _records_service

ROOT = Path(__file__).resolve().parents[1]


def _fields(result, **kwargs):
    return {field.name: field for field in service._prediction_fields(result, **kwargs)}


# ---- Step 2: the new fields, against hand-worked rows -----------------------------------

@pytest.mark.parametrize("scenario,expected", [
    ("one_dominant_payment", True),
    ("steady_daily_spending", False),
    ("surplus", False),
    ("budget_based_no_expenses", None),
    ("next_month_prediction", True),
    ("allowance_based_income", True),
])
def test_one_payment_dominates_is_decided_by_code(scenario, expected):
    assert predict(scenario)["one_payment_dominates"] is expected


def test_one_payment_dominates_reaches_the_writer_only_when_spending_is_recorded():
    for scenario in ("one_dominant_payment", "steady_daily_spending", "surplus",
                     "next_month_prediction", "allowance_based_income"):
        field = _fields(predict(scenario))["one_payment_dominates"]
        assert field.value in ("yes", "no") and field.money is False
    assert "one_payment_dominates" not in _fields(predict("budget_based_no_expenses"))


@pytest.mark.parametrize("scenario", ["one_dominant_payment", "steady_daily_spending", "surplus",
                                      "budget_based_no_expenses", "next_month_prediction",
                                      "allowance_based_income"])
def test_estimate_result_is_a_fact_in_every_scenario(scenario):
    result = predict(scenario)
    field = _fields(result)["estimate_result"]
    assert field.money is False
    if service._money_decimal(result["projected_remaining"]) < 0:
        assert field.value.startswith("a shortfall")
    else:
        assert field.value.startswith("no shortfall")


def test_one_dominant_payment():
    result = predict("one_dominant_payment")
    # RM600 income; 800 + 30.25 + 22.20 = 852.45 spent; 852.45 / 9 x 30 = 2,841.50.
    assert (result["recorded_expenses"], result["expense_count"]) == ("RM852.45", 3)
    assert result["balance_so_far"] == "-RM252.45" and result["overspent_so_far"] == "RM252.45"
    assert result["largest_expense"] == {"category": "Entertainment", "amount": "RM800.00"}
    assert result["category_spending"] == [{"name": "Entertainment", "amount": "RM800.00"},
                                           {"name": "Food", "amount": "RM52.45"}]
    assert (result["projected_month_spending"], result["projected_shortfall"]) == ("RM2,841.50", "RM2,241.50")
    fields = _fields(result)
    assert fields["overspent_so_far"].value == "RM252.45" and "left_so_far" not in fields
    assert fields["largest_payment_share"].value == "93%"          # 800 / 852.45, rounded down
    assert fields["entertainment_share"].value == "93%"


def test_steady_daily_spending():
    result = predict("steady_daily_spending")
    # RM20 x 10 days = 200; 200 / 10 x 30 = 600 against RM500 income.
    assert (result["recorded_expenses"], result["projected_month_spending"]) == ("RM200.00", "RM600.00")
    assert (result["balance_so_far"], result["overspent_so_far"]) == ("RM300.00", "RM0.00")
    assert result["largest_expense"] == {"category": "Food", "amount": "RM20.00"}
    assert result["projected_shortfall"] == "RM100.00"
    fields = _fields(result)
    assert fields["left_so_far"].value == "RM300.00" and "overspent_so_far" not in fields
    assert fields["largest_payment_share"].value == "10%"


def test_surplus():
    result = predict("surplus")
    # 95.50 + 54.50 + 90 = 240 over 12 days -> 600 a month; 2,000 - 600 = 1,400.
    assert (result["recorded_expenses"], result["projected_saveable"]) == ("RM240.00", "RM1,400.00")
    assert result["balance_so_far"] == "RM1,760.00"
    assert result["category_spending"][0] == {"name": "Food", "amount": "RM150.00"}
    fields = _fields(result)
    assert fields["estimated_savings"].value == "RM1,400.00" and "estimated_shortfall" not in fields


def test_budget_based_estimate_with_no_expenses():
    result = predict("budget_based_no_expenses")
    assert result["projection_basis"] == "monthly_budget" and result["expense_count"] == 0
    assert (result["income"], result["projected_month_spending"], result["projected_saveable"]) == (
        "RM1,200.00", "RM900.00", "RM300.00")
    assert result["largest_expense"] is None and result["category_spending"] == []
    assert result["balance_so_far"] is None and result["overspent_so_far"] is None
    fields = _fields(result)
    assert "budget" in fields["projected_spending"].meaning and "recorded_spending" not in fields
    assert "daily_spending" not in fields and "left_so_far" not in fields


def test_next_month_prediction():
    result = predict("next_month_prediction")
    # December: allowance RM1,000; November pace 310 / 10 x 31 = 961.
    assert result["month"] == "2026-12-01" and result["income_basis"] == "monthly_allowance"
    assert (result["projected_month_spending"], result["projected_saveable"]) == ("RM961.00", "RM39.00")
    # No "so far" balance: that would mix December income with November spending.
    assert result["balance_so_far"] is None and result["overspent_so_far"] is None
    fields = _fields(result)
    assert "earlier month" in fields["records_note"].value
    assert "left_so_far" not in fields and "overspent_so_far" not in fields


def test_allowance_based_income_and_a_custom_category():
    result = predict("allowance_based_income")
    # Allowance RM800; 100 + 60 = 160 over 5 days -> 960 a month; shortfall 160.
    assert (result["income_basis"], result["income"]) == ("monthly_allowance", "RM800.00")
    assert (result["projected_month_spending"], result["projected_shortfall"]) == ("RM960.00", "RM160.00")
    assert result["category_spending"] == [{"name": "Food", "amount": "RM100.00"},
                                           {"name": "Other categories", "amount": "RM60.00"}]
    assert "allowance" in _fields(result)["income"].meaning


def test_a_custom_category_name_never_leaves_the_tool_or_reaches_the_writer():
    for name in ("allowance_based_income", "one_dominant_payment"):
        result = predict(name)
        assert CUSTOM_NAME.casefold() not in json.dumps(result).casefold()
        prompt = service._prediction_prompt("q", "en", "advise", service._prediction_fields(result))
        assert CUSTOM_NAME.casefold() not in prompt.casefold()


def test_a_custom_category_that_is_the_largest_payment_stays_unnamed():
    executor, _ = __import__("savings_scenarios").allowance_based_income()
    rows = executor.admin_client.table("transactions").rows
    rows.append({"id": "big", "amount": 500, "transaction_date": "2026-11-05", "user_id": "u",
                 "category": {"name": CUSTOM_NAME, "type": "expense"}})
    result = __import__("savings_scenarios")._REAL_PREDICT(executor, {"include_goals": False})
    assert result["largest_expense"] == {"category": "Other categories", "amount": "RM500.00"}
    assert CUSTOM_NAME not in json.dumps(result)
    assert "do not guess its name" in _fields(result)["largest_payment"].meaning


# ---- Gaps between a stated amount and each calculated figure ----------------------------

@pytest.mark.parametrize("seed", range(40))
def test_gap_fields_are_exact_for_random_amounts(seed):
    rng = random.Random(seed)
    result = predict(rng.choice(["one_dominant_payment", "steady_daily_spending", "surplus",
                                 "next_month_prediction", "allowance_based_income"]))
    stated = Decimal(rng.randint(1, 300000)) / 100
    fields = _fields(result, stated=(str(stated),))
    shortfall = service._money_decimal(result["projected_shortfall"])
    projected = service._money_decimal(result["projected_month_spending"])
    remaining = service._money_decimal(result["projected_remaining"])
    money = service._format_money
    assert fields["stated_amount"].value == money(stated)
    if shortfall > stated:
        assert fields["shortfall_minus_stated_amount"].value == money(shortfall - stated)
    elif 0 < shortfall < stated:
        assert fields["stated_amount_minus_shortfall"].value == money(stated - shortfall)
    if projected > stated:
        assert fields["projected_spending_minus_stated_amount"].value == money(projected - stated)
    elif projected < stated:
        assert fields["stated_amount_minus_projected_spending"].value == money(stated - projected)
    if stated > remaining:
        assert fields["needed_to_save_stated_amount"].value == money(stated - remaining)
    else:
        assert fields["left_after_saving_stated_amount"].value == money(remaining - stated)


def test_a_target_and_a_stated_amount_get_their_own_fields():
    fields = _fields(predict("one_dominant_payment"), stated=("50", "900"), target="50")
    assert fields["target"].value == "RM50.00" and fields["stated_amount"].value == "RM900.00"
    assert fields["needed_to_save_target"].value == "RM2,291.50"         # 50 + 2,241.50
    assert fields["shortfall_minus_stated_amount"].value == "RM1,341.50"  # 2,241.50 - 900


# ---- Round 3: every case states its own facts, and every gap names its kind ---------

ROUND3_SCENARIOS = ("one_dominant_payment", "steady_daily_spending", "surplus",
                    "budget_based_no_expenses", "next_month_prediction", "allowance_based_income")


@pytest.mark.parametrize("scenario,start", [
    ("one_dominant_payment", "the shortfall is above the amount"),
    ("steady_daily_spending", "the shortfall is above the amount"),
    ("surplus", "there is no shortfall"),
    ("budget_based_no_expenses", "there is no shortfall"),
    ("next_month_prediction", "there is no shortfall"),
    ("allowance_based_income", "the shortfall is above the amount"),
])
def test_how_the_shortfall_compares_is_stated_in_every_scenario(scenario, start):
    field = _fields(predict(scenario), stated=("90",))["shortfall_compared_with_stated_amount"]
    assert field.value.startswith(start)
    assert field.money is False


@pytest.mark.parametrize("scenario,stated,target", [
    ("one_dominant_payment", "no", "no"),
    ("steady_daily_spending", "no", "no"),
    ("surplus", "yes", "yes"),
    ("budget_based_no_expenses", "yes", "yes"),
    ("next_month_prediction", "no", "no"),
    ("allowance_based_income", "no", "no"),
])
def test_yes_or_no_to_can_i_save_is_decided_by_code(scenario, stated, target):
    result = predict(scenario)
    assert _fields(result, stated=("90",))["can_save_stated_amount_at_this_pace"].value == stated
    assert _fields(result, target="200")["can_save_target_at_this_pace"].value == target


def test_a_target_gets_no_shortfall_or_projected_gap():
    for scenario in ROUND3_SCENARIOS:
        fields = _fields(predict(scenario), target="200")
        assert "shortfall_compared_with_target" not in fields
        assert "projected_spending_minus_target" not in fields


@pytest.mark.parametrize("scenario", ROUND3_SCENARIOS)
def test_every_gap_says_which_kind_of_amount_it_is_for(scenario):
    fields = _fields(predict(scenario), stated=("90",), target="200")
    gaps = [field for name, field in fields.items()
            if "_minus_" in name or name.startswith("needed_to_save_")
            or name.startswith("left_after_saving_")]
    assert gaps
    assert all(field.meaning.startswith("only for when") for field in gaps)


# ---- Placeholder filling --------------------------------------------------------------

FIELDS = service._prediction_fields(predict("one_dominant_payment"), stated=("400",))


def test_a_known_field_is_filled_with_its_verified_value():
    text = service.fill_answer_fields("So far you spent {{recorded_spending}}, {{ overspent_so_far }} over.", FIELDS)
    assert text == "So far you spent RM852.45, RM252.45 over."


def test_a_currency_sign_typed_before_a_placeholder_is_not_doubled():
    assert service.fill_answer_fields("You spent RM{{recorded_spending}}.", FIELDS) == "You spent RM852.45."


def test_the_users_stated_amount_and_its_gap_are_fields():
    text = service.fill_answer_fields("To reach {{stated_amount}}, cut {{shortfall_minus_stated_amount}}.", FIELDS)
    assert text == "To reach RM400.00, cut RM1,841.50."


@pytest.mark.parametrize("text", [
    "You have {{bank_balance}}.",               # unknown field
    "You spent RM852.45.",                      # a typed amount, even a correct one
    "You spent 852.45 so far.",                 # typed, no currency sign
    "That is about 800 more than income.",      # a bare typed number
    "Cut RM50 a week.",                         # a typed amount with a currency sign
    "Save {stated_amount} now.",                # a broken placeholder
    "Follow 50/30/20.",                         # numbers that are not listed values
])
def test_unknown_fields_and_typed_numbers_are_rejected(text):
    assert service.fill_answer_fields(text, FIELDS) is None


def test_listed_non_money_values_and_list_numbers_may_be_typed():
    text = ("In the 9 days from 1 to 9 November 2026 you made 3 payments; one was 93% of it.\n"
            "1. Pause one treat.\n2) Log every payment.")
    assert service.fill_answer_fields(text, FIELDS) == text


def test_a_typed_day_count_still_has_to_be_true_after_filling(monkeypatch):
    content, model, _ = _turn(monkeypatch, "one_dominant_payment", "In {{days_recorded}} days you spent "
                              "{{recorded_spending}}, which is 15 days of pace.")
    assert model == "fincoach-verified-read"                               # 15 is not a listed value


# ---- Whole turns --------------------------------------------------------------------------

def _payload(goal="explain", amounts=(), language="en"):
    return {"route": "personal_finance", "relation": "new", "goal": goal, "response_language": language,
            "read": {"operation": "predict_savings", "category": {"decision": "none"}},
            "amounts": [{"amount": amount, "role": "context"} for amount in amounts]}


def _turn(monkeypatch, scenario, writer, *, payload=None, question="(question)"):
    _all_providers_down(monkeypatch)
    prompts = []
    if writer is not None:
        def generate(prompt, **_kwargs):
            prompts.append(prompt)
            return SimpleNamespace(content=writer, model="test-writer", prompt_tokens=1, completion_tokens=1,
                                   finish_reason="stop")
        monkeypatch.setattr(service, "generate_result", generate)
    result = predict(scenario)
    svc = _records_service(monkeypatch, copy.deepcopy(payload or _payload()), question)
    monkeypatch.setattr(tools.AgentToolExecutor, "_predict_savings", lambda self, raw: copy.deepcopy(result))
    message = svc.send_message("s", "m", question)["assistant_message"]
    return message["content"], message.get("model"), prompts


# ---- Step 4: one retry when the writer's text is rejected -------------------------------

def _turn_replies(monkeypatch, scenario, replies, *, payload=None, question="(question)"):
    """A whole turn where the writer gives each reply in turn (an Exception raises)."""
    _all_providers_down(monkeypatch)
    prompts = []

    def generate(prompt, **_kwargs):
        prompts.append(prompt)
        reply = replies[len(prompts) - 1]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply, model="test-writer", prompt_tokens=1, completion_tokens=1,
                               finish_reason="stop")

    monkeypatch.setattr(service, "generate_result", generate)
    result = predict(scenario)
    svc = _records_service(monkeypatch, copy.deepcopy(payload or _payload()), question)
    monkeypatch.setattr(tools.AgentToolExecutor, "_predict_savings", lambda self, raw: copy.deepcopy(result))
    message = svc.send_message("s", "m", question)["assistant_message"]
    return message["content"], message.get("model"), prompts


TYPED_AMOUNT = "You spent RM852.45 so far."
UNKNOWN_FIELD = "Your income is {{bank_balance}}."


def test_a_rejected_reply_is_written_once_more_and_the_second_reply_is_shown(monkeypatch):
    content, model, prompts = _turn_replies(
        monkeypatch, "steady_daily_spending", [TYPED_AMOUNT, "Words from the writer."])
    working = service._prediction_working(predict("steady_daily_spending"), "en")
    assert content == f"Words from the writer.\n\n{working}" and model == "test-writer"
    assert len(prompts) == 2


def test_two_rejected_replies_give_the_code_figures_and_never_a_third_call(monkeypatch):
    content, model, prompts = _turn_replies(
        monkeypatch, "steady_daily_spending", [TYPED_AMOUNT, UNKNOWN_FIELD])
    assert content == service._format_fast_verified_read("predict_savings", predict("steady_daily_spending"))
    assert model == "fincoach-verified-read" and len(prompts) == 2


def test_a_good_first_reply_is_written_only_once(monkeypatch):
    content, model, prompts = _turn_replies(
        monkeypatch, "steady_daily_spending", ["Words from the writer."])
    working = service._prediction_working(predict("steady_daily_spending"), "en")
    assert content == f"Words from the writer.\n\n{working}" and model == "test-writer"
    assert len(prompts) == 1


def test_a_writer_error_is_not_retried(monkeypatch):
    content, model, prompts = _turn_replies(
        monkeypatch, "steady_daily_spending", [RuntimeError("writer down")])
    assert content == service._format_fast_verified_read("predict_savings", predict("steady_daily_spending"))
    assert model == "fincoach-verified-read" and len(prompts) == 1


def test_the_retry_prompt_carries_the_first_reply_and_the_retry_instruction(monkeypatch):
    _, _, prompts = _turn_replies(
        monkeypatch, "steady_daily_spending", [TYPED_AMOUNT, "Words from the writer."])
    assert len(prompts) == 2
    assert TYPED_AMOUNT in prompts[1] and service._PREDICTION_RETRY in prompts[1]
    assert service._PREDICTION_RETRY not in prompts[0]


@pytest.mark.parametrize("scenario", ["one_dominant_payment", "steady_daily_spending", "surplus",
                                      "budget_based_no_expenses", "next_month_prediction",
                                      "allowance_based_income"])
def test_providers_down_still_give_the_code_written_figures(scenario, monkeypatch):
    content, model, _ = _turn(monkeypatch, scenario, None)
    assert content == service._format_fast_verified_read("predict_savings", predict(scenario))
    assert model == "fincoach-verified-read"


@pytest.mark.parametrize("language", ["en", "ms", "zh", "ta", "ja"])
def test_the_working_is_two_lines_at_the_end_in_each_scenario(language, monkeypatch):
    for scenario in ("one_dominant_payment", "budget_based_no_expenses", "next_month_prediction"):
        content, model, prompts = _turn(monkeypatch, scenario, "Words from the writer.",
                                        payload=_payload(language=language))
        working = service._prediction_working(predict(scenario), language)
        assert content == f"Words from the writer.\n\n{working}" and len(working.splitlines()) == 2
        assert model == "test-writer" and len(prompts) == 1
        if scenario == "budget_based_no_expenses":
            assert "pace" not in working and "RM0.00 over" not in working


def test_the_writer_input_is_the_question_the_language_and_the_fields(monkeypatch):
    _, _, prompts = _turn(monkeypatch, "one_dominant_payment", "Fine.", payload=_payload(language="ms"),
                          question="(the user's own words)")
    prompt = prompts[0]
    assert "Reply language: ms." in prompt and "(the user's own words)" in prompt
    for field in service._prediction_fields(predict("one_dominant_payment")):
        assert f"- {field.name}: {field.meaning} = {field.value}" in prompt


def test_advice_keeps_its_section_headings_and_the_working_stays_in_insight(monkeypatch):
    writer = ("**Insight**\nMost of it is one {{largest_payment}} payment.\n\n**Recommended action**\n"
              "Cut back on Entertainment first.\n\n**Educational guidance**\nThis is educational guidance, "
              "not licensed financial advice.")
    content, _, prompts = _turn(monkeypatch, "one_dominant_payment", writer, payload=_payload(goal="advise"))
    assert "**Insight**" in prompts[0] and "**Recommended action**" in prompts[0]
    working = service._prediction_working(predict("one_dominant_payment"), "en")
    assert content.index("RM800.00 payment") < content.index(working) < content.index("**Recommended action**")


def test_model_text_checks_still_run_on_the_writer_part_only(monkeypatch):
    # An app-action claim in the writer's text is replaced by the code figures.
    content, model, _ = _turn(monkeypatch, "steady_daily_spending", "I have created a reminder for you.")
    assert model == "fincoach-verified-read" and "reminder" not in content
    text = service._model_written_text(SimpleNamespace(content="A.\n\nWORK"), "model_with_code", "facts", "WORK")
    assert text == "A.\n\n"


# ---- No hard-coding --------------------------------------------------------------------

def _trial_questions():
    path = ROOT / "experiment" / "trial_questions.json"
    if not path.exists():
        pytest.skip("trial file lives only in the stage folder")
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [row for key, value in data.items() if key.startswith("reading") for row in value]
    return [row["question"] for row in rows] + data["answers"] + data.get("answers_heldout", []) + data.get("answers_heldout_r3", [])


def test_no_trial_question_appears_in_the_app_or_the_tests():
    def norm(text):
        return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())
    questions = [norm(question) for question in _trial_questions()]
    files = [*(ROOT / "app").rglob("*.py"), *(ROOT / "tests").rglob("*.py"), *(ROOT / "tests").rglob("*.json")]
    for path in files:
        text = norm(path.read_text(encoding="utf-8", errors="ignore"))
        for question in questions:
            assert question not in text, f"trial question found in {path.name}"


def _module_strings():
    """Every string constant written in service.py (fixed text candidates)."""
    tree = ast.parse((ROOT / "app" / "rag" / "service.py").read_text(encoding="utf-8"))
    return {node.value.strip() for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value.strip()) > 12}


@pytest.mark.parametrize("payload", [_payload(), _payload(goal="advise", amounts=("300",)), _payload(language="zh")])
def test_the_opening_is_the_writers_own_and_not_a_constant(payload, monkeypatch):
    openings = []
    for writer in ("Your records so far tell a clear story.", "Short answer: not yet, and here is why."):
        content, _, _ = _turn(monkeypatch, "one_dominant_payment", writer, payload=payload)
        openings.append(content.split("\n")[0])
    assert openings == ["Your records so far tell a clear story.", "Short answer: not yet, and here is why."]
    constants = _module_strings()
    assert not any(opening.startswith(constant) or constant.startswith(opening)
                   for opening in openings for constant in constants)


def test_the_fixed_no_surplus_sentence_is_gone():
    assert not hasattr(service, "_TARGET_NO_SURPLUS_LINES")


def test_the_fields_do_not_depend_on_the_question():
    import inspect
    assert "question" not in inspect.signature(service._prediction_fields).parameters


def test_the_writer_prompt_changes_only_by_the_question_text():
    fields = service._prediction_fields(predict("steady_daily_spending"), stated=("90",))
    first = service._prediction_prompt("first question text", "en", "explain", fields)
    second = service._prediction_prompt("a completely different message", "en", "explain", fields)
    assert first.replace("first question text", "") == second.replace("a completely different message", "")
