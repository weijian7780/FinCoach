import json
import unittest
from pathlib import Path


class RagEvaluationCaseTests(unittest.TestCase):
    def test_every_labelled_financial_education_case_enters_a_rag_route(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        fixture = Path(__file__).parent / "fixtures" / "rag_retrieval_cases.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))

        positive_cases = [case for case in cases if case["expected_source"]]
        self.assertEqual(len(positive_cases), 51)
        for case in positive_cases:
            with self.subTest(case=case["id"]):
                self.assertIn(
                    route_coach_message(case["query"]),
                    {CoachingRoute.FINANCIAL_EDUCATION, CoachingRoute.COMBINED},
                )

    def test_casual_negative_cases_do_not_enter_rag(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        fixture = Path(__file__).parent / "fixtures" / "rag_retrieval_cases.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))

        for case in (case for case in cases if case["expected_source"] is None):
            with self.subTest(case=case["id"]):
                self.assertEqual(route_coach_message(case["query"]), CoachingRoute.CASUAL)


if __name__ == "__main__":
    unittest.main()
