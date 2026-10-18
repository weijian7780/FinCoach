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


class ReferenceQuery:
    """Rows-or-error lookup for the owner-scoped cleanup evidence check."""

    def __init__(self, rows):
        self.rows = rows
        self.error = None

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def in_(self, *_args):
        return self

    def execute(self):
        if self.rows is None:
            return SimpleNamespace(data=None, error=RuntimeError("lookup failed"))
        return SimpleNamespace(data=self.rows, error=None)


def report_rows(rows):
    return ReferenceQuery(rows)


ACTION_ID = "00000000-0000-0000-0000-000000000123"
MESSAGE_ID = "assistant-1"


def report_attempt(**overrides):
    """A server-projected attempt: safe fields plus the computed lease facts."""
    attempt_id = overrides.get("attempt_id", "00000000-0000-0000-0000-000000000321")
    attempt = {
        "attempt_id": attempt_id,
        "message_id": MESSAGE_ID,
        "action_id": ACTION_ID,
        "status": "active",
        "storage_path": f"verified-user/coach/{attempt_id}.pdf",
        "period": "current_month",
        "report_type": "monthly",
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "category_id": None,
        "category_name": None,
        "report_id": None,
        "lease_expires_at": "2030-01-01T00:05:00+00:00",
        "server_time": "2030-01-01T00:00:00+00:00",
        "lease_valid": True,
    }
    attempt.update(overrides)
    return attempt


class AgentActionModelTests(unittest.TestCase):
    def test_action_decision_requires_uuid_and_rejects_extra_identity(self):
        from app.models import CoachActionCompletion, CoachActionDecision

        action_id = UUID("00000000-0000-0000-0000-000000000123")
        attempt_id = UUID("00000000-0000-0000-0000-000000000321")
        self.assertEqual(CoachActionDecision(action_id=action_id).action_id, action_id)
        self.assertIsNone(CoachActionDecision(action_id=action_id).attempt_id)
        self.assertEqual(
            CoachActionDecision(action_id=action_id, attempt_id=attempt_id).attempt_id,
            attempt_id,
        )
        self.assertEqual(
            CoachActionCompletion(
                action_id=action_id, attempt_id=attempt_id, success=True, result={},
            ).attempt_id,
            attempt_id,
        )
        with self.assertRaises(ValidationError):
            CoachActionDecision(action_id=action_id, user_id="foreign-user")
        with self.assertRaises(ValidationError):
            CoachActionDecision(action_id=action_id, attempt_id="not-a-uuid")
        with self.assertRaises(ValidationError):
            CoachActionCompletion(action_id=action_id, success=True, storage_path="someone-else/fake.pdf")


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
                    "due_at": "2030-08-15T20:00:00+08:00",
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
        lookup = MutationQuery([])
        insert = MutationQuery([{"id": "00000000-0000-0000-0000-000000000123"}])
        def commit(_id, expected, payload, *, reminder=None, **_kwargs):
            self.assertEqual(expected["status"], "pending")
            insert.insert_payload = reminder
            return {**self.action_message(), "ui_payload": payload}
        repository.commit_action.side_effect = commit
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
        self.assertEqual(admin.table.call_count, 1)

    def test_report_confirmation_claims_and_returns_the_reserved_attempt(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(action_type="generate_report")
        message["ui_payload"]["arguments"] = {
            "period": "current_month",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "category_name": None,
        }
        approved_message = {
            **message,
            "ui_payload": {**message["ui_payload"], "status": "approved"},
        }
        attempt = report_attempt()
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.claim_report_attempt.return_value = (approved_message, attempt)
        profile_query = MutationQuery({"spending_records_consent": "granted"})
        admin = MagicMock()
        admin.table.return_value = profile_query

        result = AgentActionService(repository, admin).confirm(
            MESSAGE_ID,
            ACTION_ID,
            attempt_id="00000000-0000-0000-0000-000000000321",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "approved")
        self.assertEqual(result["effect"]["type"], "generate_report")
        self.assertNotIn("user_id", result["effect"]["arguments"])
        self.assertEqual(
            result["effect"]["attempt"]["attempt_id"],
            "00000000-0000-0000-0000-000000000321",
        )
        self.assertEqual(
            result["effect"]["attempt"]["storage_path"],
            "verified-user/coach/00000000-0000-0000-0000-000000000321.pdf",
        )
        # The whole claim is one transaction; no post-claim lookup can race it.
        repository.claim_report_attempt.assert_called_once_with(
            MESSAGE_ID, ACTION_ID, "00000000-0000-0000-0000-000000000321",
        )
        repository.find_active_report_attempt.assert_not_called()

    def test_report_confirmation_without_an_attempt_id_is_told_to_update(self):
        from app.agent_actions import AgentActionService
        from app.coaching_history import ActionProtocolError

        message = self.action_message(action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        admin = MagicMock()

        with self.assertRaises(ActionProtocolError) as raised:
            AgentActionService(repository, admin).confirm(MESSAGE_ID, ACTION_ID)

        self.assertEqual(raised.exception.code, "update_required")
        self.assertEqual(raised.exception.status_code, 426)
        self.assertEqual(
            str(raised.exception), "Update FinCoach to generate this report."
        )
        repository.claim_report_attempt.assert_not_called()
        admin.table.assert_not_called()

    def test_report_confirmation_surfaces_a_competing_live_claim(self):
        from app.agent_actions import AgentActionService
        from app.coaching_history import ActionProtocolError

        message = self.action_message(status="approved", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.claim_report_attempt.side_effect = ActionProtocolError(
            "action_in_progress",
            "Report generation is already in progress.",
            lease_expires_at="2030-01-01T00:05:00+00:00",
        )
        admin = MagicMock()
        admin.table.return_value = MutationQuery({"spending_records_consent": "granted"})

        with self.assertRaises(ActionProtocolError) as raised:
            AgentActionService(repository, admin).confirm(
                MESSAGE_ID, ACTION_ID, attempt_id="00000000-0000-0000-0000-000000000321",
            )

        self.assertEqual(raised.exception.code, "action_in_progress")
        self.assertEqual(raised.exception.lease_expires_at, "2030-01-01T00:05:00+00:00")

    def test_report_confirmation_surfaces_an_expired_attempt(self):
        from app.agent_actions import AgentActionService
        from app.coaching_history import ActionProtocolError

        message = self.action_message(status="approved", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.claim_report_attempt.side_effect = ActionProtocolError(
            "attempt_expired", "The report attempt expired before it could be used.",
        )
        admin = MagicMock()
        admin.table.return_value = MutationQuery({"spending_records_consent": "granted"})

        with self.assertRaises(ActionProtocolError) as raised:
            AgentActionService(repository, admin).confirm(
                MESSAGE_ID, ACTION_ID, attempt_id="00000000-0000-0000-0000-000000000321",
            )

        self.assertEqual(raised.exception.code, "attempt_expired")

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
                MESSAGE_ID,
                ACTION_ID,
                attempt_id="00000000-0000-0000-0000-000000000321",
            )
        repository.claim_report_attempt.assert_not_called()

    def test_failed_report_can_be_retried_after_consent_recheck(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="failed", action_type="generate_report")
        attempt = report_attempt(attempt_id="00000000-0000-0000-0000-000000000322")
        approved_message = {
            **message,
            "ui_payload": {**message["ui_payload"], "status": "approved"},
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.claim_report_attempt.return_value = (approved_message, attempt)
        admin = MagicMock()
        admin.table.return_value = MutationQuery(
            {"spending_records_consent": "granted"}
        )

        result = AgentActionService(repository, admin).confirm(
            MESSAGE_ID,
            ACTION_ID,
            attempt_id="00000000-0000-0000-0000-000000000322",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "approved")
        self.assertEqual(result["effect"]["type"], "generate_report")
        self.assertEqual(
            result["effect"]["attempt"]["attempt_id"],
            "00000000-0000-0000-0000-000000000322",
        )

    def test_report_confirmation_of_an_already_executed_card_returns_the_result(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="approved", action_type="generate_report")
        executed_message = {
            **message,
            "ui_payload": {**message["ui_payload"], "status": "executed", "result": {"report_id": 7}},
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        # The claim transaction won by another device reports the terminal
        # result instead of issuing a second attempt.
        repository.claim_report_attempt.return_value = (executed_message, None)
        admin = MagicMock()
        admin.table.return_value = MutationQuery({"spending_records_consent": "granted"})

        result = AgentActionService(repository, admin).confirm(
            MESSAGE_ID, ACTION_ID, attempt_id="00000000-0000-0000-0000-000000000321",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "executed")
        self.assertEqual(result["message"]["ui_payload"]["result"], {"report_id": 7})
        self.assertIsNone(result["effect"])

    def test_locally_executed_report_card_never_claims_again(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="executed", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message

        result = AgentActionService(repository, MagicMock()).confirm(
            MESSAGE_ID, ACTION_ID, attempt_id="00000000-0000-0000-0000-000000000321",
        )

        self.assertEqual(result["message"]["ui_payload"]["status"], "executed")
        self.assertIsNone(result["effect"])
        repository.claim_report_attempt.assert_not_called()

    def test_successful_report_completion_verifies_and_publishes_the_artifact(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="approved", action_type="generate_report")
        attempt = report_attempt(attempt_id="00000000-0000-0000-0000-000000000323")
        published = {
            **message,
            "ui_payload": {
                **message["ui_payload"],
                "status": "executed",
                "result": {"report_id": 7},
            },
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.require_active_report_attempt.return_value = attempt
        repository.complete_report_attempt.return_value = published
        storage = {
            "path": attempt["storage_path"],
            "object_id": "00000000-0000-0000-0000-000000000999",
            "version": "v-fixture-1",
            "updated_at": "2030-01-01T00:00:00.123+00:00",
            "size": 512,
        }
        verifier = MagicMock()
        verifier.verify.return_value = storage
        service = AgentActionService(
            repository, MagicMock(), artifact_verifier=verifier,
        )

        completed = service.complete(
            MESSAGE_ID,
            ACTION_ID,
            success=True,
            attempt_id="00000000-0000-0000-0000-000000000323",
            result={
                "title": " July report ",
                "file_name": "FinCoach_July_report.pdf",
                "generated_at": "2026-07-24T00:00:00.000Z",
                # Caller-supplied paths and ids are ignored by the server.
                "report_id": 42,
                "storage_path": "someone-else/fake.pdf",
            },
        )

        self.assertEqual(completed["message"]["ui_payload"]["status"], "executed")
        repository.require_active_report_attempt.assert_called_once_with(
            MESSAGE_ID, ACTION_ID, "00000000-0000-0000-0000-000000000323",
        )
        verifier.verify.assert_called_once_with(user_id="verified-user", attempt=attempt)
        repository.complete_report_attempt.assert_called_once_with(
            MESSAGE_ID,
            ACTION_ID,
            "00000000-0000-0000-0000-000000000323",
            success=True,
            report={
                "title": "July report",
                "file_name": "FinCoach_July_report.pdf",
                "generated_at": "2026-07-24T00:00:00.000Z",
            },
            storage=storage,
        )

    def test_report_completion_rejects_missing_attempt_or_display_metadata(self):
        from app.agent_actions import AgentActionConflict, AgentActionService
        from app.coaching_history import ActionProtocolError

        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = self.action_message(
            status="approved", action_type="generate_report"
        )
        service = AgentActionService(repository, MagicMock())

        with self.assertRaises(ActionProtocolError) as raised:
            service.complete(
                MESSAGE_ID,
                ACTION_ID,
                success=True,
                result={},
            )
        self.assertEqual(raised.exception.code, "update_required")
        self.assertEqual(raised.exception.status_code, 426)

        with self.assertRaisesRegex(AgentActionConflict, "metadata"):
            service.complete(
                MESSAGE_ID,
                ACTION_ID,
                success=True,
                attempt_id="00000000-0000-0000-0000-000000000323",
                result={"title": "July report", "file_name": None, "generated_at": "not-a-date"},
            )
        repository.require_active_report_attempt.assert_not_called()
        repository.complete_report_attempt.assert_not_called()

    def test_report_completion_requires_a_live_attempt(self):
        from app.agent_actions import AgentActionService
        from app.coaching_history import ActionProtocolError

        message = self.action_message(status="approved", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.require_active_report_attempt.side_effect = ActionProtocolError(
            "attempt_expired", "The report attempt expired before it could be used.",
        )
        verifier = MagicMock()
        service = AgentActionService(
            repository, MagicMock(), artifact_verifier=verifier,
        )

        with self.assertRaises(ActionProtocolError) as raised:
            service.complete(
                MESSAGE_ID,
                ACTION_ID,
                success=True,
                attempt_id="00000000-0000-0000-0000-000000000323",
                result={
                    "title": "July report",
                    "file_name": "FinCoach_July_report.pdf",
                    "generated_at": "2026-07-24T00:00:00.000Z",
                },
            )

        self.assertEqual(raised.exception.code, "attempt_expired")
        verifier.verify.assert_not_called()
        repository.complete_report_attempt.assert_not_called()

    def test_report_completion_rejects_an_unverifiable_artifact(self):
        from app.agent_actions import AgentActionService
        from app.coaching_history import ActionProtocolError
        from app.report_artifacts import ReportArtifactInvalid

        message = self.action_message(status="approved", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.require_active_report_attempt.return_value = report_attempt()
        verifier = MagicMock()
        verifier.verify.side_effect = ReportArtifactInvalid(
            "The uploaded report could not be verified."
        )
        service = AgentActionService(
            repository, MagicMock(), artifact_verifier=verifier,
        )

        with self.assertRaises(ActionProtocolError) as raised:
            service.complete(
                MESSAGE_ID,
                ACTION_ID,
                success=True,
                attempt_id="00000000-0000-0000-0000-000000000321",
                result={
                    "title": "July report",
                    "file_name": "FinCoach_July_report.pdf",
                    "generated_at": "2026-07-24T00:00:00.000Z",
                },
            )

        self.assertEqual(raised.exception.code, "report_artifact_invalid")
        repository.complete_report_attempt.assert_not_called()

    def test_repeated_report_completion_returns_the_existing_report(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="executed", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        verifier = MagicMock()
        service = AgentActionService(
            repository, MagicMock(), artifact_verifier=verifier,
        )

        repeated = service.complete(
            MESSAGE_ID,
            ACTION_ID,
            success=True,
            attempt_id="00000000-0000-0000-0000-000000000323",
            result={
                "title": "July report",
                "file_name": "FinCoach_July_report.pdf",
                "generated_at": "2026-07-24T00:00:00.000Z",
            },
        )

        self.assertEqual(repeated["message"]["ui_payload"]["status"], "executed")
        verifier.verify.assert_not_called()
        repository.complete_report_attempt.assert_not_called()

    def test_failed_report_completion_releases_the_attempt(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="approved", action_type="generate_report")
        failed = {
            **message,
            "ui_payload": {**message["ui_payload"], "status": "failed", "result": {}},
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.complete_report_attempt.return_value = failed
        verifier = MagicMock()
        completed = AgentActionService(
            repository, MagicMock(), artifact_verifier=verifier,
        ).complete(
            MESSAGE_ID,
            ACTION_ID,
            success=False,
            attempt_id="00000000-0000-0000-0000-000000000323",
            result={"message": "The PDF could not be generated."},
        )

        self.assertEqual(completed["message"]["ui_payload"]["status"], "failed")
        repository.complete_report_attempt.assert_called_once_with(
            MESSAGE_ID,
            ACTION_ID,
            "00000000-0000-0000-0000-000000000323",
            success=False,
            report={"message": "The PDF could not be generated."},
        )
        verifier.verify.assert_not_called()

    def test_cleanup_removes_only_artifacts_no_saved_report_references(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="approved", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.complete_report_attempt.return_value = {
            **message, "ui_payload": {**message["ui_payload"], "status": "failed"},
        }
        admin = MagicMock()
        admin.rpc.return_value = report_rows([
            {'attempt_id': 'a2', 'user_id': 'verified-user', 'storage_path': 'verified-user/coach/a2.pdf'},
        ])
        remove = admin.storage.from_.return_value.remove

        AgentActionService(repository, admin).complete(
            MESSAGE_ID,
            ACTION_ID,
            success=False,
            attempt_id="00000000-0000-0000-0000-000000000323",
            result={"message": "The PDF could not be generated."},
        )

        remove.assert_called_once_with(["verified-user/coach/a2.pdf"])

    def test_cleanup_never_deletes_files_when_the_reference_check_fails(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(status="approved", action_type="generate_report")
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.commit_action.side_effect = lambda _id, _expected, payload, **_kwargs: {
            **message, "ui_payload": payload,
        }
        admin = MagicMock()
        admin.rpc.side_effect = RuntimeError('reference check unavailable')
        remove = admin.storage.from_.return_value.remove

        AgentActionService(repository, admin).cancel(MESSAGE_ID, ACTION_ID)

        remove.assert_not_called()

    def test_repeated_cancellation_retries_cleanup_for_a_late_upload(self):
        from app.agent_actions import AgentActionService
        message = self.action_message(status='cancelled', action_type='generate_report')
        repository = MagicMock(user_id='verified-user')
        repository.require_action_message.return_value = message
        admin = MagicMock()
        admin.rpc.return_value = report_rows([
            dict(attempt_id='late', user_id='verified-user', storage_path='verified-user/coach/late.pdf'),
        ])
        AgentActionService(repository, admin).cancel(MESSAGE_ID, ACTION_ID)
        repository.commit_action.assert_not_called()
        admin.storage.from_.return_value.remove.assert_called_once_with(['verified-user/coach/late.pdf'])

    def test_cancel_and_complete_update_only_owned_action_message(self):
        from app.agent_actions import AgentActionService

        message = self.action_message(action_type="generate_report")
        message["ui_payload"]["arguments"] = {
            "start_date": "2026-07-01", "end_date": "2026-07-31", "category_name": None,
        }
        repository = MagicMock(user_id="verified-user")
        repository.require_action_message.return_value = message
        repository.commit_action.side_effect = lambda _id, _expected, payload, **_kwargs: {
            **message,
            "ui_payload": payload,
        }
        repository.complete_report_attempt.side_effect = lambda _id, _action, _attempt, **_kwargs: {
            **message,
            "ui_payload": {**message["ui_payload"], "status": "failed"},
        }
        service = AgentActionService(repository, MagicMock())

        cancelled = service.cancel(MESSAGE_ID, ACTION_ID)
        self.assertEqual(cancelled["message"]["ui_payload"]["status"], "cancelled")

        message["ui_payload"]["status"] = "approved"
        completed = service.complete(
            MESSAGE_ID,
            ACTION_ID,
            success=False,
            attempt_id="00000000-0000-0000-0000-000000000330",
            result={"message": "The PDF could not be generated."},
        )
        self.assertEqual(completed["message"]["ui_payload"]["status"], "failed")
        self.assertEqual(repository.commit_action.call_count, 1)
        self.assertEqual(repository.complete_report_attempt.call_count, 1)

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
        repository.commit_action.assert_not_called()

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

        repository.commit_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
