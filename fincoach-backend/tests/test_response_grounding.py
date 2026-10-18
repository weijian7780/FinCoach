import unittest

from app.rag import grounding

_SAVED_VALIDATION_FLAG = grounding._VALIDATION_ENABLED


def setUpModule():
    # These tests assert the deterministic guard CATCHES fabrication, so they
    # run with validation forced on regardless of the COACH_ANSWER_VALIDATION
    # kill switch (which defaults off in the live path).
    grounding._VALIDATION_ENABLED = True


def tearDownModule():
    grounding._VALIDATION_ENABLED = _SAVED_VALIDATION_FLAG


class ResponseGroundingTests(unittest.TestCase):
    def test_does_not_treat_a_cited_recommendation_as_an_external_fact(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects eligible deposits [S1].\n"
            "**Recommended action**\n"
            "Review your own account balance before acting [S1].\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertTrue(result.is_valid, result.errors)

    def test_exposes_supported_paraphrase_as_an_uncertain_claim_for_verification(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PTPTN is Malaysia's national higher-education fund that provides study "
            "financing to students [S1].\n"
            "**Recommended action**\n"
            "Check the current PTPTN rules before applying.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        source = (
            "PTPTN manages loans for higher education and collects repayments. "
            "The PTPTN Education Loan Scheme provides educational loans to students "
            "at local higher education institutions."
        )

        result = validate_coach_answer(content, [source], "")

        self.assertEqual(result.hard_errors, ())
        self.assertEqual(len(result.uncertain_claims), 1)
        self.assertEqual(result.uncertain_claims[0].cited_indices, (1,))

    def test_epf_paraphrase_across_passages_requires_semantic_review(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "EPF (KWSP) is Malaysia's retirement savings scheme; as a student, you can "
            "voluntarily contribute through i-Simpan if you are an eligible Malaysian "
            "citizen or permanent resident [S1].\n"
            "**Recommended action**\n"
            "Check the current KWSP eligibility rules before contributing.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        source = (
            "# EPF (KWSP) basics for Malaysian students and new workers\n"
            "## Voluntary retirement savings: i-Simpan\n"
            "i-Simpan is KWSP's voluntary contribution option for eligible Malaysian "
            "citizens or permanent residents who are registered EPF members."
        )

        result = validate_coach_answer(content, [source], "")

        # Overlap across headings and prose does not establish the whole rule;
        # the source also qualifies contributors as registered EPF members.
        self.assertEqual(result.hard_errors, ())
        self.assertEqual(len(result.uncertain_claims), 1)
        self.assertEqual(result.uncertain_claims[0].cited_indices, (1,))

    def test_accepts_line_level_citation_for_each_supported_sentence(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects eligible deposits. PIDM protects eligible deposits up to "
            "RM250,000 [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits up to RM250,000."],
            "",
        )

        self.assertTrue(result.is_valid, result.errors)

    def test_rejects_a_cited_claim_that_contradicts_its_source(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM does not protect eligible deposits [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("opposite negation polarity", result.hard_errors[0])

    def test_marks_an_opposite_polarity_claim_as_a_hard_error(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM does not protect eligible deposits [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertIn("opposite negation polarity", result.hard_errors[0])

    def test_checks_the_matching_source_sentence_not_document_wide_negation(self):
        from app.rag.grounding import validate_coach_answer

        valid_content = (
            "**Insight**\n"
            "PIDM protects eligible deposits [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        invalid_content = valid_content.replace(
            "PIDM protects eligible deposits",
            "PIDM does not protect eligible deposits",
        )
        document = (
            "PIDM protects eligible deposits. "
            "PIDM does not cover every investment."
        )

        self.assertTrue(validate_coach_answer(valid_content, [document], "").is_valid)
        self.assertFalse(validate_coach_answer(invalid_content, [document], "").is_valid)

    def test_rejects_an_uncited_external_guarantee(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM guarantees every investment.\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("source marker", result.errors[0])

    def test_rejects_any_cited_statement_that_its_source_cannot_support(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "Investment products receive PIDM protection [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM does not protect investment products."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("opposite negation polarity", result.hard_errors[0])

    def test_accepts_a_personal_amount_from_verified_context_without_a_source(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "Your recorded spending this month is RM120.\n"
            "**Recommended action**\n"
            "Review the transaction list before spending more.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            [],
            "Monthly recorded spending: RM120.",
        )

        self.assertTrue(result.is_valid)

    def test_accepts_equivalent_monetary_formats_from_verified_context(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "Your recorded spending this month is RM120.\n"
            "**Recommended action**\n"
            "Review the transaction list before spending more.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            [],
            "Monthly recorded spending: RM120.00.",
        )

        self.assertTrue(result.is_valid)

    def test_rejects_a_citation_when_the_non_numeric_claim_is_not_supported(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM covers foreign equities [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
            require_source_for_facts=True,
        )

        self.assertFalse(result.is_valid)
        self.assertIn("does not support", result.errors[0])

    def test_rejects_a_partial_numeric_match(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects RM250 [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits up to RM250,000."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("RM250", result.errors[0])

    def test_rejects_an_external_financial_fact_without_a_source_marker(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects eligible deposits.\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("source marker", result.errors[0])

    def test_marks_a_supported_missing_citation_as_repairable(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PTPTN provides education loans.\n"
            "**Recommended action**\n"
            "Check the current PTPTN rules before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PTPTN provides education loans to students at local institutions."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.hard_errors, ())
        self.assertEqual(len(result.uncertain_claims), 1)
        self.assertEqual(result.uncertain_claims[0].cited_indices, (1,))

    def test_rejects_an_amount_not_present_in_the_cited_reference(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects RM100,000 [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits up to RM250,000."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("RM100,000", result.errors[0])

    def test_accepts_a_number_supported_by_the_cited_reference(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects eligible deposits up to RM250,000 [S1].\n"
            "**Recommended action**\n"
            "Check PIDM before acting.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits up to RM250,000."],
            "",
        )

        self.assertTrue(result.is_valid)

    def test_rejects_a_specific_product_recommendation(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "Open a Student Savings Account [S1].\n"
            "**Recommended action**\n"
            "Use that account today.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )
        result = validate_coach_answer(
            content,
            ["FinCoach must not recommend an app or product."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("product recommendation", result.errors[0])


class LabeledExampleNumberTests(unittest.TestCase):
    def test_accepts_a_clearly_labeled_hypothetical_amount(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects eligible deposits [S1].\n"
            "**Recommended action**\n"
            "For example, setting aside RM50 each week builds a steady saving habit.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertTrue(result.is_valid, result.errors)

    def test_still_rejects_an_unlabeled_invented_amount(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM protects eligible deposits [S1].\n"
            "**Recommended action**\n"
            "Aim to save RM9999 in total.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM protects eligible deposits."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("RM9999", result.errors[0])


class ProductRedirectTests(unittest.TestCase):
    def test_detects_a_specific_product_recommendation(self):
        from app.rag.grounding import contains_specific_product_recommendation

        self.assertTrue(
            contains_specific_product_recommendation(
                "You should open a Maybank savings account today."
            )
        )
        self.assertTrue(
            contains_specific_product_recommendation(
                "Just use the Touch 'n Go e-wallet for everything."
            )
        )

    def test_ignores_a_neutral_educational_statement(self):
        from app.rag.grounding import contains_specific_product_recommendation

        self.assertFalse(
            contains_specific_product_recommendation(
                "An emergency fund helps you prepare for unexpected costs."
            )
        )

    def test_safe_product_redirect_is_a_neutral_coach_answer(self):
        from app.rag.grounding import (
            DISCLAIMER,
            contains_specific_product_recommendation,
            safe_product_redirect,
        )

        redirect = safe_product_redirect()

        self.assertIn("**Insight**", redirect)
        self.assertIn("**Recommended action**", redirect)
        self.assertTrue(redirect.endswith(DISCLAIMER))
        self.assertIn("does not recommend or rank", redirect)
        # The redirect itself must not trip the product-recommendation detector.
        self.assertFalse(contains_specific_product_recommendation(redirect))


class MalayGroundingTests(unittest.TestCase):
    def test_accepts_a_cited_malay_fact_supported_by_its_source(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM melindungi deposit yang layak [S1].\n"
            "**Recommended action**\n"
            "Semak laman web rasmi PIDM sebelum bertindak.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM melindungi deposit yang layak."],
            "",
        )

        self.assertTrue(result.is_valid, result.errors)

    def test_marks_an_uncited_malay_external_fact_as_repairable(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM melindungi deposit yang layak.\n"
            "**Recommended action**\n"
            "Semak laman web rasmi PIDM sebelum bertindak.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM melindungi deposit yang layak."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.hard_errors, ())
        self.assertEqual(len(result.uncertain_claims), 1)
        self.assertEqual(result.uncertain_claims[0].cited_indices, (1,))

    def test_rejects_an_opposite_polarity_malay_claim_as_a_hard_error(self):
        from app.rag.grounding import validate_coach_answer

        content = (
            "**Insight**\n"
            "PIDM tidak melindungi deposit yang layak [S1].\n"
            "**Recommended action**\n"
            "Semak laman web rasmi PIDM sebelum bertindak.\n"
            "**Educational guidance**\n"
            "This is educational guidance, not licensed financial advice."
        )

        result = validate_coach_answer(
            content,
            ["PIDM melindungi deposit yang layak."],
            "",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("opposite negation polarity", result.hard_errors[0])


if __name__ == "__main__":
    unittest.main()
