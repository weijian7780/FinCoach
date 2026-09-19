"""The profile coaching-style label is turned into an explicit tone directive
that reaches the coach prompt via the financial context."""

import unittest


class CoachingStyleDirectiveTests(unittest.TestCase):
    def test_known_styles_map_to_explicit_tone_directives(self):
        from app.rag.service import _coaching_style_directive

        gentle = _coaching_style_directive("Gentle nudges")
        detailed = _coaching_style_directive("Detailed guidance")
        tough = _coaching_style_directive("Tough-love")

        self.assertIn("gentle nudges", gentle.lower())
        self.assertIn("low-pressure", gentle.lower())
        self.assertIn("explain the reasoning", detailed.lower())
        self.assertIn("tough love", tough.lower())
        self.assertIn("direct", tough.lower())
        # Tough-love must stay respectful, never shaming.
        self.assertIn("never harsh", tough.lower())

    def test_matching_is_case_and_whitespace_insensitive(self):
        from app.rag.service import _coaching_style_directive

        self.assertEqual(
            _coaching_style_directive("  TOUGH-LOVE  "),
            _coaching_style_directive("Tough-love"),
        )

    def test_unknown_style_falls_back_to_the_label(self):
        from app.rag.service import _coaching_style_directive

        # Preserves the pre-existing behaviour for any non-UI value.
        self.assertEqual(
            _coaching_style_directive("direct"),
            "Preferred coaching style: direct",
        )

    def test_missing_style_yields_nothing(self):
        from app.rag.service import _coaching_style_directive

        self.assertIsNone(_coaching_style_directive(None))
        self.assertIsNone(_coaching_style_directive(""))

    def test_directive_reaches_the_financial_context(self):
        from app.rag.service import format_financial_context

        context = format_financial_context(
            profile={"monthly_allowance": 800, "coaching_style": "Tough-love"},
            transactions=[],
            monthly_budget=None,
            category_limits=[],
            savings_goals=[],
        )
        self.assertIn("tough love", context.lower())
        self.assertIn("push for action", context.lower())


if __name__ == "__main__":
    unittest.main()
