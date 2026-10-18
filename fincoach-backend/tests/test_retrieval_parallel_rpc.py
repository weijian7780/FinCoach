"""Unit tests for bounded parallel per-subquery hybrid RPC fan-out.

``_fetch_hybrid_candidates`` must behave exactly like the previous sequential
loop: same per-subquery results in subquery order, same failure contract
(first exception in subquery order propagates; the hybrid-RPC error text that
triggers the dense fallback is preserved). The Supabase RPC itself is stubbed
so these tests are hermetic (no network).
"""

import threading
import unittest
from unittest.mock import patch

from app.rag.query_analysis import SearchSubquery


def _subqueries(*texts):
    return [SearchSubquery(None, None, text) for text in texts]


def _embeddings(n):
    return [[0.0] * 4 for _ in range(n)]


class FetchHybridCandidatesTests(unittest.TestCase):
    def test_single_subquery_uses_sequential_path(self):
        from app.rag import retrieval

        seen_threads = []

        def fake_rpc(subquery, embedding, match_count):
            seen_threads.append(threading.current_thread().name)
            return [("chunk-a", subquery.text)]

        with patch.object(retrieval, "_hybrid_candidates", side_effect=fake_rpc):
            result = retrieval._fetch_hybrid_candidates(
                _subqueries("alpha"), _embeddings(1), 5
            )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].text, "alpha")
        self.assertEqual(result[0][1], [("chunk-a", "alpha")])
        # No worker threads for the single-subquery fast path.
        self.assertTrue(
            all("fincoach-hybrid-rpc" not in name for name in seen_threads),
            f"unexpected worker threads: {seen_threads}",
        )

    def test_parallel_results_preserve_subquery_order(self):
        from app.rag import retrieval

        def fake_rpc(subquery, embedding, match_count):
            return [f"chunk-for-{subquery.text}"]

        with patch.object(retrieval, "_hybrid_candidates", side_effect=fake_rpc):
            result = retrieval._fetch_hybrid_candidates(
                _subqueries("alpha", "beta", "gamma"), _embeddings(3), 5
            )
        self.assertEqual(
            [(sq.text, chunks) for sq, chunks in result],
            [
                ("alpha", ["chunk-for-alpha"]),
                ("beta", ["chunk-for-beta"]),
                ("gamma", ["chunk-for-gamma"]),
            ],
        )

    def test_parallel_runs_rpc_calls_concurrently(self):
        from app.rag import retrieval

        barrier = threading.Barrier(3)
        thread_names = set()
        lock = threading.Lock()

        def fake_rpc(subquery, embedding, match_count):
            with lock:
                thread_names.add(threading.current_thread().name)
            # If the calls ran sequentially this barrier would deadlock and
            # the test would time out instead of passing.
            barrier.wait(timeout=10)
            return []

        with patch.object(retrieval, "_hybrid_candidates", side_effect=fake_rpc):
            retrieval._fetch_hybrid_candidates(
                _subqueries("a", "b", "c"), _embeddings(3), 5
            )
        worker_threads = {
            name for name in thread_names if "fincoach-hybrid-rpc" in name
        }
        self.assertEqual(len(worker_threads), 3, thread_names)

    def test_first_exception_in_subquery_order_propagates(self):
        from app.rag import retrieval

        def fake_rpc(subquery, embedding, match_count):
            if subquery.text == "alpha":
                raise ValueError("unrelated failure")
            if subquery.text == "beta":
                raise RuntimeError("match_knowledge_documents_hybrid outage")
            return []

        with patch.object(retrieval, "_hybrid_candidates", side_effect=fake_rpc):
            with self.assertRaisesRegex(ValueError, "unrelated failure"):
                retrieval._fetch_hybrid_candidates(
                    _subqueries("alpha", "beta", "gamma"), _embeddings(3), 5
                )

    def test_hybrid_rpc_error_text_preserved_for_dense_fallback(self):
        from app.rag import retrieval

        def fake_rpc(subquery, embedding, match_count):
            raise RuntimeError("match_knowledge_documents_hybrid outage")

        with patch.object(retrieval, "_hybrid_candidates", side_effect=fake_rpc):
            with self.assertRaisesRegex(
                RuntimeError, "match_knowledge_documents_hybrid"
            ):
                retrieval._fetch_hybrid_candidates(
                    _subqueries("alpha", "beta"), _embeddings(2), 5
                )


if __name__ == "__main__":
    unittest.main()
