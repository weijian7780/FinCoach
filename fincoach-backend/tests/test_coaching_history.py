import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

from pydantic import ValidationError


def query_with(data=None, count=None):
    query = MagicMock()
    for name in (
        "select",
        "eq",
        "gte",
        "lt",
        "in_",
        "order",
        "limit",
        "insert",
        "update",
        "delete",
    ):
        getattr(query, name).return_value = query
    query.maybe_single.return_value = query
    query.single.return_value = query
    query.execute.return_value = SimpleNamespace(data=data, count=count)
    return query


class MutationQueryWithoutSingle:
    """Match the current PostgREST mutation builder returned after select()."""

    def __init__(self, row):
        self.response = SimpleNamespace(data=[row], count=None)
        self.insert_payload = None
        self.update_payload = None
        self.eq_calls = []
        self.selected_columns = None

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def eq(self, column, value):
        self.eq_calls.append((column, value))
        return self

    def select(self, columns):
        self.selected_columns = columns
        return self

    def execute(self):
        return self.response


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

    def test_feedback_accepts_supported_values_or_clear_only(self):
        from app.models import MessageFeedbackUpdate

        self.assertEqual(MessageFeedbackUpdate(feedback="helpful").feedback, "helpful")
        self.assertIsNone(MessageFeedbackUpdate(feedback=None).feedback)
        with self.assertRaises(ValidationError):
            MessageFeedbackUpdate(feedback="maybe")


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

    def test_real_postgrest_empty_optional_response_is_treated_as_missing(self):
        from app.coaching_history import CoachingHistoryRepository, ConversationNotFound

        empty_query = query_with()
        empty_query.execute.return_value = None
        user_client = MagicMock()
        admin_client = MagicMock()
        user_client.table.return_value = empty_query
        admin_client.table.return_value = empty_query
        repository = CoachingHistoryRepository(user_client, admin_client, "user-1")

        with self.assertRaisesRegex(ConversationNotFound, "Conversation not found"):
            repository.require_session("missing-session")
        self.assertIsNone(repository.find_user_message("missing-message"))
        self.assertIsNone(repository.find_reply("missing-message"))

    def test_creates_session_with_current_postgrest_mutation_builder(self):
        row = {"id": "session-1", "user_id": "user-1", "title": "New conversation"}
        mutation_query = MutationQueryWithoutSingle(row)
        user_client = MagicMock()
        user_client.table.return_value = mutation_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        try:
            created = repository.create_session()
        except AttributeError as error:
            self.fail(f"Mutation query used an unsupported builder method: {error}")

        self.assertEqual(created, row)
        self.assertEqual(
            mutation_query.insert_payload,
            {"user_id": "user-1", "title": "New conversation"},
        )

    def test_create_session_rejects_missing_mutation_response_row(self):
        mutation_query = MutationQueryWithoutSingle(None)
        mutation_query.response.data = []
        user_client = MagicMock()
        user_client.table.return_value = mutation_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        try:
            with self.assertRaisesRegex(RuntimeError, "Coaching persistence is unavailable"):
                repository.create_session()
        except AttributeError as error:
            self.fail(f"Mutation query used an unsupported builder method: {error}")

    def test_renames_session_with_current_postgrest_mutation_builder(self):
        current = {"id": "session-1", "user_id": "user-1"}
        renamed = {**current, "title": "Food budget"}
        session_query = query_with(current)
        mutation_query = MutationQueryWithoutSingle(renamed)
        user_client = MagicMock()
        user_client.table.side_effect = [session_query, mutation_query]
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        try:
            row = repository.rename_session("session-1", "Food budget")
        except AttributeError as error:
            self.fail(f"Mutation query used an unsupported builder method: {error}")

        self.assertEqual(row, renamed)
        self.assertEqual(mutation_query.update_payload, {"title": "Food budget"})

    def test_inserts_user_message_with_verified_owner(self):
        session_query = query_with({"id": "session-1", "user_id": "user-1"})
        message_query = MutationQueryWithoutSingle({"id": "message-1", "role": "user"})
        user_client = MagicMock()
        user_client.table.side_effect = lambda table: session_query if table == "coaching_sessions" else message_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        try:
            row = repository.insert_user_message("session-1", "message-1", "Help me save")
        except AttributeError as error:
            self.fail(f"Mutation query used an unsupported builder method: {error}")

        self.assertEqual(row["id"], "message-1")
        self.assertEqual(
            message_query.insert_payload,
            {
                "id": "message-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "role": "user",
                "content": "Help me save",
                "status": "completed",
            },
        )

    def test_lists_latest_messages_in_chronological_order(self):
        session_query = query_with({"id": "session-1", "user_id": "user-1"})
        newest_first = [
            {"id": "message-14", "created_at": "2026-07-17T00:00:14+00:00"},
            {"id": "message-13", "created_at": "2026-07-17T00:00:13+00:00"},
            {"id": "message-12", "created_at": "2026-07-17T00:00:12+00:00"},
        ]
        messages_query = query_with(newest_first)
        user_client = MagicMock()
        user_client.table.side_effect = [session_query, messages_query]
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        rows = repository.list_messages("session-1", limit=3)

        self.assertEqual([row["id"] for row in rows], ["message-12", "message-13", "message-14"])
        messages_query.order.assert_called_once_with("created_at", desc=True)
        messages_query.limit.assert_called_once_with(3)

    def test_lists_cursor_page_and_batches_sources_with_owner_scope(self):
        session_query = query_with({"id": "session-1", "user_id": "user-1"})
        newest_first = [
            {"id": "message-14", "created_at": "2026-07-17T00:00:14+00:00"},
            {"id": "message-13", "created_at": "2026-07-17T00:00:13+00:00"},
            {"id": "message-12", "created_at": "2026-07-17T00:00:12+00:00"},
            {"id": "message-11", "created_at": "2026-07-17T00:00:11+00:00"},
        ]
        messages_query = query_with(newest_first)
        retrievals = [{"assistant_message_id": "message-14", "rank": 1}]
        retrievals_query = query_with(retrievals)
        user_client = MagicMock()
        user_client.table.side_effect = [session_query, messages_query, retrievals_query]
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(user_client, MagicMock(), "user-1")
        page = repository.list_message_page(
            "session-1",
            limit=3,
            before="2026-07-17T00:00:15+00:00",
        )
        sources = repository.list_retrievals_for_messages(["message-14", "message-12"])

        self.assertEqual(
            [row["id"] for row in page["messages"]],
            ["message-12", "message-13", "message-14"],
        )
        self.assertEqual(page["next_before"], "2026-07-17T00:00:12+00:00")
        self.assertEqual(sources, retrievals)
        messages_query.lt.assert_called_once_with("created_at", "2026-07-17T00:00:15+00:00")
        messages_query.order.assert_called_once_with("created_at", desc=True)
        messages_query.limit.assert_called_once_with(4)
        retrievals_query.eq.assert_called_once_with("user_id", "user-1")
        retrievals_query.in_.assert_called_once_with(
            "assistant_message_id",
            ["message-14", "message-12"],
        )

    def test_recovers_existing_assistant_reply_for_duplicate_send(self):
        reply = {"id": "assistant-1", "reply_to_message_id": "message-1"}
        query = query_with(reply)
        repository, _, admin = self.make_repository(admin_query=query)

        self.assertEqual(repository.find_reply("message-1"), reply)
        admin.table.assert_called_once_with("coaching_messages")
        query.eq.assert_any_call("reply_to_message_id", "message-1")
        query.eq.assert_any_call("user_id", "user-1")

    def test_inserts_assistant_reply_with_current_postgrest_mutation_builder(self):
        payload = {
            "id": "assistant-1",
            "user_id": "user-1",
            "role": "assistant",
            "content": "Start with RM50.",
        }
        mutation_query = MutationQueryWithoutSingle(payload)
        admin_client = MagicMock()
        admin_client.table.return_value = mutation_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(MagicMock(), admin_client, "user-1")
        try:
            row = repository.insert_assistant_reply(payload)
        except AttributeError as error:
            self.fail(f"Mutation query used an unsupported builder method: {error}")

        self.assertEqual(row, payload)
        self.assertEqual(mutation_query.insert_payload, payload)

    def test_completes_assistant_turn_through_one_database_rpc(self):
        assistant = {
            "id": "assistant-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "role": "assistant",
            "content": "Start with RM50.",
            "reply_to_message_id": "message-1",
            "status": "completed",
        }
        response = SimpleNamespace(data=[assistant], count=None)
        rpc_query = MagicMock()
        rpc_query.execute.return_value = response
        admin_client = MagicMock()
        admin_client.rpc.return_value = rpc_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(MagicMock(), admin_client, "user-1")
        row = repository.complete_turn(
            session_id="session-1",
            user_message_id="message-1",
            assistant_payload=assistant,
            retrieval_rows=[{"knowledge_document_id": 9, "rank": 1}],
            title="Help me save",
        )

        self.assertEqual(row, assistant)
        admin_client.rpc.assert_called_once_with(
            "complete_coaching_turn",
            {
                "p_user_id": "user-1",
                "p_session_id": "session-1",
                "p_user_message_id": "message-1",
                "p_assistant_message": assistant,
                "p_retrievals": [{"knowledge_document_id": 9, "rank": 1}],
                "p_title": "Help me save",
            },
        )

    def test_updates_session_after_message_with_current_postgrest_mutation_builder(self):
        updated = {"id": "session-1", "user_id": "user-1", "title": "Help me save"}
        mutation_query = MutationQueryWithoutSingle(updated)
        admin_client = MagicMock()
        admin_client.table.return_value = mutation_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(MagicMock(), admin_client, "user-1")
        try:
            row = repository.update_session_after_message("session-1", title="Help me save")
        except AttributeError as error:
            self.fail(f"Mutation query used an unsupported builder method: {error}")

        self.assertEqual(row, updated)
        self.assertEqual(mutation_query.update_payload["title"], "Help me save")

    def test_marks_failed_message_and_claims_it_for_retry(self):
        failed = {
            "id": "message-1",
            "user_id": "user-1",
            "role": "user",
            "status": "failed",
        }
        failed_query = MutationQueryWithoutSingle(failed)
        claimed_query = MutationQueryWithoutSingle({**failed, "status": "completed"})
        admin_client = MagicMock()
        admin_client.table.side_effect = [failed_query, claimed_query]
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(MagicMock(), admin_client, "user-1")
        repository.mark_user_message_failed("message-1", "provider_timeout")
        claimed = repository.claim_failed_user_message("message-1")

        self.assertEqual(failed_query.update_payload, {
            "status": "failed",
            "error_code": "provider_timeout",
        })
        self.assertEqual(claimed["status"], "completed")
        self.assertEqual(claimed_query.update_payload, {
            "status": "completed",
            "error_code": None,
        })
        self.assertIn(("status", "failed"), claimed_query.eq_calls)

    def test_sets_feedback_only_on_the_owned_assistant_message(self):
        updated = {
            "id": "assistant-1",
            "user_id": "user-1",
            "role": "assistant",
            "feedback": "helpful",
        }
        mutation_query = MutationQueryWithoutSingle(updated)
        admin_client = MagicMock()
        admin_client.table.return_value = mutation_query
        from app.coaching_history import CoachingHistoryRepository

        repository = CoachingHistoryRepository(MagicMock(), admin_client, "user-1")
        row = repository.set_message_feedback("assistant-1", "helpful")

        self.assertEqual(row["feedback"], "helpful")
        self.assertEqual(mutation_query.update_payload, {"feedback": "helpful"})
        self.assertIn(("id", "assistant-1"), mutation_query.eq_calls)
        self.assertIn(("user_id", "user-1"), mutation_query.eq_calls)
        self.assertIn(("role", "assistant"), mutation_query.eq_calls)

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
