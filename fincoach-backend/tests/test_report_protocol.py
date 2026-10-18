"""Repository mapping of the atomic report claim/completion protocol."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.coaching_history import (
    ActionProtocolError,
    ActionStateConflict,
    CoachingHistoryRepository,
    MessageNotFound,
)


class FakeRPCError(Exception):
    """Mimics the PostgREST APIError attributes the repository inspects."""

    def __init__(self, code=None, message="", details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def make_repository(*, error=None, data=None):
    repository = CoachingHistoryRepository(
        user_client=MagicMock(), admin_client=MagicMock(), user_id="user-1",
    )
    execute = repository.admin_client.rpc.return_value.execute
    if error is not None:
        execute.side_effect = error
    else:
        execute.return_value = SimpleNamespace(data=data)
    return repository


class ClaimProtocolMappingTests(unittest.TestCase):
    def assert_code(self, error, code, *, status_code=409):
        repository = make_repository(error=error)
        with self.assertRaises(ActionProtocolError) as raised:
            repository.claim_report_attempt("m1", "a1", "t1")
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(raised.exception.status_code, status_code)
        return raised.exception

    def test_missing_attempt_id_maps_to_update_required(self):
        raised = self.assert_code(
            FakeRPCError("P0101", "Update FinCoach to generate this report."),
            "update_required",
            status_code=426,
        )
        self.assertEqual(str(raised), "Update FinCoach to generate this report.")

    def test_competing_claim_maps_to_action_in_progress_with_the_lease(self):
        raised = self.assert_code(
            FakeRPCError(
                "P0102",
                "Report generation is already in progress.",
                details='{"lease_expires_at":"2030-01-01T00:05:00+00:00"}',
            ),
            "action_in_progress",
        )
        self.assertEqual(raised.lease_expires_at, "2030-01-01T00:05:00+00:00")

    def test_competing_claim_without_parseable_details_stays_action_in_progress(self):
        raised = self.assert_code(
            FakeRPCError("P0102", "Report generation is already in progress.", details="not-json"),
            "action_in_progress",
        )
        self.assertIsNone(raised.lease_expires_at)

    def test_expired_attempt_maps_to_attempt_expired(self):
        self.assert_code(
            FakeRPCError("P0103", "The report attempt expired before it could be used."),
            "attempt_expired",
        )

    def test_reused_terminal_id_maps_to_attempt_id_reused(self):
        self.assert_code(
            FakeRPCError("P0104", "This report attempt can no longer be used. Start a new attempt."),
            "attempt_id_reused",
        )

    def test_unverified_artifact_maps_to_report_artifact_invalid(self):
        self.assert_code(
            FakeRPCError("P0105", "The uploaded report could not be verified."),
            "report_artifact_invalid",
        )

    def test_cancelled_action_maps_to_a_state_conflict(self):
        repository = make_repository(
            error=FakeRPCError("P0001", "This report action was cancelled. Ask for a new report."),
        )
        with self.assertRaises(ActionStateConflict) as raised:
            repository.claim_report_attempt("m1", "a1", "t1")
        self.assertIn("cancelled", str(raised.exception))

    def test_foreign_action_maps_to_not_found(self):
        repository = make_repository(error=FakeRPCError("P0002", "Action not found."))
        with self.assertRaises(MessageNotFound):
            repository.claim_report_attempt("m1", "a1", "t1")

    def test_unmapped_failure_is_re_raised(self):
        repository = make_repository(error=FakeRPCError("42601", "syntax error"))
        with self.assertRaises(FakeRPCError):
            repository.claim_report_attempt("m1", "a1", "t1")

    def test_claim_returns_the_message_and_projected_attempt(self):
        attempt_id = "00000000-0000-0000-0000-000000000321"
        repository = make_repository(data={
            "message": {"id": "m1", "ui_payload": {"status": "approved"}},
            "attempt": {
                "attempt_id": attempt_id,
                "message_id": "m1",
                "action_id": "a1",
                "status": "active",
                "storage_path": f"user-1/coach/{attempt_id}.pdf",
                "period": "monthly",
                "report_type": "monthly",
                "start_date": "2030-01-01",
                "end_date": "2030-01-31",
                "category_id": None,
                "category_name": None,
                "report_id": None,
                "lease_expires_at": "2020-12-31T00:05:00+00:00",
                "lease_owner": "user-1",
            },
        })

        message, attempt = repository.claim_report_attempt("m1", "a1", attempt_id)

        self.assertEqual(message["ui_payload"]["status"], "approved")
        self.assertEqual(attempt["attempt_id"], attempt_id)
        self.assertEqual(attempt["storage_path"], f"user-1/coach/{attempt_id}.pdf")
        # The projection exposes the server-calculated lease facts, never the
        # internal lease owner.
        self.assertNotIn("lease_owner", attempt)
        self.assertIn("server_time", attempt)
        self.assertFalse(attempt["lease_valid"])  # lease expired years ago
        repository.admin_client.rpc.assert_called_once_with(
            "claim_coach_report_attempt",
            {
                "p_user_id": "user-1",
                "p_message_id": "m1",
                "p_action_id": "a1",
                "p_attempt_id": attempt_id,
            },
        )

    def test_claim_lease_valid_is_true_for_a_live_lease(self):
        attempt_id = "00000000-0000-0000-0000-000000000321"
        repository = make_repository(data={
            "message": {"id": "m1"},
            "attempt": {
                "attempt_id": attempt_id,
                "status": "active",
                "storage_path": f"user-1/coach/{attempt_id}.pdf",
                "lease_expires_at": "2100-01-01T00:05:00+00:00",
            },
        })
        _, attempt = repository.claim_report_attempt("m1", "a1", attempt_id)
        self.assertTrue(attempt["lease_valid"])

    def test_claim_lease_valid_is_false_without_a_parseable_lease(self):
        repository = make_repository(data={
            "message": {"id": "m1"},
            "attempt": {"attempt_id": "t1", "status": "active", "lease_expires_at": "not-a-time"},
        })
        _, attempt = repository.claim_report_attempt("m1", "a1", "t1")
        self.assertFalse(attempt["lease_valid"])

    def test_executed_claim_returns_the_terminal_message_without_an_attempt(self):
        repository = make_repository(data={
            "message": {"id": "m1", "ui_payload": {"status": "executed"}},
            "attempt": None,
        })
        message, attempt = repository.claim_report_attempt("m1", "a1", "t1")
        self.assertEqual(message["ui_payload"]["status"], "executed")
        self.assertIsNone(attempt)


class CompleteProtocolTests(unittest.TestCase):
    def test_completion_forwards_the_verified_storage_identity(self):
        repository = make_repository(data=[{"id": "m1", "ui_payload": {"status": "executed"}}])
        storage = {
            "path": "user-1/coach/t1.pdf",
            "object_id": "object-1",
            "version": "v-fixture-1",
            "updated_at": "2030-01-01T00:00:00.123+00:00",
            "size": 512,
        }
        message = repository.complete_report_attempt(
            "m1", "a1", "t1",
            success=True,
            report={"title": "July report", "file_name": "July.pdf"},
            storage=storage,
        )
        self.assertEqual(message["ui_payload"]["status"], "executed")
        repository.admin_client.rpc.assert_called_once_with(
            "complete_coach_report_attempt",
            {
                "p_user_id": "user-1",
                "p_message_id": "m1",
                "p_action_id": "a1",
                "p_attempt_id": "t1",
                "p_success": True,
                "p_report": {"title": "July report", "file_name": "July.pdf"},
                "p_storage": storage,
            },
        )

    def test_artifact_refusal_maps_to_report_artifact_invalid(self):
        repository = make_repository(
            error=FakeRPCError("P0105", "The uploaded report could not be verified."),
        )
        with self.assertRaises(ActionProtocolError) as raised:
            repository.complete_report_attempt("m1", "a1", "t1", success=True)
        self.assertEqual(raised.exception.code, "report_artifact_invalid")

    def test_late_completion_maps_to_attempt_expired(self):
        repository = make_repository(
            error=FakeRPCError("P0103", "The report attempt expired before it could be used."),
        )
        with self.assertRaises(ActionProtocolError) as raised:
            repository.complete_report_attempt("m1", "a1", "t1", success=False)
        self.assertEqual(raised.exception.code, "attempt_expired")

    def test_failure_completion_does_not_require_storage(self):
        repository = make_repository(data=[{"id": "m1", "ui_payload": {"status": "failed"}}])
        message = repository.complete_report_attempt(
            "m1", "a1", "t1", success=False, report={"message": "The PDF could not be generated."},
        )
        self.assertEqual(message["ui_payload"]["status"], "failed")
        self.assertIsNone(
            repository.admin_client.rpc.call_args.args[1]["p_storage"]
        )


def fluent_table(data):
    """A table query whose chained filters keep returning the same node."""
    node = MagicMock()
    node.select.return_value = node
    node.eq.return_value = node
    node.in_.return_value = node
    node.maybe_single.return_value = node
    node.execute.return_value = SimpleNamespace(data=data, error=None)
    return node


class AttemptLookupTests(unittest.TestCase):
    def test_require_active_attempt_returns_the_row(self):
        row = {"attempt_id": "t1", "status": "active", "storage_path": "user-1/coach/t1.pdf"}
        repository = CoachingHistoryRepository(MagicMock(), MagicMock(), "user-1")
        repository.admin_client.table.return_value = fluent_table(row)
        self.assertEqual(
            repository.require_active_report_attempt("m1", "a1", "t1"), row,
        )

    def test_require_active_attempt_refuses_a_missing_row(self):
        repository = CoachingHistoryRepository(MagicMock(), MagicMock(), "user-1")
        repository.admin_client.table.return_value = fluent_table(None)
        with self.assertRaises(ActionProtocolError) as raised:
            repository.require_active_report_attempt("m1", "a1", "t1")
        self.assertEqual(raised.exception.code, "attempt_expired")

    def test_renewal_projects_the_lease_facts(self):
        from app.coaching_history import MessageNotFound

        row = {
            "attempt_id": "t1",
            "status": "active",
            "storage_path": "user-1/coach/t1.pdf",
            "lease_expires_at": "2100-01-01T00:05:00+00:00",
        }
        repository = make_repository(data=[row])
        renewed = repository.renew_report_attempt("m1", "t1")
        self.assertTrue(renewed["lease_valid"])
        self.assertIn("server_time", renewed)

        repository = make_repository(error=FakeRPCError("P0002", "lease expired"))
        with self.assertRaises(MessageNotFound):
            repository.renew_report_attempt("m1", "t1")

    def test_find_report_attempt_projects_and_returns_none_for_a_missing_row(self):
        repository = CoachingHistoryRepository(MagicMock(), MagicMock(), "user-1")
        table = fluent_table({
            "attempt_id": "t1",
            "status": "completed",
            "storage_path": "user-1/coach/t1.pdf",
            "lease_expires_at": "2100-01-01T00:05:00+00:00",
        })
        repository.admin_client.table.return_value = table
        found = repository.find_report_attempt("m1", "t1")
        self.assertEqual(found["status"], "completed")
        self.assertFalse(found["lease_valid"])  # only an active attempt can be live

        repository.admin_client.table.return_value = fluent_table(None)
        self.assertIsNone(repository.find_report_attempt("m1", "t1"))


if __name__ == "__main__":
    unittest.main()
