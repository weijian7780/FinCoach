"""Service-level coverage for the web-research fallback TRIGGER inside
``CoachingService.send_message``.

``test_web_research.py`` covers the pure ranking/adapter functions
(``classify_tier``, ``to_retrieved_chunks``, ...). It has ZERO coverage of the
decision in ``service.py`` that fires them. That exact gap let an
``UnboundLocalError`` (``web_fallback_used``) ship and crash every structured
interaction reply. These tests pin the trigger contract so a regression on this
path fails loudly:

  * corpus adequate    -> web fallback does NOT fire
  * corpus empty       -> web fallback fires exactly once, evidence reaches prompt
  * corpus low-similarity -> web fallback fires
  * (xfail, Task 3)    -> the query sent to Tavily is de-identified (no PII)
  * (xfail, Task 3)    -> web evidence MERGES with corpus, does not replace it

The two ``xfail(strict=True)`` cases are the shipped defects the evidence-
validation plan's Task 3 fixes (raw ``content`` leak; wholesale ``chunks =
web_chunks`` replace). They pass as expected-failures today; when Task 3 lands
they flip to unexpected-pass, which fails the suite and forces removal of the
marker. That is the tripwire.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from app.llm import LLMResult
from app.rag.retrieval import RetrievedChunk
from app.rag.routing import CoachingRoute


def _corpus_chunk(similarity: float, *, cid: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        id=cid,
        title="Compound interest",
        source="official_compound_interest_and_savings_growth.md",
        page_number=None,
        chunk_index=0,
        content="Compound interest grows savings on prior returns.",
        similarity=similarity,
    )


def _web_chunk(*, cid: int = -1) -> RetrievedChunk:
    return RetrievedChunk(
        id=cid,
        title="EPF dividend",
        source="kwsp.gov.my",
        page_number=None,
        chunk_index=None,
        content="KWSP announced its 2024 dividend for members.",
        similarity=0.8,
        url="https://www.kwsp.gov.my/example",
        source_type="web",
        tier=1,
        confidence="established",
    )


def _drive(content: str, *, corpus_chunks, web_chunks):
    """Drive one education-route turn with the trigger's collaborators patched.

    Everything the trigger touches is stubbed so no network runs and routing is
    deterministic. Returns ``(research_web_mock, build_prompt_mock, result)``.
    The trigger (``research_web``) and ``build_coach_prompt`` both execute before
    branch dispatch and generation, so their call args are captured regardless of
    which answer branch the turn ultimately takes.
    """
    from app.rag import service

    repository = mock.MagicMock(user_id="verified-user")
    repository.require_session.return_value = {"id": "session-1", "title": "Chat"}
    repository.find_user_message.return_value = None
    repository.insert_user_message.return_value = {
        "id": "message-1",
        "session_id": "session-1",
        "user_id": "verified-user",
        "role": "user",
        "content": content,
    }
    repository.list_messages.return_value = []
    repository.complete_turn.side_effect = lambda **kw: kw["assistant_payload"]

    research_web = mock.MagicMock(return_value=list(web_chunks))
    build_prompt = mock.MagicMock(return_value="PROMPT")

    edu_route = SimpleNamespace(
        route=CoachingRoute.FINANCIAL_EDUCATION,
        tool_name=None,
        arguments={},
        inherited=False,
        clarification=None,
    )
    analysis = SimpleNamespace(inherited=False, clarification=None)

    with (
        mock.patch.object(service, "COACH_RESEARCH_POLICY_ENABLED", False),
        mock.patch.object(service, "resolve_read_request", return_value=edu_route),
        mock.patch.object(service, "analyze_knowledge_query", return_value=analysis),
        mock.patch.object(service, "retrieve", return_value=list(corpus_chunks)),
        mock.patch.object(service, "research_web", research_web),
        mock.patch.object(service, "build_coach_prompt", build_prompt),
        mock.patch.object(
            service,
            "generate_result",
            return_value=LLMResult(
                "Compound interest lets your savings grow on past returns.",
                "test-model",
            ),
        ),
        mock.patch.object(
            service,
            "_ground_educational_answer",
            side_effect=lambda result, **kw: (result, False, False),
        ),
        mock.patch.object(service, "WEB_FALLBACK_ENABLED", True),
        mock.patch.object(service, "WEB_FALLBACK_SIM_THRESHOLD", 0.45),
        mock.patch.object(service, "TAVILY_API_KEY", "test-key"),
        mock.patch.object(service, "COACH_WRITE_ACTIONS_ENABLED", True),
    ):
        result = service.CoachingService(repository, mock.MagicMock()).send_message(
            "session-1",
            "message-1",
            content,
        )
    return research_web, build_prompt, result


def _prompt_chunks(build_prompt) -> list[RetrievedChunk]:
    # build_coach_prompt(content, chunks, context, history, limit, financial_triage=...)
    return list(build_prompt.call_args.args[1])


def test_adequate_corpus_does_not_trigger_web_fallback():
    research_web, build_prompt, result = _drive(
        "Explain compound interest",
        corpus_chunks=[_corpus_chunk(0.90)],
        web_chunks=[_web_chunk()],
    )
    research_web.assert_not_called()
    assert [c.id for c in _prompt_chunks(build_prompt)] == [1]
    assert result["assistant_message"]["content"]


def test_empty_corpus_triggers_web_fallback_once_and_evidence_reaches_prompt():
    research_web, build_prompt, _ = _drive(
        "Explain compound interest",
        corpus_chunks=[],
        web_chunks=[_web_chunk()],
    )
    research_web.assert_called_once()
    assert any(c.source_type == "web" for c in _prompt_chunks(build_prompt))


def test_low_similarity_corpus_triggers_web_fallback():
    research_web, _, _ = _drive(
        "Explain compound interest",
        corpus_chunks=[_corpus_chunk(0.10)],
        web_chunks=[_web_chunk()],
    )
    research_web.assert_called_once()


def test_no_web_results_leaves_the_turn_grounded_without_fallback_flag():
    # Tavily returns nothing (no key / timeout / miss): the turn must still answer
    # from whatever corpus it had, never crash. This is the production path here,
    # where tavily-python is not installed.
    research_web, build_prompt, result = _drive(
        "Explain compound interest",
        corpus_chunks=[_corpus_chunk(0.10)],
        web_chunks=[],
    )
    research_web.assert_called_once()
    # web returned []; the corpus chunk is what remains in the prompt.
    assert [c.id for c in _prompt_chunks(build_prompt)] == [1]
    assert result["assistant_message"]["content"]


def test_query_sent_to_tavily_is_deidentified():
    # Task 3 fixed: service.py now sends build_research_query(content), not raw
    # content, so names/refs never reach Tavily (invariant #7).
    research_web, _, _ = _drive(
        "Explain compound interest. Regards, Ahmad, ref 5234.",
        corpus_chunks=[],
        web_chunks=[_web_chunk()],
    )
    research_web.assert_called_once()
    query_sent = research_web.call_args.args[0]
    assert "Ahmad" not in query_sent
    assert "5234" not in query_sent


def test_web_evidence_merges_with_corpus_rather_than_replacing_it():
    # Task 3 fixed: service.py now merge_evidence(corpus, web) instead of
    # `chunks = web_chunks`, so corpus stays primary (invariant #1).
    _, build_prompt, _ = _drive(
        "Explain compound interest",
        corpus_chunks=[_corpus_chunk(0.10, cid=1)],
        web_chunks=[_web_chunk(cid=-1)],
    )
    corpus_ids = [c.id for c in _prompt_chunks(build_prompt) if c.source_type == "corpus"]
    assert 1 in corpus_ids
