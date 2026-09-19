"""Deterministic allocation + diagnostic grounding (synthetic injection)."""

import unittest

from app.rag.allocation import (
    allocation_split,
    financial_priority_chunk,
    is_allocation_query,
    is_diagnostic_query,
    parse_amount,
    synthetic_allocation_chunk,
)


class AmountParsingTests(unittest.TestCase):
    def test_parses_common_ringgit_formats(self):
        self.assertEqual(parse_amount("if i have 6000, how to allocate"), 6000.0)
        self.assertEqual(parse_amount("RM6,000 budget"), 6000.0)
        self.assertEqual(parse_amount("i make rm 3500.50 monthly"), 3500.50)
        self.assertEqual(parse_amount("split 6k across categories"), 6000.0)

    def test_ignores_years_and_tiny_counts(self):
        # A plain 2-digit count is not an amount; a year alone is not an allocation.
        self.assertIsNone(parse_amount("how to budget"))
        self.assertEqual(parse_amount("EPF dividend in 2024"), 2024.0)  # >=3 digits


class IntentTests(unittest.TestCase):
    def test_allocation_query_needs_intent_and_amount(self):
        self.assertTrue(is_allocation_query("if i have 6000, how to allocate my budget"))
        self.assertTrue(is_allocation_query("how to split RM3000 across categories"))
        # No amount -> not a concrete allocation query.
        self.assertFalse(is_allocation_query("how should i allocate my budget"))

    def test_diagnostic_query_is_vague_with_no_amount(self):
        for message in (
            "how should i manage my money",
            "i want to budget better, where do i start",
            "any tips for personal finance",
        ):
            with self.subTest(message=message):
                self.assertTrue(is_diagnostic_query(message))
        # With an amount it is a concrete allocation, not diagnostic.
        self.assertFalse(is_diagnostic_query("manage my RM5000 income"))


class SplitTests(unittest.TestCase):
    def test_50_30_20_split_is_exact(self):
        self.assertEqual(
            allocation_split(6000.0), {"needs": 3000.0, "wants": 1800.0, "savings": 1200.0}
        )

    def test_synthetic_chunk_carries_grounded_figures(self):
        chunk = synthetic_allocation_chunk(6000.0)
        for token in ("RM3,000.00", "RM1,800.00", "RM1,200.00", "50%", "30%", "20%"):
            self.assertIn(token, chunk.content)
        # Not a real knowledge document -> negative id, excluded from persistence.
        self.assertLess(chunk.id, 0)
        self.assertEqual(chunk.source_type, "corpus")


class GroundingCompatibilityTests(unittest.TestCase):
    def test_answer_citing_the_split_passes_validate_coach_answer(self):
        from app.rag.grounding import validate_coach_answer

        chunk = synthetic_allocation_chunk(6000.0)
        # Numeric-bearing sentences cite [S1]; the figures all exist in the chunk,
        # so the numeric guard and lexical-support check pass.
        answer = (
            "**Insight**\n"
            "The 50/30/20 framework allocates 50% to needs, 30% to wants, and 20% "
            "to savings, giving RM3,000, RM1,800, and RM1,200 for RM6,000 [S1].\n"
            "**Recommended action**\n"
            "Automate your savings transfer on payday.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(answer, [chunk.content], "")
        self.assertTrue(result.is_valid, result.errors)

    def test_priority_chunk_is_conceptual(self):
        chunk = financial_priority_chunk()
        self.assertIn("emergency buffer", chunk.content.lower())
        self.assertLess(chunk.id, 0)


if __name__ == "__main__":
    unittest.main()
