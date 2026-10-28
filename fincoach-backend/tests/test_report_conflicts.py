"""Local regression coverage of report protocol error translation.

Uses the real repository, service, and FastAPI router. Only the Supabase
transport is fake; its SQLSTATE matches the current migration's refusal.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.agent_actions import AgentActionService
from app.coaching_history import CoachingHistoryRepository
from app.api.coach_routes import get_agent_action_service, router

OWNER = "11111111-1111-4111-8111-111111111111"
MESSAGE = "22222222-2222-4222-8222-222222222222"
ACTION = "33333333-3333-4333-8333-333333333333"
ATTEMPT = "44444444-4444-4444-8444-444444444444"


class SqlRefusal(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class Query:
    def __init__(self, data=None, failure=None):
        self.data, self.failure = data, failure

    def select(self, *_): return self
    def eq(self, *_): return self
    def maybe_single(self): return self

    def execute(self):
        if self.failure: raise self.failure
        return SimpleNamespace(data=self.data, error=None)


@pytest.mark.parametrize("operation", ["claim", "complete"])
@pytest.mark.parametrize("code,reason", [
    ("P0003", "The report category is no longer available."),
    ("P0001", "This report action was cancelled. Ask for a new report."),
])
def test_report_conflicts_return_a_controlled_http_409(code, reason, operation):
    message = {"id": MESSAGE, "ui_payload": {
        "type": "action", "action_type": "generate_report", "action_id": ACTION,
        "status": "pending" if operation == "claim" else "approved", "arguments": {"category_name": "Deleted Food"},
    }}
    admin = MagicMock()
    admin.table.side_effect = lambda table: Query(
        {"spending_records_consent": "granted"} if table == "profiles" else message
    )
    admin.rpc.return_value = Query(failure=SqlRefusal(code, reason))
    service = AgentActionService(CoachingHistoryRepository(MagicMock(), admin, OWNER), admin)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_action_service] = lambda: service
    with TestClient(app, raise_server_exceptions=False) as client:
        payload = {"action_id": ACTION, "attempt_id": ATTEMPT}
        if operation == "complete": payload.update(success=False, result={})
        endpoint = "confirm" if operation == "claim" else "complete"
        response = client.post(f"/coach/messages/{MESSAGE}/actions/{endpoint}", json=payload)
    # Refusals remain bounded and actionable without exposing SQL internals.
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "report_state_conflict"
    assert len(response.json()["detail"]["message"]) <= 200
    assert admin.rpc.call_count == 1
    assert admin.rpc.call_args.args[0] == ("claim_coach_report_attempt" if operation == "claim" else "complete_coach_report_attempt")
