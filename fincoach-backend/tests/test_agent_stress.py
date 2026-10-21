import unittest
from datetime import date, datetime, timedelta, timezone
from itertools import product


class RoutingStressTests(unittest.TestCase):
    def test_reminder_management_matrix_never_forces_creation(self):
        from app.rag.routing import (
            CoachingRoute,
            required_agent_tool_name,
            route_coach_message,
        )

        reminder_objects = [
            "rent reminder",
            "WiFi reminder",
            "bill alert",
            "spending notification",
            "peringatan sewa",
            "notifikasi belanja",
        ]
        management_verbs = [
            "show",
            "list",
            "view",
            "cancel",
            "delete",
            "remove",
            "turn off",
            "disable",
            "change",
            "edit",
            "open settings for",
            "tunjuk",
            "padam",
            "matikan",
            "tukar",
        ]
        for verb, reminder_object in product(management_verbs, reminder_objects):
            prompt = f"{verb} my {reminder_object}"
            with self.subTest(prompt=prompt):
                self.assertIsNone(required_agent_tool_name(prompt))
                self.assertEqual(
                    route_coach_message(prompt),
                    CoachingRoute.PERSONAL_FINANCE,
                )

    def test_reminder_creation_matrix_forces_preparation(self):
        from app.rag.routing import required_agent_tool_name

        templates = [
            "remind me to {task}",
            "create a reminder to {task}",
            "set an alert to {task}",
            "notify me to {task}",
            "nudge me to {task}",
            "ping me to {task}",
            "ingatkan saya untuk {task}",
            "buat peringatan untuk {task}",
        ]
        tasks = [
            "pay rent",
            "record spending",
            "submit assignment",
            "bayar sewa",
            "rekod belanja",
        ]
        for template, task in product(templates, tasks):
            prompt = template.format(task=task)
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    required_agent_tool_name(prompt),
                    "prepare_reminder",
                )

    def test_report_management_matrix_never_forces_generation(self):
        from app.rag.routing import required_agent_tool_name

        report_objects = [
            "report",
            "financial report",
            "spending PDF",
            "laporan",
            "PDF laporan",
        ]
        management_phrases = [
            "show history for",
            "list saved",
            "view saved",
            "delete",
            "remove",
            "explain",
            "why did you create",
            "tunjuk sejarah",
            "padam",
        ]
        for phrase, report_object in product(management_phrases, report_objects):
            prompt = f"{phrase} my {report_object}"
            with self.subTest(prompt=prompt):
                self.assertIsNone(required_agent_tool_name(prompt))

    def test_report_creation_matrix_forces_preparation(self):
        from app.rag.routing import required_agent_tool_name

        report_objects = [
            "report",
            "financial report",
            "spending PDF",
            "laporan",
            "PDF laporan",
        ]
        creation_verbs = [
            "generate",
            "create",
            "make",
            "download",
            "export",
            "build",
            "prepare",
            "jana",
            "buat",
            "sediakan",
            "muat turun",
        ]
        for verb, report_object in product(creation_verbs, report_objects):
            prompt = f"{verb} my {report_object} for July"
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    required_agent_tool_name(prompt),
                    "prepare_report",
                )

    def test_action_negation_matrix_never_forces_a_tool(self):
        from app.rag.routing import required_agent_tool_name

        prompts = [
            "do not create a reminder",
            "do not set an alert",
            "don't make a reminder",
            "I don't want a reminder",
            "jangan buat peringatan",
            "do not generate a report",
            "don't create a PDF",
            "I don't want a report",
            "jangan jana laporan",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIsNone(required_agent_tool_name(prompt))


class BoundedActionPolicyStressTests(unittest.TestCase):
    def test_write_claim_matrix_is_never_allowed_as_ordinary_chat(self):
        from app.rag.action_policy import ground_unverified_action_claim

        verbs_and_objects = [
            ("set", "reminder"),
            ("created", "reminder"),
            ("scheduled", "alert"),
            ("added", "notification"),
            ("generated", "report"),
            ("saved", "report"),
            ("updated", "budget"),
            ("deleted", "transaction"),
            ("removed", "category"),
            ("cancelled", "reminder"),
            ("exported", "report"),
        ]
        subjects = ["I", "I have", "I've", "We", "FinCoach"]
        for subject, (verb, action_object) in product(subjects, verbs_and_objects):
            content = f"{subject} {verb} your {action_object}."
            with self.subTest(content=content):
                grounded = ground_unverified_action_claim(
                    content,
                    has_action_ui=False,
                )
                self.assertIn("not completed", grounded.lower())

    def test_completed_state_matrix_is_never_allowed_as_ordinary_chat(self):
        from app.rag.action_policy import ground_unverified_action_claim

        action_objects = [
            "reminder",
            "report",
            "transaction",
            "budget",
            "savings goal",
        ]
        states = ["created", "scheduled", "saved", "updated", "deleted"]
        for action_object, state in product(action_objects, states):
            content = f"Your {action_object} has been {state}."
            with self.subTest(content=content):
                grounded = ground_unverified_action_claim(
                    content,
                    has_action_ui=False,
                )
                self.assertIn("not completed", grounded.lower())

    def test_advice_and_negation_matrix_remains_normal_coaching_text(self):
        from app.rag.action_policy import ground_unverified_action_claim

        templates = [
            "You can create a {item} in the app.",
            "I recommend creating a {item}.",
            "Would you like me to create a {item}?",
            "No {item} was created.",
            "Your {item} was not created.",
        ]
        for template, item in product(
            templates,
            ["reminder", "report", "transaction", "budget", "savings goal"],
        ):
            content = template.format(item=item)
            with self.subTest(content=content):
                self.assertEqual(
                    ground_unverified_action_claim(
                        content,
                        has_action_ui=False,
                    ),
                    content,
                )


class ClarificationParserStressTests(unittest.TestCase):
    def test_every_valid_24_hour_minute_round_trips(self):
        from app.rag.service import _parse_local_time

        for hour in range(24):
            for minute in range(60):
                value = f"{hour:02d}:{minute:02d}"
                with self.subTest(value=value):
                    self.assertEqual(_parse_local_time(value), value)

    def test_english_and_malay_date_aliases_cross_boundaries(self):
        from app.rag.service import _parse_local_date

        reference_dates = [
            date(2024, 2, 28),
            date(2024, 2, 29),
            date(2026, 7, 29),
            date(2026, 12, 31),
        ]
        for reference in reference_dates:
            with self.subTest(reference=reference, value="tomorrow"):
                self.assertEqual(
                    _parse_local_date("tomorrow", reference),
                    reference + timedelta(days=1),
                )
            with self.subTest(reference=reference, value="esok"):
                self.assertEqual(
                    _parse_local_date("esok", reference),
                    reference + timedelta(days=1),
                )
            with self.subTest(reference=reference, value="minggu depan"):
                self.assertEqual(
                    _parse_local_date("minggu depan", reference),
                    reference + timedelta(days=7),
                )

    def test_natural_and_iso_date_ranges_parse_to_literal_dates(self):
        from app.rag.service import _parse_date_range

        cases = {
            "1 May 2026 to 30 June 2026": (
                date(2026, 5, 1),
                date(2026, 6, 30),
            ),
            "1 May 2026 hingga 30 June 2026": (
                date(2026, 5, 1),
                date(2026, 6, 30),
            ),
            "2026-05-01 to 2026-06-30": (
                date(2026, 5, 1),
                date(2026, 6, 30),
            ),
            "20 Ogos 2026 sampai 31 Disember 2026": (
                date(2026, 8, 20),
                date(2026, 12, 31),
            ),
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    _parse_date_range(value, date(2026, 7, 29)),
                    expected,
                )


class ReminderBoundaryStressTests(unittest.TestCase):
    def test_240_past_and_future_hour_offsets_are_classified_safely(self):
        from app.agent_tools import AgentToolExecutor

        now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        executor = AgentToolExecutor(
            None,
            user_id="synthetic-user",
            session_id="synthetic-session",
            now=lambda: now,
        )
        for hours in range(-120, 121):
            if hours == 0:
                continue
            due_at = now + timedelta(hours=hours)
            result = executor.execute(
                "prepare_reminder",
                {
                    "title": f"Offset {hours}",
                    "due_at": due_at.isoformat(),
                },
            )
            expected = "confirmation_required" if hours > 0 else "invalid_arguments"
            with self.subTest(hours=hours):
                self.assertEqual(result["status"], expected)
                if hours > 0:
                    self.assertEqual(
                        result["ui_payload"]["arguments"]["lead_days"],
                        0,
                    )

    def test_all_supported_monthly_anchor_days_resolve_to_the_future(self):
        from app.agent_tools import AgentToolExecutor

        now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        executor = AgentToolExecutor(
            None,
            user_id="synthetic-user",
            session_id="synthetic-session",
            now=lambda: now,
        )
        for day in range(1, 29):
            result = executor.execute(
                "prepare_reminder",
                {
                    "title": f"Monthly {day}",
                    "day_of_month": day,
                    "time_of_day": "20:00",
                    "recurrence": "monthly",
                },
            )
            with self.subTest(day=day):
                self.assertEqual(result["status"], "confirmation_required")
                due_at = datetime.fromisoformat(
                    result["ui_payload"]["arguments"]["due_at"]
                )
                self.assertGreater(due_at.astimezone(timezone.utc), now)


if __name__ == "__main__":
    unittest.main()
