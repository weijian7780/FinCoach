"""Budget-allocation / hypothetical-amount routing.

Regression for: "if I have 6000, how to allocate my monthly budget" was routed to
PERSONAL_FINANCE and answered with the user's recorded budget rows (month limit /
remaining) instead of explaining an allocation method. An allocation/method
request is educational; a hypothetical amount is planning framing, not a recorded
figure.
"""

import unittest

from app.rag.routing import (
    CoachingRoute,
    required_read_agent_tool_name,
    route_coach_message,
    select_financial_context_scope,
)


class BudgetAllocationRoutingTests(unittest.TestCase):
    def test_hypothetical_amount_allocation_is_educational_not_personal(self):
        for message in (
            "if i have 6000, how to allocate my monthly budget",
            "how to split RM3000 across categories",
            "what is the 50/30/20 rule",
            "kalau saya ada 6000, macam mana nak agih bajet",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    route_coach_message(message), CoachingRoute.FINANCIAL_EDUCATION
                )

    def test_allocation_of_own_budget_without_hypothetical_is_combined(self):
        # "my" budget + a method request -> education applied to their records.
        self.assertEqual(
            route_coach_message("how should I allocate my monthly budget"),
            CoachingRoute.COMBINED,
        )

    def test_normative_general_questions_are_educational(self):
        # "what do people normally set" carries no personal marker -> educational,
        # not a dump of the user's recorded budget.
        for message in (
            "people normally set what budget",
            "what budget do most students set",
            "how much should a student save",
            "what's the recommended emergency fund",
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    route_coach_message(message), CoachingRoute.FINANCIAL_EDUCATION
                )

    def test_normative_budget_question_does_not_request_personal_budget_data(self):
        message = "people normally set what budget"

        self.assertEqual(route_coach_message(message), CoachingRoute.FINANCIAL_EDUCATION)
        self.assertIsNone(required_read_agent_tool_name(message))
        self.assertIsNone(select_financial_context_scope(message))

    def test_recorded_status_questions_stay_personal(self):
        # These must NOT be pulled into the education path by the new rules.
        for message in (
            "Am I over budget?",
            "How much did I spend this month?",
            "how is my savings goal going?",
            "which bill is due tomorrow?",
            "show my budget breakdown",  # shipped quick-action; a personal lookup
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    route_coach_message(message), CoachingRoute.PERSONAL_FINANCE
                )


if __name__ == "__main__":
    unittest.main()
