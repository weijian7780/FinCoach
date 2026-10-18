"""Owner-scoped coaching history and durable usage controls."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4


class ConversationNotFound(RuntimeError):
    pass


class MessageNotFound(RuntimeError):
    pass


class ActionStateConflict(RuntimeError):
    pass


class ActionProtocolError(RuntimeError):
    """A report protocol refusal the client must resolve by its stable code.

    `status_code` is the HTTP status the API returns; `lease_expires_at` is the
    competing device's live lease when the code is `action_in_progress`.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        lease_expires_at: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.lease_expires_at = lease_expires_at


class CoachingRateLimitExceeded(RuntimeError):
    pass


# One attempt is one reserved PDF path; every reader sees the same projection so
# the mobile can reconcile a lost response without learning internal lease data.
REPORT_ATTEMPT_FIELDS = (
    "attempt_id,message_id,action_id,status,storage_path,period,report_type,"
    "start_date,end_date,category_id,category_name,report_id"
).split(",")
REPORT_ATTEMPT_COLUMNS = ",".join([*REPORT_ATTEMPT_FIELDS, "lease_expires_at"])


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant



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
        self._processing_tokens: dict[str, str] = {}

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
            try:
                timestamp, separator, identifier = before.partition('|')
                instant = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if instant.tzinfo is None:
                    raise ValueError('Timezone required')
                timestamp = instant.isoformat()
                if separator:
                    identifier = str(UUID(identifier))
            except (ValueError, TypeError) as error:
                raise ValueError('Invalid history cursor.') from error
            if separator:
                # A timestamp alone skips messages committed at the same instant.
                query = query.or_(f'created_at.lt.{timestamp},and(created_at.eq.{timestamp},id.lt.{identifier})')
            else:
                query = query.lt('created_at', timestamp)
        rows = self._execute(
            query.order("created_at", desc=True).order('id', desc=True).limit(safe_limit + 1)
        ).data or []
        has_more = len(rows) > safe_limit
        messages = list(reversed(rows[:safe_limit]))
        return {
            "messages": messages,
            "next_before": f"{messages[0]['created_at']}|{messages[0]['id']}" if has_more and messages else None,
        }

    def _claim_message(self, message_id: str, session_id: str | None = None, content: str | None = None) -> dict | None:
        token = str(uuid4())
        response = self._execute(self.admin_client.rpc("claim_coaching_message", {
            "p_user_id": self.user_id, "p_message_id": message_id, "p_token": token,
            "p_session_id": session_id, "p_content": content,
        }))
        if response.data == []:
            return None
        row = self._single_mutation_row(response)
        self._processing_tokens[message_id] = token
        return row

    def insert_user_message(self, session_id: str, message_id: str, content: str) -> dict | None:
        return self._claim_message(message_id, session_id, content)

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

    def mark_user_message_failed(self, message_id: str, error_code: str) -> dict | None:
        token = self._processing_tokens.get(message_id)
        if not token:
            return None
        response = self._execute(self.admin_client.rpc("fail_coaching_message", {
            "p_user_id": self.user_id, "p_message_id": message_id,
            "p_token": token, "p_error_code": error_code,
        }))
        return self._single_mutation_row(response) if response.data else None

    def claim_failed_user_message(self, message_id: str) -> dict | None:
        """Claim a failed or expired request; active workers keep their lease."""
        return self._claim_message(message_id)

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
                "complete_coaching_turn_leased",
                {
                    "p_user_id": self.user_id,
                    "p_session_id": session_id,
                    "p_user_message_id": user_message_id,
                    "p_token": self._processing_tokens.get(user_message_id),
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

    @staticmethod
    def _report_protocol_error(error: Exception) -> "ActionProtocolError | None":
        """Translate the database's protocol SQLSTATEs into stable client codes."""
        code = getattr(error, "code", None)
        message = str(getattr(error, "message", None) or error)
        if code == "P0101":
            return ActionProtocolError("update_required", message, status_code=426)
        if code == "P0102":
            lease_expires_at = None
            details = getattr(error, "details", None)
            if isinstance(details, str) and details.strip():
                try:
                    parsed = json.loads(details)
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict):
                    lease = parsed.get("lease_expires_at")
                    if isinstance(lease, str) and lease:
                        lease_expires_at = lease
            return ActionProtocolError(
                "action_in_progress", message, lease_expires_at=lease_expires_at,
            )
        if code == "P0103":
            return ActionProtocolError("attempt_expired", message)
        if code == "P0104":
            return ActionProtocolError("attempt_id_reused", message)
        if code == "P0105":
            return ActionProtocolError("report_artifact_invalid", message)
        return None

    def _raise_action_error(self, error: Exception) -> None:
        protocol = self._report_protocol_error(error)
        if protocol is not None:
            raise protocol from error
        code = getattr(error, "code", None)
        if code == "P0002":
            raise MessageNotFound("Action not found.") from error
        if code in ("P0001", "P0003"):
            raise ActionStateConflict(
                str(getattr(error, "message", None) or error)
            ) from error
        raise error

    def commit_action(self, message_id: str, expected_payload: dict,
                      next_payload: dict, reminder: dict | None = None) -> dict:
        """Commit a reminder or cancellation effect and state together.

        Report claims and completions never use this generic transition; they
        must go through `claim_report_attempt` / `complete_report_attempt`.
        """
        try:
            response = self._execute(self.admin_client.rpc('commit_coach_action', {
                'p_user_id': self.user_id, 'p_message_id': message_id,
                'p_expected_payload': expected_payload, 'p_next_payload': next_payload,
                'p_reminder': reminder,
            }))
        except Exception as error:
            if getattr(error, 'code', None) == 'P0001':
                raise ActionStateConflict('Action state changed. Reload and try again.') from error
            if getattr(error, 'code', None) == 'P0002':
                raise MessageNotFound('Action not found.') from error
            if getattr(error, 'code', None) == 'P0003':
                # Attempt-specific fences keep their exact reason so the client
                # can reconcile instead of treating every loss as a state race.
                raise ActionStateConflict(str(getattr(error, 'message', None) or error)) from error
            raise
        return self._single_mutation_row(response)

    def claim_report_attempt(
        self, message_id: str, action_id: str, attempt_id: str,
    ) -> tuple[dict, dict | None]:
        """Atomically confirm a report card and return the claimed attempt.

        The database locks the owned action message first and its current live
        attempt second, so a claim, a heartbeat and a completion can never
        interleave: one attempt is returned, resumed, replaced or refused.
        """
        try:
            response = self._execute(self.admin_client.rpc('claim_coach_report_attempt', {
                'p_user_id': self.user_id, 'p_message_id': message_id,
                'p_action_id': action_id, 'p_attempt_id': attempt_id,
            }))
        except Exception as error:
            self._raise_action_error(error)
        data = getattr(response, 'data', None)
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict) or not isinstance(data.get('message'), dict):
            raise RuntimeError('Coaching persistence is unavailable.')
        row = data.get('attempt')
        attempt = self._project_attempt(row) if isinstance(row, dict) else None
        return data['message'], attempt

    def complete_report_attempt(
        self, message_id: str, action_id: str, attempt_id: str, *,
        success: bool, report: dict | None = None, storage: dict | None = None,
    ) -> dict:
        """Publish or release the attempt, its history row and its action together."""
        try:
            response = self._execute(self.admin_client.rpc('complete_coach_report_attempt', {
                'p_user_id': self.user_id, 'p_message_id': message_id,
                'p_action_id': action_id, 'p_attempt_id': attempt_id,
                'p_success': success, 'p_report': report, 'p_storage': storage,
            }))
        except Exception as error:
            self._raise_action_error(error)
        return self._single_mutation_row(response)

    @staticmethod
    def _project_attempt(row: dict, *, now: datetime | None = None) -> dict:
        attempt = {key: row.get(key) for key in REPORT_ATTEMPT_FIELDS}
        lease = _parse_instant(row.get("lease_expires_at"))
        instant = now or datetime.now(timezone.utc)
        attempt["lease_expires_at"] = row.get("lease_expires_at")
        # `server_time` and `lease_valid` are computed here, never trusted from
        # the device, so clock skew cannot make an expired lease look live.
        attempt["server_time"] = instant.isoformat()
        attempt["lease_valid"] = bool(
            attempt["status"] == "active" and lease is not None and lease > instant
        )
        return attempt

    def find_report_attempt(self, message_id: str, attempt_id: str) -> dict | None:
        """Owner-scoped attempt lookup used to reconcile an uncertain response."""
        response = self._execute(
            self.admin_client.table('report_attempts')
            .select(REPORT_ATTEMPT_COLUMNS)
            .eq('attempt_id', attempt_id)
            .eq('message_id', message_id)
            .eq('user_id', self.user_id)
            .maybe_single()
        )
        row = self._optional_single_row(response)
        return self._project_attempt(row) if row else None

    def require_active_report_attempt(
        self, message_id: str, action_id: str, attempt_id: str,
    ) -> dict:
        """The one live attempt a completion may still publish, or a refusal."""
        response = self._execute(
            self.admin_client.table('report_attempts')
            .select(REPORT_ATTEMPT_COLUMNS)
            .eq('attempt_id', attempt_id)
            .eq('action_id', action_id)
            .eq('message_id', message_id)
            .eq('user_id', self.user_id)
            .eq('status', 'active')
            .maybe_single()
        )
        row = self._optional_single_row(response)
        if not row:
            raise ActionProtocolError(
                'attempt_expired',
                'The report attempt expired before it could be used.',
            )
        return row

    def renew_report_attempt(self, message_id: str, attempt_id: str) -> dict:
        """Extend the owner's live lease so a slow render keeps its claim."""
        try:
            response = self._execute(self.admin_client.rpc('renew_report_attempt', {
                'p_user_id': self.user_id, 'p_message_id': message_id,
                'p_attempt_id': attempt_id,
            }))
        except Exception as error:
            if getattr(error, 'code', None) == 'P0002':
                raise MessageNotFound('The report attempt lease expired or was replaced.') from error
            raise
        return self._project_attempt(self._single_mutation_row(response))

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
