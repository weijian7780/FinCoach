"""Semantic execution tests use actual tools and independently seeded records."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import llm
from app.rag import request_interpretation as intent
from app.rag import service
from test_category_interpretation_contract import StoredClient, stored_rows, USER_ID


def proposal(category=None, operation="get_spending_summary", **fields):
    return intent.IntentProposal.model_validate({
        "route": "personal_finance", "read": {"operation": operation,
        "category": {"decision": "named", "name": category} if category else {"decision": "none"},
        "period": {"kind": "month", "month": "2026-09"}, **fields}})


@pytest.mark.parametrize("category,total", [(None,350),("Food",100),("Transport",250)])
def test_actual_tool_totals_without_second_guess(category,total):
    from app.agent_tools import AgentToolExecutor
    client = StoredClient(stored_rows(["Food", "Transport"]))
    executor = AgentToolExecutor(client,user_id=USER_ID,session_id="s",request_text="erm erm this month what i have spend")
    result = executor.execute_read(intent.compile_read(proposal(category),date(2026,9,22)))
    assert result["status"] == "ok"
    assert result["expense_total"] == f"RM{total:.2f}"
    assert all(("eq","user_id",USER_ID) in q.filters for q in client.executed if q.table_name == "transactions")


@pytest.mark.parametrize("category", ["Secret","Unknown"])
def test_unknown_category_never_broadens(category):
    from app.agent_tools import AgentToolExecutor
    client=StoredClient(stored_rows(["Food","Transport"]))
    result=AgentToolExecutor(client,user_id=USER_ID,session_id="s").execute_read(intent.compile_read(proposal(category),date(2026,9,22)))
    assert result["status"] != "ok"
    assert not any(q.table_name=="transactions" for q in client.executed)


def test_denied_consent_remains_denied():
    from app.agent_tools import AgentToolExecutor
    client=StoredClient(stored_rows(["Food"],consent="denied"))
    result=AgentToolExecutor(client,user_id=USER_ID,session_id="s").execute_read(intent.compile_read(proposal(),date(2026,9,22)))
    assert result["status"] == "permission_required"
    assert not any(q.table_name=="transactions" for q in client.executed)


@pytest.mark.parametrize("period", [{"kind":"range","start":"2026-09-30","end":"2026-09-01"}, {"kind":"this_month","month":"2025-01"}, {"kind":"month","month":"2026-13"}])
def test_invalid_period_cannot_silently_default(period):
    with pytest.raises(ValueError):
        intent.compile_read(proposal(period=period),date(2026,9,22))


@pytest.mark.parametrize("bad", ["length","invalid","transport"])
def test_primary_failure_gets_exactly_one_fallback(monkeypatch,bad):
    monkeypatch.setattr(llm,"_providers",lambda:[SimpleNamespace(role="primary"),SimpleNamespace(role="fallback")])
    calls=[]
    def generate(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1:
            if bad=="transport": raise TimeoutError()
            return SimpleNamespace(content="invalid" if bad=="invalid" else "{}",finish_reason="length" if bad=="length" else "stop")
        return SimpleNamespace(content='{"ok":true}',finish_reason="stop")
    monkeypatch.setattr(llm,"_generate_with_provider",generate)
    result=llm.generate_validated_interpretation("x",response_schema={},validate=json.loads,budget=llm.CoachRequestBudget.start())
    assert result=={"ok":True}
    assert len(calls)==2 and all(0<x["timeout_seconds"]<=15 for x in calls)


def test_service_original_query_and_explanation_failure(monkeypatch):
    p=proposal()
    semantic=intent.InterpretedRequest(p,intent.compile_read(p,date(2026,9,22)),context={"version":1,"proposal":p.model_dump()})
    monkeypatch.setattr(service,"COACH_LLM_INTERPRETATION_ENABLED",True)
    monkeypatch.setattr(service,"interpret_request",lambda *a,**k:semantic)
    monkeypatch.setattr(service,"resolve_read_request",lambda *a,**k:pytest.fail("Legacy parser ran"))
    monkeypatch.setattr(service,"interpret_question",lambda *a,**k:pytest.fail("Second interpreter ran"))
    monkeypatch.setattr(service,"generate_result",lambda *a,**k:(_ for _ in ()).throw(TimeoutError()))
    repository=MagicMock(user_id=USER_ID)
    repository.require_session.return_value={"id":"session","title":"Existing"}
    repository.find_user_message.return_value=None
    repository.insert_user_message.return_value={"id":"message"}
    repository.list_messages.return_value=[]
    repository.complete_turn.side_effect=lambda **kw:kw["assistant_payload"]
    client=StoredClient(stored_rows(["Food","Transport"]))
    result=service.CoachingService(repository,client).send_message("session","message","erm this month what i have spend")
    assert "350" in str(result)
    assert "category was not found" not in str(result)
    assert "intent_context" in str(result)


def test_followup_context_keeps_category_and_merchant():
    previous=proposal("Food",operation="search_transactions",merchant="Tesco",amount="20")
    captured=[]
    def generate(prompt,**kwargs):
        captured.append(prompt)
        next_proposal=previous.model_dump()
        next_proposal["relation"]="follow_up"
        next_proposal["read"]["period"]={"kind":"last_month"}
        return kwargs["validate"](json.dumps(next_proposal))
    history=[{"role":"assistant","ui_payload":{"intent_context":{"version":1,"proposal":previous.model_dump()}}}]
    result=intent.interpret_request("and last month?",history,today=date(2026,10,17),budget=llm.CoachRequestBudget.start(),generate=generate)
    assert result.resolved.arguments=={"category_name":"Food","start_date":"2026-09-01","end_date":"2026-09-30","result_mode":"list","limit":20,"text":"Tesco","amount":"20"}
    assert "accepted_context" in captured[0]


def _interpreter_outage(monkeypatch, text):
    """The interpreter fails; no model, retrieval or web call may follow."""
    monkeypatch.setattr(service,"COACH_LLM_INTERPRETATION_ENABLED",True)
    result=intent.interpret_request(text,[],today=date(2026,10,17),budget=llm.CoachRequestBudget.start(),generate=lambda *a,**k:(_ for _ in ()).throw(TimeoutError()))
    assert result.failure=="interpretation_unavailable"
    monkeypatch.setattr(service,"interpret_request",lambda *a,**k:result)
    for name in ("generate_result","generate_agent_result","generate_fallback_result","generate_structured_result",
                 "interpret_question","retrieve","research_web","run_research_policy"):
        monkeypatch.setattr(service,name,lambda *a,**k:pytest.fail("Unexpected model, retrieval or web call"))


def test_failed_interpretation_does_not_read_or_generate(monkeypatch):
    _interpreter_outage(monkeypatch,"what about that one thing")
    repo=MagicMock(user_id=USER_ID)
    repo.require_session.return_value={"id":"s","title":"Existing"}
    repo.find_user_message.return_value=None
    repo.insert_user_message.return_value={"id":"m"}
    repo.list_messages.return_value=[]
    repo.complete_turn.side_effect=lambda **kw:kw["assistant_payload"]
    client=StoredClient(stored_rows(["Food"]))
    response=service.CoachingService(repo,client).send_message("s","m","what about that one thing")
    assert "Please try again" in str(response)
    # Only the shared category list (app constants for the interpreter) may be read.
    assert {q.table_name for q in client.executed} <= {"categories"}


@pytest.fixture
def frozen_september():
    from datetime import datetime, timezone
    from unittest.mock import patch
    now=datetime(2026,9,22,10,tzinfo=timezone.utc)

    class FixtureClock(type):
        def __instancecheck__(cls,value):
            return isinstance(value,datetime)

    class FixtureDatetime(datetime,metaclass=FixtureClock):
        @classmethod
        def now(cls,tz=None):
            return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)
    with (patch("app.rag.routing.datetime",FixtureDatetime),patch("app.rag.service.datetime",FixtureDatetime),
          patch("app.agent_tools.datetime",FixtureDatetime)):
        yield


@pytest.mark.parametrize("text,expected",[
    ("how much did I spend on Food in September 2026","RM100.00"),
    ("How much did I spend this month?","RM350.00"),
    ("erm spend","RM350.00"),
])
def test_interpreter_outage_answers_clear_reads_from_rules(monkeypatch,frozen_september,text,expected):
    _interpreter_outage(monkeypatch,text)
    message=_send(text)
    assert expected in message["content"] and message["model"]=="fincoach-verified-read"


@pytest.mark.parametrize("writes,expected",[
    (True,"I can't prepare that reminder or report right now."),
    (False,"AI write actions are disabled. No reminder was created."),
])
def test_interpreter_outage_never_turns_a_reminder_request_into_a_lookup(monkeypatch,writes,expected):
    _interpreter_outage(monkeypatch,"Remind me to pay rent on Friday")
    monkeypatch.setattr(service,"COACH_WRITE_ACTIONS_ENABLED",writes)
    client=StoredClient(stored_rows(["Food"]))
    message=_send("Remind me to pay rent on Friday",client=client)
    assert message["content"].startswith(expected)
    assert not any(q.table_name=="reminders" for q in client.executed)


def test_duplicate_category_never_selects_arbitrary_records():
    from app.agent_tools import AgentToolExecutor
    rows=stored_rows(["Food"])
    rows["categories"].append({"id":888,"name":"Food","user_id":USER_ID})
    client=StoredClient(rows)
    result=AgentToolExecutor(client,user_id=USER_ID,session_id="s").execute_read(intent.compile_read(proposal("Food"),date(2026,9,22)))
    assert result["status"] != "ok"
    assert not any(q.table_name=="transactions" for q in client.executed)


@pytest.mark.parametrize("operation", list(intent.Operation.__args__))
def test_all_read_operations_compile_and_execute(operation):
    from app.agent_tools import AgentToolExecutor
    from datetime import datetime, timezone
    fields={}
    if operation=="get_period_comparison":
        fields["period"]={"kind":"months","months":["2026-08","2026-09"]}
    elif operation in ("get_financial_profile","get_savings_goals","get_cashflow_forecast"):
        fields["period"]={"kind":"default"}
    request=intent.compile_read(proposal(operation=operation,**fields),date(2026,9,22))
    client=StoredClient(stored_rows(["Food","Transport"]))
    result=AgentToolExecutor(client,user_id=USER_ID,session_id="s",now=lambda:datetime(2026,9,22,tzinfo=timezone.utc)).execute_read(request)
    assert result["status"]=="ok", result


def test_unclear_private_category_blocks_even_with_partial_public_question():
    p=intent.IntentProposal.model_validate({"route":"combined",
        "read":{"operation":"get_spending_summary","category":{"decision":"unclear"}},
        "public":{"topic":"ICU JPM","required_facts":["duties","application"],"clarification_facts":["application"]},
        "clarification":"Which category and programme do you mean?"})
    assert intent.compile_read(p,date(2026,10,17)).readiness.value=="needs_clarification"


def _send(text, *, semantic=None, client=None, history=None):
    """Drive one coach turn end to end with real tools over stored rows."""
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = list(history or [])
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    client = client or StoredClient(stored_rows(["Food", "Transport"]))
    return service.CoachingService(repository, client).send_message("s", "m", text)["assistant_message"]


def _interpreted(monkeypatch, payload):
    p = intent.IntentProposal.model_validate(payload)
    semantic = intent.InterpretedRequest(p, intent.compile_read(p, date(2026, 10, 22)), intent._public_plan(p, "q"),
                                         context={"version": 1, "anchor_date": "2026-10-22", "proposal": p.model_dump()})
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", lambda *a, **k: semantic)
    return semantic


COMPARISON = {"route": "personal_finance", "read": {"operation": "get_period_comparison",
              "category": {"decision": "none"}, "period": {"kind": "months", "months": ["2026-08", "2026-09"]}}}


def test_comparison_percentage_survives_numeric_guard_on_interpreter_path(monkeypatch):
    _interpreted(monkeypatch, COMPARISON)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    message = _send("compare my spending august vs september")
    assert "RM150.00 more · 75% increase" in message["content"]
    assert message["model"] != "fincoach-grounding-policy"


def test_comparison_percentage_in_explanation_is_verified(monkeypatch):
    _interpreted(monkeypatch, COMPARISON)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: SimpleNamespace(
        content="Your spending rose by RM150.00, a 75% increase, from August to September.",
        model="m", finish_reason="stop"))
    message = _send("compare my spending august vs september")
    assert message["content"].startswith("**Spending comparison")
    assert message["content"].endswith("Your spending rose by RM150.00, a 75% increase, from August to September.")


def test_comparison_percentage_survives_on_rule_router_fast_path(monkeypatch):
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", False)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", False)
    message = _send("Compare my spending in August 2026 and September 2026")
    assert "75% increase" in message["content"]


def test_bare_definition_gets_the_stable_identity_plan():
    from app.rag.research_policy import _DEFINITIONAL_FACTS
    p = intent.IntentProposal.model_validate({"route": "financial_education", "public": {
        "topic": "PTPTN", "time_scope": "current", "required_facts": ["eligibility", "how to apply"]}})
    plan = intent._public_plan(p, "What is PTPTN?")
    assert plan.definitional and plan.time_scope == "stable"
    assert plan.required_facts == _DEFINITIONAL_FACTS and not plan.explicit_search
    procedural = intent._public_plan(p, "How do I apply for PTPTN?")
    assert not procedural.definitional and procedural.required_facts == ("eligibility", "how to apply")


SEPTEMBER_SPENDING = {"route": "personal_finance", "read": {"operation": "get_spending_summary",
                      "category": {"decision": "none"}, "period": {"kind": "month", "month": "2026-09"}}}


def _explanation(text):
    return lambda *a, **k: SimpleNamespace(content=text, model="m", finish_reason="stop")


@pytest.mark.parametrize("explanation", [
    "You have 2 transactions recorded in September, and your spending is RM350.00.",
    "Your spending in September is RM350.00. Use the Maybank app to track it.",
])
def test_unsafe_model_explanation_falls_back_to_verified_figures(monkeypatch, explanation):
    _interpreted(monkeypatch, SEPTEMBER_SPENDING)
    monkeypatch.setattr(service, "generate_result", _explanation(explanation))
    message = _send("how much did i spend in september")
    assert message["content"].startswith("Recorded expenses from 2026-09-01 to 2026-09-30: RM350.00")
    assert message["model"] == "fincoach-verified-read"


def test_interpreter_authored_clarification_is_scanned(monkeypatch):
    _interpreted(monkeypatch, {"route": "personal_finance", "read": {
        "operation": "get_spending_summary", "category": {"decision": "unclear"}},
        "clarification": "Open a savings account with maybank first - which category do you mean?"})
    message = _send("how much did i spend on that")
    assert "maybank" not in message["content"].lower()
    assert "does not recommend or rank" in message["content"]


def test_code_written_text_is_never_scanned(monkeypatch):
    assert service._model_written_text(SimpleNamespace(content="Done - budget updated."), "code", None) == ""
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", False)
    monkeypatch.setattr(service, "_format_fast_verified_read", lambda *a, **k: "Your budget has been updated.")
    message = _send("Show my budget status")
    assert message["content"] == "Your budget has been updated."


ADVICE_QUESTION = "How can I reduce my Food spending in September 2026?"


@pytest.mark.parametrize("generate", [
    lambda *a, **k: (_ for _ in ()).throw(TimeoutError()),
    lambda *a, **k: SimpleNamespace(content="Cook at home more", model="m", finish_reason="length",
                                    prompt_tokens=None, completion_tokens=None),
    lambda *a, **k: SimpleNamespace(content="Done - budget updated. Cook at home more.", model="m",
                                    finish_reason="stop", prompt_tokens=None, completion_tokens=None),
    lambda *a, **k: SimpleNamespace(content="I can set a reminder for your next grocery trip.", model="m",
                                    finish_reason="stop", prompt_tokens=None, completion_tokens=None),
])
def test_two_phase_advice_keeps_verified_figures(monkeypatch, generate):
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", False)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", False)
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", False)
    monkeypatch.setattr(service, "generate_result", generate)
    message = _send(ADVICE_QUESTION)
    assert message["content"].startswith("Recorded expenses from 2026-09-01 to 2026-09-30: RM100.00")
    assert "budget updated" not in message["content"] and "reminder" not in message["content"]


def test_two_phase_advice_ships_safe_advice_with_figures(monkeypatch):
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", False)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", False)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: SimpleNamespace(
        content="Plan meals for the week and cook at home more often.", model="m", finish_reason="stop",
        prompt_tokens=None, completion_tokens=None))
    message = _send(ADVICE_QUESTION)
    assert "RM100.00" in message["content"] and message["content"].endswith("cook at home more often.")


def test_overview_reports_denied_spending_instead_of_zero(monkeypatch):
    _interpreted(monkeypatch, {"route": "personal_finance", "read": {"operation": "get_financial_overview",
                 "category": {"decision": "none"}, "period": {"kind": "month", "month": "2026-09"}}})
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    client = StoredClient(stored_rows(["Food", "Transport"], consent="denied"))
    content = _send("how am i doing overall in september", client=client)["content"]
    assert "Spending records were not read because spending access is not granted." in content
    assert "Recorded expenses" not in content and "RM0.00" not in content
    assert "Monthly limit: RM700.00" in content


def test_overview_lists_each_verified_section(monkeypatch):
    _interpreted(monkeypatch, {"route": "personal_finance", "read": {"operation": "get_financial_overview",
                 "category": {"decision": "none"}, "period": {"kind": "month", "month": "2026-09"}}})
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    content = _send("how am i doing overall in september")["content"]
    assert "RM350.00 across 2 transaction(s)" in content and "Monthly limit: RM700.00" in content
    assert "Your verified FinCoach data is ready." not in content


def test_hesitation_words_are_not_categories():
    from app.category_resolution import resolve_category_phrase
    from app.rag.routing import resolve_read_request
    assert resolve_category_phrase("erm spend", ["Food", "Transport"]).status == "none"
    assert "category_name" not in resolve_read_request("erm spend", [], now=date(2026, 9, 22)).arguments
    assert resolve_read_request("erm food spending", [], now=date(2026, 9, 22)).arguments["category_name"] == "Food"


def _spending_proposal(**fields):
    return dict(SEPTEMBER_SPENDING, **fields)


def test_single_rule_write_needs_the_interpreter_to_agree(monkeypatch):
    # The reminder rule matches "ping me", but the interpreter reads a spending ask.
    _interpreted(monkeypatch, _spending_proposal())
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", False)
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    content = _send("Ping me my spending for September")["content"]
    assert "RM350.00" in content and "write actions are disabled" not in content


def test_agreed_reminder_request_gets_the_existing_disabled_reply(monkeypatch):
    _interpreted(monkeypatch, {"route": "personal_finance", "actions": [{"kind": "create_reminder"}]})
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", False)
    content = _send("Remind me to pay rent tomorrow at 9pm")["content"]
    assert content.startswith("AI write actions are disabled. No reminder was created.")


@pytest.mark.parametrize("writes,expected", [
    (False, "AI write actions are disabled. No reminder was created."),
    (True, "I found both a reminder and a report request."),
])
def test_multiple_actions_keep_todays_reply(monkeypatch, writes, expected):
    _interpreted(monkeypatch, {"route": "personal_finance", "actions": [
        {"kind": "create_reminder", "title": "Pay rent"}, {"kind": "generate_report"}]})
    monkeypatch.setattr(service, "COACH_WRITE_ACTIONS_ENABLED", writes)
    content = _send("Remind me to pay rent and generate my spending report")["content"]
    assert content.startswith(expected)


def test_interpreted_budget_change_gets_the_budget_tab_reply(monkeypatch):
    _interpreted(monkeypatch, {"route": "personal_finance", "actions": [{"kind": "change_budget"}]})
    content = _send("Could you make my food limit 300?")["content"]
    assert content.startswith("Budget limits aren't saved through Coach.")


def test_interpreted_product_pick_gets_the_neutral_redirect(monkeypatch):
    _interpreted(monkeypatch, {"route": "financial_education", "product_pick": True,
                               "public": {"topic": "choosing a bank"}})
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: pytest.fail("provider called"))
    content = _send("Maybank or CIMB, which one should I go with?")["content"]
    assert "does not recommend or rank" in content


def test_read_constraint_is_explained_instead_of_reported_as_outage(monkeypatch):
    bad = json.dumps(intent.IntentProposal.model_validate({"route": "personal_finance", "read": {
        "operation": "get_budget_status", "category": {"decision": "none"},
        "period": {"kind": "this_week"}}}).model_dump())
    semantic = intent.interpret_request("Am I over budget this week?", [], today=date(2026, 9, 22),
                                        budget=llm.CoachRequestBudget.start(),
                                        generate=lambda prompt, **k: k["validate"](bad))
    assert semantic.failure == "read_constraint" and "whole calendar months" in semantic.failure_message
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", lambda *a, **k: semantic)
    message = _send("Am I over budget this week?")
    assert "whole calendar months" in message["content"]
    assert not (message.get("ui_payload") or {}).get("type")


def test_second_interpretation_attempt_gets_static_feedback(monkeypatch):
    monkeypatch.setattr(llm, "_providers", lambda: [SimpleNamespace(role="primary"), SimpleNamespace(role="fallback")])
    prompts = []

    def generate(_client, _provider, prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(content="{}", finish_reason="stop")
    monkeypatch.setattr(llm, "_generate_with_provider", generate)
    attempts = iter([intent.ProposalRejected("Comparison requires at least two distinct months")])

    def validate(_content):
        raise next(attempts, ValueError("done"))
    with pytest.raises(ValueError):
        llm.generate_validated_interpretation("BASE", response_schema={}, validate=validate,
                                              budget=llm.CoachRequestBudget.start())
    assert prompts[0] == "BASE"
    assert "PREVIOUS PROPOSAL REJECTED (Comparison requires at least two distinct months)" in prompts[1]
    try:
        intent.IntentProposal.model_validate_json('{"route": "personal_finance", "read": {"operation": "SECRET9999"}}')
    except Exception as error:
        pydantic_error = error
    fields = [{"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in pydantic_error.errors()]
    feedback = llm._interpretation_feedback(pydantic_error, fields)
    assert "read.operation" in feedback and "SECRET9999" not in feedback


PARTIAL = {"route": "financial_education", "public": {"topic": "ICU JPM",
           "required_facts": ["duties", "application"], "clarification_facts": ["application"]},
           "clarification": "Raw model text: which programme?"}


def test_partial_public_question_answers_the_clear_part_on_the_plain_path(monkeypatch):
    _interpreted(monkeypatch, PARTIAL)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", False)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: llm.LLMResult(
        content="**Insight**\nICU JPM coordinates implementation of national programmes.\n"
                "**Educational guidance**\nThis is educational guidance, not licensed financial advice.",
        model="m"))
    content = _send("What does ICU JPM do and how do I apply?")["content"]
    assert "coordinates implementation" in content
    assert "Which programme or service would you like to apply for?" in content
    assert "Raw model text" not in content


def test_partial_public_question_reaches_the_research_explanation(monkeypatch):
    from app.rag.research_policy import EvidenceAssessment, ResearchDecision
    _interpreted(monkeypatch, PARTIAL)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", True)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "run_research_policy",
                        lambda *a, **k: ResearchDecision([], EvidenceAssessment("insufficient")))
    message = _send("What does ICU JPM do and how do I apply?")
    assert message["content"] != PARTIAL["clarification"]
    assert "Which programme or service would you like to apply for?" in message["content"]


def test_interpreted_advice_uses_figures_then_advice(monkeypatch):
    _interpreted(monkeypatch, _spending_proposal(requested_output="advice"))
    prompts = []

    def generate(prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(content="Plan your meals for the week and cook at home more often.", model="m",
                               finish_reason="stop", prompt_tokens=None, completion_tokens=None)
    monkeypatch.setattr(service, "generate_result", generate)
    content = _send("how can i spend less than in september")["content"]
    assert content.startswith("Recorded expenses from 2026-09-01 to 2026-09-30: RM350.00")
    assert content.endswith("cook at home more often.") and len(prompts) == 1
    assert "never write a specific RM figure" in prompts[0]


def test_interpreter_context_skips_failed_and_current_messages():
    captured = []

    def generate(prompt, **kwargs):
        captured.append(prompt)
        raise TimeoutError()
    history = [{"id": "old", "role": "user", "content": "earlier question", "status": "completed"},
               {"id": "bad", "role": "user", "content": "failed question", "status": "failed"},
               {"id": "now", "role": "user", "content": "current question", "status": "processing"}]
    intent.interpret_request("current question", history, today=date(2026, 9, 22),
                             budget=llm.CoachRequestBudget.start(), generate=generate, current_message_id="now")
    data = json.loads(captured[0].split("INPUT DATA:\n", 1)[1])
    assert data["context"] == [{"role": "user", "content": "earlier question"}]


def _category_read(name=None, built_in=None, decision="named"):
    category = {"decision": decision}
    if name is not None:
        category["name"] = name
    if built_in is not None:
        category["built_in"] = built_in
    return {"route": "personal_finance", "read": {"operation": "get_spending_summary",
            "category": category, "period": {"kind": "month", "month": "2026-09"}}}


def _no_explanation(monkeypatch):
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))


def test_named_category_reads_only_that_category_and_says_so(monkeypatch):
    _interpreted(monkeypatch, _category_read("Food"))
    _no_explanation(monkeypatch)
    content = _send("how much did i spend on food in september")["content"]
    assert content.startswith("Food category: Recorded expenses") and "RM100.00" in content


def test_built_in_match_is_used_only_when_nothing_closer_is_saved(monkeypatch):
    _interpreted(monkeypatch, _category_read("makan", built_in="Food"))
    _no_explanation(monkeypatch)
    content = _send("berapa belanja makan bulan september")["content"]
    assert content.startswith("Food category:") and "RM100.00" in content


def test_users_own_category_beats_the_built_in_alias(monkeypatch):
    _interpreted(monkeypatch, _category_read("lunch", built_in="Food"))
    _no_explanation(monkeypatch)
    client = StoredClient(stored_rows(["Food", "Transport", "Lunch"]))
    content = _send("how much on lunch in september", client=client)["content"]
    assert content.startswith("Lunch category:") and "RM100.00" not in content


def test_unmatched_category_suggests_real_names_as_text_only(monkeypatch):
    _interpreted(monkeypatch, _category_read("foods"))
    client = StoredClient(stored_rows(["Food", "Transport"]))
    message = _send("how much on foods in september", client=client)
    assert "Did you mean Food?" in message["content"]
    assert not (message.get("ui_payload") or {}).get("type") and "follow_ups" not in message["ui_payload"]
    assert message["ui_payload"]["intent_context"]["suggested_categories"] == ["Food"]
    assert not any(q.table_name == "transactions" for q in client.executed)


@pytest.mark.parametrize("reply,category", [
    ("Food", {"decision": "named", "name": "Food"}),
    ("yes", {"decision": "suggested"}),
])
def test_typed_reply_to_a_suggestion_is_interpreted_then_resumed(monkeypatch, reply, category):
    _interpreted(monkeypatch, _category_read("foods"))
    first = _send("how much on foods in september")
    follow_up = _category_read()
    follow_up["read"]["category"] = category
    _interpreted(monkeypatch, dict(follow_up, relation="follow_up"))
    _no_explanation(monkeypatch)
    history = [{"id": "u1", "role": "user", "content": "how much on foods in september", "status": "completed"},
               {"id": "a1", "role": "assistant", "content": first["content"], "status": "completed",
                "ui_payload": first["ui_payload"]}]
    message = _send(reply, history=history)
    assert message["content"].startswith("Food category:") and "RM100.00" in message["content"]
    follow_up_context = message["ui_payload"]["intent_context"]["proposal"]["read"]["category"]
    assert follow_up_context == {"decision": "named", "name": "Food", "built_in": None}


def test_interpreter_sees_built_in_names_but_never_custom_ones(monkeypatch):
    rows = stored_rows(["Food", "Transport"])
    rows["categories"].append({"id": 77, "name": "My Private Stash", "type": "expense", "user_id": USER_ID})
    seen = {}

    def interpret(*args, **kwargs):
        seen.update(kwargs)
        raise TimeoutError()
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", True)
    monkeypatch.setattr(service, "interpret_request", interpret)
    with pytest.raises(TimeoutError):
        _send("how much on food", client=StoredClient(rows))
    assert set(seen["built_in_categories"]) == {"Food", "Transport"}
    captured = []
    intent.interpret_request("x", [], today=date(2026, 9, 22), budget=llm.CoachRequestBudget.start(),
                             built_in_categories=("Food",),
                             generate=lambda prompt, **k: captured.append(prompt) or (_ for _ in ()).throw(TimeoutError()))
    assert '"built_in_categories": ["Food"]' in captured[0]


def test_built_in_outside_the_supplied_list_is_rejected():
    proposal = json.dumps(intent.IntentProposal.model_validate(_category_read("x", built_in="Yachts")).model_dump())
    result = intent.interpret_request("x", [], today=date(2026, 9, 22), budget=llm.CoachRequestBudget.start(),
                                      built_in_categories=("Food",),
                                      generate=lambda prompt, **k: k["validate"](proposal))
    assert result.failure == "interpretation_unavailable"


def test_resumed_existing_card_keeps_its_saved_category(monkeypatch):
    from app.rag.read_clarification import build_read_clarification
    from app.rag.routing import resolve_read_request
    monkeypatch.setattr(service, "COACH_LLM_INTERPRETATION_ENABLED", False)
    pending = resolve_read_request("Show my Food transactions at Grab and Foodpanda in September 2026", [],
                                   now=date(2026, 9, 22))
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=date(2026, 9, 22))
    assert payload["state"]["arguments"]["category_name"] == "Food"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = []
    repository.require_interaction_message.return_value = {"id": "a1", "session_id": "s", "ui_payload": payload}
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]
    client = StoredClient(stored_rows(["Food", "Transport"]))
    message = service.CoachingService(repository, client).send_message(
        "s", "m", "Fixture", interaction_reply={"assistant_message_id": "a1", "value": "Fixture"})["assistant_message"]
    assert "Food RM100.00" in message["content"] and "Transport" not in message["content"]


_PLAN_ANSWER = ("**Insight**\nFor RM1,500.00, needs (50%) = RM750.00, wants (30%) = RM450.00, savings (20%) = RM300.00.\n"
                "**Recommended action**\nTrack spending weekly against each bucket.\n"
                "**Educational guidance**\nThis is educational guidance, not licensed financial advice.")


@pytest.mark.parametrize("proposal", [
    {"route": "financial_education", "public": {"topic": "budget allocation for a monthly allowance",
     "framework": "allocation", "stated_amount": "1500"}},
    # A "current" time-scope guess must not block a fixed framework for a stated amount.
    {"route": "financial_education", "public": {"topic": "budget plan for 1500 allowance allocation",
     "time_scope": "current", "required_facts": ["budget allocation", "saving plan"],
     "framework": "allocation", "stated_amount": "1500"}},
])
@pytest.mark.parametrize("text", ["create budget plan for my 1500 allowance",
                                  "Create a budget plan for my RM1500 allowance"])
def test_budget_plan_request_gets_an_allocation_answer(monkeypatch, proposal, text):
    _interpreted(monkeypatch, proposal)
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", True)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "run_research_policy", lambda *a, **k: pytest.fail("allocation is deterministic"))
    prompts = []

    def generate(prompt, **kwargs):
        prompts.append(prompt)
        return llm.LLMResult(content=_PLAN_ANSWER, model="m")
    monkeypatch.setattr(service, "generate_result", generate)
    content = _send(text)["content"]
    assert not content.startswith("Budget limits aren't saved through Coach.")
    assert "RM750.00" in content
    assert "needs (50%) = RM750.00" in prompts[0]


def test_real_budget_change_still_gets_the_budget_tab_reply(monkeypatch):
    _interpreted(monkeypatch, {"route": "personal_finance", "actions": [{"kind": "change_budget"}]})
    content = _send("Could you change my food budget to RM300?")["content"]
    assert content.startswith("Budget limits aren't saved through Coach.")


def test_users_own_current_wording_still_gets_live_research(monkeypatch):
    from app.rag.research_policy import EvidenceAssessment, ResearchDecision
    _interpreted(monkeypatch, {"route": "financial_education", "public": {
        "topic": "latest recommended budget split", "time_scope": "current"}})
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", True)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    calls = []

    def research(*a, **k):
        calls.append(a)
        return ResearchDecision([], EvidenceAssessment("insufficient"))
    monkeypatch.setattr(service, "run_research_policy", research)
    _send("What is the latest recommended budget split for RM1500 in 2026?")
    assert calls, "an explicit current/dated ask must still use live research"


def test_education_reply_text_has_no_source_markers(monkeypatch):
    _interpreted(monkeypatch, {"route": "financial_education", "public": {
        "topic": "budget allocation", "framework": "allocation", "stated_amount": "1500"}})
    monkeypatch.setattr(service, "COACH_RESEARCH_POLICY_ENABLED", False)
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(service, "generate_result", lambda *a, **k: llm.LLMResult(
        content="**Insight**\nNeeds (50%) = RM750.00 [S1].\n**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice.", model="m"))
    response = service.CoachingService(MagicMock(**{
        "user_id": USER_ID, "require_session.return_value": {"id": "s", "title": "Existing"},
        "find_user_message.return_value": None, "insert_user_message.return_value": {"id": "m"},
        "list_messages.return_value": [], "complete_turn.side_effect": lambda **kw: kw["assistant_payload"],
    }), StoredClient(stored_rows(["Food"]))).send_message("s", "m", "create budget plan for my 1500 allowance")
    content = response["assistant_message"]["content"]
    assert "[S1]" not in content and "Needs (50%) = RM750.00." in content
    assert response["sources"], "the sources card is unchanged"
