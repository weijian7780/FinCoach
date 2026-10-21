"""Action boundary regressions using real preparation and execution logic."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.agent_actions import AgentActionConflict, AgentActionService
from app.coaching_history import ActionStateConflict
import test_agent_actions as action_fixtures
import test_agent_tools as tool_fixtures


def reminder_service(arguments, *, existing=None):
    message = action_fixtures.AgentActionServiceTests().action_message()
    message["ui_payload"]["arguments"].update(arguments)
    repository = MagicMock(user_id="verified-user")
    repository.require_action_message.return_value = message
    lookup = action_fixtures.MutationQuery(existing)
    insert = action_fixtures.MutationQuery([{"id": message["ui_payload"]["action_id"]}])
    def commit(_id, _expected, payload, *, reminder=None, **_kwargs):
        insert.insert_payload = reminder
        return {**message, "ui_payload": payload}
    repository.commit_action.side_effect = commit
    admin = MagicMock()
    admin.table.side_effect = [lookup, insert]
    return AgentActionService(repository, admin), message, insert


def confirm(service, message):
    return service.confirm(message["id"], message["ui_payload"]["action_id"])


def test_confirmation_anchors_utc_date_to_the_shown_malaysia_day():
    service, message, insert = reminder_service({"due_at": "2030-01-31T16:30:00Z"})
    result = confirm(service, message)
    assert result["message"]["ui_payload"]["status"] == "executed"
    assert insert.insert_payload["recurrence_anchor_day"] == 1
    assert insert.insert_payload["due_at"] == "2030-02-01T00:30:00+08:00"


def test_confirmation_rejects_a_card_that_expired_while_waiting():
    service, message, insert = reminder_service({"due_at": "2026-07-24T17:59:00+08:00"})
    with patch("app.agent_actions.datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc)
        with pytest.raises(AgentActionConflict, match="future"):
            confirm(service, message)
    assert insert.insert_payload is None


def test_completed_reminder_recovers_even_after_its_due_time():
    service, message, insert = reminder_service(
        {"due_at": "2020-01-31T16:30:00Z"}, existing={"id": "saved-reminder"},
    )
    result = confirm(service, message)
    assert result["message"]["ui_payload"]["result"] == {"reminder_id": "saved-reminder"}
    assert insert.insert_payload is None


@pytest.mark.parametrize("amount", ["0.001", "10.005", "10000000000"])
def test_preparation_rejects_money_the_reminder_column_cannot_store_exactly(amount):
    executor, _ = tool_fixtures.AgentToolExecutorTests().make_executor()
    result = executor.execute("prepare_reminder", {
        "title": "Rent", "due_at": "2030-02-01T20:00:00+08:00", "amount": amount,
    })
    assert result["status"] == "invalid_arguments"
    assert "ui_payload" not in result


@pytest.mark.parametrize("amount", ["0.001", "10.005", "10000000000"])
def test_confirmation_revalidates_money_in_preexisting_cards(amount):
    service, message, insert = reminder_service({
        "due_at": "2030-02-01T20:00:00+08:00", "amount": amount,
    })
    with pytest.raises(AgentActionConflict, match="amount"):
        confirm(service, message)
    assert insert.insert_payload is None


def test_date_options_use_malaysia_day_at_utc_month_boundary():
    executor, _ = tool_fixtures.AgentToolExecutorTests().make_executor(
        now=lambda: datetime(2026, 1, 31, 16, 30, tzinfo=timezone.utc),
    )
    result = executor.execute("prepare_reminder", {"title": "Rent"})
    options = {row["id"]: row["value"] for row in result["ui_payload"]["options"]}
    assert options["today"] == "2026-02-01"
    assert options["tomorrow"] == "2026-02-02"


@pytest.mark.parametrize("period,start,end", [
    ("current_month", "2026-02-01", "2026-02-28"),
    ("last_month", "2026-01-01", "2026-01-31"),
    ("last_3_months", "2025-12-01", "2026-02-28"),
])
def test_report_presets_use_malaysia_calendar_month(period, start, end):
    executor, _ = tool_fixtures.AgentToolExecutorTests().make_executor(
        {"profiles": {"spending_records_consent": "granted"}},
        now=lambda: datetime(2026, 1, 31, 16, 30, tzinfo=timezone.utc),
    )
    result = executor.execute("prepare_report", {"period": period})
    assert result["ui_payload"]["arguments"]["start_date"] == start
    assert result["ui_payload"]["arguments"]["end_date"] == end


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 2, 1, tzinfo=timezone.utc), "2026-02-28T20:00:00+08:00"),
    (datetime(2028, 2, 1, tzinfo=timezone.utc), "2028-02-29T20:00:00+08:00"),
    (datetime(2026, 12, 31, 13, tzinfo=timezone.utc), "2027-01-31T20:00:00+08:00"),
])
def test_monthly_day_31_clamps_short_month_but_preserves_recurrence_anchor(now, expected):
    executor, _ = tool_fixtures.AgentToolExecutorTests().make_executor(now=lambda: now)
    result = executor.execute("prepare_reminder", {
        "title": "Rent", "day_of_month": 31, "time_of_day": "20:00", "recurrence": "monthly",
    })
    assert result["status"] == "confirmation_required"
    assert result["ui_payload"]["arguments"]["due_at"] == expected
    assert result["ui_payload"]["arguments"]["recurrence_anchor_day"] == 31


def test_confirmation_keeps_day_31_anchor_after_february_clamp():
    service, message, insert = reminder_service({
        "due_at": "2030-02-28T20:00:00+08:00", "recurrence_anchor_day": 31,
    })
    confirm(service, message)
    assert insert.insert_payload["recurrence_anchor_day"] == 31


@pytest.mark.parametrize("result,allowed", [
    ({"title": "July report", "file_name": "FinCoach_July_report.pdf", "generated_at": "2026-07-24T00:00:00Z"}, True),
    ({"title": " ", "file_name": "FinCoach_July_report.pdf", "generated_at": "2026-07-24T00:00:00Z"}, False),
    ({"title": "July report", "file_name": None, "generated_at": "2026-07-24T00:00:00Z"}, False),
    ({"title": "July report", "file_name": "FinCoach_July_report.pdf", "generated_at": 1753315200}, False),
])
def test_report_success_accepts_only_string_display_metadata(result, allowed):
    message = action_fixtures.AgentActionServiceTests().action_message(
        status="approved", action_type="generate_report",
    )
    message["ui_payload"]["arguments"] = {
        "start_date": "2026-07-01", "end_date": "2026-07-31", "category_name": None,
    }
    attempt_id = "00000000-0000-0000-0000-00000000042a"
    attempt = action_fixtures.report_attempt(attempt_id=attempt_id)
    repository = MagicMock(user_id="verified-user")
    repository.require_action_message.return_value = message
    repository.require_active_report_attempt.return_value = attempt
    repository.complete_report_attempt.side_effect = lambda _id, _action, _attempt, **_kwargs: {
        **message, "ui_payload": {**message["ui_payload"], "status": "executed"},
    }
    storage = {"path": attempt["storage_path"], "object_id": "object-1",
               "version": "v-1", "updated_at": "2030-01-01T00:00:00+00:00", "size": 512}
    verifier = MagicMock()
    verifier.verify.return_value = storage
    service = AgentActionService(repository, MagicMock(), artifact_verifier=verifier)
    def complete():
        return service.complete(
            message["id"], message["ui_payload"]["action_id"], success=True,
            attempt_id=attempt_id,
            # A device can name the PDF it rendered, but never its stored path,
            # period, category, or history key.
            result={**result, "report_id": 42, "storage_path": "someone-else/fake.pdf"},
        )
    if allowed:
        completed = complete()["message"]["ui_payload"]
        assert completed["status"] == "executed"
        kwargs = repository.complete_report_attempt.call_args.kwargs
        assert kwargs["report"] == result
        assert kwargs["storage"] == storage
        verifier.verify.assert_called_once_with(user_id="verified-user", attempt=attempt)
    else:
        with pytest.raises(AgentActionConflict, match="metadata"):
            complete()
        repository.complete_report_attempt.assert_not_called()
        verifier.verify.assert_not_called()


def test_report_completion_publishes_only_through_the_single_attempt_transaction():
    """The history row is written by the completing transaction, not verified after it."""
    message = action_fixtures.AgentActionServiceTests().action_message(
        status="approved", action_type="generate_report",
    )
    attempt_id = "00000000-0000-0000-0000-00000000042b"
    attempt = action_fixtures.report_attempt(attempt_id=attempt_id)
    repository = MagicMock(user_id="verified-user")
    repository.require_action_message.return_value = message
    repository.require_active_report_attempt.return_value = attempt
    repository.complete_report_attempt.return_value = {
        **message,
        "ui_payload": {
            **message["ui_payload"], "status": "executed",
            "result": {"report_id": 7, "storage_path": attempt["storage_path"], "title": "July report"},
        },
    }
    verifier = MagicMock()
    verifier.verify.return_value = {
        "path": attempt["storage_path"], "object_id": "object-1", "version": "v-1",
        "updated_at": "2030-01-01T00:00:00+00:00", "size": 512,
    }
    service = AgentActionService(repository, MagicMock(), artifact_verifier=verifier)

    completed = service.complete(
        message["id"], message["ui_payload"]["action_id"], success=True,
        attempt_id=attempt_id,
        result={
            "title": "July report",
            "file_name": "FinCoach_July_report.pdf",
            "generated_at": "2026-07-24T00:00:00Z",
        },
    )

    assert completed["message"]["ui_payload"]["status"] == "executed"
    repository.require_active_report_attempt.assert_called_once_with(
        message["id"], message["ui_payload"]["action_id"], attempt_id,
    )
    repository.complete_report_attempt.assert_called_once_with(
        message["id"], message["ui_payload"]["action_id"], attempt_id,
        success=True,
        report={
            "title": "July report",
            "file_name": "FinCoach_July_report.pdf",
            "generated_at": "2026-07-24T00:00:00Z",
        },
        storage=verifier.verify.return_value,
    )


def test_advice_only_mode_still_allows_cancelling_pending_cards():
    service, message, insert = reminder_service({})
    service.writes_enabled = False
    result = service.cancel(message["id"], message["ui_payload"]["action_id"])
    assert result["message"]["ui_payload"]["status"] == "cancelled"
    assert result["effect"] is None
    assert insert.insert_payload is None


def test_stale_confirmation_returns_conflict_without_claiming_success():
    service, message, insert = reminder_service({"due_at": "2030-02-01T20:00:00+08:00"})
    service.repository.commit_action.side_effect = ActionStateConflict("Action state changed.")
    with pytest.raises(AgentActionConflict, match="state changed"):
        confirm(service, message)
    assert insert.insert_payload is None
    assert message["ui_payload"]["status"] == "pending"


@pytest.mark.parametrize("status,operation", [
    ("cancelled", "confirm"), ("executed", "cancel"),
    ("cancelled", "complete"), ("pending", "complete"), ("failed", "complete"),
])
def test_terminal_and_unapproved_actions_cannot_cross_confirmation_boundary(status, operation):
    message = action_fixtures.AgentActionServiceTests().action_message(
        status=status, action_type="generate_report",
    )
    repository = MagicMock(user_id="verified-user")
    repository.require_action_message.return_value = message
    service = AgentActionService(repository, MagicMock())
    arguments = (message["id"], message["ui_payload"]["action_id"])
    with pytest.raises(AgentActionConflict):
        if operation == "complete":
            service.complete(*arguments, success=True, result={"report_id": 42})
        else:
            getattr(service, operation)(*arguments)
    repository.commit_action.assert_not_called()
    repository.claim_report_attempt.assert_not_called()
    repository.complete_report_attempt.assert_not_called()


def test_report_completion_ignores_smuggled_selection_and_verification_fields():
    """The period, category scope, path and history key come from the attempt."""
    message = action_fixtures.AgentActionServiceTests().action_message(
        status="approved", action_type="generate_report",
    )
    message["ui_payload"]["arguments"] = {
        "start_date": "2026-07-01", "end_date": "2026-07-31", "category_name": "Food",
    }
    attempt_id = "00000000-0000-0000-0000-000000000430"
    attempt = action_fixtures.report_attempt(
        attempt_id=attempt_id, report_type="monthly_category",
        category_id=9, category_name="Food",
    )
    repository = MagicMock(user_id="verified-user")
    repository.require_action_message.return_value = message
    repository.require_active_report_attempt.return_value = attempt
    repository.complete_report_attempt.return_value = {
        **message,
        "ui_payload": {
            **message["ui_payload"], "status": "executed",
            "result": {"report_id": 7, "storage_path": attempt["storage_path"]},
        },
    }
    verifier = MagicMock()
    verifier.verify.return_value = {
        "path": attempt["storage_path"], "object_id": "object-1", "version": "v-1",
        "updated_at": "2030-01-01T00:00:00+00:00", "size": 512,
    }
    service = AgentActionService(repository, MagicMock(), artifact_verifier=verifier)

    completed = service.complete(
        message["id"], message["ui_payload"]["action_id"], success=True,
        attempt_id=attempt_id,
        result={
            "title": "July Food report",
            "file_name": "FinCoach_July_Food_report.pdf",
            "generated_at": "2026-07-24T00:00:00Z",
            "category_name": "Transport",
            "category_id": 8,
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
            "report_id": 999,
            "storage_path": "someone-else/fake.pdf",
        },
    )

    assert completed["message"]["ui_payload"]["status"] == "executed"
    assert repository.complete_report_attempt.call_args.kwargs["report"] == {
        "title": "July Food report",
        "file_name": "FinCoach_July_Food_report.pdf",
        "generated_at": "2026-07-24T00:00:00Z",
    }
    # The verified storage payload is exactly what the backend looked up; the
    # attempt must still be the owner's active reserved row.
    verifier.verify.assert_called_once_with(user_id="verified-user", attempt=attempt)
    assert (
        repository.complete_report_attempt.call_args.kwargs["storage"]
        == verifier.verify.return_value
    )
