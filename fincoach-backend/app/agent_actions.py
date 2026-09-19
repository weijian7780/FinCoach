"""Confirmation-gated execution for durable FinCoach coach actions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from app.coaching_history import CoachingHistoryRepository


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
    ):
        self.repository = repository
        self.admin_client = admin_client
        # This is injected by the API dependency.  Keeping it explicit makes
        # the execution boundary testable and prevents an old pending card
        # from bypassing the advice-only deployment setting.
        self.writes_enabled = writes_enabled

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

    def confirm(self, message_id: str, action_id: str) -> dict:
        message, payload = self._owned_action(message_id, action_id)
        status = payload.get("status")
        if status == "executed":
            return {"message": message, "effect": None}
        self._require_writes_enabled()
        if status == "approved" and payload.get("action_type") == "generate_report":
            self._require_report_consent()
            return {
                "message": message,
                "effect": {
                    "type": "generate_report",
                    "arguments": payload.get("arguments") or {},
                },
            }
        if status == "failed" and payload.get("action_type") == "generate_report":
            self._require_report_consent()
            payload["status"] = "approved"
            updated = self.repository.update_message_ui_payload(message_id, payload)
            return {
                "message": updated,
                "effect": {
                    "type": "generate_report",
                    "arguments": payload.get("arguments") or {},
                },
            }
        if status != "pending":
            raise AgentActionConflict("This action is no longer pending.")

        if payload["action_type"] == "create_reminder":
            reminder = self._create_reminder(payload)
            payload["status"] = "executed"
            payload["result"] = {"reminder_id": reminder["id"]}
            updated = self.repository.update_message_ui_payload(message_id, payload)
            return {"message": updated, "effect": None}

        self._require_report_consent()
        payload["status"] = "approved"
        updated = self.repository.update_message_ui_payload(message_id, payload)
        return {
            "message": updated,
            "effect": {
                "type": "generate_report",
                "arguments": payload.get("arguments") or {},
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
            return {"message": message, "effect": None}
        if payload.get("status") == "executed":
            raise AgentActionConflict("An executed action cannot be cancelled.")
        payload["status"] = "cancelled"
        updated = self.repository.update_message_ui_payload(message_id, payload)
        return {"message": updated, "effect": None}

    def complete(
        self,
        message_id: str,
        action_id: str,
        *,
        success: bool,
        result: dict,
    ) -> dict:
        message, payload = self._owned_action(message_id, action_id)
        if payload.get("action_type") != "generate_report":
            raise AgentActionNotFound("Action not found.")
        if payload.get("status") == "executed":
            return {"message": message, "effect": None}
        self._require_writes_enabled()
        if payload.get("status") != "approved":
            raise AgentActionConflict("The report action has not been approved.")
        payload["status"] = "executed" if success else "failed"
        payload["result"] = result
        updated = self.repository.update_message_ui_payload(message_id, payload)
        return {"message": updated, "effect": None}

    def _require_writes_enabled(self) -> None:
        if not self.writes_enabled:
            raise AgentActionConflict(
                "AI write actions are disabled. No reminder or report was created."
            )

    def _create_reminder(self, payload: dict) -> dict:
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
            return existing
        if isinstance(existing, list) and existing:
            return existing[0]

        due_at = datetime.fromisoformat(str(arguments["due_at"]).replace("Z", "+00:00"))
        lead_days = max(0, min(30, int(arguments.get("lead_days") or 0)))
        recurrence = str(arguments.get("recurrence") or "none")
        if recurrence not in {"none", "weekly", "monthly"}:
            raise AgentActionConflict("The reminder recurrence is invalid.")
        row = {
            "id": action_id,
            "user_id": self.repository.user_id,
            "type": "bill",
            "title": str(arguments["title"]).strip(),
            "amount": arguments.get("amount"),
            "due_at": due_at.isoformat(),
            "lead_days": lead_days,
            "recurrence": recurrence,
            # The active schema requires an anchor day for every reminder shape.
            "recurrence_anchor_day": due_at.day,
            "enabled": True,
            "next_trigger_at": (due_at - timedelta(days=lead_days)).isoformat(),
        }
        rows = self._execute(
            self.admin_client.table("reminders").insert(row).select("*")
        )
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise RuntimeError("The reminder was not returned after creation.")
        return rows[0]
