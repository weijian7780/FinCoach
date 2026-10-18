import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock


class ToolQuery:
    def __init__(self, rows):
        self.rows = rows
        self.eq_calls = []
        self.filters = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.eq_calls.append((column, value))
        return self

    def is_(self, column, value):
        self.eq_calls.append((column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def lt(self, column, value):
        self.filters.append(("lt", column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self.rows = self.rows[start:end + 1]
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class AgentToolExecutorTests(unittest.TestCase):
    def make_executor(
        self,
        table_rows=None,
        *,
        user_id="verified-user",
        request_text=None,
        now=None,
    ):
        from app.agent_tools import AgentToolExecutor

        table_rows = table_rows or {}
        table_rows.setdefault("categories", [{"name": "Food"}, {"name": "Entertainment"}])
        queries = {}
        client = MagicMock()

        def table(name):
            query = ToolQuery(table_rows.get(name, []))
            queries.setdefault(name, []).append(query)
            return query

        client.table.side_effect = table
        executor = AgentToolExecutor(
            client,
            user_id=user_id,
            session_id="session-1",
            now=now or (lambda: datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc)),
            request_text=request_text,
        )
        return executor, queries

    def test_registry_exposes_only_bounded_fincoach_tools(self):
        from app.agent_tools import AGENT_TOOL_DEFINITIONS

        names = [item["function"]["name"] for item in AGENT_TOOL_DEFINITIONS]
        self.assertEqual(
            names,
            [
                "get_financial_overview",
                "get_spending_summary",
                "get_period_comparison",
                "get_budget_status",
                "get_category_budget_recommendation",
                "get_savings_goals",
                "get_weekly_savings_plan",
                "get_upcoming_reminders",
                "get_report_summary",
                "search_transactions",
                "get_financial_profile",
                "get_cashflow_forecast",
                "predict_savings",
                "prepare_reminder",
                "prepare_report",
            ],
        )
        self.assertNotIn("delete_reminder", names)
        self.assertNotIn("run_sql", names)

    def test_new_read_tools_are_owner_scoped_and_return_only_safe_financial_fields(self):
        executor, queries = self.make_executor(
            {
                "profiles": {
                    "spending_records_consent": "granted",
                    "monthly_allowance": 500,
                    "income_source": "Allowance",
                    "financial_status": "student",
                    "coaching_style": "direct",
                    "year_of_study": "3",
                    "email": "private@example.com",
                    "full_name": "Private User",
                },
                "transactions": [
                    {
                        "id": "expense-1", "amount": 120, "source": "manual",
                        "description": "Campus food", "transaction_date": "2026-07-20",
                        "category": {"name": "Food", "type": "expense"},
                    },
                ],
                "reminders": [
                    {"id": "reminder-1", "title": "Phone bill", "amount": 30, "due_at": "2026-07-28T10:00:00+08:00", "enabled": True},
                ],
            }
        )

        found = executor.execute(
            "search_transactions",
            {"transaction_type": "expense", "text": "food"},
        )
        profile = executor.execute("get_financial_profile", {})
        forecast = executor.execute("get_cashflow_forecast", {})

        self.assertEqual(found["transactions"][0]["id"], "expense-1")
        self.assertIn(("user_id", "verified-user"), queries["transactions"][0].eq_calls)
        self.assertEqual(
            profile,
            {
                "status": "ok", "monthly_allowance": "RM500.00", "income_source": "Allowance",
                "financial_status": "student", "coaching_style": "direct", "year_of_study": "3",
            },
        )
        self.assertNotIn("email", profile)
        self.assertEqual(forecast["income_basis"], "monthly_allowance")
        self.assertEqual(forecast["estimated_available_by_month_end"], "RM350.00")

    def test_search_transactions_filters_by_amount_text_and_limit(self):
        rows = [
            {"id": "t1", "amount": 25, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-22", "category": {"name": "Transport", "type": "expense"}},
            {"id": "t2", "amount": 25, "source": "Speedmart", "description": "snacks",
             "transaction_date": "2026-07-21", "category": {"name": "Food", "type": "expense"}},
            {"id": "t3", "amount": 40, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-20", "category": {"name": "Transport", "type": "expense"}},
        ]
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"}, "transactions": rows}
        )
        by_amount = executor.execute("search_transactions", {"amount": 25})
        self.assertEqual([t["id"] for t in by_amount["transactions"]], ["t1", "t2"])
        grab_25 = executor.execute("search_transactions", {"amount": 25, "text": "Grab"})
        self.assertEqual([t["id"] for t in grab_25["transactions"]], ["t1"])
        first_only = executor.execute("search_transactions", {"limit": 1})
        self.assertEqual(len(first_only["transactions"]), 1)
        # A non-matching amount returns nothing, never an unfiltered dump.
        self.assertEqual(executor.execute("search_transactions", {"amount": 99})["transactions"], [])

    def test_search_transactions_amount_respects_denied_consent(self):
        executor, queries = self.make_executor(
            {"profiles": {"spending_records_consent": "denied"},
             "transactions": [{"id": "t1", "amount": 25, "source": "Grab", "description": "x",
                               "transaction_date": "2026-07-22",
                               "category": {"name": "Transport", "type": "expense"}}]}
        )
        result = executor.execute("search_transactions", {"amount": 25})
        self.assertEqual(result["status"], "permission_required")
        self.assertNotIn("transactions", queries)

    def test_search_transactions_count_mode_counts_all_matches_before_limit(self):
        rows = [
            {"id": f"g{i}", "amount": 10, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-10", "category": {"name": "Transport", "type": "expense"}}
            for i in range(55)
        ]
        rows.append({"id": "other", "amount": 10, "source": "Speedmart", "description": "x",
                     "transaction_date": "2026-07-10", "category": {"name": "Food", "type": "expense"}})
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"}, "transactions": rows}
        )
        result = executor.execute("search_transactions", {"result_mode": "count", "text": "Grab"})
        self.assertEqual(result["result_mode"], "count")
        self.assertEqual(result["count"], 55)  # not capped at the 20/50 display limit
        self.assertNotIn("transactions", result)

    def test_search_transactions_expense_total_sums_expenses_only(self):
        rows = [
            {"id": "e1", "amount": 12, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-10", "category": {"name": "Transport", "type": "expense"}},
            {"id": "e2", "amount": 8, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-11", "category": {"name": "Transport", "type": "expense"}},
            {"id": "inc", "amount": 999, "source": "Grab", "description": "refund",
             "transaction_date": "2026-07-12", "category": {"name": "Salary", "type": "income"}},
        ]
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"}, "transactions": rows}
        )
        result = executor.execute("search_transactions", {"result_mode": "expense_total", "text": "Grab"})
        self.assertEqual(result["result_mode"], "expense_total")
        self.assertEqual(result["expense_total"], "RM20.00")  # income excluded
        self.assertEqual(result["expense_count"], 2)

    def test_search_transactions_all_dates_skips_date_filter_owner_scoped(self):
        rows = [
            {"id": "old", "amount": 49.70, "source": "IPOH KOPI KIA", "description": "",
             "transaction_date": "2026-04-14", "category": {"name": "Food", "type": "expense"}},
        ]
        executor, queries = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"}, "transactions": rows}
        )
        result = executor.execute("search_transactions", {"text": "IPOH", "all_dates": True})
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["all_dates"])
        self.assertEqual(result["period"], {"start": None, "end": None})
        self.assertEqual(result["transactions"][0]["id"], "old")
        txn_query = queries["transactions"][0]
        self.assertEqual(txn_query.filters, [])  # no date-range filter applied
        self.assertIn(("user_id", "verified-user"), txn_query.eq_calls)

    def test_search_transactions_rejects_all_dates_combined_with_a_date(self):
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"}, "transactions": []}
        )
        result = executor.execute(
            "search_transactions", {"all_dates": True, "start_date": "2026-07-01"}
        )
        self.assertEqual(result["status"], "invalid_arguments")

    def test_bare_name_becomes_text_when_not_a_category(self):
        rows = [
            {"id": "g1", "amount": 10, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-10", "category": {"name": "Transport", "type": "expense"}},
            {"id": "f1", "amount": 20, "source": "Speedmart", "description": "lunch",
             "transaction_date": "2026-07-11", "category": {"name": "Food", "type": "expense"}},
        ]
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"},
             "categories": [{"name": "Food"}, {"name": "Transport"}], "transactions": rows},
            request_text="my Grab transactions",
        )
        result = executor.execute("search_transactions", {})
        self.assertEqual([t["id"] for t in result["transactions"]], ["g1"])

    def test_bare_name_typo_clarifies_category_or_text(self):
        executor, queries = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"},
             "categories": [{"name": "Food"}, {"name": "Transport"}], "transactions": []},
            request_text="my Fod transactions",
        )
        result = executor.execute("search_transactions", {})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("transactions", queries)

    def test_bare_name_exact_category_filters_by_category(self):
        rows = [
            {"id": "f1", "amount": 20, "source": "Speedmart", "description": "lunch",
             "transaction_date": "2026-07-11", "category": {"name": "Food", "type": "expense"}},
            {"id": "t1", "amount": 10, "source": "Grab", "description": "ride",
             "transaction_date": "2026-07-10", "category": {"name": "Transport", "type": "expense"}},
        ]
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"},
             "categories": [{"name": "Food"}, {"name": "Transport"}], "transactions": rows},
            request_text="my Food transactions",
        )
        result = executor.execute("search_transactions", {})
        self.assertEqual([t["id"] for t in result["transactions"]], ["f1"])

    def test_optional_tool_fields_accept_null_and_apply_model_defaults(self):
        from app.agent_tools import AGENT_TOOL_DEFINITIONS

        overview = next(
            item
            for item in AGENT_TOOL_DEFINITIONS
            if item["function"]["name"] == "get_financial_overview"
        )
        properties = overview["function"]["parameters"]["properties"]
        self.assertEqual(properties["month"]["type"], ["string", "null"])
        self.assertEqual(
            properties["compare_previous_period"]["type"], ["boolean", "null"]
        )
        self.assertIn(None, properties["reminder_range"]["enum"])

        executor, queries = self.make_executor(
            {"monthly_budgets": {}, "budgets": [], "profiles": {"spending_records_consent": "denied"}}
        )
        result = executor.execute(
            "get_budget_status", {"month": None, "category_name": None}
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn(("month", "2026-07-01"), queries["monthly_budgets"][0].eq_calls)

    def test_missing_reminder_date_returns_dynamic_choices_and_other(self):
        executor, _ = self.make_executor()

        result = executor.execute("prepare_reminder", {"title": "Pay PTPTN"})

        self.assertEqual(result["status"], "needs_clarification")
        interaction = result["ui_payload"]
        self.assertEqual(interaction["type"], "clarification")
        self.assertEqual(interaction["action_type"], "create_reminder")
        self.assertEqual(interaction["input_type"], "date")
        self.assertTrue(interaction["allow_other"])
        self.assertIn("Tomorrow", [option["label"] for option in interaction["options"]])
        self.assertEqual(interaction["draft"]["title"], "Pay PTPTN")

    def test_selected_reminder_date_without_time_asks_only_for_time(self):
        executor, _ = self.make_executor()

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Pay PTPTN",
                "due_date": "2026-07-29",
            },
        )

        self.assertEqual(result["status"], "needs_clarification")
        interaction = result["ui_payload"]
        self.assertEqual(interaction["field"], "time_of_day")
        self.assertEqual(interaction["input_type"], "time")
        self.assertEqual(interaction["draft"]["due_date"], "2026-07-29")

    def test_selected_reminder_date_and_time_return_confirmation(self):
        executor, _ = self.make_executor()

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Pay PTPTN",
                "due_date": "2026-07-29",
                "time_of_day": "20:00",
            },
        )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(
            result["ui_payload"]["arguments"]["due_at"],
            "2026-07-29T20:00:00+08:00",
        )

    def test_reminder_without_requested_lead_time_notifies_at_due_time(self):
        executor, _ = self.make_executor()

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Call mother",
                "due_at": "2026-07-24T20:00:00+08:00",
            },
        )

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["ui_payload"]["arguments"]["lead_days"], 0)
        self.assertNotIn(
            "Notify",
            [field["label"] for field in result["ui_payload"]["fields"]],
        )

    def test_past_reminder_is_rejected_before_confirmation(self):
        executor, _ = self.make_executor()

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Expired bill",
                "due_at": "2026-07-20T20:00:00+08:00",
            },
        )

        self.assertEqual(result["status"], "invalid_arguments")
        self.assertNotIn("ui_payload", result)

    def test_complete_reminder_returns_confirmation_not_database_write(self):
        executor, queries = self.make_executor()

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Pay PTPTN",
                "amount": 150,
                "due_at": "2026-08-15T20:00:00+08:00",
                "lead_days": 3,
                "recurrence": "monthly",
                "user_id": "attacker-controlled",
            },
        )

        self.assertEqual(result["status"], "confirmation_required")
        interaction = result["ui_payload"]
        self.assertEqual(interaction["type"], "action")
        self.assertEqual(interaction["action_type"], "create_reminder")
        self.assertEqual(interaction["status"], "pending")
        self.assertNotIn("user_id", interaction["arguments"])
        self.assertEqual(queries, {})

    def test_noncreation_request_cannot_prepare_a_reminder(self):
        executor, _ = self.make_executor(
            request_text="Cancel my existing rent reminder."
        )

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Rent",
                "due_at": "2026-08-15T20:00:00+08:00",
            },
        )

        self.assertEqual(result["status"], "not_allowed")
        self.assertNotIn("ui_payload", result)

    def test_explicit_creation_request_can_prepare_a_reminder(self):
        executor, _ = self.make_executor(
            request_text="Create a reminder to pay rent on 15 August at 8 PM."
        )

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Rent",
                "due_at": "2026-08-15T20:00:00+08:00",
            },
        )

        self.assertEqual(result["status"], "confirmation_required")

    def test_monthly_day_and_time_are_resolved_to_the_next_occurrence(self):
        executor, _ = self.make_executor()

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Pay PTPTN",
                "amount": 150,
                "day_of_month": 15,
                "time_of_day": "20:00",
                "lead_days": 3,
                "recurrence": "monthly",
            },
        )

        self.assertEqual(result["status"], "confirmation_required")
        arguments = result["ui_payload"]["arguments"]
        self.assertEqual(arguments["due_at"], "2026-08-15T20:00:00+08:00")
        self.assertEqual(arguments["lead_days"], 3)

    def test_user_wording_keeps_monthly_due_day_separate_from_lead_days(self):
        executor, _ = self.make_executor(
            request_text=(
                "Every month on the 15th, remind me three days earlier at 8 PM "
                "Malaysia time to pay PTPTN RM150."
            )
        )

        result = executor.execute(
            "prepare_reminder",
            {
                "title": "Pay PTPTN RM150",
                "amount": 150,
                "day_of_month": 12,
                "time_of_day": "20:00",
                "lead_days": 1,
                "recurrence": "monthly",
            },
        )

        arguments = result["ui_payload"]["arguments"]
        self.assertEqual(arguments["due_at"], "2026-08-15T20:00:00+08:00")
        self.assertEqual(arguments["lead_days"], 3)

    def test_transaction_tool_requires_consent_without_querying_transactions(self):
        executor, queries = self.make_executor(
            {"profiles": {"spending_records_consent": "denied"}}
        )

        result = executor.execute(
            "get_spending_summary",
            {"start_date": "2026-07-01", "end_date": "2026-07-31"},
        )

        self.assertEqual(result["status"], "permission_required")
        self.assertNotIn("transactions", queries)
        self.assertIn(("id", "verified-user"), queries["profiles"][0].eq_calls)

    def test_report_action_requires_spending_consent(self):
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "denied"}}
        )

        result = executor.execute("prepare_report", {"period": "current_month"})

        self.assertEqual(result["status"], "permission_required")
        self.assertNotIn("ui_payload", result)

    def test_report_dates_are_complete_without_reasking_for_a_period(self):
        executor, _ = self.make_executor(
            {"profiles": {"spending_records_consent": "granted"}}
        )

        result = executor.execute(
            "prepare_report",
            {
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
            },
        )

        self.assertEqual(result["status"], "confirmation_required")
        interaction = result["ui_payload"]
        self.assertEqual(interaction["type"], "action")
        self.assertEqual(interaction["arguments"]["period"], "custom")
        self.assertEqual(interaction["arguments"]["start_date"], "2026-07-01")
        self.assertEqual(interaction["arguments"]["end_date"], "2026-07-31")

    def test_all_data_queries_are_scoped_to_authenticated_user(self):
        executor, queries = self.make_executor(
            {
                "profiles": {"spending_records_consent": "granted"},
                "transactions": [],
            }
        )

        executor.execute(
            "get_spending_summary",
            {
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
                "user_id": "foreign-user",
            },
        )

        self.assertIn(("user_id", "verified-user"), queries["transactions"][0].eq_calls)
        self.assertNotIn(("user_id", "foreign-user"), queries["transactions"][0].eq_calls)

    def test_upcoming_reminders_use_malaysia_day_boundaries(self):
        executor, queries = self.make_executor(
            {"reminders": []},
            now=lambda: datetime(2026, 7, 24, 0, 30, tzinfo=timezone.utc),
        )

        result = executor.execute("get_upcoming_reminders", {"range": "today"})

        self.assertEqual(result["period"], {"start": "2026-07-24", "end": "2026-07-24"})
        filters = queries["reminders"][0].filters
        self.assertIn(("gte", "due_at", "2026-07-23T16:00:00+00:00"), filters)
        self.assertIn(("lt", "due_at", "2026-07-24T16:00:00+00:00"), filters)

    def test_month_shorthand_from_provider_is_accepted(self):
        executor, queries = self.make_executor(
            {
                "monthly_budgets": {"limit_amount": 600},
                "budgets": [],
                "profiles": {"spending_records_consent": "denied"},
            }
        )

        result = executor.execute("get_budget_status", {"month": "2026-07"})

        self.assertEqual(result["status"], "ok")
        self.assertIn(("month", "2026-07-01"), queries["monthly_budgets"][0].eq_calls)

    def test_category_budget_status_exposes_the_selected_category_limit(self):
        executor, _ = self.make_executor(
            {
                "monthly_budgets": {"limit_amount": 1000},
                "budgets": [
                    {"amount": 250, "category": {"name": "Food"}},
                    {"amount": 100, "category": {"name": "Entertainment"}},
                ],
                "profiles": {"spending_records_consent": "granted"},
                "transactions": [
                    {
                        "amount": 220,
                        "category": {"name": "Food", "type": "expense"},
                    },
                ],
            }
        )

        result = executor.execute(
            "get_budget_status",
            {"month": "2026-07", "category_name": "Food"},
        )

        self.assertEqual(
            result["selected_category"],
            {
                "name": "Food",
                "limit": "RM250.00",
                "recorded_spending": "RM220.00",
                "remaining": "RM30.00",
            },
        )

    def test_unfiltered_budget_status_exposes_per_category_spending(self):
        executor, _ = self.make_executor(
            {
                "monthly_budgets": {"limit_amount": 1000},
                "budgets": [
                    {"amount": 250, "category": {"name": "Food"}},
                    {"amount": 100, "category": {"name": "Entertainment"}},
                ],
                "profiles": {"spending_records_consent": "granted"},
                "transactions": [
                    {
                        "amount": 220,
                        "category": {"name": "Food", "type": "expense"},
                    },
                    {
                        "amount": 40,
                        "category": {"name": "Entertainment", "type": "expense"},
                    },
                ],
            }
        )

        result = executor.execute("get_budget_status", {"month": "2026-07"})

        self.assertEqual(
            result["category_statuses"],
            [
                {
                    "name": "Food",
                    "limit": "RM250.00",
                    "recorded_spending": "RM220.00",
                    "remaining": "RM30.00",
                },
                {
                    "name": "Entertainment",
                    "limit": "RM100.00",
                    "recorded_spending": "RM40.00",
                    "remaining": "RM60.00",
                },
            ],
        )


class AgentLLMLoopTests(unittest.TestCase):
    @staticmethod
    def response(*, content=None, tool_calls=None, model="test-model"):
        calls = []
        for index, call in enumerate(tool_calls or []):
            calls.append(
                SimpleNamespace(
                    id=f"call-{index}",
                    function=SimpleNamespace(
                        name=call[0],
                        arguments=json.dumps(call[1]) if not isinstance(call[1], str) else call[1],
                    ),
                )
            )
        message = SimpleNamespace(content=content, tool_calls=calls)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls" if calls else "stop")],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10),
            model=model,
        )

    def test_complex_question_executes_multiple_module_tools_before_answering(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(
            tool_calls=[
                ("get_spending_summary", {"compare_previous_period": True, "category_name": "Food"}),
                ("get_budget_status", {}),
                ("get_savings_goals", {"name": "Laptop"}),
                ("get_upcoming_reminders", {"range": "next_week"}),
            ]
        )
        second = self.response(content="Your food spending rose, budget is close, laptop goal is progressing, and one bill is due.")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create
        executed = []

        result = _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "Compare food spending with last month, check my budget, laptop goal, and bills next week.",
            tool_definitions=[
                {"type": "function", "function": {"name": name}}
                for name in (
                    "get_spending_summary",
                    "get_budget_status",
                    "get_savings_goals",
                    "get_upcoming_reminders",
                )
            ],
            tool_executor=lambda name, arguments: executed.append((name, arguments)) or {"status": "ok"},
            reasoning_effort="medium",
            max_iterations=3,
        )

        self.assertEqual(
            [name for name, _ in executed],
            [
                "get_spending_summary",
                "get_budget_status",
                "get_savings_goals",
                "get_upcoming_reminders",
            ],
        )
        self.assertIn("food spending rose", result.content.lower())
        self.assertEqual(
            [entry["name"] for entry in result.tool_results],
            [
                "get_spending_summary",
                "get_budget_status",
                "get_savings_goals",
                "get_upcoming_reminders",
            ],
        )
        second_request = create.call_args_list[1].kwargs
        self.assertEqual(
            [message["role"] for message in second_request["messages"][-5:]],
            ["assistant", "tool", "tool", "tool", "tool"],
        )

    def test_malformed_tool_arguments_are_returned_as_safe_tool_error(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(tool_calls=[("get_budget_status", "{not-json")])
        second = self.response(content="Please rephrase the budget period.")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create
        executor = MagicMock()

        result = _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "How is my budget?",
            tool_definitions=[],
            tool_executor=executor,
            reasoning_effort="medium",
            max_iterations=3,
        )

        executor.assert_not_called()
        tool_message = create.call_args_list[1].kwargs["messages"][-1]
        self.assertEqual(json.loads(tool_message["content"])["status"], "invalid_arguments")
        self.assertEqual(result.content, "Please rephrase the budget period.")

    def test_explicit_action_forces_its_first_tool_call(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(
            tool_calls=[("prepare_reminder", {"title": "Pay rent"})]
        )
        second = self.response(content="When should I remind you about Pay rent?")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create

        _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "Create a reminder to pay rent.",
            tool_definitions=[
                {"type": "function", "function": {"name": "prepare_reminder"}},
                {"type": "function", "function": {"name": "get_spending_summary"}},
            ],
            tool_executor=lambda _name, _arguments: {"status": "needs_clarification"},
            reasoning_effort="medium",
            max_iterations=3,
            required_tool_name="prepare_reminder",
        )

        self.assertEqual(
            create.call_args_list[0].kwargs["tool_choice"],
            "required",
        )
        self.assertEqual(
            [
                item["function"]["name"]
                for item in create.call_args_list[0].kwargs["tools"]
            ],
            ["prepare_reminder"],
        )
        self.assertEqual(create.call_args_list[1].kwargs["tool_choice"], "auto")

    def test_groq_agent_request_hides_reasoning_for_tool_calls(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(tool_calls=[("get_financial_overview", {})])
        second = self.response(content="Verified financial advice.")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create

        _generate_agent_with_provider(
            client_factory,
            _Provider(
                "primary",
                "https://api.groq.com/openai/v1",
                "secret",
                "openai/gpt-oss-120b",
            ),
            "What should I do first?",
            tool_definitions=[
                {"type": "function", "function": {"name": "get_financial_overview"}}
            ],
            tool_executor=lambda _name, _arguments: {"status": "ok"},
            reasoning_effort="high",
            max_iterations=3,
            required_tool_name="get_financial_overview",
        )

        self.assertEqual(
            create.call_args_list[0].kwargs["extra_body"],
            {"reasoning_format": "hidden"},
        )
        self.assertEqual(
            create.call_args_list[1].kwargs["extra_body"],
            {"reasoning_format": "hidden"},
        )

    def test_required_action_tool_cannot_be_ignored_by_provider(self):
        from app.llm import _Provider, _generate_agent_with_provider

        create = MagicMock(
            return_value=self.response(content="I handled it without a tool.")
        )
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create

        with self.assertRaisesRegex(RuntimeError, "required tool"):
            _generate_agent_with_provider(
                client_factory,
                _Provider("primary", "https://example.test", "secret", "test-model"),
                "Generate my July report.",
                tool_definitions=[
                    {"type": "function", "function": {"name": "prepare_report"}}
                ],
                tool_executor=MagicMock(),
                reasoning_effort="medium",
                max_iterations=3,
                required_tool_name="prepare_report",
            )

    def test_unregistered_tool_name_is_never_executed(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(
            tool_calls=[("prepare_report<|channel|>commentary", {"period": "last_month"})]
        )
        second = self.response(content="That tool call was rejected.")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create
        executor = MagicMock()

        result = _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "Generate my July report.",
            tool_definitions=[
                {"type": "function", "function": {"name": "prepare_report"}}
            ],
            tool_executor=executor,
            reasoning_effort="medium",
            max_iterations=3,
        )

        executor.assert_not_called()
        self.assertEqual(result.tool_names, ())
        tool_message = create.call_args_list[1].kwargs["messages"][-1]
        self.assertEqual(
            json.loads(tool_message["content"])["status"],
            "not_allowed",
        )

    def test_first_interaction_is_not_overwritten_by_a_later_tool_result(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(
            tool_calls=[
                ("prepare_reminder", {"title": "Pay rent"}),
                ("prepare_report", {"period": "last_month"}),
            ]
        )
        second = self.response(content="Both actions were considered.")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create
        reminder = {
            "status": "confirmation_required",
            "ui_payload": {
                "type": "action",
                "action_type": "create_reminder",
                "description": "Confirm reminder.",
            },
        }
        report = {
            "status": "confirmation_required",
            "ui_payload": {
                "type": "action",
                "action_type": "generate_report",
                "description": "Confirm report.",
            },
        }

        result = _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "Remind me to pay rent and generate last month's report.",
            tool_definitions=[
                {"type": "function", "function": {"name": "prepare_reminder"}},
                {"type": "function", "function": {"name": "prepare_report"}},
            ],
            tool_executor=lambda name, _arguments: (
                reminder if name == "prepare_reminder" else report
            ),
            reasoning_effort="medium",
            max_iterations=3,
        )

        self.assertEqual(result.ui_payload["action_type"], "create_reminder")

    def test_permission_required_result_cannot_be_contradicted_by_model(self):
        from app.llm import _Provider, _generate_agent_with_provider

        first = self.response(tool_calls=[("get_spending_summary", {})])
        second = self.response(content="You spent RM500 this month.")
        create = MagicMock(side_effect=[first, second])
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create

        result = _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "How much did I spend?",
            tool_definitions=[
                {"type": "function", "function": {"name": "get_spending_summary"}}
            ],
            tool_executor=lambda _name, _arguments: {
                "status": "permission_required",
                "message": "Spending access is required before reading transactions.",
            },
            reasoning_effort="medium",
            max_iterations=3,
        )

        self.assertIn("spending access is required", result.content.lower())
        self.assertNotIn("rm500", result.content.lower())

    def test_loop_is_bounded_to_three_tool_rounds_then_forces_final_synthesis(self):
        from app.llm import _Provider, _generate_agent_with_provider

        create = MagicMock(
            side_effect=[
                self.response(tool_calls=[("get_budget_status", {})]),
                self.response(tool_calls=[("get_budget_status", {})]),
                self.response(tool_calls=[("get_budget_status", {})]),
                self.response(content="Three checks completed; here is the bounded summary."),
            ]
        )
        client_factory = MagicMock()
        client_factory.return_value.chat.completions.create = create
        executor = MagicMock(return_value={"status": "ok"})

        result = _generate_agent_with_provider(
            client_factory,
            _Provider("primary", "https://example.test", "secret", "test-model"),
            "Keep checking forever.",
            tool_definitions=[],
            tool_executor=executor,
            reasoning_effort="medium",
            max_iterations=3,
        )
        self.assertEqual(executor.call_count, 3)
        self.assertEqual(create.call_count, 4)
        self.assertNotIn("tool_choice", create.call_args_list[3].kwargs)
        self.assertNotIn("tools", create.call_args_list[3].kwargs)
        self.assertIn("bounded summary", result.content)


class CoachingAgentIntegrationTests(unittest.TestCase):
    @staticmethod
    def interaction_service(payload, table_rows=None):
        from app.rag.service import CoachingService

        repository = MagicMock(user_id="verified-user")
        repository.require_interaction_message.return_value = {
            "id": "assistant-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "assistant",
            "ui_payload": payload,
        }
        rows = table_rows or {}
        client = MagicMock()
        client.table.side_effect = lambda name: ToolQuery(rows.get(name, []))
        return CoachingService(repository, client)

    def test_structured_date_reply_resumes_the_saved_reminder_draft_without_chat(self):
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        from app.rag.service import CoachingService

        tomorrow = (
            datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date() + timedelta(days=1)
        ).isoformat()
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "WiFi reminder",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-2",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": "Tomorrow",
        }
        repository.require_interaction_message.return_value = {
            "id": "assistant-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "assistant",
            "ui_payload": {
                "type": "clarification",
                "action_type": "create_reminder",
                "question": "When should I remind you about Pay WiFi bill?",
                "input_type": "date",
                "field": "due_at",
                "options": [],
                "allow_other": True,
                "draft": {
                    "title": "Pay WiFi bill",
                    "time_of_day": "21:00",
                    "lead_days": 1,
                    "recurrence": "none",
                },
            },
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]

        with (
            unittest.mock.patch("app.rag.service.COACH_WRITE_ACTIONS_ENABLED", True),
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError("A saved option reply must not return to ordinary chat."),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-2",
                "Tomorrow",
                interaction_reply={
                    "assistant_message_id": "assistant-1",
                    "value": tomorrow,
                },
            )

        interaction = result["assistant_message"]["ui_payload"]
        self.assertEqual(interaction["type"], "action")
        self.assertEqual(interaction["action_type"], "create_reminder")
        self.assertEqual(
            interaction["arguments"]["due_at"],
            f"{tomorrow}T21:00:00+08:00",
        )

    def test_typed_tomorrow_reply_resumes_reminder_date_clarification(self):
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        tomorrow = (
            datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date() + timedelta(days=1)
        ).isoformat()
        service = self.interaction_service(
            {
                "type": "clarification",
                "action_type": "create_reminder",
                "question": "When should I remind you?",
                "input_type": "date",
                "field": "due_at",
                "options": [],
                "allow_other": True,
                "draft": {
                    "title": "Pay WiFi",
                    "time_of_day": "21:00",
                    "recurrence": "none",
                },
            }
        )

        result = service._resume_interaction(
            "session-1",
            {"assistant_message_id": "assistant-1", "value": "tomorrow"},
        )

        self.assertEqual(result.ui_payload["type"], "action")
        self.assertEqual(
            result.ui_payload["arguments"]["due_at"],
            f"{tomorrow}T21:00:00+08:00",
        )

    def test_typed_malay_time_resumes_reminder_time_clarification(self):
        from datetime import timedelta
        from zoneinfo import ZoneInfo

        tomorrow = (
            datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date() + timedelta(days=1)
        ).isoformat()
        service = self.interaction_service(
            {
                "type": "clarification",
                "action_type": "create_reminder",
                "question": "Pukul berapa?",
                "input_type": "time",
                "field": "time_of_day",
                "options": [],
                "allow_other": True,
                "draft": {
                    "title": "Bayar sewa",
                    "due_date": tomorrow,
                    "recurrence": "none",
                },
            }
        )

        result = service._resume_interaction(
            "session-1",
            {"assistant_message_id": "assistant-1", "value": "pukul 9 malam"},
        )

        self.assertEqual(result.ui_payload["type"], "action")
        self.assertEqual(
            result.ui_payload["arguments"]["due_at"],
            f"{tomorrow}T21:00:00+08:00",
        )

    def test_typed_natural_report_range_resumes_date_range_clarification(self):
        service = self.interaction_service(
            {
                "type": "clarification",
                "action_type": "generate_report",
                "question": "What start and end dates should I use?",
                "input_type": "date_range",
                "field": "date_range",
                "options": [],
                "allow_other": True,
                "draft": {"period": "custom"},
            },
            {"profiles": {"spending_records_consent": "granted"}},
        )

        result = service._resume_interaction(
            "session-1",
            {
                "assistant_message_id": "assistant-1",
                "value": "1 May 2026 to 30 June 2026",
            },
        )

        self.assertEqual(result.ui_payload["type"], "action")
        self.assertEqual(
            result.ui_payload["arguments"]["start_date"],
            "2026-05-01",
        )
        self.assertEqual(
            result.ui_payload["arguments"]["end_date"],
            "2026-06-30",
        )

    def test_multiple_write_actions_are_split_before_calling_provider(self):
        from app.rag.service import CoachingService

        content = (
            "Remind me to pay rent on 5 August 2026 at 8 PM "
            "and generate my July spending report."
        )
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch("app.rag.service.COACH_WRITE_ACTIONS_ENABLED", True),
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError(
                    "Multiple confirmation actions must be split before provider execution."
                ),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        assistant = result["assistant_message"]
        self.assertIn("one at a time", assistant["content"].lower())
        self.assertEqual(assistant["ui_payload"], {})

    def test_invalid_calendar_date_is_rejected_before_calling_provider(self):
        from app.rag.service import CoachingService

        content = "Remind me to submit a form on 31 February 2027 at 9 AM."
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch("app.rag.service.COACH_WRITE_ACTIONS_ENABLED", True),
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError(
                    "An explicitly invalid calendar date must not reach the provider."
                ),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        assistant = result["assistant_message"]
        self.assertIn("not a valid calendar date", assistant["content"].lower())
        self.assertEqual(assistant["ui_payload"], {})

    def test_ambiguous_bill_payment_asks_permission_before_collecting_reminder_details(self):
        from app.rag.service import CoachingService

        content = "pay wifi bill"
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch("app.rag.service.COACH_WRITE_ACTIONS_ENABLED", True),
            unittest.mock.patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError(
                    "An ambiguous payment command must not reach ordinary chat."
                ),
            ),
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError(
                    "No reminder tool may run until the user confirms their intent."
                ),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        assistant = result["assistant_message"]
        interaction = assistant["ui_payload"]
        self.assertEqual(interaction["type"], "clarification")
        self.assertEqual(interaction["action_type"], "create_reminder")
        self.assertEqual(interaction["field"], "confirm_reminder_intent")
        self.assertEqual(interaction["draft"]["title"], "Pay wifi bill")
        self.assertEqual(
            [option["value"] for option in interaction["options"]],
            ["create_reminder", "not_now"],
        )
        self.assertNotIn("tomorrow", assistant["content"].lower())
        self.assertNotIn("9 pm", assistant["content"].lower())

    def test_declining_ambiguous_reminder_intent_stops_without_preparing_action(self):
        service = self.interaction_service(
            {
                "type": "clarification",
                "action_type": "create_reminder",
                "question": "Would you like me to create a reminder to pay wifi bill?",
                "input_type": "single_select",
                "field": "confirm_reminder_intent",
                "options": [
                    {
                        "id": "create_reminder",
                        "label": "Create reminder",
                        "value": "create_reminder",
                    },
                    {
                        "id": "not_now",
                        "label": "Not now",
                        "value": "not_now",
                    },
                ],
                "allow_other": False,
                "draft": {"title": "Pay wifi bill", "recurrence": "none"},
            }
        )

        result = service._resume_interaction(
            "session-1",
            {"assistant_message_id": "assistant-1", "value": "not_now"},
        )

        self.assertEqual(result.model, "fincoach-action-engine")
        self.assertIsNone(result.ui_payload)
        self.assertIn("not created", result.content.lower())

    def test_confirming_ambiguous_reminder_intent_collects_date_before_time(self):
        service = self.interaction_service(
            {
                "type": "clarification",
                "action_type": "create_reminder",
                "question": "Would you like me to create a reminder to pay wifi bill?",
                "input_type": "single_select",
                "field": "confirm_reminder_intent",
                "options": [
                    {
                        "id": "create_reminder",
                        "label": "Create reminder",
                        "value": "create_reminder",
                    },
                    {
                        "id": "not_now",
                        "label": "Not now",
                        "value": "not_now",
                    },
                ],
                "allow_other": False,
                "draft": {"title": "Pay wifi bill", "recurrence": "none"},
            }
        )

        result = service._resume_interaction(
            "session-1",
            {
                "assistant_message_id": "assistant-1",
                "value": "create_reminder",
            },
        )

        self.assertEqual(result.ui_payload["type"], "clarification")
        self.assertEqual(result.ui_payload["field"], "due_date")
        self.assertIn("when should i remind", result.content.lower())
        self.assertNotIn("9 pm", result.content.lower())

    def test_no_tool_chat_response_cannot_claim_a_reminder_was_scheduled(self):
        from app.llm import LLMResult
        from app.rag.service import CoachingService

        content = "tell a joke"
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with unittest.mock.patch(
            "app.rag.service.generate_result",
            return_value=LLMResult(
                "Sure, I'll remind you tomorrow at 9 PM.",
                "test-model",
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        assistant = result["assistant_message"]
        self.assertIn("not created", assistant["content"].lower())
        self.assertNotIn("tomorrow at 9", assistant["content"].lower())
        self.assertEqual(assistant["ui_payload"], {})

    def test_non_action_question_executes_one_read_tool_without_agent_loop(self):
        from app.llm import AgentLLMResult, LLMResult
        from app.rag.service import CoachingService

        content = "Show my Food budget status"
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch(
                "app.rag.service.AgentToolExecutor.execute",
                return_value={
                    "status": "ok",
                    "selected_category": {"name": "Food", "limit": "RM250.00"},
                },
            ) as execute_tool,
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                return_value=AgentLLMResult("Agent response.", "agent-model"),
            ) as generate_agent,
            unittest.mock.patch(
                "app.rag.service.generate_result",
                return_value=LLMResult("Food budget is RM250.", "test-model"),
            ) as generate,
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        execute_tool.assert_called_once_with("get_budget_status", {"category_name": "Food"})
        generate_agent.assert_not_called()
        generate.assert_not_called()
        self.assertIn("RM250.00", result["assistant_message"]["content"])

    def test_disabled_write_actions_never_call_provider_or_show_action_ui(self):
        from app.rag.service import CoachingService

        content = "Remind me to pay rent tomorrow at 8 PM"
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch(
                "app.rag.service.COACH_WRITE_ACTIONS_ENABLED",
                False,
                create=True,
            ),
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                side_effect=AssertionError(
                    "Disabled write actions must not reach the provider."
                ),
            ),
            unittest.mock.patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError(
                    "Disabled write actions must return a deterministic response."
                ),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        assistant = result["assistant_message"]
        self.assertIn("disabled", assistant["content"].lower())
        self.assertIn("reminder", assistant["content"].lower())
        self.assertEqual(assistant["ui_payload"], {})

    def test_advice_only_mode_blocks_action_offer_after_a_typo_routes_to_chat(self):
        from app.llm import LLMResult
        from app.rag.service import CoachingService

        content = "pay billl"
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": content,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch(
                "app.rag.service.COACH_WRITE_ACTIONS_ENABLED",
                False,
            ),
            unittest.mock.patch(
                "app.rag.service.generate_result",
                return_value=LLMResult(
                    "Let me know the amount and I can help you plan or "
                    "set a reminder.",
                    "test-model",
                ),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                content,
            )

        assistant = result["assistant_message"]
        self.assertIn("advice-only", assistant["content"].lower())
        self.assertIn("cannot create", assistant["content"].lower())
        self.assertIn("alerts", assistant["content"].lower())
        self.assertEqual(assistant["ui_payload"], {})

    def test_disabled_write_actions_reject_an_existing_confirmation_card(self):
        from app.rag.service import CoachingService

        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": "Confirm",
        }
        repository.complete_turn.side_effect = (
            lambda **kwargs: kwargs["assistant_payload"]
        )

        with (
            unittest.mock.patch(
                "app.rag.service.COACH_WRITE_ACTIONS_ENABLED",
                False,
            ),
            unittest.mock.patch.object(
                CoachingService,
                "_resume_interaction",
                side_effect=AssertionError(
                    "The kill switch must also block old confirmation cards."
                ),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                "Confirm",
                interaction_reply={
                    "interaction_id": "old-action-card",
                    "field": "confirm",
                    "value": "confirm",
                },
            )

        assistant = result["assistant_message"]
        self.assertIn("disabled", assistant["content"].lower())
        self.assertIn("no reminder or report was created", assistant["content"].lower())
        self.assertEqual(assistant["ui_payload"], {})

    def test_finance_turn_uses_agent_tools_and_persists_interaction_payload(self):
        from app.llm import AgentLLMResult
        from app.rag.service import CoachingService

        request_text = (
            "Every month on the 15th, remind me three days earlier at 8 PM "
            "to pay PTPTN."
        )
        repository = MagicMock(user_id="verified-user")
        repository.require_session.return_value = {
            "id": "session-1",
            "title": "New conversation",
        }
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "user_id": "verified-user",
            "role": "user",
            "content": request_text,
        }
        repository.list_messages.return_value = []
        repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
        interaction = {
            "type": "clarification",
            "question": "When should I remind you?",
            "input_type": "date",
            "options": [],
            "allow_other": True,
        }

        with (
            unittest.mock.patch("app.rag.service.COACH_WRITE_ACTIONS_ENABLED", True),
            unittest.mock.patch("app.rag.service.retrieve", return_value=[]),
            unittest.mock.patch(
                "app.rag.service.generate_agent_result",
                return_value=AgentLLMResult(
                    "When should I remind you?",
                    "test-model",
                    30,
                    8,
                    interaction,
                    ("prepare_reminder",),
                ),
            ) as generate,
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1",
                "message-1",
                request_text,
            )

        self.assertEqual(result["assistant_message"]["ui_payload"], interaction)
        self.assertEqual(
            repository.complete_turn.call_args.kwargs["assistant_payload"]["ui_payload"],
            interaction,
        )
        self.assertEqual(generate.call_args.kwargs["max_iterations"], 3)
        definition_names = {
            item["function"]["name"]
            for item in generate.call_args.kwargs["tool_definitions"]
        }
        self.assertIn("prepare_reminder", definition_names)
        self.assertNotIn("prepare_report", definition_names)
        self.assertIn(
            "Current Malaysia date and time:",
            generate.call_args.args[0],
        )
        self.assertIn("Asia/Kuala_Lumpur", generate.call_args.args[0])
        self.assertEqual(
            generate.call_args.kwargs["required_tool_name"],
            "prepare_reminder",
        )
        tool_executor = generate.call_args.kwargs["tool_executor"]
        self.assertTrue(callable(tool_executor))
        prepared = tool_executor(
            "prepare_reminder",
            {
                "title": "Pay PTPTN",
                "day_of_month": 12,
                "time_of_day": "20:00",
                "lead_days": 1,
                "recurrence": "monthly",
            },
        )
        self.assertEqual(prepared["ui_payload"]["arguments"]["lead_days"], 3)
        self.assertEqual(
            prepared["ui_payload"]["arguments"]["due_at"][8:10],
            "15",
        )


if __name__ == "__main__":
    unittest.main()
