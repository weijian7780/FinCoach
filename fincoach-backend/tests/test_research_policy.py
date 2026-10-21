"""Conversation-level checks for typed research planning and source decisions."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.llm import CoachRequestBudget, LLMResult
from app.rag.research_policy import (
    _DEFINITIONAL_FACTS,
    EvidenceAssessment,
    QuestionPlan,
    ResearchDecision,
    assess_evidence,
    interpret_question,
    research_query,
    run_research_policy,
)
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import ResearchOutcome, classify_tier


def _supported_explanation(claims, *_args, **_kwargs):
    from app.rag.verifier import GroundingVerification
    return GroundingVerification({c.id: "supported" for c in claims},
                                 {c.id: c.cited_indices[0] for c in claims},
                                 supporting_sources={c.id: c.cited_indices for c in claims})


def _reply(data):
    return SimpleNamespace(content=json.dumps(data))


def _chunk(title, content, *, url=None):
    return RetrievedChunk(
        id=-1 if url else 1, title=title, source="bnm.gov.my" if url else "official.md",
        page_number=None, chunk_index=None, content=content, similarity=0.9,
        source_type="web" if url else "corpus", url=url,
        tier=classify_tier(url) if url else None,
        confidence="established", checked_at="2026-09-23" if url else None,
    )


def test_semantic_plan_resolves_context_and_current_period_without_tool_access():
    history = [{"role": "user", "content": "How does the EPF withdrawal rule work?"}]
    model = MagicMock(return_value=_reply({
        "topic": "EPF withdrawal rule Malaysia",
        "needs_personal": False, "needs_external": True,
        "time_scope": "current", "period": None,
        "entities": ["EPF"], "required_facts": ["current withdrawal eligibility"],
        "clarification": None, "explicit_search": False,
    }))
    plan = interpret_question("Has that rule changed recently?", history,
                              base_personal=False, base_external=False,
                              generate=model, budget=CoachRequestBudget.start())
    assert plan.topic == "EPF withdrawal rule Malaysia"
    assert plan.time_scope == "current"
    assert plan.needs_external is True
    assert "withdrawal" in research_query(plan)
    assert "How does" not in research_query(plan)


def test_public_query_excludes_private_money_and_account_numbers():
    plan = QuestionPlan(
        topic="How would a RM4,000 OPR change affect my account 123456789?",
        needs_personal=True, needs_external=True, time_scope="current",
        original_question="My name is Ahmad and account 123456789 contains private records",
    )
    query = research_query(plan)
    assert "4,000" not in query
    assert "123456789" not in query
    assert "Ahmad" not in query


def test_comparison_cannot_be_sufficient_without_each_entity():
    plan = QuestionPlan("deposit rates Malaysia", False, True, "current",
                        entities=("Maybank", "CIMB"))
    assessor = MagicMock(return_value=_reply({
        "status": "sufficient", "missing": [], "conflicting": False,
        "jurisdiction_matches": True, "period_matches": True,
        "support": [{"source_id": 1, "quote": "Maybank rate 2%"}],
    }))
    result = assess_evidence(plan, [_chunk("Maybank", "Maybank rate 2%", url="https://maybank.com/rates")],
                             generate=assessor, budget=CoachRequestBudget.start())
    assert result.status == "partial"
    assert "comparable evidence for CIMB" in result.missing
    assert "official current source for CIMB" in result.missing


def test_aggregator_cannot_establish_both_banks_current_rates():
    plan = QuestionPlan("fixed deposit rates", False, True, "current",
                        entities=("Maybank", "CIMB"))
    aggregator = _chunk(
        "Fixed deposit rates for Maybank and CIMB",
        "Maybank 12 month rate 1.85%; CIMB 12 month rate 1.75%.",
        url="https://stashaway.my/r/fixed-deposit-rates",
    )
    assessor = MagicMock(return_value=_reply({
        "status": "sufficient", "missing": [], "conflicting": False,
        "jurisdiction_matches": True, "period_matches": True,
        "support": [{"source_id": 1,
                     "quote": "Maybank 12 month rate 1.85%; CIMB 12 month rate 1.75%."}],
    }))
    result = assess_evidence(plan, [aggregator], generate=assessor)
    assert result.status == "partial"
    assert "official current source for Maybank" in result.missing
    assert "official current source for CIMB" in result.missing


def test_current_question_searches_even_when_corpus_is_related_and_recovers_once():
    plan = QuestionPlan("OPR Malaysia", False, True, "current",
                        required_facts=("current OPR",))
    assessment = iter([
        EvidenceAssessment("sufficient", supported_sources=(1,)),
        EvidenceAssessment("partial", ("latest dated BNM rate",), supported_sources=(1,)),
        EvidenceAssessment("sufficient", supported_sources=(1,)),
    ])
    first = _chunk("BNM old", "Old OPR page", url="https://bnm.gov.my/old")
    second = _chunk("BNM current", "Latest dated OPR page", url="https://bnm.gov.my/new")
    with (
        patch("app.rag.research_policy.assess_evidence", side_effect=assessment),
        patch("app.rag.research_policy.research_evidence", side_effect=[
            ResearchOutcome([first], True, "ok"),
            ResearchOutcome([second], True, "ok"),
        ]) as search,
    ):
        result = run_research_policy(
            plan, [_chunk("Corpus", "General OPR explanation")],
            generate=MagicMock(), budget=CoachRequestBudget.start(),
            api_key="test", web_enabled=True, max_results=4, timeout=4,
        )
    assert result.assessment.status == "sufficient"
    assert result.web_used is True
    assert search.call_count == 2
    assert "latest dated BNM rate" in search.call_args_list[1].args[0]


def test_search_failure_remains_distinct_from_no_answering_evidence():
    plan = QuestionPlan("current Malaysian tax rule", False, True, "current")
    with patch("app.rag.research_policy.research_evidence",
               return_value=ResearchOutcome([], True, "search_failed")):
        result = run_research_policy(
            plan, [], generate=MagicMock(), budget=CoachRequestBudget.start(),
            api_key="test", web_enabled=True, max_results=4, timeout=4,
        )
    assert result.failure == "search_failed"
    assert result.assessment.status == "insufficient"
    assert "web verification" in result.assessment.missing


def test_contextual_current_rule_fails_honestly_through_service():
    from app.rag.service import CoachingService

    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Existing"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": "Has that rule changed recently?"}
    repo.list_messages.return_value = [
        {"id": "prior", "role": "user", "content": "How does compound interest work?",
         "status": "completed"},
    ]
    repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    interpretation = _reply({
        "topic": "compound interest rule Malaysia", "needs_personal": False,
        "needs_external": True, "time_scope": "current", "period": None,
        "entities": [], "required_facts": ["recent rule change"],
        "clarification": None, "explicit_search": False,
    })
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.generate_structured_result", return_value=interpretation),
        patch("app.rag.service.retrieve", return_value=[]),
        patch("app.rag.research_policy.research_evidence",
              return_value=ResearchOutcome([], True, "search_failed")),
        patch("app.rag.service.generate_result",
              side_effect=AssertionError("insufficient evidence must not invoke answer model")),
    ):
        reply = CoachingService(repo, MagicMock()).send_message(
            "s", "m", "Has that rule changed recently?"
        )["assistant_message"]
    assert "could not complete the source search" not in reply["content"].lower()
    assert reply["content"] == "I could not retrieve the source details needed for this question. Please try again."
    assert reply["ui_payload"]["research_outcome"]["failure"] == "search_failed"


def test_related_high_similarity_does_not_prove_historical_coverage():
    plan = QuestionPlan("PIDM deposit insurance coverage", False, True, "historical",
                        period="2023", required_facts=("2023 coverage limit",))
    source = _chunk("PIDM 2026 overview", "PIDM protects eligible deposits under the current scheme.")
    assessor = MagicMock(return_value=_reply({
        "status": "sufficient", "missing": [], "conflicting": False,
        "jurisdiction_matches": True, "period_matches": False,
        "support": [{"source_id": 1, "quote": "PIDM protects eligible deposits"}],
    }))
    result = assess_evidence(plan, [source], generate=assessor,
                             budget=CoachRequestBudget.start())
    assert result.status == "partial"
    assert "2023" in result.missing[0]


def test_assessor_sees_original_question_and_can_ignore_unasked_formula():
    plan = QuestionPlan(
        "Compound interest", False, True, "stable",
        required_facts=("compound interest formula",),
        original_question="How does compound interest work?",
    )
    chunk = _chunk("Savings guide", "Interest is earned on the principal and previously earned interest.")
    def model(prompt, **_kwargs):
        assert "How does compound interest work?" in prompt
        return _reply({
            "status": "sufficient", "missing": [], "conflicting": False,
            "jurisdiction_matches": True, "period_matches": True,
            "support": [{"source_id": 1, "quote": "Interest is earned on the principal and previously earned interest."}],
        })
    result = assess_evidence(plan, [chunk], generate=model)
    assert result.status == "sufficient"
    assert result.supported_sources == (1,)


def test_assessor_rejects_invented_quote_and_flags_conflicting_sources():
    plan = QuestionPlan("bank fixed deposit rate", False, True, "current")
    source = _chunk("Bank rate", "The rate effective September 2026 is 2.5%.",
                    url="https://maybank.com/rate")
    fake = MagicMock(return_value=_reply({
        "status": "sufficient", "missing": [], "conflicting": False,
        "jurisdiction_matches": True, "period_matches": True,
        "support": [{"source_id": 1, "quote": "The rate effective September 2026 is 9.5%."}],
    }))
    assert assess_evidence(plan, [source], generate=fake).status == "insufficient"
    fake.return_value = _reply({
        "status": "sufficient", "missing": [], "conflicting": True,
        "jurisdiction_matches": True, "period_matches": True,
        "support": [{"source_id": 1, "quote": "The rate effective September 2026 is 2.5%."}],
    })
    result = assess_evidence(plan, [source], generate=fake)
    assert result.status == "partial"
    assert result.conflicting is True


def test_current_related_corpus_cannot_authorize_answer_after_web_failure():
    plan = QuestionPlan("current EPF withdrawal rule", False, True, "current")
    corpus = _chunk("EPF guide", "An older EPF guide describes withdrawals.")
    with (
        patch("app.rag.research_policy.assess_evidence",
              return_value=EvidenceAssessment("sufficient", supported_sources=(1,))),
        patch("app.rag.research_policy.research_evidence",
              return_value=ResearchOutcome([], True, "search_failed")),
    ):
        result = run_research_policy(plan, [corpus], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assert result.chunks == []
    assert result.assessment.status == "partial"
    assert result.failure == "search_failed"


def test_interpretation_failure_never_searches_raw_personal_message():
    plan = QuestionPlan("OPR change on account 123456789", True, True, "current",
                        interpreted=False, interpretation_failure="interpretation_unavailable")
    with patch("app.rag.research_policy.research_evidence") as search:
        result = run_research_policy(plan, [], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assert result.failure == "interpretation_unavailable"
    assert result.chunks == []
    search.assert_not_called()


def test_service_rewrites_verified_evidence_without_inlining_url_when_generated_answer_fails():
    from app.rag.service import CoachingService

    question = "What is the current OPR?"
    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Existing"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": question}
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    chunk = _chunk("Official rate", "The OPR effective September 2026 is 2.75%.",
                   url="https://bnm.gov.my/rate")
    plan = QuestionPlan("Malaysia OPR", False, True, "current")
    decision = ResearchDecision(
        [chunk], EvidenceAssessment("sufficient", supported_sources=(1,),
                                   supported_quotes=((1, chunk.content),)),
        web_used=True, source_quotes=("The OPR effective September 2026 is 2.75%.",)
    )
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.interpret_question", return_value=plan),
        patch("app.rag.service.retrieve", return_value=[]),
        patch("app.rag.service.run_research_policy", return_value=decision),
        patch("app.rag.service.generate_result", return_value=LLMResult("The rate is 9.99%", "test")),
        patch("app.rag.research_answer._generate_research_correction", return_value=LLMResult(
            "**Insight**\nThe published rate is 2.75%, effective September 2026 [S1].\n\n"
            "**Recommended action**\nCheck the published rate of 2.75% [S1].\n\n"
            "**Educational guidance**\nThis is educational guidance, not licensed financial advice.", "fallback")),
        patch("app.rag.research_answer.verify_grounding_claims", side_effect=_supported_explanation),
    ):
        reply = CoachingService(repo, MagicMock()).send_message("s", "m", question)
    answer = reply["assistant_message"]["content"]
    assert "9.99%" not in answer
    assert "The published rate is 2.75%, effective September 2026." in answer
    assert chunk.content not in answer
    # The URL is no longer inlined into content (it wrapped ugly and duplicated the
    # "View sources" card). It rides source_snapshot, which drives that card.
    assert "https://bnm.gov.my/rate" not in answer
    assert reply["assistant_message"]["ui_payload"]["source_snapshot"][0]["url"] == "https://bnm.gov.my/rate"


def test_service_surfaces_conflicting_sources_to_the_user():
    from app.rag.service import CoachingService

    question = "What is the current OPR?"
    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Existing"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": question}
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    first = _chunk("Source A", "The OPR effective September 2026 is 2.75%.",
                   url="https://bnm.gov.my/rate")
    second = _chunk("Source B", "The OPR effective September 2026 is 3.25%.",
                    url="https://news.example/opr")
    plan = QuestionPlan("Malaysia OPR", False, True, "current")
    decision = ResearchDecision(
        [first, second],
        EvidenceAssessment("partial", ("resolution of conflicting sources",),
                           conflicting=True, supported_sources=(1, 2),
                           supported_quotes=((1, first.content), (2, second.content))),
        web_used=True,
        source_quotes=("The OPR effective September 2026 is 2.75%.",
                       "The OPR effective September 2026 is 3.25%."),
    )
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.interpret_question", return_value=plan),
        patch("app.rag.service.retrieve", return_value=[]),
        patch("app.rag.service.run_research_policy", return_value=decision),
        patch("app.rag.service.generate_result", return_value=LLMResult("The OPR is 2.75%.", "test")),
        patch("app.rag.research_answer._generate_research_correction", return_value=LLMResult(
            "**Insight**\nThe sources conflict: one reports 2.75% [S1], another 3.25% [S2].\n\n"
            "**Recommended action**\nCompare the conflicting published rates of 2.75% [S1] and 3.25% [S2].\n\n"
            "**Educational guidance**\nThis is educational guidance, not licensed financial advice.", "fallback")),
        patch("app.rag.research_answer.verify_grounding_claims", side_effect=_supported_explanation),
    ):
        reply = CoachingService(repo, MagicMock()).send_message("s", "m", question)
    answer = reply["assistant_message"]["content"]
    # Both conflicting figures must reach the user; neither may be silently dropped.
    assert "2.75%" in answer and "3.25%" in answer
    assert "sources conflict" in answer
    urls = {s["url"] for s in reply["assistant_message"]["ui_payload"]["source_snapshot"]}
    assert {"https://bnm.gov.my/rate", "https://news.example/opr"} <= urls


def test_compose_research_answer_is_clean_across_states():
    from app.rag.service import _compose_research_answer

    # State 2: a verified quote is surfaced as plain prose — no citation markers,
    # no raw URL, no verification-log scaffolding.
    single = _compose_research_answer(quotes=["The OPR effective September 2026 is 2.75%."])
    assert "The OPR effective September 2026 is 2.75%." in single
    assert "[S" not in single
    assert "http" not in single
    assert "Sources:" not in single
    assert "could not verify" not in single.lower()
    assert "cannot establish" not in single.lower()

    # State 2 (conflict): both figures reach the user under a disagreement lead.
    conflict = _compose_research_answer(
        quotes=["The OPR is 2.75%.", "The OPR is 3.25%."], conflicting=True,
    )
    assert "2.75%" in conflict and "3.25%" in conflict
    assert "disagree" in conflict.lower()

    # State 3a: no quotes + a failure still gives a practical official next step.
    search_failed = _compose_research_answer(quotes=[], failure="search_failed")
    assert "could not complete the source search" not in search_failed
    assert "official guidance" in search_failed
    assert "http" not in search_failed

    # State 3b: no verified quotes, no failure -> the "did not establish" line.
    unestablished = _compose_research_answer(quotes=[], failure=None)
    assert "did not establish" in unestablished


def test_service_guidance_separates_search_failure_from_unestablished():
    from app.rag.service import CoachingService

    def _guidance_for(failure):
        repo = MagicMock(user_id="u")
        repo.require_session.return_value = {"id": "s", "title": "Existing"}
        repo.find_user_message.return_value = None
        repo.insert_user_message.return_value = {"id": "m", "content": "What is the current OPR?"}
        repo.list_messages.return_value = []
        repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
        plan = QuestionPlan("Malaysia OPR", False, True, "current")
        decision = ResearchDecision(
            [], EvidenceAssessment("partial", ("current OPR figure",), supported_sources=()),
            web_used=False, failure=failure,
        )
        captured = {}

        def _capture_guidance(*args, **kwargs):
            captured["guidance"] = kwargs.get("extra_guidance", "")
            return "PROMPT"

        with (
            patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
            patch("app.rag.service.interpret_question", return_value=plan),
            patch("app.rag.service.retrieve", return_value=[]),
            patch("app.rag.service.run_research_policy", return_value=decision),
            patch("app.rag.service.build_coach_prompt", side_effect=_capture_guidance),
            patch("app.rag.service.generate_result", return_value=LLMResult("x", "test")),
        ):
            CoachingService(repo, MagicMock()).send_message("s", "m", "What is the current OPR?")
        return captured.get("guidance", "")

    # Service failure and "sources did not establish it" are distinct messages (plan 4.3).
    assert "Web search failed or could not run." in _guidance_for("search_failed")
    unestablished = _guidance_for(None)
    assert "Available sources did not establish the full answer." in unestablished
    assert "Web search failed or could not run." not in unestablished


# --- Definitional scope guard + stable-aware evidence (the "what is X" matrix) ---
# A bare public definition ("what is ptptn") must be answered from the corpus and
# never escalate to trending news; a genuinely current, historical, mixed or
# personal turn must keep its full scope. These lock the interpret_question guard
# and the stable-aware evidence ordering added for that class of bug.


def test_bare_definition_is_clamped_to_stable_identity_scope():
    # Interpreter over-scopes AND mis-times a bare definition — the live PTPTN bug.
    model = MagicMock(return_value=_reply({
        "topic": "PTPTN education loan scheme in Malaysia",
        "needs_personal": False, "needs_external": True,
        "time_scope": "current", "period": None, "entities": [],
        "required_facts": ["What PTPTN is", "Who is eligible", "How to apply",
                            "Repayment terms"],
        "clarification": None, "explicit_search": True, "jurisdiction": "Malaysia",
    }))
    plan = interpret_question("what is ptptn", [], base_personal=False,
                              base_external=True, generate=model,
                              budget=CoachRequestBudget.start())
    # time_scope normalised to stable, over-scoped facts dropped, search cue cleared.
    assert plan.time_scope == "stable"
    assert plan.required_facts == _DEFINITIONAL_FACTS
    assert plan.explicit_search is False
    assert plan.definitional is True


def test_definitional_corpus_hit_answers_from_corpus_without_assessor_or_web():
    # The deterministic guarantee: a bare definition with a corpus hit is answered
    # from the corpus — the LLM answerability gate (whose non-determinism let news
    # in intermittently) and the web search are both skipped entirely.
    plan = QuestionPlan("PTPTN", False, True, "stable",
                        required_facts=_DEFINITIONAL_FACTS, definitional=True)
    corpus = _chunk("PTPTN guide", "PTPTN manages education loans and repayments.")
    with (
        patch("app.rag.research_policy.assess_evidence") as assessor,
        patch("app.rag.research_policy.research_evidence") as search,
    ):
        result = run_research_policy(plan, [corpus], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assessor.assert_not_called()
    search.assert_not_called()
    assert result.web_used is False
    assert result.assessment.status == "sufficient"
    assert result.chunks and result.chunks[0].source_type == "corpus"


def test_definitional_without_corpus_hit_still_reaches_official_web():
    # No corpus hit → the shortcut does not apply; a definition the corpus misses
    # can still be answered from official web (the caged pass), just not news.
    plan = QuestionPlan("obscure fund", False, True, "stable",
                        required_facts=_DEFINITIONAL_FACTS, definitional=True)
    official = _chunk("Official", "The fund is a government scheme.",
                      url="https://x.gov.my/fund")
    with (
        patch("app.rag.research_policy.assess_evidence", side_effect=[
            EvidenceAssessment("insufficient", ("identity",)),
            EvidenceAssessment("sufficient", supported_sources=(1,),
                               supported_quotes=((1, "The fund is a government scheme."),)),
        ]),
        patch("app.rag.research_policy.research_evidence",
              return_value=ResearchOutcome([official], True, "ok")) as search,
    ):
        result = run_research_policy(plan, [], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    search.assert_called()
    assert result.web_used is True


def test_latest_news_question_keeps_current_scope_and_full_facts():
    model = MagicMock(return_value=_reply({
        "topic": "PTPTN latest news", "needs_personal": False, "needs_external": True,
        "time_scope": "current", "period": None, "entities": [],
        "required_facts": ["latest PTPTN news updates"], "clarification": None,
        "explicit_search": False, "jurisdiction": "Malaysia",
    }))
    plan = interpret_question("latest ptptn news", [], base_personal=False,
                              base_external=True, generate=model,
                              budget=CoachRequestBudget.start())
    assert plan.time_scope == "current"
    assert plan.required_facts == ("latest PTPTN news updates",)


def test_mixed_definition_and_latest_change_is_not_clamped():
    model = MagicMock(return_value=_reply({
        "topic": "PTPTN latest changes", "needs_personal": False,
        "needs_external": True, "time_scope": "current", "period": None,
        "entities": [], "required_facts": ["latest PTPTN policy changes",
                                            "current repayment rules"],
        "clarification": None, "explicit_search": False, "jurisdiction": "Malaysia",
    }))
    plan = interpret_question("explain ptptn and its latest changes", [],
                              base_personal=False, base_external=True,
                              generate=model, budget=CoachRequestBudget.start())
    # "latest" keeps the mixed turn current so the change half still reaches news.
    assert plan.time_scope == "current"
    assert "latest PTPTN policy changes" in plan.required_facts


def test_personal_amount_question_is_never_treated_as_public_definition():
    model = MagicMock(return_value=_reply({
        "topic": "PTPTN disbursement amount", "needs_personal": True,
        "needs_external": False, "time_scope": "stable", "period": None,
        "entities": [], "required_facts": ["user PTPTN amount received"],
        "clarification": None, "explicit_search": False, "jurisdiction": "Malaysia",
        "personal_read": "search_transactions",
    }))
    plan = interpret_question("how much ptptn did i receive", [],
                              base_personal=True, base_external=False,
                              generate=model, budget=CoachRequestBudget.start())
    assert plan.needs_personal is True
    assert plan.required_facts == ("user PTPTN amount received",)


def test_stable_definition_answered_from_corpus_without_web_search():
    plan = QuestionPlan("PTPTN", False, True, "stable",
                        required_facts=_DEFINITIONAL_FACTS)
    corpus = _chunk("PTPTN guide", "PTPTN (Perbadanan Tabung Pendidikan Tinggi "
                    "Nasional) is Malaysia's national higher-education loan fund.")
    with (
        patch("app.rag.research_policy.assess_evidence",
              return_value=EvidenceAssessment(
                  "sufficient", supported_sources=(1,),
                  supported_quotes=((1, "PTPTN is Malaysia's loan fund."),))),
        patch("app.rag.research_policy.research_evidence") as search,
    ):
        result = run_research_policy(plan, [corpus], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    # Corpus sufficient + stable → no web search, corpus definition is the answer.
    search.assert_not_called()
    assert result.web_used is False
    assert result.chunks and result.chunks[0].source_type == "corpus"


def test_stable_definition_second_search_never_escalates_to_news():
    plan = QuestionPlan("obscure scheme", False, True, "stable",
                        required_facts=_DEFINITIONAL_FACTS)
    first_hit = _chunk("A", "partial info about the scheme", url="https://x.gov.my/a")
    second_hit = _chunk("B", "more official detail on the scheme",
                        url="https://y.gov.my/b")
    assessments = iter([
        EvidenceAssessment("insufficient", ("identity",)),
        EvidenceAssessment("partial", ("more detail",), supported_sources=(1,),
                           supported_quotes=((1, "partial info about the scheme"),)),
        EvidenceAssessment("sufficient", supported_sources=(1,),
                           supported_quotes=((1, "more official detail on the scheme"),)),
    ])
    with (
        patch("app.rag.research_policy.assess_evidence", side_effect=assessments),
        patch("app.rag.research_policy.research_evidence", side_effect=[
            ResearchOutcome([first_hit], True, "ok"),
            ResearchOutcome([second_hit], True, "ok"),
        ]) as search,
    ):
        run_research_policy(plan, [_chunk("corpus", "unrelated text")],
                            generate=MagicMock(), budget=CoachRequestBudget.start(),
                            api_key="test", web_enabled=True, max_results=4, timeout=4)
    # A stable definition may reach official web, but the escalation pass stays
    # caged (unrestricted False) so trending news can never enter the evidence.
    assert search.call_count == 2
    assert search.call_args_list[1].kwargs["unrestricted"] is False


def test_corpus_only_definition_ships_full_explanation_not_a_bare_quote():
    # The reported regression: "what is ptptn" answered from the corpus was
    # collapsed to a bare name quote. A corpus-only, sufficient answer must now
    # ship the fuller generated explanation (with [S] markers stripped), because
    # the web-research citation contract does not apply when nothing left FinCoach.
    from app.llm import LLMResult
    from app.rag.service import CoachingService

    question = "what is ptptn"
    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Existing"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": question}
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    corpus = _chunk("PTPTN guide",
                    "PTPTN manages education loans and repayments and runs savings schemes.")
    plan = QuestionPlan("PTPTN", False, True, "stable", required_facts=_DEFINITIONAL_FACTS)
    decision = ResearchDecision(
        [corpus], EvidenceAssessment("sufficient", supported_sources=(1,)),
        web_used=False, source_quotes=("PTPTN manages education loans and repayments.",),
    )
    generated = (
        "**Insight**\nPTPTN (Perbadanan Tabung Pendidikan Tinggi Nasional) is "
        "Malaysia's higher-education loan fund [S1]. It manages education loans and "
        "repayments and runs savings schemes.\n\n**Recommended action**\nRecord "
        "PTPTN as a future commitment.\n\n**Educational guidance**\nThis is "
        "educational guidance, not licensed financial advice."
    )
    with (
        patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
        patch("app.rag.service.interpret_question", return_value=plan),
        patch("app.rag.service.retrieve", return_value=[corpus]),
        patch("app.rag.service.run_research_policy", return_value=decision),
        patch("app.rag.service._ground_educational_answer",
              side_effect=lambda result, **_kw: (result, False, False)),
        patch("app.rag.service.generate_result", return_value=LLMResult(generated, "test")),
    ):
        reply = CoachingService(repo, MagicMock()).send_message("s", "m", question)
    answer = reply["assistant_message"]["content"]
    # The fuller explanation ships, not the bare "Here is what I could confirm" quote.
    assert "manages education loans and repayments and runs savings schemes" in answer
    assert "**Insight**" in answer
    assert "Here is what I could confirm" not in answer
    # [S] markers are stripped; sources render through the View sources card only.
    assert "[S1]" not in answer
    # The full structured answer shipped (disclaimer present), not a bare quote.
    assert "This is educational guidance, not licensed financial advice." in answer
