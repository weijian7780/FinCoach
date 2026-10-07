import unittest
from pathlib import Path


class RetrievalEvaluationTests(unittest.TestCase):
    def test_fails_acceptance_when_expected_sources_are_filtered_out(self):
        from rag_evaluation import passes_acceptance

        metrics = {
            "hit_at_3": 1.0,
            "mrr": 1.0,
            "expected_retained": 0.0,
            "average_returned_sources": 0.0,
        }

        self.assertFalse(
            passes_acceptance(
                metrics,
                min_hit_at_3=1.0,
                min_mrr=0.98,
                min_expected_retained=1.0,
                max_average_sources=2.0,
            )
        )

    def test_reports_hit_rates_mrr_and_filtered_source_count(self):
        from app.rag.evaluation import EvaluationCase, evaluate_rankings

        cases = [
            EvaluationCase("first", "Question one", ("source-a",)),
            EvaluationCase("second", "Question two", ("source-b",)),
        ]
        ranked = {
            "first": ["source-a", "source-b"],
            "second": ["source-a", "source-b"],
        }
        returned = {
            "first": ["source-a"],
            "second": ["source-a", "source-b"],
        }

        result = evaluate_rankings(cases, ranked, returned)

        self.assertEqual(result.case_count, 2)
        self.assertEqual(result.hit_at_1, 0.5)
        self.assertEqual(result.hit_at_3, 1.0)
        self.assertEqual(result.expected_retained, 1.0)
        self.assertEqual(result.mrr, 0.75)
        self.assertEqual(result.average_returned_sources, 1.5)

    def test_reports_full_coverage_for_a_multi_source_question(self):
        from app.rag.evaluation import EvaluationCase, evaluate_rankings

        result = evaluate_rankings(
            [
                EvaluationCase(
                    "two-topics",
                    "PTPTN and SOCSO",
                    ("ptptn.md", "perkeso.md"),
                ),
            ],
            {"two-topics": ["ptptn.md", "other.md", "perkeso.md"]},
            {"two-topics": ["ptptn.md", "perkeso.md"]},
        )

        self.assertEqual(result.expected_retained, 1.0)
        self.assertEqual(result.source_coverage_at_3, 1.0)
        self.assertEqual(result.precision_at_3, 2 / 3)

    def test_load_cases_converts_legacy_labels_to_source_tuples(self):
        from rag_evaluation import load_cases

        cases = load_cases(Path("tests/fixtures/rag_retrieval_cases.json"))

        self.assertEqual(cases[0].expected_sources, ("official_akpk_debt_help_and_financial_education.md",))


if __name__ == "__main__":
    unittest.main()
