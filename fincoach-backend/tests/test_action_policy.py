import importlib
import os
import unittest
from unittest.mock import patch


class BoundedActionPolicyTests(unittest.TestCase):
    def test_grounds_every_unverified_write_claim_without_blocking_advice(self):
        from app.rag.action_policy import ground_unverified_action_claim

        claims = [
            "Sure! I'll set a reminder for tomorrow at 9 PM.",
            "I set a reminder for your bill.",
            "I've added a reminder for Friday.",
            "I created your rent reminder.",
            "I scheduled an alert for next Monday.",
            "I'll remind you tomorrow at 9 PM.",
            "I will notify you next Friday.",
            "Your reminder has been scheduled.",
            "The reminder is now set.",
            "Done — reminder created.",
            "I generated and saved your report.",
            "Your report is ready for download.",
            "The monthly report has been generated.",
        ]
        for content in claims:
            with self.subTest(content=content):
                grounded = ground_unverified_action_claim(
                    content,
                    has_action_ui=False,
                )
                self.assertIn("not completed", grounded.lower())
                self.assertNotEqual(grounded, content)

        advice = [
            "You can set a reminder in the Alerts module.",
            "I recommend setting a reminder before the bill is due.",
            "Would you like me to create a reminder?",
            "Your next step is to review the report.",
            "No reminder or report was created.",
        ]
        for content in advice:
            with self.subTest(content=content):
                self.assertEqual(
                    ground_unverified_action_claim(
                        content,
                        has_action_ui=False,
                    ),
                    content,
                )

    def test_action_ui_allows_confirmation_copy_but_not_free_chat_claims(self):
        from app.rag.action_policy import ground_unverified_action_claim

        content = "FinCoach will add this reminder only after you confirm."
        self.assertEqual(
            ground_unverified_action_claim(content, has_action_ui=True),
            content,
        )

    def test_bounded_tools_never_expose_unrequested_write_actions(self):
        from app.rag.action_policy import bounded_tool_definitions

        definitions = [
            {"function": {"name": "get_budget_status"}},
            {"function": {"name": "get_upcoming_reminders"}},
            {"function": {"name": "prepare_reminder"}},
            {"function": {"name": "prepare_report"}},
        ]

        read_only = bounded_tool_definitions(definitions)
        reminder = bounded_tool_definitions(
            definitions,
            requested_write_tool="prepare_reminder",
        )
        disabled = bounded_tool_definitions(
            definitions,
            requested_write_tool="prepare_reminder",
            writes_enabled=False,
        )

        self.assertEqual(
            [item["function"]["name"] for item in read_only],
            ["get_budget_status", "get_upcoming_reminders"],
        )
        self.assertEqual(
            [item["function"]["name"] for item in reminder],
            [
                "get_budget_status",
                "get_upcoming_reminders",
                "prepare_reminder",
            ],
        )
        self.assertEqual(
            [item["function"]["name"] for item in disabled],
            ["get_budget_status", "get_upcoming_reminders"],
        )

    def test_write_action_environment_flag_requires_explicit_opt_in(self):
        import app.config as config

        original = os.environ.get("COACH_WRITE_ACTIONS_ENABLED")
        try:
            # Keep a developer's local .env from masking the missing-variable case.
            # A deployment that omits this setting must never expose write tools.
            os.environ.pop("COACH_WRITE_ACTIONS_ENABLED", None)
            with patch("dotenv.load_dotenv", return_value=False):
                config = importlib.reload(config)
            self.assertFalse(config.COACH_WRITE_ACTIONS_ENABLED)

            os.environ["COACH_WRITE_ACTIONS_ENABLED"] = "false"
            config = importlib.reload(config)
            self.assertFalse(config.COACH_WRITE_ACTIONS_ENABLED)

            os.environ["COACH_WRITE_ACTIONS_ENABLED"] = "true"
            config = importlib.reload(config)
            self.assertTrue(config.COACH_WRITE_ACTIONS_ENABLED)
        finally:
            if original is None:
                os.environ.pop("COACH_WRITE_ACTIONS_ENABLED", None)
            else:
                os.environ["COACH_WRITE_ACTIONS_ENABLED"] = original
            importlib.reload(config)

    def test_advice_only_mode_replaces_first_person_action_offers(self):
        from app.rag.action_policy import ground_disabled_action_offer

        offers = [
            "Let me know the amount and I can help you plan or set a reminder.",
            "We can check your balance and set a reminder for the due date.",
            "Would you like me to create a reminder for tomorrow?",
            "Let me generate and save that report for you.",
        ]
        for content in offers:
            with self.subTest(content=content):
                grounded = ground_disabled_action_offer(content)
                self.assertIn("advice-only", grounded.lower())
                self.assertIn("cannot create", grounded.lower())
                self.assertNotEqual(grounded, content)

        advice = [
            "You can set a phone alarm for 8:45 AM.",
            "Open Alerts and choose Manage reminders.",
            "I can help you plan how much money to keep aside.",
        ]
        for content in advice:
            with self.subTest(content=content):
                self.assertEqual(
                    ground_disabled_action_offer(content),
                    content,
                )


if __name__ == "__main__":
    unittest.main()
