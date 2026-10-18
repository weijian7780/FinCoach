import unittest

from app.rag import grounding

_SAVED_VALIDATION_FLAG = grounding._VALIDATION_ENABLED


def setUpModule():
    # The guard-behaviour tests here assert validation rejects bad drafts, so
    # they force it on regardless of the COACH_ANSWER_VALIDATION kill switch
    # (which defaults off in the live path).
    grounding._VALIDATION_ENABLED = True


def tearDownModule():
    grounding._VALIDATION_ENABLED = _SAVED_VALIDATION_FLAG


class FinancialGroundingRoutingTests(unittest.TestCase):
    def test_routes_malay_general_budget_and_emergency_fund_questions_to_rag(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        for message in ("Apa itu bajet?", "Apa itu simpanan kecemasan?"):
            with self.subTest(message=message):
                self.assertEqual(
                    route_coach_message(message),
                    CoachingRoute.FINANCIAL_EDUCATION,
                )

    def test_routes_malay_and_informal_financial_education_to_rag(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        cases = (
            "Bagaimana AKPK boleh membantu saya mengurus hutang?",
            "Apa maksud pelaburan patuh Syariah?",
            "duit ewallet dgn bank digital pidm cover tak",
        )

        for message in cases:
            with self.subTest(message=message):
                self.assertEqual(
                    route_coach_message(message),
                    CoachingRoute.FINANCIAL_EDUCATION,
                )

    def test_routes_malay_personal_spending_question_to_owner_scoped_tools(self):
        from app.rag.routing import (
            CoachingRoute,
            required_read_agent_tool_name,
            route_coach_message,
        )

        message = "Berapa saya belanja bulan ini?"

        self.assertEqual(route_coach_message(message), CoachingRoute.PERSONAL_FINANCE)
        self.assertEqual(required_read_agent_tool_name(message), "get_spending_summary")

    def test_data_dependent_quick_actions_are_not_casual_chat(self):
        from app.rag.routing import (
            CoachingRoute,
            required_read_agent_tool_name,
            route_coach_message,
        )

        for message in ("What should I do first?", "Show the calculation"):
            with self.subTest(message=message):
                self.assertEqual(route_coach_message(message), CoachingRoute.PERSONAL_FINANCE)
                self.assertEqual(
                    required_read_agent_tool_name(message),
                    "get_financial_overview",
                )

    def test_personal_facts_force_the_narrowest_relevant_read_tool(self):
        from app.rag.routing import required_read_agent_tool_name

        cases = {
            "How much did I spend this month?": "get_spending_summary",
            "Am I over budget?": "get_budget_status",
            "How is my savings goal going?": "get_savings_goals",
            "Which bill is due tomorrow?": "get_upcoming_reminders",
        }
        for message, expected_tool in cases.items():
            with self.subTest(message=message):
                self.assertEqual(required_read_agent_tool_name(message), expected_tool)


class FinancialGroundingPromptTests(unittest.TestCase):
    def test_prompt_rejects_history_as_evidence_for_personal_facts(self):
        from app.rag.prompts import build_coach_prompt

        prompt = build_coach_prompt(
            "What should I do first?",
            [],
            "Personal records are available through tools.",
            [{"role": "assistant", "content": "Pay RM100 at 9 PM."}],
            10,
        )

        self.assertIn("never evidence for a recorded amount", prompt)
        self.assertIn("tool result from this turn verifies them", prompt)


class FactualNamingPromptTests(unittest.TestCase):
    def test_prompt_permits_factual_naming_from_any_cited_source(self):
        from app.rag.prompts import build_coach_prompt

        prompt = build_coach_prompt("What was the EPF dividend?", [], "", [], 6)

        # Task 6: factual naming from ANY cited tier is allowed, with a confidence
        # label; recommending/ranking/endorsing stays absolutely prohibited.
        self.assertIn("cited source of\n  ANY tier supports the naming", prompt)
        self.assertIn("Never recommend, rank, endorse", prompt)
        self.assertIn("never the same as recommending", prompt)
        # The old tier-1/2-only restriction must be gone.
        self.assertNotIn("backed by a cited tier-1 or tier-2", prompt)

    def test_education_guard_still_blocks_imperative_recommendation(self):
        from app.rag.grounding import validate_coach_answer

        answer = (
            "**Insight**\nYou should open a Maybank account today.\n"
            "**Recommended action**\nDo it now.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(answer, [], "")
        self.assertFalse(result.is_valid)
        self.assertIn(
            "specific product recommendation is not allowed", result.errors
        )


class FinancialNumericClaimTests(unittest.TestCase):
    def test_example_abbreviations_cannot_match_inside_ordinary_words(self):
        from app.rag.grounding import (
            normalise_and_validate_numeric_claims,
            recorded_money_claims_match_tools,
        )

        for content in (
            "Begin to save RM9999 monthly.",
            "It is convenient to save RM9999 each month.",
        ):
            with self.subTest(content=content):
                self.assertIsNone(normalise_and_validate_numeric_claims(
                    content, "Verified monthly allowance RM900 and expenses RM650."
                ))
                self.assertFalse(recorded_money_claims_match_tools(content, [{
                    "result": {"status": "ok", "monthly_allowance": "RM900", "recorded_expenses": "RM650"},
                }]))

    def test_standalone_example_abbreviation_still_allows_an_illustration(self):
        from app.rag.grounding import normalise_and_validate_numeric_claims

        for content in ("For example, save RM50.", "E.g. save RM50.", "Contohnya simpan RM50."):
            with self.subTest(content=content):
                self.assertEqual(normalise_and_validate_numeric_claims(content, ""), content)

    def test_normalises_only_a_verified_dollar_label_to_ringgit(self):
        from app.rag.grounding import normalise_and_validate_numeric_claims

        self.assertEqual(
            normalise_and_validate_numeric_claims(
                "Your Food budget has $140 remaining.",
                "Verified tool result: remaining RM140.",
            ),
            "Your Food budget has RM140 remaining.",
        )

    def test_rejects_an_invented_financial_number_without_another_provider_call(self):
        from app.rag.grounding import normalise_and_validate_numeric_claims

        self.assertIsNone(
            normalise_and_validate_numeric_claims(
                "Save RM100 this week.",
                "Verified tool result: monthly allowance RM900 and expenses RM650.",
            )
        )

    def test_allows_a_clearly_labeled_hypothetical_amount(self):
        from app.rag.grounding import normalise_and_validate_numeric_claims

        content = "For example, saving RM500 monthly builds a steady habit."
        self.assertEqual(
            normalise_and_validate_numeric_claims(
                content,
                "Verified tool result: monthly allowance RM900.",
            ),
            content,
        )

    def test_rejects_an_amount_in_a_different_sentence_from_the_example_cue(self):
        from app.rag.grounding import normalise_and_validate_numeric_claims

        self.assertIsNone(
            normalise_and_validate_numeric_claims(
                "For example, budgeting helps. You must set aside RM777 now.",
                "Verified tool result: monthly allowance RM900.",
            )
        )


class ProductSelectionRoutingTests(unittest.TestCase):
    def test_flags_market_product_selection_requests(self):
        from app.rag.routing import is_product_selection_request

        for message in (
            "which bank should I open an account with?",
            "what's the best e-wallet in Malaysia?",
            "recommend a unit trust",
            "should I buy Bitcoin?",
            "which broker should I use for stocks?",
            "best insurance to get?",
        ):
            with self.subTest(message=message):
                self.assertTrue(is_product_selection_request(message))

    def test_leaves_educational_and_personal_questions_alone(self):
        from app.rag.routing import is_product_selection_request

        for message in (
            "what is an emergency fund?",
            "what is a mutual fund?",
            "how do e-wallets work?",
            "what does PIDM protect?",
            "which of my funds performed best?",
            "how much did I spend at the bank?",
            "hi there",
        ):
            with self.subTest(message=message):
                self.assertFalse(is_product_selection_request(message))


class CasualPromptSafetyTests(unittest.TestCase):
    def test_casual_prompt_forbids_naming_a_specific_product(self):
        from app.rag.prompts import build_casual_prompt

        prompt = build_casual_prompt("which bank is best?", [], 10)

        self.assertIn("Never recommend or name a specific", prompt)


if __name__ == "__main__":
    unittest.main()
