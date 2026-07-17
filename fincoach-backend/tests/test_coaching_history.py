import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from pydantic import ValidationError


def query_with(data=None, count=None):
    query = MagicMock()
    for name in ("select", "eq", "gte", "order", "limit", "insert", "update", "delete"):
        getattr(query, name).return_value = query
    query.maybe_single.return_value = query
    query.single.return_value = query
    query.execute.return_value = SimpleNamespace(data=data, count=count)
    return query


class CoachingModelsTests(unittest.TestCase):
    def test_message_create_trims_and_validates_content(self):
        from app.models import MessageCreate

        message = MessageCreate(
            message_id=UUID("00000000-0000-0000-0000-000000000001"),
            content="  Help me save RM50  ",
        )
        self.assertEqual(message.content, "Help me save RM50")
        for content in ("", " ", "x" * 1001):
            with self.subTest(content_length=len(content)):
                with self.assertRaises(ValidationError):
                    MessageCreate(
                        message_id=UUID("00000000-0000-0000-0000-000000000001"),
                        content=content,
                    )

    def test_conversation_title_is_trimmed_and_bounded(self):
        from app.models import ConversationUpdate

        self.assertEqual(ConversationUpdate(title="  Food budget  ").title, "Food budget")
        with self.assertRaises(ValidationError):
            ConversationUpdate(title="x" * 81)


class CoachingHistoryRepositoryTests(unittest.TestCase):
    def make_repository(self, user_query=None, admin_query=None):
        from app.coaching_history import CoachingHistoryRepository

        user_client = MagicMock()
        admin_client = MagicMock()
        user_client.table.return_value = user_query or query_with([])
        admin_client.table.return_value = admin_query or query_with([])
        return CoachingHistoryRepository(user_client, admin_client, "user-1"), user_client, admin_client

    def test_lists_sessions_with_owner_order_and_bounded_limit(self):
        rows = [{"id": "session-1", "user_id": "user-1"}]
        query = query_with(rows)
        repository, client, _ = self.make_repository(user_query=query)

        self.assertEqual(repository.list_sessions(limit=500), rows)

        client.table.assert_called_once_with("coaching_sessions")
        query.eq.assert_called_with("user_id", "user-1")
        query.order.assert_called_with("last_message_at", desc=True)
        query.limit.assert_called_with(50)

    def test_foreign_or_missing_session_raises_same_not_found(self):
        from app.coaching_history import ConversationNotFound

        query = query_with(None)
        repository, _, _ = self.make_repository(user_query=query)
        with self.assertRaisesRegex(ConversationNotFound, "Conversation not found"):
            repository.require_session("foreign-session")
        query.eq.assert_any_call("id", "foreign-session")
        query.eq.assert_any_call("user_id", "user-1")

    def test_inserts_user_message_with_verified_owner(self):
        session_query = query_with({"id": "session-1", "user_id": "user-1"})
        message_query = query_with({"id": "message-1", "role": "user"})
        user_client = MagicMock()
        user_client.table.side_effect = lambda table: session_query if table == "coaching_sessions" else message_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        row = repository.insert_user_message("session-1", "message-1", "Help me save")

        self.assertEqual(row["id"], "message-1")
        message_query.insert.assert_called_once_with({
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "role": "user",
            "content": "Help me save",
            "status": "completed",
        })

    def test_recovers_existing_assistant_reply_for_duplicate_send(self):
        reply = {"id": "assistant-1", "reply_to_message_id": "message-1"}
        query = query_with(reply)
        repository, _, admin = self.make_repository(admin_query=query)

        self.assertEqual(repository.find_reply("message-1"), reply)
        admin.table.assert_called_once_with("coaching_messages")
        query.eq.assert_any_call("reply_to_message_id", "message-1")
        query.eq.assert_any_call("user_id", "user-1")

    def test_rate_limit_rejects_minute_and_daily_excess(self):
        from app.coaching_history import CoachingRateLimitExceeded

        minute_query = query_with([], count=6)
        day_query = query_with([], count=100)
        admin = MagicMock()
        admin.table.side_effect = [minute_query, day_query]
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(MagicMock(), admin, "user-1")
        with self.assertRaises(CoachingRateLimitExceeded):
            repository.enforce_usage_limits(minute_limit=6, daily_limit=100)


if __name__ == "__main__":
    unittest.main()
