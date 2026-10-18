import unittest
from unittest.mock import patch

from app.rag import grounding

_SAVED_VALIDATION_FLAG = grounding._VALIDATION_ENABLED


def setUpModule():
    # The verifier/salvage path only runs when validation first fails, so these
    # tests force the guard on regardless of the COACH_ANSWER_VALIDATION kill
    # switch (which defaults off in the live path).
    grounding._VALIDATION_ENABLED = True


def tearDownModule():
    grounding._VALIDATION_ENABLED = _SAVED_VALIDATION_FLAG


class GroundingVerifierTests(unittest.TestCase):
    def test_service_uses_the_verifier_selected_source_for_a_missing_citation(self):
        from app.llm import LLMResult, CoachRequestBudget
        from app.rag.retrieval import RetrievedChunk
        from app.rag.service import _ground_educational_answer
        from app.rag.verifier import GroundingVerification

        answer = LLMResult(
            content=(
                "**Insight**\n"
                "PTPTN provides education loans.\n"
                "**Recommended action**\n"
                "Check the current PTPTN rules before acting.\n"
                "**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice."
            ),
            model="deepseek-v4-flash",
        )
        unrelated_chunk = RetrievedChunk(
            1, "PIDM guidance", "official_pidm.md", None, 0,
            "PIDM protects eligible deposits.", 0.71,
        )
        ptptn_chunk = RetrievedChunk(
            2, "PTPTN guidance", "official_ptptn.md", None, 0,
            "PTPTN provides education loans to students at local institutions.", 0.70,
        )

        with (
            patch(
                "app.rag.service.verify_grounding_claims",
                return_value=GroundingVerification(
                    {1: "supported"}, source_indices={1: 2}
                ),
            ),
            patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError("a repairable citation must not regenerate"),
            ),
        ):
            result, retried, fallback = _ground_educational_answer(
                answer,
                chunks=[unrelated_chunk, ptptn_chunk],
                prompt="unused",
                verified_context="",
                allow_uncited_numbers=False,
                require_source_for_facts=True,
                budget=CoachRequestBudget.start(),
            )

        self.assertIn("PTPTN provides education loans [S2].", result.content)
        self.assertFalse(retried)
        self.assertFalse(fallback)

    def test_service_uses_deepseek_directly_for_one_correction(self):
        from app.llm import LLMResult, CoachRequestBudget
        from app.rag.retrieval import RetrievedChunk
        from app.rag.service import _ground_educational_answer
        from app.rag.verifier import GroundingVerification

        invalid_answer = LLMResult(
            content=(
                "**Insight**\n"
                "PIDM provides education loans.\n"
                "**Recommended action**\n"
                "Check official information before acting.\n"
                "**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice."
            ),
            model="deepseek-v4-flash",
        )
        corrected_answer = LLMResult(
            content=(
                "**Insight**\n"
                "PTPTN provides education loans [S1].\n"
                "**Recommended action**\n"
                "Check the current PTPTN rules before acting.\n"
                "**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice."
            ),
            model="deepseek-v4-flash",
        )
        chunk = RetrievedChunk(
            1, "PTPTN guidance", "official_ptptn.md", None, 0,
            "PTPTN provides education loans to students at local institutions.", 0.70,
        )

        with (
            patch(
                "app.rag.service.verify_grounding_claims",
                return_value=GroundingVerification({1: "unsupported"}),
            ),
            patch(
                "app.rag.service.generate_fallback_result",
                return_value=corrected_answer,
            ) as fallback_generate,
            patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError("correction must bypass NVIDIA"),
            ),
        ):
            result, retried, fallback = _ground_educational_answer(
                invalid_answer,
                chunks=[chunk],
                prompt="unused",
                verified_context="",
                allow_uncited_numbers=False,
                require_source_for_facts=True,
                budget=CoachRequestBudget.start(),
            )

        self.assertEqual(result.content, corrected_answer.content)
        self.assertTrue(retried)
        self.assertFalse(fallback)
        fallback_generate.assert_called_once()

    def test_service_repairs_a_supported_missing_citation_without_regeneration(self):
        from app.llm import LLMResult, CoachRequestBudget
        from app.rag.retrieval import RetrievedChunk
        from app.rag.service import _ground_educational_answer
        from app.rag.verifier import GroundingVerification

        answer = LLMResult(
            content=(
                "**Insight**\n"
                "PTPTN provides education loans.\n"
                "**Recommended action**\n"
                "Check the current PTPTN rules before acting.\n"
                "**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice."
            ),
            model="deepseek-v4-flash",
        )
        chunk = RetrievedChunk(
            1,
            "PTPTN guidance",
            "official_ptptn_loan_guidance.md",
            None,
            0,
            "PTPTN provides education loans to students at local institutions.",
            0.70,
        )

        with (
            patch(
                "app.rag.service.verify_grounding_claims",
                return_value=GroundingVerification({1: "supported"}),
            ),
            patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError("a repairable citation must not regenerate"),
            ),
        ):
            result, retried, fallback = _ground_educational_answer(
                answer,
                chunks=[chunk],
                prompt="unused",
                verified_context="",
                allow_uncited_numbers=False,
                require_source_for_facts=True,
                budget=CoachRequestBudget.start(),
            )

        self.assertIn("PTPTN provides education loans [S1].", result.content)
        self.assertFalse(retried)
        self.assertFalse(fallback)

    def test_service_returns_the_original_answer_when_the_verifier_supports_its_only_uncertain_claim(self):
        from app.llm import LLMResult, CoachRequestBudget
        from app.rag.retrieval import RetrievedChunk
        from app.rag.service import _ground_educational_answer
        from app.rag.verifier import GroundingVerification

        answer = LLMResult(
            content=(
                "**Insight**\n"
                "PTPTN is Malaysia's national higher-education fund that provides study "
                "financing to students [S1].\n"
                "**Recommended action**\n"
                "Check the current PTPTN rules before applying.\n"
                "**Educational guidance**\n"
                "This is educational guidance, not licensed financial advice."
            ),
            model="deepseek-v4-flash",
        )
        chunk = RetrievedChunk(
            1,
            "PTPTN guidance",
            "official_ptptn_loan_guidance.md",
            None,
            0,
            (
                "PTPTN manages loans for higher education and collects repayments. "
                "The PTPTN Education Loan Scheme provides educational loans to students "
                "at local higher education institutions."
            ),
            0.70,
        )

        with (
            patch(
                "app.rag.service.verify_grounding_claims",
                return_value=GroundingVerification({1: "supported"}),
            ),
            patch(
                "app.rag.service.generate_result",
                side_effect=AssertionError("a supported answer must not be regenerated"),
            ),
        ):
            result, retried, fallback = _ground_educational_answer(
                answer,
                chunks=[chunk],
                prompt="unused",
                verified_context="",
                allow_uncited_numbers=False,
                require_source_for_facts=True,
                budget=CoachRequestBudget.start(),
            )

        self.assertEqual(result.content, answer.content)
        self.assertFalse(retried)
        self.assertFalse(fallback)

    def test_returns_supported_only_for_every_requested_claim_id(self):
        from app.rag.grounding import GroundingClaim
        from app.rag.verifier import verify_grounding_claims

        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {
                                    "content": (
                                        '{"claims":[{"id":1,"verdict":"supported","source_index":1}]}'
                                    )
                                },
                            )()
                        },
                    )()
                ]
            },
        )()
        client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": type("Completions", (), {"create": lambda *_args, **_kwargs: response})()})()},
        )()
        claim = GroundingClaim(
            id=1,
            text="PTPTN provides education loans [S1].",
            cited_indices=(1,),
        )

        with patch("app.rag.verifier._create_verifier_client", return_value=client):
            result = verify_grounding_claims(
                [claim],
                ["PTPTN provides education loans to local students."],
                timeout_seconds=5,
            )

        self.assertTrue(result.all_supported)
        self.assertEqual(result.verdicts, {1: "supported"})
        self.assertEqual(result.source_indices, {1: 1})

    def test_rejects_a_supported_missing_citation_without_a_selected_source(self):
        from app.rag.grounding import GroundingClaim
        from app.rag.verifier import verify_grounding_claims

        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {"content": '{"claims":[{"id":1,"verdict":"supported"}]}'},
                            )()
                        },
                    )()
                ]
            },
        )()
        client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": type("Completions", (), {"create": lambda *_args, **_kwargs: response})()})()},
        )()
        claim = GroundingClaim(
            id=1,
            text="PTPTN provides education loans.",
            cited_indices=(1,),
            requires_citation=True,
        )

        with patch("app.rag.verifier._create_verifier_client", return_value=client):
            result = verify_grounding_claims(
                [claim],
                ["PTPTN provides education loans to local students."],
                timeout_seconds=5,
            )

        self.assertEqual(result.error_code, "invalid_verifier_response")

    def test_rejects_a_verifier_response_that_omits_a_claim_id(self):
        from app.rag.grounding import GroundingClaim
        from app.rag.verifier import verify_grounding_claims

        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": '{"claims":[]}'})()},
                    )()
                ]
            },
        )()
        client = type(
            "Client",
            (),
            {"chat": type("Chat", (), {"completions": type("Completions", (), {"create": lambda *_args, **_kwargs: response})()})()},
        )()
        claim = GroundingClaim(
            id=1,
            text="PTPTN provides education loans [S1].",
            cited_indices=(1,),
        )

        with patch("app.rag.verifier._create_verifier_client", return_value=client):
            result = verify_grounding_claims(
                [claim],
                ["PTPTN provides education loans to local students."],
                timeout_seconds=5,
            )

        self.assertFalse(result.all_supported)
        self.assertEqual(result.error_code, "invalid_verifier_response")
