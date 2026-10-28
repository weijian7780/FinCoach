"""UI payload contract: backend-generated cards and chips must not drift.

The golden file was recorded from the coach code before the 2026-10-22
understanding optimisation. Each scenario drives CoachingService.send_message
end to end with stubbed providers and records only what the mobile app renders:
card fields, follow-up chips and whether sources were attached. Backend-only
nested context (intent/research diagnostics) is recorded as present/absent.

Regenerate ONLY from unmodified code: set UPDATE_UI_GOLDEN=1.
"""
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.llm import AgentLLMResult, LLMResult
from app.rag import request_interpretation as intent
from app.rag import service
from app.rag.retrieval import RetrievedChunk
from test_category_interpretation_contract import StoredClient, stored_rows, USER_ID

GOLDEN = Path(__file__).parent / "fixtures" / "ui_payload_golden.json"
NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
_BACKEND_ONLY = {"intent_context", "research_context", "research_outcome"}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ANSWER = (
    "**Insight**\nPTPTN provides education loans to eligible students [S1].\n"
    "**Recommended action**\nCheck the official PTPTN website before applying.\n"
    "**Educational guidance**\nThis is educational guidance, not licensed financial advice."
)
_CHOICES = (
    "PTPTN is the national higher-education loan.\n\n<<<FINCOACH_CHOICES>>>\n"
    '{"choices": [{"label": "Repayment options", "query": "How do I repay PTPTN?"},'
    ' {"label": "Check my balance", "query": "How much PTPTN do I still owe?"}]}\n'
    "<<<END_FINCOACH_CHOICES>>>"
)


@pytest.fixture(autouse=True)
def _freeze_clock():
    class FixtureClock(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class FixtureDatetime(datetime, metaclass=FixtureClock):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    with (patch("app.rag.routing.datetime", FixtureDatetime),
          patch("app.rag.service.datetime", FixtureDatetime),
          patch("app.agent_tools.datetime", FixtureDatetime)):
        yield


def _rows():
    rows = stored_rows(["Food", "Transport"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Laptop", "target_amount": "2000.00",
                              "current_amount": "500.00", "deadline": "2026-12-31", "created_at": "2026-08-01"}]
    rows["reminders"] = [{"id": "r1", "user_id": USER_ID, "title": "Pay rent", "amount": "300.00",
                          "due_at": "2026-09-25T01:00:00+00:00", "lead_days": 1, "recurrence": "none",
                          "next_trigger_at": "2026-09-24T01:00:00+00:00", "enabled": True}]
    return rows


def _repository():
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "s", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "m"}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    return repository


def _normalise(value, key=None):
    if key in _BACKEND_ONLY:
        return "<present>"
    if key == "source_snapshot":
        return {"count": len(value or [])}
    if isinstance(value, dict):
        return {k: _normalise(v, k) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    if isinstance(value, str) and _UUID.match(value):
        return "<uuid>"
    return value


def _proposal(operation, period, **read):
    return intent.IntentProposal.model_validate({"route": "personal_finance", "read": {
        "operation": operation, "category": {"decision": "none"}, "period": period, **read}})


def _semantic(proposal):
    return intent.InterpretedRequest(proposal, intent.compile_read(proposal, NOW.date()),
                                     intent._public_plan(proposal, "q"),
                                     context={"version": 1, "anchor_date": NOW.date().isoformat(),
                                              "proposal": proposal.model_dump()})


def _agent_stub(*_args, **kwargs):
    result = kwargs["tool_executor"]("prepare_reminder", {
        "title": "Pay rent", "due_at": "2026-09-23T21:00:00+08:00", "recurrence": "none"})
    return AgentLLMResult(content="Please review the reminder details.", model="stub",
                          ui_payload=result.get("ui_payload"), tool_names=("prepare_reminder",),
                          tool_results=({"name": "prepare_reminder", "result": result},))


def _raise_timeout(*_args, **_kwargs):
    raise TimeoutError()


_CORPUS = [RetrievedChunk(id=1, title="PTPTN", source="ptptn.md", page_number=None, chunk_index=0,
                          content="PTPTN provides education loans to eligible students.", similarity=0.9)]

_SEMANTIC_READS = {
    "spending": ("get_spending_summary", {"kind": "month", "month": "2026-09"}, {}),
    "budget": ("get_budget_status", {"kind": "month", "month": "2026-09"}, {}),
    "transactions": ("search_transactions", {"kind": "month", "month": "2026-09"}, {}),
    "goals": ("get_savings_goals", {"kind": "default"}, {}),
    "predict": ("predict_savings", {"kind": "month", "month": "2026-09"}, {}),
    "weekly_plan": ("get_weekly_savings_plan", {"kind": "month", "month": "2026-09"}, {}),
    "cashflow": ("get_cashflow_forecast", {"kind": "default"}, {}),
    "reminders": ("get_upcoming_reminders", {"kind": "default"}, {}),
    "profile": ("get_financial_profile", {"kind": "default"}, {}),
    "comparison": ("get_period_comparison", {"kind": "months", "months": ["2026-08", "2026-09"]}, {}),
    "recommendation": ("get_category_budget_recommendation", {"kind": "month", "month": "2026-09"}, {}),
    "overview": ("get_financial_overview", {"kind": "month", "month": "2026-09"}, {}),
    "report_summary": ("get_report_summary", {"kind": "month", "month": "2026-09"}, {}),
}


def _scenarios():
    legacy = {"interpretation": False}
    cases = {
        "ambiguous_reminder_card": dict(legacy, text="Pay rent", writes=True),
        "action_card": dict(legacy, text="Remind me to pay rent tomorrow at 9pm", writes=True,
                            agent=_agent_stub),
        "write_disabled_reply": dict(legacy, text="Remind me to pay rent tomorrow at 9pm"),
        "multi_action_reply": dict(legacy, text="Remind me to pay rent and generate my spending report",
                                   writes=True),
        "product_policy_reply": dict(legacy, text="Which bank is best for students?"),
        "read_card_month": dict(legacy, text="Show my budget last week"),
        "read_card_savings": dict(legacy, text="What about my savings?"),
        "read_card_transaction": dict(legacy, text="Show me that transaction"),
        "read_card_amount": dict(legacy, text="Show transactions for RM25k"),
        "legacy_fast_budget": dict(legacy, text="Show my budget status"),
        "research_answer_sources": dict(legacy, text="What is PTPTN?", chunks=_CORPUS,
                                        generate=lambda *a, **k: LLMResult(content=_ANSWER, model="stub")),
        "choices_card": dict(legacy, text="What is PTPTN?", choices=True,
                             generate=lambda *a, **k: LLMResult(content=_CHOICES, model="stub")),
        "interpreter_clarification": dict(semantic=_semantic(intent.IntentProposal.model_validate({
            "route": "personal_finance", "read": {"operation": "get_spending_summary",
                                                  "category": {"decision": "unclear"}},
            "clarification": "Which category do you mean?"})), text="how much did i spend on that"),
    }
    for name, (operation, period, read) in _SEMANTIC_READS.items():
        cases[f"semantic_read_{name}"] = dict(semantic=_semantic(_proposal(operation, period, **read)),
                                              text=f"show my {name}", generate=_raise_timeout)
    return cases


def _run(case):
    semantic = case.get("semantic")
    patches = [
        patch.object(service, "COACH_LLM_INTERPRETATION_ENABLED", semantic is not None),
        patch.object(service, "COACH_RESEARCH_POLICY_ENABLED", False),
        patch.object(service, "WEB_FALLBACK_ENABLED", False),
        patch.object(service, "COACH_LLM_CHOICES_ENABLED", case.get("choices", False)),
        patch.object(service, "COACH_WRITE_ACTIONS_ENABLED", case.get("writes", False)),
        patch.object(service, "retrieve", lambda *a, **k: list(case.get("chunks", []))),
        patch.object(service, "generate_result", case.get("generate", _raise_timeout)),
        patch.object(service, "generate_agent_result", case.get("agent", _raise_timeout)),
        patch.object(service, "interpret_question", lambda *a, **k: pytest.fail("research interpreter")),
    ]
    if semantic is not None:
        patches.append(patch.object(service, "interpret_request", lambda *a, **k: semantic))
    for item in patches:
        item.start()
    try:
        response = service.CoachingService(_repository(), StoredClient(_rows())).send_message(
            "s", "m", case["text"])
    finally:
        for item in reversed(patches):
            item.stop()
    payload = response["assistant_message"].get("ui_payload") or {}
    return {"ui_payload": _normalise(payload), "source_count": len(response.get("sources") or [])}


def _record():
    return {name: _run(case) for name, case in _scenarios().items()}


def test_ui_payload_contract_matches_pre_optimisation_golden():
    actual = _record()
    if os.environ.get("UPDATE_UI_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert sorted(actual) == sorted(expected)
    for name in expected:
        assert actual[name] == expected[name], name
