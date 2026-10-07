import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient


USER_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
REPLY_ID = "44444444-4444-4444-8444-444444444444"
NOW = "2026-07-17T02:00:00+00:00"
PROVIDER_CONSENT_HEADERS = {"X-FinCoach-Provider-Consent": "openrouter-free-v1"}


def session_row(title="New conversation"):
    return {
        "id": SESSION_ID,
        "user_id": USER_ID,
        "title": title,
        "created_at": NOW,
        "updated_at": NOW,
        "last_message_at": NOW,
    }


def message_row(message_id=MESSAGE_ID, role="user", content="Help me save"):
    return {
        "id": message_id,
        "session_id": SESSION_ID,
        "user_id": USER_ID,
        "role": role,
        "content": content,
        "status": "completed",
        "created_at": NOW,
    }


class CoachRouteTests(unittest.TestCase):
    def setUp(self):
        from app.api.coach_routes import (
            get_agent_action_service,
            get_coaching_repository,
            get_coaching_service,
            get_current_user,
            router,
        )
        from app.auth import AuthenticatedUser
        from app.observability import RequestContextMiddleware

        self.repository = MagicMock()
        self.service = MagicMock()
        self.action_service = MagicMock()
        app = FastAPI()
        app.add_middleware(RequestContextMiddleware)
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(USER_ID, "token")
        app.dependency_overrides[get_coaching_repository] = lambda: self.repository
        app.dependency_overrides[get_coaching_service] = lambda: self.service
        app.dependency_overrides[get_agent_action_service] = lambda: self.action_service
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_requires_authentication_without_override(self):
        from app.api.coach_routes import router

        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).get("/coach/conversations")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required."})

    def test_web_citations_survive_conversation_reload(self):
        assistant = message_row(REPLY_ID, "assistant", "Current rate [S1].")
        assistant["ui_payload"] = {"source_snapshot": [{
            "title": "Official rate", "source": "bnm.gov.my",
            "similarity": 0.9, "rank": 1, "url": "https://bnm.gov.my/rate",
            "source_type": "web", "tier": 1, "confidence": "established",
            "published_date": "2026-09-01", "checked_at": "2026-09-23",
        }]}
        self.repository.list_message_page.return_value = {
            "messages": [message_row(), assistant], "next_before": None,
        }
        self.repository.list_retrievals_for_messages.return_value = []
        response = self.client.get(f"/coach/conversations/{SESSION_ID}/messages")
        self.assertEqual(response.status_code, 200)
        source = response.json()["messages"][1]["sources"][0]
        self.assertEqual(source["url"], "https://bnm.gov.my/rate")
        self.assertEqual(source["published_date"], "2026-09-01")

    def test_conversation_crud_contract(self):
        self.repository.list_sessions.return_value = [session_row()]
        self.repository.create_session.return_value = session_row("Semester plan")
        self.repository.rename_session.return_value = session_row("Food budget")

        listed = self.client.get("/coach/conversations")
        created = self.client.post("/coach/conversations", json={"title": " Semester plan "})
        renamed = self.client.patch(
            f"/coach/conversations/{SESSION_ID}", json={"title": "Food budget"}
        )
        deleted = self.client.delete(f"/coach/conversations/{SESSION_ID}")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["title"], "Semester plan")
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(deleted.status_code, 204)
        self.repository.create_session.assert_called_once_with("Semester plan")
        self.repository.delete_session.assert_called_once_with(SESSION_ID)

    def test_lists_a_paginated_message_page_with_batched_sources(self):
        assistant = message_row(REPLY_ID, "assistant", "Save RM80 first")
        self.repository.list_message_page.return_value = {
            "messages": [message_row(), assistant],
            "next_before": "2026-07-16T02:00:00+00:00",
        }
        self.repository.list_retrievals_for_messages.return_value = [
            {
                "assistant_message_id": REPLY_ID,
                "title": "Guide",
                "source": "guide.pdf",
                "similarity": 0.8,
                "rank": 1,
            }
        ]

        response = self.client.get(
            f"/coach/conversations/{SESSION_ID}/messages?limit=30&before=2026-07-17T03:00:00%2B00:00"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["role"] for item in payload["messages"]], ["user", "assistant"])
        self.assertEqual(payload["messages"][1]["sources"][0]["source"], "guide.pdf")
        self.assertEqual(payload["next_before"], "2026-07-16T02:00:00+00:00")
        self.repository.list_message_page.assert_called_once_with(
            SESSION_ID,
            limit=30,
            before="2026-07-17T03:00:00+00:00",
        )
        self.repository.list_retrievals_for_messages.assert_called_once_with([REPLY_ID])

    def test_successful_turn_uses_client_message_id(self):
        turn = {
            "user_message": message_row(),
            "assistant_message": message_row(REPLY_ID, "assistant", "Save RM80 first"),
            "sources": [{"title": "Guide", "source": "guide.pdf", "similarity": 0.8, "rank": 1}],
        }
        self.service.send_message.return_value = turn

        response = self.client.post(
            f"/coach/conversations/{SESSION_ID}/messages",
            headers=PROVIDER_CONSENT_HEADERS,
            json={"message_id": MESSAGE_ID, "content": "Help me save"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["assistant_message"]["id"], REPLY_ID)
        self.service.send_message.assert_called_once_with(SESSION_ID, MESSAGE_ID, "Help me save")

    def test_new_messages_require_current_ai_provider_consent(self):
        missing = self.client.post(
            f"/coach/conversations/{SESSION_ID}/messages",
            json={"message_id": MESSAGE_ID, "content": "Help me save"},
        )
        outdated = self.client.post(
            f"/coach/conversations/{SESSION_ID}/messages",
            headers={"X-FinCoach-Provider-Consent": "openrouter-free-v0"},
            json={"message_id": MESSAGE_ID, "content": "Help me save"},
        )

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(outdated.status_code, 403)
        self.assertEqual(missing.json(), {"detail": "AI provider consent is required."})
        self.service.send_message.assert_not_called()

    def test_structured_clarification_reply_reaches_the_coaching_service(self):
        turn = {
            "user_message": message_row(content="Tomorrow"),
            "assistant_message": message_row(REPLY_ID, "assistant", "Create reminder?"),
            "sources": [],
        }
        self.service.send_message.return_value = turn

        response = self.client.post(
            f"/coach/conversations/{SESSION_ID}/messages",
            headers=PROVIDER_CONSENT_HEADERS,
            json={
                "message_id": MESSAGE_ID,
                "content": "Tomorrow",
                "interaction_reply": {
                    "assistant_message_id": REPLY_ID,
                    "value": "2026-07-29",
                },
            },
        )

        self.assertEqual(response.status_code, 201)
        self.service.send_message.assert_called_once_with(
            SESSION_ID,
            MESSAGE_ID,
            "Tomorrow",
            interaction_reply={
                "assistant_message_id": REPLY_ID,
                "value": "2026-07-29",
            },
        )

    def test_persists_and_returns_assistant_message_feedback(self):
        updated = {
            **message_row(REPLY_ID, "assistant", "Save RM80 first"),
            "feedback": "helpful",
        }
        self.repository.set_message_feedback.return_value = updated

        response = self.client.patch(
            f"/coach/messages/{REPLY_ID}/feedback",
            json={"feedback": "helpful"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"], "helpful")
        self.repository.set_message_feedback.assert_called_once_with(REPLY_ID, "helpful")

    def test_confirmation_gated_action_routes(self):
        action_id = "55555555-5555-4555-8555-555555555555"
        action_message = {
            **message_row(REPLY_ID, "assistant", "Create reminder?"),
            "ui_payload": {
                "type": "action",
                "action_id": action_id,
                "action_type": "create_reminder",
                "status": "executed",
            },
        }
        self.action_service.confirm.return_value = {
            "message": action_message,
            "effect": None,
        }
        self.action_service.cancel.return_value = {
            "message": {**action_message, "ui_payload": {**action_message["ui_payload"], "status": "cancelled"}},
            "effect": None,
        }

        confirmed = self.client.post(
            f"/coach/messages/{REPLY_ID}/actions/confirm",
            json={"action_id": action_id},
        )
        cancelled = self.client.post(
            f"/coach/messages/{REPLY_ID}/actions/cancel",
            json={"action_id": action_id},
        )

        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["message"]["ui_payload"]["status"], "executed")
        self.assertEqual(cancelled.status_code, 200)
        self.action_service.confirm.assert_called_once_with(REPLY_ID, action_id)
        self.action_service.cancel.assert_called_once_with(REPLY_ID, action_id)

    def test_safe_error_status_mapping(self):
        from app.coaching_history import CoachingRateLimitExceeded, ConversationNotFound
        from app.rag.service import CoachingConflict

        cases = [
            (ConversationNotFound("secret database text"), 404, "Conversation not found."),
            (CoachingConflict("secret duplicate text"), 409, "Message is already being processed."),
            (CoachingRateLimitExceeded("secret usage text"), 429, "Coaching message limit reached."),
            (TimeoutError("provider hostname"), 504, "Coaching provider timed out."),
            (RuntimeError("provider API secret"), 502, "Coaching provider is unavailable."),
        ]
        for error, expected_status, expected_detail in cases:
            with self.subTest(expected_status=expected_status):
                self.service.send_message.side_effect = error
                response = self.client.post(
                    f"/coach/conversations/{SESSION_ID}/messages",
                    headers=PROVIDER_CONSENT_HEADERS,
                    json={"message_id": MESSAGE_ID, "content": "Help me save"},
                )
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json()["detail"], expected_detail)
                self.assertNotIn("secret", response.text)

    def test_every_response_has_bounded_request_id_and_privacy_safe_log(self):
        self.repository.list_sessions.return_value = []
        supplied = str(UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))

        with self.assertLogs("fincoach.http", level="INFO") as captured:
            response = self.client.get(
                "/coach/conversations",
                headers={"X-Request-ID": supplied, "Authorization": "Bearer top-secret-token"},
            )

        self.assertEqual(response.headers["X-Request-ID"], supplied)
        event = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(event["request_id"], supplied)
        self.assertEqual(event["route"], "/coach/conversations")
        self.assertEqual(event["status"], 200)
        self.assertIn("elapsed_ms", event)
        serialized = json.dumps(event)
        self.assertNotIn("top-secret-token", serialized)
        self.assertNotIn("Help me save", serialized)


class MainAppSafetyTests(unittest.TestCase):
    def test_registers_new_router_removes_legacy_route_and_restricts_cors(self):
        from app.main import app

        paths = set(app.openapi()["paths"])
        self.assertIn("/coach/conversations", paths)
        self.assertNotIn("/coach", paths)

        response = TestClient(app, raise_server_exceptions=False).options(
            "/coach/conversations",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)
        self.assertIn("X-Request-ID", response.headers)


if __name__ == "__main__":
    unittest.main()
