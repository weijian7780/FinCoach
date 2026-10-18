import unittest
from pathlib import Path


class KnowledgeQueryAnalysisTests(unittest.TestCase):
    def test_topic_switch_does_not_resurrect_an_older_knowledge_topic(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("what about last month?", history=[
            {"role": "user", "content": "Explain PTPTN repayment"},
            {"role": "user", "content": "How much did I spend this month?"},
        ])
        self.assertFalse(analysis.inherited)
        self.assertEqual(analysis.topic_matches, ())

    def test_personal_topic_switch_with_followup_prefix_resets_knowledge_topic(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("and the eligibility?", history=[
            {"role": "user", "content": "Explain PTPTN repayment"},
            {"role": "user", "content": "what about my budget?"},
        ])
        self.assertFalse(analysis.inherited)

    def test_failed_user_turn_does_not_establish_a_knowledge_topic(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("what about repayment?", history=[
            {"role": "user", "content": "Explain PTPTN", "status": "failed"},
        ])
        self.assertFalse(analysis.inherited)

    def test_contiguous_followups_keep_their_knowledge_topic(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("and the eligibility?", history=[
            {"role": "user", "content": "Explain PTPTN"},
            {"role": "user", "content": "what about repayment?"},
        ])
        self.assertTrue(analysis.inherited)
        self.assertEqual([match.topic.topic_id for match in analysis.topic_matches], ["ptptn"])

    def test_detects_fuzzy_socso_alias_and_splits_two_topics(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("ptptn and sosco")

        self.assertEqual(
            [subquery.topic_id for subquery in analysis.subqueries],
            ["ptptn", "perkeso"],
        )
        self.assertEqual(
            [subquery.source for subquery in analysis.subqueries],
            [
                "official_ptptn_loan_guidance.md",
                "official_perkeso_employee_protection.md",
            ],
        )
        self.assertTrue(analysis.has_knowledge_intent)

    def test_inherits_one_previous_knowledge_topic_for_a_follow_up(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query(
            "what about repayment?",
            history=[
                {
                    "id": "previous-user-message",
                    "role": "user",
                    "content": "Explain PTPTN repayment",
                },
                {
                    "id": "current-message",
                    "role": "user",
                    "content": "what about repayment?",
                },
            ],
            current_message_id="current-message",
        )

        self.assertTrue(analysis.inherited)
        self.assertEqual([subquery.topic_id for subquery in analysis.subqueries], ["ptptn"])

    def test_requires_clarification_for_more_than_three_detected_topics(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("PTPTN, EPF, SOCSO and PIDM")

        self.assertEqual(analysis.subqueries, ())
        self.assertIn("up to three", analysis.clarification or "")

    def test_does_not_inherit_an_ambiguous_multi_topic_follow_up(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query(
            "what about that?",
            history=[
                {
                    "role": "user",
                    "content": "Compare PTPTN and SOCSO",
                },
            ],
        )

        self.assertFalse(analysis.inherited)
        self.assertIn("Which topic", analysis.clarification or "")

    def test_detects_compound_interest_and_binds_its_corpus_source(self):
        from app.rag.query_analysis import analyze_knowledge_query

        for message in ("What is compound interest?", "how does compounding work"):
            with self.subTest(message=message):
                analysis = analyze_knowledge_query(message)

                self.assertTrue(analysis.has_knowledge_intent)
                self.assertEqual(
                    [subquery.topic_id for subquery in analysis.subqueries],
                    ["compound_interest"],
                )
                self.assertEqual(
                    [subquery.source for subquery in analysis.subqueries],
                    ["official_compound_interest_and_savings_growth.md"],
                )

    def test_detects_malay_compound_interest_alias(self):
        from app.rag.query_analysis import analyze_knowledge_query

        analysis = analyze_knowledge_query("apa itu faedah kompaun?")

        self.assertEqual(
            [subquery.topic_id for subquery in analysis.subqueries],
            ["compound_interest"],
        )


class KnowledgeRoutingTests(unittest.TestCase):
    def test_routes_typo_only_knowledge_query_to_rag(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        self.assertEqual(route_coach_message("sosco"), CoachingRoute.FINANCIAL_EDUCATION)

    def test_keeps_non_financial_keyword_collision_out_of_rag(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        self.assertEqual(route_coach_message("weather at PTPTN office"), CoachingRoute.CASUAL)
        self.assertEqual(route_coach_message("tell me a joke about debt"), CoachingRoute.CASUAL)

    def test_routes_compound_interest_question_to_rag(self):
        from app.rag.routing import CoachingRoute, route_coach_message

        self.assertEqual(
            route_coach_message("What is compound interest?"),
            CoachingRoute.FINANCIAL_EDUCATION,
        )


class HybridRetrievalTests(unittest.TestCase):
    def test_reserves_one_source_for_each_detected_topic(self):
        from unittest.mock import MagicMock, patch
        from types import SimpleNamespace

        from app.rag.query_analysis import analyze_knowledge_query
        from app.rag.retrieval import retrieve

        responses = [
            [
                {
                    "id": 1,
                    "content": "PTPTN evidence",
                    "source": "official_ptptn_loan_guidance.md",
                    "similarity": 0.44,
                    "dense_rank": 1,
                    "lexical_rank": 1,
                    "lexical_score": 0.9,
                },
            ],
            [
                {
                    "id": 2,
                    "content": "PERKESO evidence",
                    "source": "official_perkeso_employee_protection.md",
                    "similarity": 0.36,
                    "dense_rank": 2,
                    "lexical_rank": 1,
                    "lexical_score": 0.8,
                },
            ],
        ]
        client = MagicMock()
        client.rpc.side_effect = [
            MagicMock(execute=MagicMock(return_value=SimpleNamespace(data=rows)))
            for rows in responses
        ]
        analysis = analyze_knowledge_query("ptptn and sosco")

        with (
            patch("app.rag.retrieval.embed_texts", return_value=[[0.1], [0.2]]),
            patch("app.rag.retrieval.get_supabase", return_value=client),
        ):
            result = retrieve("ptptn and sosco", analysis=analysis, candidate_k=5)

        self.assertEqual([chunk.id for chunk in result], [1, 2])
        self.assertEqual(client.rpc.call_count, 2)
        self.assertEqual(
            client.rpc.call_args_list[0].args[0],
            "match_knowledge_documents_hybrid",
        )


class HybridSqlContractTests(unittest.TestCase):
    def test_knowledge_sql_defines_service_role_only_hybrid_search(self):
        sql = (Path(__file__).parents[1] / "sql" / "knowledge.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("match_knowledge_documents_hybrid", sql)
        self.assertIn("websearch_to_tsquery('simple'", sql)
        self.assertIn("knowledge_documents_fts_idx", sql)
        self.assertIn(
            "grant execute on function public.match_knowledge_documents_hybrid",
            sql,
        )
        self.assertIn("to service_role", sql)


class KnowledgeFollowUpServiceTests(unittest.TestCase):
    def test_knowledge_follow_up_uses_retrieval_instead_of_personal_record_clarification(self):
        from unittest.mock import MagicMock, patch

        from app.llm import LLMResult
        from app.rag.service import CoachingService

        repository = MagicMock(user_id="user-1")
        repository.require_session.return_value = {"id": "session-1", "title": "New conversation"}
        repository.find_user_message.return_value = None
        repository.insert_user_message.return_value = {
            "id": "message-1",
            "session_id": "session-1",
            "role": "user",
            "content": "what about repayment?",
        }
        repository.list_messages.return_value = [
            {"id": "previous", "role": "user", "content": "Explain PTPTN repayment"},
            {"id": "message-1", "role": "user", "content": "what about repayment?"},
        ]
        repository.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]

        with (
            patch("app.rag.service.retrieve", return_value=[]) as retrieve_chunks,
            patch(
                "app.rag.service.generate_result",
                return_value=LLMResult("retrieved reply", "test-model", 1, 1),
            ) as generate,
            patch(
                "app.rag.service._ground_educational_answer",
                side_effect=lambda result, **_: (result, False, False),
            ),
        ):
            result = CoachingService(repository, MagicMock()).send_message(
                "session-1", "message-1", "what about repayment?"
            )

        retrieve_chunks.assert_called_once()
        generate.assert_called_once()
        self.assertEqual(result["assistant_message"]["content"], "retrieved reply")


if __name__ == "__main__":
    unittest.main()
