"""End-to-end coverage for recorded-spending category-budget recommendations."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.category_resolution import resolve_category_phrase
from app.rag.routing import (
    is_budget_save_command,
    is_budget_planning_request,
    required_read_agent_tool_name,
    resolve_read_request,
)


NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
USER_ID = "verified-user"


@pytest.fixture(autouse=True)
def _freeze_fixture_clock():
    """Recorded September fixtures must not change meaning as real time passes."""
    class FixtureClock(type):
        def __instancecheck__(cls, value):
            # Explicit datetime arguments remain recognized by isinstance guards.
            return isinstance(value, datetime)

    class FixtureDatetime(datetime, metaclass=FixtureClock):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    with (patch("app.rag.routing.datetime", FixtureDatetime),
          patch("app.rag.service.datetime", FixtureDatetime),
          patch("app.agent_tools.datetime", FixtureDatetime)):
        yield


def test_category_budget_recommendation_intent_precedes_budget_status():
    cases = (
        "Now what budget can I add?",
        "Suggest another category to budget for",
        "Which category needs a limit?",
        "Which category should I budget for?",
        "Recommend a budget for Groceries",
        "What other budget should I add?",
        "Which expense needs a budget?",
        "Which spending category should get a cap?",
        "Help me choose a category to put a limit on",
    )
    for question in cases:
        request = resolve_read_request(question, [], now=NOW)
        assert request.tool_name == "get_category_budget_recommendation", question
        assert request.arguments["month"] == "2026-09", question
    screenshot_question = resolve_read_request("Now what budget can I add?", [], now=NOW)
    assert "category_name" not in screenshot_question.arguments


def test_default_month_uses_malaysia_date_across_utc_month_boundary():
    utc_after_midnight_in_malaysia = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)
    request = resolve_read_request(
        "Which category needs a limit?", [], now=utc_after_midnight_in_malaysia
    )
    assert request.arguments["month"] == "2026-10"


def test_explicit_month_and_category_are_preserved_for_recommendation():
    request = resolve_read_request(
        "Recommend a category limit for Groceries in July 2026", [], now=NOW
    )
    assert request.tool_name == "get_category_budget_recommendation"
    assert request.arguments == {"month": "2026-07", "category_name": "Groceries"}
    now_category = resolve_read_request(
        "Recommend a budget for category Now", [], now=NOW
    )
    assert now_category.arguments["category_name"] == "Now"


def test_overall_budget_recommendation_and_save_command_stay_distinct():
    overall = "Suggest an overall monthly budget limit for me"
    save = "Save a category budget for Food at RM300"
    assert is_budget_planning_request(overall)
    assert required_read_agent_tool_name(overall) != "get_category_budget_recommendation"
    assert is_budget_save_command(save)
    assert required_read_agent_tool_name(save) is None
    assert required_read_agent_tool_name(save) != "get_category_budget_recommendation"
    assert required_read_agent_tool_name("Show my budget status") == "get_budget_status"
    assert required_read_agent_tool_name("Which category had the most spending?") != "get_category_budget_recommendation"


def test_category_resolution_uses_role_before_matching_catalog_words():
    names = ["Now", "Food", "Groceries"]
    assert resolve_category_phrase("Now what budget can I add", names).status == "none"
    assert resolve_category_phrase("I want a budget for Now", names).category == "Now"
    assert resolve_category_phrase("Recommend a budget for Now", names).category == "Now"
    assert resolve_category_phrase("Recommend a budget for category Now", names).category == "Now"
    assert resolve_category_phrase("Which category needs a limit", names).status == "none"
    assert resolve_category_phrase("budget for Yachts", names).status == "needs_interpretation"


def test_duplicate_category_names_require_clarification():
    result = resolve_category_phrase("Set a budget for Food", ["Food", "Food"])
    assert result.status == "ambiguous"


def _expense(day: str, category_id: int, category_name: str, amount: str):
    return {
        "id": f"txn-{day}-{category_id}",
        "user_id": USER_ID,
        "category_id": category_id,
        "amount": amount,
        "transaction_date": day,
        "category": {"id": category_id, "name": category_name, "type": "expense"},
    }


def _catalog():
    return [
        {"id": 1, "name": "Food", "type": "expense", "user_id": None},
        {"id": 2, "name": "Transport", "type": "expense", "user_id": None},
        {"id": 3, "name": "Groceries", "type": "expense", "user_id": None},
        {"id": 4, "name": "Now", "type": "expense", "user_id": None},
        # A user's custom category may share a label with a default category.
        {"id": 5, "name": "Food", "type": "expense", "user_id": USER_ID},
        {"id": 6, "name": "Salary", "type": "income", "user_id": None},
    ]


class _StoredQuery:
    """Small PostgREST-shaped query fixture over representative stored rows."""

    def __init__(self, store, table):
        self.store = store
        self.table_name = table
        self.filters = []
        self.range_bounds = None
        self.single = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def is_(self, field, value):
        self.filters.append(("is", field, value))
        return self

    def gte(self, field, value):
        self.filters.append(("gte", field, value))
        return self

    def lte(self, field, value):
        self.filters.append(("lte", field, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self.range_bounds = (start, end)
        return self

    def maybe_single(self):
        self.single = True
        return self

    def execute(self):
        if self.table_name in self.store.fail_tables:
            return SimpleNamespace(data=None, error=RuntimeError("database read failed"))
        rows = list(self.store.rows.get(self.table_name, []))
        for operation, field, expected in self.filters:
            if operation == "eq":
                rows = [row for row in rows if row.get(field) == expected]
            elif operation == "is":
                expected_value = None if expected == "null" else expected
                rows = [row for row in rows if row.get(field) is expected_value]
            elif operation == "gte":
                rows = [row for row in rows if row.get(field) is not None and row[field] >= expected]
            elif operation == "lte":
                rows = [row for row in rows if row.get(field) is not None and row[field] <= expected]
        if self.range_bounds is not None:
            start, end = self.range_bounds
            rows = rows[start : end + 1]
        return SimpleNamespace(data=(rows[0] if rows else None) if self.single else rows, error=None)


class _StoredRecordClient:
    def __init__(self, rows, *, fail_tables=()):
        self.rows = rows
        self.fail_tables = set(fail_tables)
        self.queries = []

    def table(self, name):
        query = _StoredQuery(self, name)
        self.queries.append(query)
        return query


def _rows(*, monthly_limit="700", consent="granted", with_history=True):
    rows = {
        "profiles": [{"id": USER_ID, "spending_records_consent": consent}],
        "categories": _catalog(),
        "monthly_budgets": (
            [{"user_id": USER_ID, "month": "2026-09-01", "limit_amount": monthly_limit}]
            if monthly_limit is not None
            else []
        ),
        "budgets": [
            {"user_id": USER_ID, "category_id": 1, "month": "2026-09-01", "amount": "200"},
            {"user_id": USER_ID, "category_id": 3, "month": "2026-09-01", "amount": "50"},
        ],
        "transactions": [],
    }
    if with_history:
        rows["transactions"] += [
            _expense("2026-08-03", 1, "Food", "400"),
            _expense("2026-08-04", 2, "Transport", "250"),
            _expense("2026-08-05", 3, "Groceries", "600"),
            _expense("2026-08-06", 4, "Now", "250"),
            _expense("2026-08-07", 5, "Food", "200"),
            _expense("2026-07-04", 2, "Transport", "500"),
            # This month is incomplete and must not replace August as evidence.
            _expense("2026-09-10", 2, "Transport", "100"),
        ]
    return rows


def _executor(request_text, rows=None, *, fail_tables=()):
    from app.agent_tools import AgentToolExecutor

    client = _StoredRecordClient(rows or _rows(), fail_tables=fail_tables)
    executor = AgentToolExecutor(
        client,
        user_id=USER_ID,
        session_id="session-1",
        now=lambda: NOW,
        request_text=request_text,
    )
    return executor, client


def test_recommendation_selects_highest_unbudgeted_category_from_latest_completed_month_by_id():
    executor, _client = _executor("Now what budget can I add?")
    result = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert result["status"] == "ok"
    assert result["candidate"] == {"id": 2, "name": "Transport"}
    assert result["historical_month"] == "2026-08"
    assert result["suggested_starting_amount"] == "RM250.00"
    assert result["target_month_category_spending"] == "RM100.00"
    assert result["unallocated_budget_capacity"] == "RM450.00"
    assert result["feasibility"] == "fits"


def test_saved_limits_are_compared_by_category_id_even_when_names_are_duplicated():
    rows = _rows()
    rows["transactions"] = [
        {**row, "amount": "500"} if row["category_id"] == 5 else row
        for row in rows["transactions"]
    ]
    executor, _client = _executor("Which category needs a limit?", rows)
    result = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert result["status"] == "ok"
    assert result["candidate"]["id"] == 5
    assert result["suggested_starting_amount"] == "RM500.00"


def test_named_duplicate_catalog_category_clarifies_and_existing_limit_is_reported():
    executor, _client = _executor("Recommend a budget for Food")
    duplicate = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert duplicate["status"] == "needs_clarification"
    assert "more than one" in duplicate["message"].lower()

    executor, _client = _executor("Recommend a budget for Groceries")
    already_budgeted = executor.execute(
        "get_category_budget_recommendation", {"month": "2026-09"}
    )
    assert already_budgeted["status"] == "ok"
    assert already_budgeted["recommendation_status"] == "already_budgeted"

    unknown, _client = _executor("Recommend a budget for Yachts")
    missing = unknown.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert missing["status"] == "needs_clarification"


def test_no_overall_budget_and_insufficient_or_exceeded_capacity_are_explicit():
    executor, _client = _executor(
        "Which category needs a limit?", _rows(monthly_limit=None)
    )
    no_overall = executor.execute(
        "get_category_budget_recommendation", {"month": "2026-09"}
    )
    assert no_overall["recommendation_status"] == "overall_budget_required"
    assert no_overall["candidate"]["name"] == "Transport"

    tight_rows = _rows(monthly_limit="1000")
    tight_rows["budgets"] = [
        {"user_id": USER_ID, "category_id": 1, "month": "2026-09-01", "amount": "250"},
        {"user_id": USER_ID, "category_id": 3, "month": "2026-09-01", "amount": "700"},
    ]
    tight_rows["transactions"].append(_expense("2026-09-12", 2, "Transport", "300"))
    executor, _client = _executor("Which category needs a limit?", tight_rows)
    tight = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert tight["suggested_starting_amount"] == "RM250.00"
    assert tight["feasibility"] == "already_exceeded_and_insufficient_allocation"
    assert tight["unallocated_budget_capacity"] == "RM50.00"


def test_no_eligible_categories_is_reported_without_falling_back_to_partial_current_spending():
    rows = _rows()
    rows["budgets"] = [
        {"user_id": USER_ID, "category_id": category_id, "month": "2026-09-01", "amount": "10"}
        for category_id in (1, 2, 3, 4, 5)
    ]
    executor, _client = _executor("Which category needs a limit?", rows)
    result = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert result["recommendation_status"] == "no_eligible_categories"
    assert result["candidate"] is None


def test_missing_history_uses_current_candidate_without_inventing_amount():
    rows = _rows(with_history=False)
    rows["transactions"] = [_expense("2026-09-12", 2, "Transport", "80")]
    executor, _client = _executor("Which category needs a limit?", rows)
    result = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert result["candidate"]["name"] == "Transport"
    assert result["historical_month"] is None
    assert result["suggested_starting_amount"] is None
    assert result["recommendation_status"] == "no_completed_month_evidence"


def test_target_month_after_an_incomplete_month_skips_that_month_as_history():
    rows = _rows()
    rows["monthly_budgets"] = [
        {"user_id": USER_ID, "month": "2026-10-01", "limit_amount": "1000"}
    ]
    rows["budgets"] = [
        {"user_id": USER_ID, "category_id": 1, "month": "2026-10-01", "amount": "200"},
        {"user_id": USER_ID, "category_id": 3, "month": "2026-10-01", "amount": "50"},
    ]
    rows["transactions"].append(_expense("2026-09-20", 2, "Transport", "999"))
    executor, _client = _executor(
        "Which category needs a limit in October?", rows
    )
    result = executor.execute("get_category_budget_recommendation", {"month": "2026-10"})
    assert result["historical_month"] == "2026-08"
    assert result["suggested_starting_amount"] == "RM250.00"


def test_explicit_category_with_no_completed_history_keeps_amount_unavailable_without_overall_limit():
    rows = _rows(monthly_limit=None, with_history=False)
    rows["transactions"] = [_expense("2026-09-12", 2, "Transport", "80")]
    executor, _client = _executor("Recommend a budget for Transport", rows)
    result = executor.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert result["recommendation_status"] == "overall_budget_required"
    assert result["suggested_starting_amount"] is None


def test_missing_consent_and_failed_reads_are_not_reported_as_no_spending():
    denied, denied_client = _executor(
        "Which category needs a limit?", _rows(consent="denied")
    )
    permission = denied.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert permission["status"] == "permission_required"
    assert not any(query.table_name == "transactions" for query in denied_client.queries)

    failed, _client = _executor(
        "Which category needs a limit?", _rows(), fail_tables=("transactions",)
    )
    read_error = failed.execute("get_category_budget_recommendation", {"month": "2026-09"})
    assert read_error["status"] == "read_failed"
    assert read_error["recommendation_status"] != "no_completed_month_evidence"


def test_service_routes_screenshot_question_through_real_tool_and_text_renderer():
    from app.rag.service import CoachingService

    question = "Now what budget can I add?"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "New conversation"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {
        "id": "message-1",
        "session_id": "session-1",
        "user_id": USER_ID,
        "role": "user",
        "content": question,
    }
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    admin_client = _StoredRecordClient(_rows())
    with (
        patch("app.rag.service.generate_result", side_effect=AssertionError("fast read used LLM")),
        patch("app.rag.service.generate_agent_result", side_effect=AssertionError("fast read used agent")),
    ):
        result = CoachingService(repository, admin_client).send_message(
            "session-1", "message-1", question
        )
    answer = result["assistant_message"]["content"]
    assert "Transport" in answer
    assert "August 2026" in answer
    assert "RM250.00" in answer
    assert "starting amount" in answer.lower()


def test_service_does_not_turn_a_budget_save_command_into_a_read_or_recommendation():
    from app.rag.service import CoachingService

    question = "Save a category budget for Food at RM300"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "New conversation"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {
        "id": "message-1",
        "session_id": "session-1",
        "user_id": USER_ID,
        "role": "user",
        "content": question,
    }
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    with (
        patch("app.rag.service.AgentToolExecutor.execute", side_effect=AssertionError("save command ran a read")),
        patch("app.rag.service.generate_agent_result", side_effect=AssertionError("save command reached agent")),
        patch("app.rag.service.generate_result", side_effect=AssertionError("save command reached LLM")),
    ):
        result = CoachingService(repository, object()).send_message(
            "session-1", "message-1", question
        )
    answer = result["assistant_message"]["content"]
    assert "aren't saved through Coach" in answer
    assert "Budget tab" in answer


def test_research_route_reads_stored_spending_without_web_or_answer_model():
    """The semantic plan still enters the real owner scoped spending executor."""
    import json
    from app.rag.service import CoachingService

    question = "Where does my money go this month?"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "message-1", "content": question}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    admin_client = _StoredRecordClient(_rows())
    interpretation = SimpleNamespace(content=json.dumps({
        "topic": "Personal spending by category", "needs_personal": True,
        "needs_external": False, "time_scope": "stable", "period": None,
        "entities": [], "required_facts": [], "clarification": None,
        "explicit_search": False, "personal_read": "get_spending_summary",
    }))
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.generate_structured_result", return_value=interpretation),
        patch("app.rag.service.generate_result", side_effect=AssertionError("verified read must not synthesize")),
        patch("app.rag.service.research_web", side_effect=AssertionError("personal question must not search")),
    ):
        result = CoachingService(repository, admin_client).send_message("session-1", "message-1", question)
    assert "RM100.00" in result["assistant_message"]["content"]
    assert "Transport" in result["assistant_message"]["content"]
    assert any(query.table_name == "transactions" for query in admin_client.queries)
    assert all(
        (operation, field, value) != ("eq", "user_id", "other-owner")
        for query in admin_client.queries for operation, field, value in query.filters
    )


def test_research_route_denied_spending_consent_never_reads_transactions():
    import json
    from app.rag.service import CoachingService

    question = "Where does my money go this month?"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "message-1", "content": question}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    admin_client = _StoredRecordClient(_rows(consent="denied"))
    interpretation = SimpleNamespace(content=json.dumps({
        "topic": "Personal spending", "needs_personal": True,
        "needs_external": False, "time_scope": "stable", "period": None,
        "entities": [], "required_facts": [], "clarification": None,
        "explicit_search": False, "personal_read": "get_spending_summary",
    }))
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.generate_structured_result", return_value=interpretation),
        patch("app.rag.service.generate_result", side_effect=AssertionError("denied read must not synthesize")),
    ):
        result = CoachingService(repository, admin_client).send_message("session-1", "message-1", question)
    assert "not read" in result["assistant_message"]["content"].lower()
    assert not any(query.table_name == "transactions" for query in admin_client.queries)


def test_mixed_rate_question_keeps_verified_budget_when_external_search_fails():
    import json
    from app.rag.service import CoachingService
    from app.rag.web_research import ResearchOutcome

    question = "How would the latest OPR change affect my budget?"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "message-1", "content": question}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    admin_client = _StoredRecordClient(_rows())
    interpretation = SimpleNamespace(content=json.dumps({
        "topic": "Bank Negara Malaysia overnight policy rate change",
        "needs_personal": True, "needs_external": True,
        "time_scope": "current", "period": None,
        "entities": ["Bank Negara Malaysia"],
        "required_facts": ["current OPR and its effect"],
        "clarification": None, "explicit_search": False,
        "personal_read": "get_budget_status", "personal_category": None,
    }))
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.generate_structured_result", return_value=interpretation),
        patch("app.rag.service.retrieve", return_value=[]),
        patch("app.rag.research_policy.research_evidence",
              return_value=ResearchOutcome([], True, "search_failed")),
        patch("app.rag.service.generate_result", side_effect=AssertionError("unverified rate must not synthesize")),
    ):
        result = CoachingService(repository, admin_client).send_message("session-1", "message-1", question)
    assistant = result["assistant_message"]
    assert "RM700.00" in assistant["content"]
    assert "I could not retrieve the source details needed for this question. Please try again." in assistant["content"]
    assert "could not verify the external" not in assistant["content"]
    assert "latest OPR change affect" not in assistant["content"]
    assert any(query.table_name == "transactions" for query in admin_client.queries)


def test_semantic_paraphrase_selects_category_recommendation_over_generic_spending():
    import json
    from app.rag.service import CoachingService

    question = "Help me decide what expense to put a monthly cap on"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "message-1", "content": question}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    admin_client = _StoredRecordClient(_rows())
    interpretation = SimpleNamespace(content=json.dumps({
        "topic": "Personal category budget recommendation",
        "needs_personal": True, "needs_external": False,
        "time_scope": "stable", "period": None, "entities": [],
        "required_facts": [], "clarification": None,
        "explicit_search": False,
        "personal_read": "get_category_budget_recommendation",
        "personal_category": None,
    }))
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.generate_structured_result", return_value=interpretation),
        patch("app.rag.service.generate_result", side_effect=AssertionError("verified read should be direct")),
    ):
        result = CoachingService(repository, admin_client).send_message("session-1", "message-1", question)
    answer = result["assistant_message"]["content"]
    assert "Transport" in answer
    assert "August 2026" in answer
    assert "historical starting amount" in answer


def test_provider_timeout_preserves_authorized_personal_read():
    from app.rag.service import CoachingService

    question = "How much did I spend on Transport last month?"
    repository = MagicMock(user_id=USER_ID)
    repository.require_session.return_value = {"id": "session-1", "title": "Existing"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {"id": "message-1", "content": question}
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    admin_client = _StoredRecordClient(_rows())
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.generate_structured_result", side_effect=TimeoutError("provider unavailable")),
        patch("app.rag.service.generate_result", side_effect=AssertionError("read should be direct")),
        patch("app.rag.service.research_web", side_effect=AssertionError("personal records stay private")),
    ):
        result = CoachingService(repository, admin_client).send_message("session-1", "message-1", question)
    answer = result["assistant_message"]["content"]
    assert "RM250.00" in answer
    assert "Transport" in answer
