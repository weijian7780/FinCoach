"""Owner-scoped coaching history and durable usage controls."""

from datetime import datetime, timedelta, timezone
from typing import Any


class ConversationNotFound(RuntimeError):
    pass


class MessageNotFound(RuntimeError):
    pass


class CoachingRateLimitExceeded(RuntimeError):
    pass


def title_from_question(question: str) -> str:
    title = " ".join(question.split()).strip()
    if len(title) <= 60:
        return title
    return title[:57].rstrip() + "..."


class CoachingHistoryRepository:
    def __init__(self, user_client: Any, admin_client: Any, user_id: str):
        self.user_client = user_client
        self.admin_client = admin_client
        self.user_id = user_id

    @staticmethod
    def _execute(query: Any) -> Any:
        response = query.execute()
        error = getattr(response, "error", None)
        if error:
            raise RuntimeError("Coaching persistence is unavailable.")
        return response

    @staticmethod
    def _single_mutation_row(response: Any) -> dict:
        rows = getattr(response, "data", None)
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise RuntimeError("Coaching persistence is unavailable.")
        return rows[0]

    @staticmethod
    def _optional_single_row(response: Any) -> dict | None:
        """Normalize PostgREST maybe_single(), which returns None for zero rows."""
        if response is None:
            return None
        row = getattr(response, "data", None)
        if row is None or row == []:
            return None
        if not isinstance(row, dict):
            raise RuntimeError("Coaching persistence is unavailable.")
        return row

    def list_sessions(self, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(50, int(limit or 50)))
        response = self._execute(
            self.user_client.table("coaching_sessions")
            .select("*")
            .eq("user_id", self.user_id)
            .order("last_message_at", desc=True)
            .limit(safe_limit)
        )
        return response.data or []

    def require_session(self, session_id: str) -> dict:
        response = self._execute(
            self.user_client.table("coaching_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", self.user_id)
            .maybe_single()
        )
        session = self._optional_single_row(response)
        if not session:
            raise ConversationNotFound("Conversation not found.")
        return session

    def create_session(self, title: str = "New conversation") -> dict:
        response = self._execute(
            self.user_client.table("coaching_sessions")
            .insert({"user_id": self.user_id, "title": title.strip()})
            .select("*")
        )
        return self._single_mutation_row(response)

    def rename_session(self, session_id: str, title: str) -> dict:
        self.require_session(session_id)
        response = self._execute(
            self.user_client.table("coaching_sessions")
            .update({"title": title.strip()})
            .eq("id", session_id)
            .eq("user_id", self.user_id)
            .select("*")
        )
        return self._single_mutation_row(response)

    def delete_session(self, session_id: str) -> None:
        self.require_session(session_id)
        self._execute(
            self.user_client.table("coaching_sessions")
            .delete()
            .eq("id", session_id)
            .eq("user_id", self.user_id)
        )

    def list_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        self.require_session(session_id)
        safe_limit = max(1, min(100, int(limit or 100)))
        response = self._execute(
            self.user_client.table("coaching_messages")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", self.user_id)
            .order("created_at", desc=True)
            .limit(safe_limit)
        )
        # Limit newest-first in SQL, then restore chronological display/prompt order.
        return list(reversed(response.data or []))

    def list_message_page(
        self,
        session_id: str,
        *,
        limit: int = 30,
        before: str | None = None,
    ) -> dict:
        """Return one newest-first cursor page in chronological display order."""
        self.require_session(session_id)
        safe_limit = max(1, min(30, int(limit or 30)))
        query = (
            self.user_client.table("coaching_messages")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", self.user_id)
        )
        if before:
            query = query.lt("created_at", before)
        rows = self._execute(
            query.order("created_at", desc=True).limit(safe_limit + 1)
        ).data or []
        has_more = len(rows) > safe_limit
        messages = list(reversed(rows[:safe_limit]))
        return {
            "messages": messages,
            "next_before": messages[0].get("created_at") if has_more and messages else None,
        }

    def insert_user_message(self, session_id: str, message_id: str, content: str) -> dict:
        self.require_session(session_id)
        response = self._execute(
            self.user_client.table("coaching_messages")
            .insert({
                "id": message_id,
                "session_id": session_id,
                "user_id": self.user_id,
                "role": "user",
                "content": content,
                "status": "completed",
            })
            .select("*")
        )
        return self._single_mutation_row(response)

    def find_user_message(self, message_id: str) -> dict | None:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .select("*")
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "user")
            .maybe_single()
        )
        return self._optional_single_row(response)

    def find_reply(self, message_id: str) -> dict | None:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .select("*")
            .eq("reply_to_message_id", message_id)
            .eq("user_id", self.user_id)
            .maybe_single()
        )
        return self._optional_single_row(response)

    def mark_user_message_failed(self, message_id: str, error_code: str) -> dict:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .update({"status": "failed", "error_code": error_code})
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "user")
            .select("*")
        )
        return self._single_mutation_row(response)

    def claim_failed_user_message(self, message_id: str) -> dict | None:
        """Atomically allow one retry to move a failed message back into processing."""
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .update({"status": "completed", "error_code": None})
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "user")
            .eq("status", "failed")
            .select("*")
        )
        rows = getattr(response, "data", None)
        if rows == []:
            return None
        return self._single_mutation_row(response)

    def insert_assistant_reply(self, payload: dict) -> dict:
        response = self._execute(
            self.admin_client.table("coaching_messages").insert(payload).select("*")
        )
        return self._single_mutation_row(response)

    def insert_retrievals(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        response = self._execute(
            self.admin_client.table("coaching_retrievals").insert(rows).select("*")
        )
        return response.data or []

    def complete_turn(
        self,
        *,
        session_id: str,
        user_message_id: str,
        assistant_payload: dict,
        retrieval_rows: list[dict],
        title: str | None,
    ) -> dict:
        """Atomically persist the completed reply, provenance, and session state."""
        response = self._execute(
            self.admin_client.rpc(
                "complete_coaching_turn",
                {
                    "p_user_id": self.user_id,
                    "p_session_id": session_id,
                    "p_user_message_id": user_message_id,
                    "p_assistant_message": assistant_payload,
                    "p_retrievals": retrieval_rows,
                    "p_title": title_from_question(title) if title else None,
                },
            )
        )
        return self._single_mutation_row(response)

    def list_retrievals(self, assistant_message_id: str) -> list[dict]:
        response = self._execute(
            self.user_client.table("coaching_retrievals")
            .select("title, source, similarity, rank")
            .eq("assistant_message_id", assistant_message_id)
            .eq("user_id", self.user_id)
            .order("rank", desc=False)
        )
        return response.data or []

    def list_retrievals_for_messages(self, assistant_message_ids: list[str]) -> list[dict]:
        """Load all visible assistant-message sources in one owner-scoped query."""
        message_ids = list(dict.fromkeys(str(item) for item in assistant_message_ids if item))
        if not message_ids:
            return []
        response = self._execute(
            self.user_client.table("coaching_retrievals")
            .select("assistant_message_id, title, source, similarity, rank")
            .eq("user_id", self.user_id)
            .in_("assistant_message_id", message_ids)
            .order("rank", desc=False)
        )
        return response.data or []

    def set_message_feedback(self, message_id: str, feedback: str | None) -> dict:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .update({"feedback": feedback})
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "assistant")
            .select("*")
        )
        if getattr(response, "data", None) == []:
            raise MessageNotFound("Message not found.")
        return self._single_mutation_row(response)

    def require_interaction_message(self, message_id: str) -> dict:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .select("*")
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "assistant")
            .maybe_single()
        )
        message = self._optional_single_row(response)
        if not message or not isinstance(message.get("ui_payload"), dict):
            raise MessageNotFound("Action not found.")
        return message

    def require_action_message(self, message_id: str) -> dict:
        return self.require_interaction_message(message_id)

    def update_message_ui_payload(self, message_id: str, ui_payload: dict) -> dict:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .update({"ui_payload": ui_payload})
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "assistant")
            .select("*")
        )
        if getattr(response, "data", None) == []:
            raise MessageNotFound("Action not found.")
        return self._single_mutation_row(response)

    def update_session_after_message(self, session_id: str, title: str | None = None) -> dict:
        values: dict[str, Any] = {"last_message_at": datetime.now(timezone.utc).isoformat()}
        if title:
            values["title"] = title_from_question(title)
        response = self._execute(
            self.admin_client.table("coaching_sessions")
            .update(values)
            .eq("id", session_id)
            .eq("user_id", self.user_id)
            .select("*")
        )
        return self._single_mutation_row(response)

    def enforce_usage_limits(self, minute_limit: int, daily_limit: int) -> None:
        now = datetime.now(timezone.utc)
        windows = (
            (now - timedelta(minutes=1), minute_limit),
            (now.replace(hour=0, minute=0, second=0, microsecond=0), daily_limit),
        )
        for since, limit in windows:
            response = self._execute(
                self.admin_client.table("coaching_messages")
                .select("id", count="exact", head=True)
                .eq("user_id", self.user_id)
                .eq("role", "user")
                .gte("created_at", since.isoformat())
            )
            if int(response.count or 0) >= limit:
                raise CoachingRateLimitExceeded("Coaching message limit reached. Please try again later.")
