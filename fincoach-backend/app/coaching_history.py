"""Owner-scoped coaching history and durable usage controls."""

from datetime import datetime, timedelta, timezone
from typing import Any


class ConversationNotFound(RuntimeError):
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
        if not response.data:
            raise ConversationNotFound("Conversation not found.")
        return response.data

    def create_session(self, title: str = "New conversation") -> dict:
        response = self._execute(
            self.user_client.table("coaching_sessions")
            .insert({"user_id": self.user_id, "title": title.strip()})
            .select("*")
            .single()
        )
        return response.data

    def rename_session(self, session_id: str, title: str) -> dict:
        self.require_session(session_id)
        response = self._execute(
            self.user_client.table("coaching_sessions")
            .update({"title": title.strip()})
            .eq("id", session_id)
            .eq("user_id", self.user_id)
            .select("*")
            .single()
        )
        return response.data

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
            .order("created_at", desc=False)
            .limit(safe_limit)
        )
        return response.data or []

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
            .single()
        )
        return response.data

    def find_user_message(self, message_id: str) -> dict | None:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .select("*")
            .eq("id", message_id)
            .eq("user_id", self.user_id)
            .eq("role", "user")
            .maybe_single()
        )
        return response.data

    def find_reply(self, message_id: str) -> dict | None:
        response = self._execute(
            self.admin_client.table("coaching_messages")
            .select("*")
            .eq("reply_to_message_id", message_id)
            .eq("user_id", self.user_id)
            .maybe_single()
        )
        return response.data

    def insert_assistant_reply(self, payload: dict) -> dict:
        response = self._execute(
            self.admin_client.table("coaching_messages").insert(payload).select("*").single()
        )
        return response.data

    def insert_retrievals(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        response = self._execute(
            self.admin_client.table("coaching_retrievals").insert(rows).select("*")
        )
        return response.data or []

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
            .single()
        )
        return response.data

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
