import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from pydantic import ValidationError


class MutationQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.insert_payload = None
        self.eq_calls = []

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def select(self, *_args):
        return self

    def eq(self, column, value):
        self.eq_calls.append((column, value))
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class AgentActionModelTests(unittest.TestCase):
    def test_action_decision_requires_uuid_and_rejects_extra_identity(self):
        from app.models import CoachActionDecision

        action_id = UUID("00000000-0000-0000-0000-000000000123")
        self.assertEqual(CoachActionDecision(action_id=action_id).action_id, action_id)
        with self.assertRaises(ValidationError):
            CoachActionDecision(action_id=action_id, user_id="foreign-user")


class AgentActionServiceTests(unittest.TestCase):
    def action_message(self, *, status="pending", action_type="create_reminder"):
        return {
            "id": "assistant-1",
            "user_id": "verified-user",
            "role": "assistant",
            "ui_payload": {
                "type": "action",
                "action_id": "00000000-0000-0000-0000-000000000123",
                "action_type": action_type,
                "status": status,
                "title": "Create reminder?",
                "arguments": {
                    "title": "Pay PTPTN",
                    "amount": 150,
                    "due_at": "2026-08-15T20:00:00+08:00",
                    "lead_days": 3,
                    "recurrence": "monthly",
                },
                "fields": [],
            },
        }

    def test_confirm_reminder_injects_verified_owner_and_is_idempotent(self):
        from app.agent_actions import AgentActionService

        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = self.action_message()
        repository.update_message_ui_payload.side_effect = lambda _id, payload: {
            **self.action_message(),
            "ui_payload": payload,
        }
        lookup = MutationQuery([])
        insert = MutationQuery([{"id": "00000000-0000-0000-0000-000000000123"}])
        admin = MagicMock()
        admin.table.side_effect = [lookup, insert]
        service = AgentActionService(repository, admin)

        result = service.confirm(
            "assistant-1",
            "00000000-0000-0000-0000-000000000123",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "executed")
        self.assertEqual(insert.insert_payload["user_id"], "verified-user")
        self.assertEqual(
            insert.insert_payload["id"],
            "00000000-0000-0000-0000-000000000123",
        )
        self.assertEqual(insert.insert_payload["title"], "Pay PTPTN")
        self.assertEqual(insert.insert_payload["recurrence_anchor_day"], 15)
        self.assertNotIn("user_id", self.action_message()["ui_payload"]["arguments"])

        repository.require_action_message.return_value = result["message"]
        repeated = service.confirm(
            "assistant-1",
            "00000000-0000-0000-0000-000000000123",
        )
        self.assertEqual(repeated["message"]["ui_payload"]["status"], "executed")
        self.assertEqual(admin.table.call_count, 2)

    def test_report_confirmation_returns_mobile_generation_effect(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(action_type="generate_report")
        message["ui_payload"]["arguments"] = {
            "period": "current_month",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "category_name": None,
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.update_message_ui_payload.side_effect = lambda _id, payload: {
            **message,
            "ui_payload": payload,
        }
        profile_query = MutationQuery({"spending_records_consent": "granted"})

        admin = MagicMock()
        admin.table.return_value = profile_query
        result = AgentActionService(repository, admin).confirm(
            "assistant-1",
            "00000000-0000-0000-0000-000000000123",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "approved")
        self.assertEqual(result["effect"]["type"], "generate_report")
        self.assertNotIn("user_id", result["effect"]["arguments"])

    def test_report_confirmation_rechecks_spending_consent(self):
        from app.agent_actions import AgentActionConflict, AgentActionService

        message = self.action_message(action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        profile_query = MutationQuery({"spending_records_consent": "withdrawn"})
        admin = MagicMock()
        admin.table.return_value = profile_query

        with self.assertRaisesRegex(AgentActionConflict, "permission"):
            AgentActionService(repository, admin).confirm(
                "assistant-1",
                "00000000-0000-0000-0000-000000000123",
            )
        repository.update_message_ui_payload.assert_not_called()

    def test_failed_report_can_be_retried_after_consent_recheck(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="failed", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.update_message_ui_payload.side_effect = lambda _id, payload: {
            **message,
            "ui_payload": payload,
        }
        admin = MagicMock()
        admin.table.return_value = MutationQuery(
            {"spending_records_consent": "granted"}
        )

        result = AgentActionService(repository, admin).confirm(
            "assistant-1",
            "00000000-0000-0000-0000-000000000123",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "approved")
        self.assertEqual(result["effect"]["type"], "generate_report")

    def test_cancel_and_complete_update_only_owned_action_message(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.update_message_ui_payload.side_effect = lambda _id, payload: {
            **message,
            "ui_payload": payload,
        }
        service = AgentActionService(repository, MagicMock())

        cancelled = service.cancel(
            "assistant-1",
            "00000000-0000-0000-0000-000000000123",
        )
        self.assertEqual(cancelled["message"]["ui_payload"]["status"], "cancelled")

        message["ui_payload"]["status"] = "approved"
        completed = service.complete(
            "assistant-1",
            "00000000-0000-0000-0000-000000000123",
            success=True,
            result={"report_id": 42},
        )
        self.assertEqual(completed["message"]["ui_payload"]["status"], "executed")
        self.assertEqual(completed["message"]["ui_payload"]["result"]["report_id"], 42)

    def test_action_id_mismatch_is_not_found(self):
        from app.agent_actions import AgentActionNotFound, AgentActionService

        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = self.action_message()
        with self.assertRaises(AgentActionNotFound):
            AgentActionService(repository, MagicMock()).confirm(
                "assistant-1",
                "00000000-0000-0000-0000-000000000999",
            )

    def test_disabled_writes_reject_old_pending_cards_without_side_effects(self):
        from app.agent_actions import AgentActionConflict, AgentActionService

        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = self.action_message()
        admin = MagicMock()

        with self.assertRaisesRegex(AgentActionConflict, "disabled"):
            AgentActionService(repository, admin, writes_enabled=False).confirm(
                "assistant-1",
                "00000000-0000-0000-0000-000000000123",
            )

        admin.table.assert_not_called()
        repository.update_message_ui_payload.assert_not_called()

    def test_disabled_writes_cannot_complete_an_old_report_card(self):
        from app.agent_actions import AgentActionConflict, AgentActionService

        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = self.action_message(
            status="approved", action_type="generate_report"
        )

        with self.assertRaisesRegex(AgentActionConflict, "disabled"):
            AgentActionService(
                repository, MagicMock(), writes_enabled=False
            ).complete(
                "assistant-1",
                "00000000-0000-0000-0000-000000000123",
                success=True,
                result={"report_id": 42},
            )

        repository.update_message_ui_payload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
