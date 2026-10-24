"""Semantic-first routing: interpret the whole message, validate, decide, then execute.

On the interpreted path no intent rule may run before or instead of the
interpretation; rules are only the fallback when the interpreter is unavailable.
Interpretations here are stubbed; the live model is checked by the live eval.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import llm
from app.agent_tools import AgentToolExecutor
from app.rag import request_interpretation as intent
from app.rag import routing
from app.rag import service
from test_category_interpretation_contract import StoredClient, stored_rows, USER_ID

TODAY = date(2026, 9, 22)
INTENT_RULES = (
    "required_agent_tool_names", "ambiguous_reminder_title", "is_budget_save_command",
    "is_product_selection_request", "resolve_read_request", "is_allocation_query", "parse_amount",
    "is_gross_income_query", "is_diagnostic_query", "asks_for_current_facts",
    "_is_ambiguous_calculation_request", "is_budget_planning_request",
)


def _rows():
    rows = stored_rows(["Food", "Transport"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Laptop", "target_amount": "2000.00",
                              "current_amount": "500.00", "deadline": "2026-12-31", "created_at": "2026-08-01"}]
    rows["reminders"] = []
    return rows


class Trace:
    def __init__(self):
        self.calls, self.handler, self.prompts, self.messages = [], None, [], []


@pytest.fixture
def trace(monkeypatch):
    """Record the pipeline order and forbid every intent rule on the interpreted path."""
    recorded = Trace()
    real_compile, real_decide, real_read = intent.compile_read, service._decide_reply, AgentToolExecutor.execute_read

    def decide(signals):
        recorded.calls.append("decide")
        recorded.handler = real_decide(signals)
        return recorded.handler

    def execute_read(self, request):
        recorded.calls.append("tool")
        return real_read(self, request)

    monkeypatch.setattr(service, "_decide_reply", decide)
    monkeypatch.setattr(AgentToolExecutor, "execute_read", execute_read)
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", False)
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", False)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    for name in INTENT_RULES:
        monkeypatch.setattr(service, name, lambda *a, _n=name, **k: pytest.fail(f"intent rule {_n} ran"))
    monkeypatch.setattr(routing, "required_agent_tool_names",
                        lambda *a, **k: pytest.fail("write boundary used a text rule"))

    def generate(prompt, **kwargs):
        recorded.prompts.append(prompt)
        raise TimeoutError()
    monkeypatch.setattr(service, "generate_result", generate)
    recorded.real_compile = real_compile
    return recorded


def _interpret(monkeypatch, trace, payload):
    def interpret(question, history, **kwargs):
        trace.calls.append("interpret")
        trace.messages.append(question)
        proposal = intent.IntentProposal.model_validate(payload)
        trace.calls.append("compile")
        resolved = trace.real_compile(proposal, TODAY)
        return intent.InterpretedRequest(proposal, resolved, intent._public_plan(proposal, question), context={
            "version": 1, "anchor_date": TODAY.isoformat(), "proposal": proposal.model_dump()})
    monkeypatch.setattr(service, "interpret_request", interpret)


def _send(text, client=None):
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    client = client or StoredClient(_rows())
    message = service.CoachingService(repository, client).send_message("s", "m", text)["assistant_message"]
    return message, client


def _read(operation, period=None, goal="show", **extra):
    return {"route": "personal_finance", "goal": goal, "read": {
        "operation": operation, "category": {"decision": "none"},
        "period": period or {"kind": "default"}}, **extra}


def test_order_is_interpret_validate_decide_execute(monkeypatch, trace):
    text = "erm how much did i spend in september, and don't remind me of anything"
    _interpret(monkeypatch, trace, _read("get_spending_summary", {"kind": "month", "month": "2026-09"}))
    message, _ = _send(text)
    assert trace.calls == ["interpret", "compile", "decide", "tool"]
    assert trace.messages == [text], "the full original message reaches the interpreter"
    assert trace.handler == "records" and "RM350.00" in message["content"]


def test_outage_runs_rules_only_after_interpretation_failed(monkeypatch):
    order = []
    failed = intent.InterpretedRequest(None, routing.ResolvedReadRequest(routing.CoachingRoute.CASUAL, None, {}),
                                       failure="interpretation_unavailable")
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", lambda *a, **k: order.append("interpret") or failed)
    real_rule = service.required_agent_tool_names
    monkeypatch.setattr(service, "required_agent_tool_names", lambda text: order.append("rule") or real_rule(text))
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: pytest.fail("no model call in an outage"))
    _send("what about that one thing")
    assert order[0] == "interpret" and "rule" in order


def test_remember_question_is_a_goals_read_not_a_reminder(monkeypatch, trace):
    _interpret(monkeypatch, trace, _read("get_savings_goals"))
    message, client = _send("What do you remember about my goals?")
    assert trace.handler == "records"
    assert "Laptop" in message["content"]
    assert "write actions are disabled" not in message["content"]


def test_budget_plan_for_a_stated_amount_is_planning_advice(monkeypatch, trace):
    _interpret(monkeypatch, trace, {"route": "financial_education", "public": {
        "topic": "budget plan", "framework": "allocation", "stated_amount": "1500"}})
    monkeypatch.setattr(service, "generate_result", lambda prompt, **k: trace.prompts.append(prompt) or llm.LLMResult(
        content="**Insight**\nNeeds RM750.00, wants RM450.00, savings RM300.00.\n**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice.", model="m"))
    message, _ = _send("Create a budget plan for RM1500.")
    assert trace.handler == "education"
    assert "needs (50%) = RM750.00" in trace.prompts[0]
    assert not message["content"].startswith("Budget limits aren't saved")


def test_negated_write_with_a_read_only_reads(monkeypatch, trace):
    _interpret(monkeypatch, trace, _read("get_upcoming_reminders"))
    message, client = _send("Do not create a reminder; show my existing reminders.")
    assert trace.handler == "records"
    assert any(q.table_name == "reminders" for q in client.executed)
    assert message["content"].startswith("No enabled reminders")


@pytest.mark.parametrize("text,payload,handler", [
    # A command phrased as a question is still a request to act.
    ("Can you remind me to pay rent tomorrow at 9pm?",
     {"route": "personal_finance", "actions": [{"kind": "create_reminder", "title": "Pay rent"}]}, "write_disabled"),
    # A question about an existing record is a read.
    ("Did I already set a reminder for rent?", _read("get_upcoming_reminders"), "records"),
    # Hypothetical money is education; the user's own allowance is a read.
    ("If I had RM2000 a month, how should I split it?",
     {"route": "financial_education", "public": {"topic": "budget split", "framework": "allocation",
                                                 "stated_amount": "2000"}}, "education"),
    ("How should I plan with my monthly allowance?", _read("get_financial_profile", goal="plan"), "records"),
    # A genuinely unclear message gets one focused question.
    ("how about that one",
     {"route": "personal_finance", "clarification": "Which record do you mean: spending, budget or goals?"},
     "read_clarification"),
    # Two actions in one message keep the existing one-at-a-time reply (writes off: disabled reply).
    ("Remind me to pay rent and generate my report",
     {"route": "personal_finance", "actions": [{"kind": "create_reminder"}, {"kind": "generate_report"}]},
     "write_disabled"),
])
def test_meaning_decides_the_handler(monkeypatch, trace, text, payload, handler):
    _interpret(monkeypatch, trace, payload)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: llm.LLMResult(
        content="**Insight**\nA plan.\n**Educational guidance**\nThis is educational guidance, "
                "not licensed financial advice.", model="m"))
    message, _ = _send(text)
    assert trace.handler == handler
    if handler == "read_clarification":
        assert message["content"] == payload["clarification"]


def test_read_plus_public_question_is_one_combined_answer(monkeypatch, trace):
    _interpret(monkeypatch, trace, {"route": "combined", "goal": "explain",
        "read": {"operation": "get_spending_summary", "category": {"decision": "none"},
                 "period": {"kind": "month", "month": "2026-09"}},
        "public": {"topic": "50/30/20 budgeting rule"}})
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: llm.LLMResult(
        content="**Insight**\nYou spent RM350.00 in September.\n**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice.", model="m"))
    message, _ = _send("How much did I spend in September and what is the 50/30/20 rule?")
    assert trace.handler == "records" and trace.calls[-1] == "tool"
    assert "RM350.00" in message["content"]


def test_two_actions_with_writes_on_get_the_one_at_a_time_reply(monkeypatch, trace):
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", True)
    _interpret(monkeypatch, trace, {"route": "personal_finance",
                                    "actions": [{"kind": "create_reminder"}, {"kind": "generate_report"}]})
    message, _ = _send("Remind me to pay rent and generate my report")
    assert trace.handler == "one_at_a_time"
    assert message["content"].startswith("I found both a reminder and a report request.")


def test_validated_write_is_permitted_without_a_text_rule(monkeypatch, trace):
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", True)
    monkeypatch.setattr(service, "_invalid_explicit_calendar_date", lambda text: None)
    _interpret(monkeypatch, trace, {"route": "personal_finance",
                                    "actions": [{"kind": "create_reminder", "title": "Pay rent"}]})
    seen = {}

    def agent(*args, **kwargs):
        seen["prepare"] = kwargs["tool_executor"]("prepare_reminder", {
            "title": "Pay rent", "due_at": "2026-09-23T21:00:00+08:00", "recurrence": "none"})
        seen["report"] = kwargs["tool_executor"]("prepare_report", {})
        return service.AgentLLMResult(content="Please review the reminder.", model="m",
                                      ui_payload=seen["prepare"].get("ui_payload"))
    monkeypatch.setattr(service, "generate_agent_result", agent)
    message, _ = _send("Please set a reminder so I pay rent tomorrow at 9pm")
    assert trace.handler == "agent"
    assert seen["prepare"]["status"] != "not_allowed"
    assert seen["report"]["status"] == "not_allowed", "only the validated write may be prepared"


def test_implied_task_asks_to_confirm_before_any_write(monkeypatch, trace):
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", True)
    _interpret(monkeypatch, trace, {"route": "personal_finance", "actions": [
        {"kind": "create_reminder", "title": "pay rent", "explicit": False}]})
    message, _ = _send("Pay rent")
    assert trace.handler == "confirm_reminder"
    assert message["ui_payload"]["field"] == "confirm_reminder_intent"
    assert message["ui_payload"]["draft"]["title"] == "Pay rent"


def test_pending_category_question_reaches_the_interpreter_without_custom_names():
    captured = []
    history = [
        {"id": "u1", "role": "user", "content": "how much on foods", "status": "completed"},
        {"id": "a1", "role": "assistant", "status": "completed",
         "content": "I couldn't find that category. Did you mean Food & Dining?",
         "ui_payload": {"intent_context": {"version": 1, "anchor_date": "2026-09-22",
                                           "suggested_categories": ["Food & Dining"],
                                           "proposal": {"route": "casual"}}}},
        {"id": "u2", "role": "user", "content": "yes", "status": "processing"},
    ]
    intent.interpret_request("yes", history, today=TODAY, budget=llm.CoachRequestBudget.start(),
                             current_message_id="u2",
                             generate=lambda prompt, **k: captured.append(prompt) or (_ for _ in ()).throw(TimeoutError()))
    data = captured[0].split("INPUT DATA:\n", 1)[1]
    assert '"pending_question"' in data and '"suggestion_count": 1' in data
    assert "Food & Dining" not in data


def test_lookup_gets_figures_then_one_checked_sentence(monkeypatch, trace):
    _interpret(monkeypatch, trace, _read("get_spending_summary", {"kind": "month", "month": "2026-09"}))
    monkeypatch.setattr(service, "generate_result", lambda prompt, **k: trace.prompts.append(prompt) or llm.LLMResult(
        content="Your spending in September was RM350.00, mostly on transport.", model="m"))
    message, _ = _send("how much did i spend in september")
    assert message["content"].startswith("Recorded expenses from 2026-09-01 to 2026-09-30: RM350.00")
    assert message["content"].endswith("Your spending in September was RM350.00, mostly on transport.")
    assert "In one sentence" in trace.prompts[0]


def test_plan_paragraph_with_a_new_amount_is_dropped(monkeypatch, trace):
    _interpret(monkeypatch, trace, _read("get_budget_status", {"kind": "month", "month": "2026-09"}, goal="plan"))
    monkeypatch.setattr(service, "generate_result", lambda prompt, **k: trace.prompts.append(prompt) or llm.LLMResult(
        content="Spend RM120 a week on food for the rest of the month.", model="m"))
    message, _ = _send("now use my current monthly budget to plan")
    assert "RM120" not in message["content"] and "Monthly limit: RM700.00" in message["content"]
    assert "plan with these figures" in trace.prompts[0]


def test_planning_a_stated_amount_is_normalised_to_allocation():
    import json as _json
    proposal = _json.dumps({"route": "financial_education", "goal": "plan",
                            "public": {"topic": "budget plan", "stated_amount": "1500"}})
    result = intent.interpret_request("Create a budget plan for RM1500.", [], today=TODAY,
                                      budget=llm.CoachRequestBudget.start(),
                                      generate=lambda prompt, **k: k["validate"](proposal))
    assert result.proposal.public.framework == "allocation"


def test_action_labelled_casual_is_normalised_to_the_personal_route():
    proposal = intent.IntentProposal.model_validate({
        "route": "casual", "actions": [{"kind": "create_reminder", "title": "Pay rent", "explicit": False}]})
    assert proposal.route == "personal_finance"


def test_second_attempt_hears_which_consistency_rule_failed():
    try:
        intent.IntentProposal.model_validate({"route": "financial_education", "public": {"topic": "x"},
                                              "actions": [{"kind": "create_reminder"}]})
    except Exception as error:
        fields = [llm._rejected_field(e) for e in error.errors()]
        feedback = llm._interpretation_feedback(error, fields)
    assert "An app action belongs to a personal request" in feedback


@pytest.mark.parametrize("reply", [
    # Exactly the repetition seen in the app on 2026-10-22.
    "You spent a total of RM350.00 across 2 transactions between 2026-09-01 and 2026-09-30.",
    "NONE",
])
def test_lookup_sentence_that_adds_nothing_is_dropped(monkeypatch, trace, reply):
    _interpret(monkeypatch, trace, _read("get_spending_summary", {"kind": "month", "month": "2026-09"}))
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: llm.LLMResult(content=reply, model="m"))
    message, _ = _send("how much did i spend in september")
    assert message["content"] == ("Recorded expenses from 2026-09-01 to 2026-09-30: RM350.00 across "
                                  "2 transaction(s). Highest category: Transport (RM250.00).")


def test_code_written_facts_are_not_rechecked_by_the_end_guard(monkeypatch, trace):
    # Category-recommendation facts carry amounts the cue check cannot bind;
    # they are code-written, so only the advice paragraph is checked.
    _interpret(monkeypatch, trace, _read("get_category_budget_recommendation",
                                         {"kind": "month", "month": "2026-09"}, goal="advise"))
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: llm.LLMResult(
        content="Start with a modest limit and review it after two weeks.", model="m"))
    message, _ = _send("which category should I budget next and how")
    assert "Review the data above" not in message["content"]
    assert message["content"].endswith("Start with a modest limit and review it after two weeks.")
