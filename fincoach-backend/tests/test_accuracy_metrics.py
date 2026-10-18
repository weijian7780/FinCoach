import unittest
from app.rag.evaluation import EvaluationCase, evaluate_rankings


class RetrievalMetricsTests(unittest.TestCase):
    def test_precision_recall_f1_are_distinct_and_duplicates_do_not_inflate(self):
        result = evaluate_rankings([EvaluationCase("q", "query", ("a", "b"))],
                                   {"q": ["a", "a", "x", "b"]}, {"q": ["a", "a", "x"]})
        self.assertEqual(result.precision, 0.5)
        self.assertEqual(result.recall, 0.5)
        self.assertEqual(result.f1, 0.5)
        self.assertAlmostEqual(result.precision_at_3, 2 / 3)
        self.assertEqual(result.recall_at_3, 1.0)
        self.assertAlmostEqual(result.f1_at_3, 0.8)

    def test_empty_and_unanswerable_cases_are_not_dropped(self):
        cases = [EvaluationCase("a", "answerable", ("a",)), EvaluationCase("n", "none", ())]
        result = evaluate_rankings(cases, {"a": [], "n": []}, {"a": [], "n": []})
        self.assertEqual(result.f1, 0)
        self.assertEqual(result.answerable_count, 1)
        self.assertEqual(result.unanswerable_count, 1)
        self.assertEqual(result.abstention_accuracy, 1)
        self.assertEqual(len(result.per_case), 2)

    def test_dataset_loader_keeps_negatives_and_candidate_labels(self):
        from pathlib import Path
        from rag_evaluation import load_cases
        cases = load_cases(Path("tests/fixtures/rag_fyp_candidate_cases.json"))
        self.assertEqual(len(cases), 22)
        self.assertTrue(any(not case.expected_sources for case in cases))
        self.assertTrue(all(case.label_status == "candidate_unreviewed" for case in cases))
        self.assertTrue(any(case.history for case in cases))

    def test_missing_results_and_duplicate_ids_fail_loudly(self):
        case = EvaluationCase("q", "q", ("a",))
        with self.assertRaises(ValueError):
            evaluate_rankings([case], {}, {})
        with self.assertRaises(ValueError):
            evaluate_rankings([case, case], {"q": []}, {"q": []})

    def test_at_k_precision_uses_fixed_denominator(self):
        result = evaluate_rankings([EvaluationCase("q", "q", ("a",))], {"q": ["a"]}, {"q": ["a"]})
        self.assertAlmostEqual(result.precision_at_3, 1 / 3)
        self.assertEqual(result.precision, 1)
        self.assertEqual(result.recall, 1)
        self.assertEqual(result.f1, 1)
