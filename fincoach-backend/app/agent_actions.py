"""Confirmation-gated execution for durable FinCoach coach actions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.coaching_history import (
    ActionProtocolError,
    ActionStateConflict,
    CoachingHistoryRepository,
)
from app.report_artifacts import (
    ReportArtifactInvalid,
    ReportArtifactVerifier,
    default_report_artifact_verifier,
)


class AgentActionNotFound(RuntimeError):
    pass


class AgentActionConflict(RuntimeError):
    pass


class AgentActionService:
    def __init__(
        self,
        repository: CoachingHistoryRepository,
        admin_client: Any,
        *,
        writes_enabled: bool = True,
        artifact_verifier: ReportArtifactVerifier | None = None,
    ):
        self.repository = repository
        self.admin_client = admin_client
        # This is injected by the API dependency.  Keeping it explicit makes
        # the execution boundary testable and prevents an old pending card
        # from bypassing the advice-only deployment setting.
        self.writes_enabled = writes_enabled
        self.artifact_verifier = artifact_verifier

    @staticmethod
    def _execute(query: Any) -> Any:
        response = query.execute()
        error = getattr(response, "error", None)
        if error:
            raise RuntimeError("The FinCoach action could not be completed.")
        return getattr(response, "data", None)

    def _owned_action(self, message_id: str, action_id: str) -> tuple[dict, dict]:
        message = self.repository.require_action_message(message_id)
        payload = deepcopy(message.get("ui_payload") or {})
        if (
            payload.get("type") != "action"
            or str(payload.get("action_id")) != str(action_id)
        ):
            raise AgentActionNotFound("Action not found.")
        if payload.get("action_type") not in {"create_reminder", "generate_report"}:
            raise AgentActionNotFound("Action not found.")
        return message, payload

    def _commit(self, message: dict, payload: dict, *, reminder: dict | None = None) -> dict:
        # The database compares the exact state read above while holding its
        # row lock. A cancelled card cannot later be overwritten by an old
        # confirmation, and reminder creation/status change commit together.
        try:
            return self.repository.commit_action(
                message["id"], message["ui_payload"], payload, reminder=reminder,
            )
        except ActionStateConflict as error:
            raise AgentActionConflict(str(error)) from error

    @staticmethod
    def _require_report_attempt(attempt_id: str | None) -> str:
        # Without the device-reserved attempt id there is nothing to resume and
        # no reserved path to verify; older builds must be told to update.
        if not attempt_id:
            raise ActionProtocolError(
                "update_required",
                "Update FinCoach to generate this report.",
                status_code=426,
            )
        return attempt_id

    def confirm(self, message_id: str, action_id: str, *,
                attempt_id: str | None = None) -> dict:
        message, payload = self._owned_action(message_id, action_id)
        status = payload.get("status")
        if status == "executed":
            return {"message": message, "effect": None}
        self._require_writes_enabled()

        if payload["action_type"] == "create_reminder":
            if status != "pending":
                raise AgentActionConflict("This action is no longer pending.")
            reminder, needs_insert = self._prepare_reminder(payload)
            payload["status"] = "executed"
            payload["result"] = {"reminder_id": reminder["id"]}
            updated = self._commit(message, payload, reminder=reminder if needs_insert else None)
            return {"message": updated, "effect": None}

        if status not in {"pending", "failed", "approved"}:
            raise AgentActionConflict("This action is no longer pending.")
        attempt_id = self._require_report_attempt(attempt_id)
        self._require_report_consent()
        # Every confirmation starts, resumes, replaces or refuses the one live
        # attempt inside the same transaction that approves the card. The
        # returned attempt is the only one this device may render and upload.
        updated, attempt = self.repository.claim_report_attempt(
            message_id, str(payload["action_id"]), attempt_id,
        )
        self._discard_abandoned_artifacts(message_id, action_id)
        if not isinstance(attempt, dict):
            # The action was already executed on another device; its terminal
            # result comes from the message itself.
            return {"message": updated, "effect": None}
        return {
            "message": updated,
            "effect": {
                "type": "generate_report",
                "arguments": (updated.get("ui_payload") or {}).get("arguments") or {},
                "attempt": attempt,
            },
        }

    def _require_report_consent(self) -> None:
        profile = self._execute(
            self.admin_client.table("profiles")
            .select("spending_records_consent")
            .eq("id", self.repository.user_id)
            .maybe_single()
        )
        if not isinstance(profile, dict) or profile.get("spending_records_consent") != "granted":
            raise AgentActionConflict(
                "Spending-record permission is required before generating this report."
            )

    def cancel(self, message_id: str, action_id: str) -> dict:
        message, payload = self._owned_action(message_id, action_id)
        if payload.get("status") == "cancelled":
            if payload.get("action_type") == "generate_report":
                # A previously authorised upload may have arrived after the
                # first cancellation's cleanup. Terminal replay retries safely.
                self._discard_abandoned_artifacts(message_id, action_id)
            return {"message": message, "effect": None}
        if payload.get("status") == "executed":
            raise AgentActionConflict("An executed action cannot be cancelled.")
        payload["status"] = "cancelled"
        updated = self._commit(message, payload)
        if payload.get("action_type") == "generate_report":
            # The database cancelled the live attempt in the same commit, so any
            # reserved file that no saved report references is now abandoned.
            self._discard_abandoned_artifacts(message_id, action_id)
        return {"message": updated, "effect": None}

    def complete(
        self,
        message_id: str,
        action_id: str,
        *,
        success: bool,
        result: dict,
        attempt_id: str | None = None,
    ) -> dict:
        message, payload = self._owned_action(message_id, action_id)
        if payload.get("action_type") != "generate_report":
            raise AgentActionNotFound("Action not found.")
        if payload.get("status") == "executed":
            # A repeated success after the action already executed returns the
            # existing report; it never writes a second history row.
            return {"message": message, "effect": None}
        self._require_writes_enabled()
        if payload.get("status") != "approved":
            raise AgentActionConflict("The report action has not been approved.")
        attempt_id = self._require_report_attempt(attempt_id)
        if success:
            # Only the display fields come from the device; the storage path,
            # identity and history row are derived from the attempt the database
            # still recognises as live.
            report = self._report_metadata(result)
            attempt = self.repository.require_active_report_attempt(
                message_id, action_id, attempt_id,
            )
            try:
                storage = self._artifact_verifier().verify(
                    user_id=self.repository.user_id, attempt=attempt,
                )
            except ReportArtifactInvalid as error:
                raise ActionProtocolError(
                    "report_artifact_invalid", str(error),
                ) from error
            updated = self.repository.complete_report_attempt(
                message_id, action_id, attempt_id,
                success=True, report=report, storage=storage,
            )
        else:
            updated = self.repository.complete_report_attempt(
                message_id, action_id, attempt_id,
                success=False, report=result,
            )
        # Failure or supersession leaves nobody able to publish this attempt.
        self._discard_abandoned_artifacts(message_id, action_id)
        return {"message": updated, "effect": None}

    def _artifact_verifier(self) -> ReportArtifactVerifier:
        if self.artifact_verifier is None:
            self.artifact_verifier = default_report_artifact_verifier()
        return self.artifact_verifier

    @staticmethod
    def _report_metadata(result: dict) -> dict:
        """Keep only the device-rendered display fields the history row needs."""
        metadata = {key: result.get(key) for key in ("title", "file_name", "generated_at")}
        if not all(isinstance(value, str) and value.strip() for value in metadata.values()):
            raise AgentActionConflict("The generated report metadata is invalid.")
        return {key: value.strip() for key, value in metadata.items()}

    def _discard_abandoned_artifacts(self, message_id: str, action_id: str) -> None:
        """Best-effort removal of reserved PDFs whose attempts can no longer publish."""
        try:
            attempts = self._execute(self.admin_client.rpc('list_abandoned_coach_report_artifacts', {
                'p_user_id': self.repository.user_id,
                'p_message_id': message_id, 'p_action_id': action_id,
            }))
            if not isinstance(attempts, list):
                return
            # The SQL checks every history reference rather than a possibly
            # truncated REST result page. Only canonical reserved paths delete.
            paths = sorted({row['storage_path'] for row in attempts
                if isinstance(row, dict) and row.get('user_id') == self.repository.user_id
                and row.get('storage_path') == f"{self.repository.user_id}/coach/{row.get('attempt_id')}.pdf"})
            if paths:
                self.admin_client.storage.from_('financial-reports').remove(paths)
        except Exception:
            # The bounded background sweep retries late uploads and failures.
            pass

    def _require_writes_enabled(self) -> None:
        if not self.writes_enabled:
            raise AgentActionConflict(
                "AI write actions are disabled. No reminder or report was created."
            )

    def _prepare_reminder(self, payload: dict) -> tuple[dict, bool]:
        arguments = payload.get("arguments") or {}
        action_id = str(payload["action_id"])
        existing = self._execute(
            self.admin_client.table("reminders")
            .select("*")
            .eq("id", action_id)
            .eq("user_id", self.repository.user_id)
            .maybe_single()
        )
        if isinstance(existing, dict):
            return existing, False
        if isinstance(existing, list) and existing:
            return existing[0], False

        try:
            due_at = datetime.fromisoformat(str(arguments["due_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError) as error:
            raise AgentActionConflict("The reminder date and time are invalid.") from error
        malaysia = ZoneInfo("Asia/Kuala_Lumpur")
        due_at = (due_at.replace(tzinfo=malaysia) if due_at.tzinfo is None else due_at.astimezone(malaysia))
        if due_at <= datetime.now(timezone.utc):
            raise AgentActionConflict("The reminder date and time must still be in the future.")
        amount = arguments.get("amount")
        if amount is not None:
            try:
                decimal_amount = Decimal(str(amount))
                if (
                    not decimal_amount.is_finite() or decimal_amount <= 0
                    or decimal_amount > Decimal("9999999999.99")
                    or decimal_amount != decimal_amount.quantize(Decimal("0.01"))
                ):
                    raise ValueError("Invalid amount")
            except (InvalidOperation, ValueError, TypeError) as error:
                raise AgentActionConflict("The reminder amount must be positive and have at most two decimal places.") from error
            amount = float(decimal_amount)
        lead_days = max(0, min(30, int(arguments.get("lead_days") or 0)))
        recurrence = str(arguments.get("recurrence") or "none")
        if recurrence not in {"none", "weekly", "monthly"}:
            raise AgentActionConflict("The reminder recurrence is invalid.")
        row = {
            "id": action_id,
            "user_id": self.repository.user_id,
            "type": "bill",
            "title": str(arguments["title"]).strip(),
            "amount": amount,
            "due_at": due_at.isoformat(),
            "lead_days": lead_days,
            "recurrence": recurrence,
            # The active schema requires an anchor day for every reminder shape.
            "recurrence_anchor_day": arguments.get("recurrence_anchor_day") or due_at.day,
            "enabled": True,
            "next_trigger_at": (due_at - timedelta(days=lead_days)).isoformat(),
        }
        return row, True
