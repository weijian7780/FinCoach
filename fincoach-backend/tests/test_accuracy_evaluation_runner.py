"""Runner integration uses synthetic vectors/RPC results; never real scores."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from app.rag.evaluation import EvaluationCase
from app.rag.retrieval import RetrievedChunk
from rag_evaluation import run_evaluation


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("tests/fixtures/rag_retrieval_cases.json")
        self.case = EvaluationCase("q", "example", ("a.md",), label_status="human_reviewed")
        self.chunk = SimpleNamespace(source="a.md", chunk_index=0, content="Evidence", page=None, title="A")

    def test_dense_runner_scores_actual_filtered_sources(self):
        with patch("rag_evaluation.load_cases", return_value=[self.case]), patch(
            "app.rag.ingestion.load_documents", return_value=[]
        ), patch("ingest.build_chunks", return_value=[self.chunk]), patch(
            "app.embeddings.embed_texts", return_value=[[1.0, 0.0]]
        ):
            metrics = run_evaluation(self.path, mode="dense")
        self.assertEqual(metrics["precision"], 1)
        self.assertEqual(metrics["recall"], 1)
        self.assertEqual(metrics["f1"], 1)
        self.assertEqual(metrics["mode"], "dense")
        self.assertGreaterEqual(metrics["per_case"][0]["retrieval_ms"], 0)

    def test_hybrid_calls_production_boundary_and_rejects_fallback(self):
        def retrieve(_query, *, analysis, trace):
            trace.update(mode="hybrid", ranked_sources=["a.md"])
            return [RetrievedChunk(1, "A", "a.md", None, 0, "Evidence", 0.9)]
        with patch("rag_evaluation.load_cases", return_value=[self.case]), patch(
            "app.rag.ingestion.load_documents", return_value=[]
        ), patch("ingest.build_chunks", return_value=[self.chunk]), patch(
            "app.rag.retrieval.retrieve", side_effect=retrieve
        ) as production:
            metrics = run_evaluation(self.path, mode="hybrid")
        production.assert_called_once()
        self.assertEqual(metrics["f1"], 1)
        self.assertFalse(metrics["database_corpus_verified"])

        def fallback(_query, *, analysis, trace):
            trace.update(mode="dense_fallback", ranked_sources=[])
            return []
        with patch("rag_evaluation.load_cases", return_value=[self.case]), patch(
            "app.rag.ingestion.load_documents", return_value=[]
        ), patch("ingest.build_chunks", return_value=[self.chunk]), patch(
            "app.rag.retrieval.retrieve", side_effect=fallback
        ), self.assertRaisesRegex(RuntimeError, "fallback"):
            run_evaluation(self.path, mode="hybrid")

    def test_final_evaluation_rejects_unreviewed_labels_before_embedding(self):
        with patch("app.embeddings.embed_texts") as embed, self.assertRaisesRegex(ValueError, "human-reviewed"):
            run_evaluation(Path("tests/fixtures/rag_fyp_candidate_cases.json"), require_reviewed=True)
        embed.assert_not_called()
