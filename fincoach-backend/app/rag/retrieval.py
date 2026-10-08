"""Typed hybrid retrieval for shared Malaysian finance knowledge."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

from app.config import (
    RETRIEVE_CANDIDATES,
    RETRIEVE_K,
    RETRIEVE_SCORE_MARGIN,
    RETRIEVE_THRESHOLD,
)
from app.embeddings import embed_query, embed_texts
from app.rag.query_analysis import (
    KnowledgeQueryAnalysis,
    SearchSubquery,
    analyze_knowledge_query,
)


RRF_K = 50

# Upper bound on concurrent per-subquery Supabase RPCs. Each RPC is a
# network-bound read, so a small pool is enough; the bound keeps a future
# increase in subquery count from fanning out without limit.
MAX_PARALLEL_HYBRID_RPCS = 4


def get_supabase() -> Any:
    """Resolve the service-role client only when retrieval is executed."""
    from app.supabase_client import get_supabase as get_client

    return get_client()


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    title: str | None
    source: str | None
    page_number: int | None
    chunk_index: int | None
    content: str
    similarity: float
    dense_rank: int | None = None
    lexical_rank: int | None = None
    lexical_score: float = 0.0
    rrf_score: float = 0.0
    topic_id: str | None = None
    # Web-research fallback provenance. Corpus chunks keep these defaults; web
    # chunks carry the citation link, trust tier (1..5), and confidence class.
    url: str | None = None
    source_type: str = "corpus"
    tier: int | None = None
    confidence: str | None = None
    published_date: str | None = None
    checked_at: str | None = None
    # Internal excerpt identity; canonical URL still owns origin and citation.
    evidence_window_id: str | None = None
    # Literal structural units this excerpt came from. A qualification belongs to
    # the unit it was read from, so bindings resolve against these rather than
    # against the whole page. Populated only for public page windows.
    source_spans: tuple = ()
    # The heading/condition text that governs this excerpt, kept literal.
    qualification_context: str | None = None


def select_retrieved_chunks(
    chunks: list[RetrievedChunk],
    *,
    k: int,
    threshold: float,
    score_margin: float,
) -> list[RetrievedChunk]:
    """Apply the calibrated absolute and relative relevance filters."""
    if score_margin < 0:
        raise ValueError("score_margin must be greater than or equal to zero")
    result_limit = max(1, min(10, int(k)))
    candidates = sorted(
        (chunk for chunk in chunks if chunk.similarity >= threshold),
        key=lambda chunk: chunk.similarity,
        reverse=True,
    )
    if not candidates:
        return []
    minimum_similarity = candidates[0].similarity - score_margin
    return [
        chunk
        for chunk in candidates
        if chunk.similarity >= minimum_similarity
    ][:result_limit]


def _as_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _chunk_from_row(row: dict[str, Any], topic_id: str | None) -> RetrievedChunk:
    return RetrievedChunk(
        id=int(row["id"]),
        title=row.get("title"),
        source=row.get("source"),
        page_number=row.get("page_number"),
        chunk_index=row.get("chunk_index"),
        content=row["content"],
        similarity=float(row.get("similarity") or 0),
        dense_rank=_as_positive_int(row.get("dense_rank")),
        lexical_rank=_as_positive_int(row.get("lexical_rank")),
        lexical_score=float(row.get("lexical_score") or 0),
        topic_id=topic_id,
    )


def _rank_subquery_candidates(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    def score(chunk: RetrievedChunk) -> float:
        return sum(
            1.0 / (RRF_K + rank)
            for rank in (chunk.dense_rank, chunk.lexical_rank)
            if rank is not None
        )

    return sorted(
        (replace(chunk, rrf_score=score(chunk)) for chunk in chunks),
        key=lambda chunk: (chunk.rrf_score, chunk.similarity, chunk.lexical_score),
        reverse=True,
    )


def _accepted_for_subquery(
    chunk: RetrievedChunk,
    subquery: SearchSubquery,
    threshold: float,
) -> bool:
    """A fuzzy alias can locate a topic but cannot itself prove evidence."""
    return chunk.similarity >= threshold or bool(
        subquery.source
        and chunk.source == subquery.source
        and chunk.lexical_rank is not None
    )


def _hybrid_candidates(
    subquery: SearchSubquery,
    embedding: list[float],
    match_count: int,
) -> list[RetrievedChunk]:
    response = get_supabase().rpc(
        "match_knowledge_documents_hybrid",
        {
            "query_text": subquery.text,
            "query_embedding": embedding,
            "match_count": match_count,
        },
    ).execute()
    return _rank_subquery_candidates([
        _chunk_from_row(row, subquery.topic_id)
        for row in (response.data or [])
    ])


def _fetch_hybrid_candidates(
    subqueries: list[SearchSubquery],
    embeddings: list[list[float]],
    match_count: int,
) -> list[tuple[SearchSubquery, list[RetrievedChunk]]]:
    """Fetch hybrid candidates for each subquery, preserving subquery order.

    The per-subquery Supabase RPCs are independent, side-effect-free reads,
    so they run concurrently in a bounded thread pool instead of one after
    another. ``executor.map`` yields results in input order, and the first
    exception in subquery order propagates -- exactly matching the previous
    sequential behavior. Ranking, deduplication, authorization, user filters,
    timeouts, and the dense-fallback error contract are unchanged: the same
    client issues the same RPCs with the same arguments.
    """
    pairs = list(zip(subqueries, embeddings))
    if len(pairs) <= 1:
        # Single subquery: keep the exact sequential path (no thread overhead).
        return [
            (subquery, _hybrid_candidates(subquery, embedding, match_count))
            for subquery, embedding in pairs
        ]
    workers = min(len(pairs), MAX_PARALLEL_HYBRID_RPCS)
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="fincoach-hybrid-rpc"
    ) as pool:
        return list(
            pool.map(
                lambda pair: (
                    pair[0],
                    _hybrid_candidates(pair[0], pair[1], match_count),
                ),
                pairs,
            )
        )


def _select_hybrid_chunks(
    per_subquery: list[tuple[SearchSubquery, list[RetrievedChunk]]],
    *,
    k: int,
    threshold: float,
    score_margin: float,
) -> list[RetrievedChunk]:
    """Reserve one accepted source per known topic before filling top-k."""
    result_limit = max(1, min(10, int(k)))
    selected: list[RetrievedChunk] = []
    selected_ids: set[int] = set()
    minimum_similarity_by_topic: dict[str | None, float] = {}

    for subquery, chunks in per_subquery:
        if not subquery.source:
            continue
        canonical_candidates = [
            chunk
            for chunk in chunks
            if chunk.source == subquery.source
            and _accepted_for_subquery(chunk, subquery, threshold)
            and chunk.id not in selected_ids
        ]
        evidence = max(
            canonical_candidates,
            key=lambda chunk: (chunk.similarity, chunk.rrf_score, chunk.lexical_score),
            default=None,
        )
        if evidence is None:
            return []
        selected.append(evidence)
        selected_ids.add(evidence.id)
        minimum_similarity_by_topic[subquery.topic_id] = max(
            threshold,
            evidence.similarity - score_margin,
        )

    remaining = sorted(
        (
            chunk
            for subquery, chunks in per_subquery
            for chunk in chunks
            if chunk.id not in selected_ids
            and _accepted_for_subquery(chunk, SearchSubquery(None, None, ""), threshold)
            and chunk.similarity >= minimum_similarity_by_topic.get(
                subquery.topic_id,
                threshold,
            )
        ),
        key=lambda chunk: (chunk.rrf_score, chunk.similarity, chunk.lexical_score),
        reverse=True,
    )
    for chunk in remaining:
        if len(selected) >= result_limit:
            break
        if chunk.id not in selected_ids:
            selected.append(chunk)
            selected_ids.add(chunk.id)
    return selected[:result_limit]


def _retrieve_dense_fallback(
    question: str,
    *,
    k: int,
    threshold: float,
    candidate_k: int,
    score_margin: float,
) -> list[RetrievedChunk]:
    """Keep the existing RPC available until the SQL upgrade is deployed."""
    result_limit = max(1, min(10, int(k)))
    match_count = max(result_limit, min(10, int(candidate_k)))
    response = get_supabase().rpc(
        "match_knowledge_documents",
        {"query_embedding": embed_query(question), "match_count": match_count},
    ).execute()
    chunks = [_chunk_from_row(row, None) for row in (response.data or [])]
    return select_retrieved_chunks(
        chunks,
        k=result_limit,
        threshold=threshold,
        score_margin=score_margin,
    )


def retrieve(
    question: str,
    k: int = RETRIEVE_K,
    threshold: float = RETRIEVE_THRESHOLD,
    *,
    candidate_k: int = RETRIEVE_CANDIDATES,
    score_margin: float = RETRIEVE_SCORE_MARGIN,
    analysis: KnowledgeQueryAnalysis | None = None,
    trace: dict[str, Any] | None = None,
) -> list[RetrievedChunk]:
    """Return hybrid evidence with one source reserved per known topic."""
    if trace is not None:
        trace.update({"mode": "hybrid", "ranked_sources": []})
    resolved_analysis = analysis or analyze_knowledge_query(question)
    if resolved_analysis.clarification or not resolved_analysis.subqueries:
        return []
    result_limit = max(1, min(10, int(k)))
    match_count = max(result_limit, min(10, int(candidate_k)))
    embeddings = embed_texts([subquery.text for subquery in resolved_analysis.subqueries])
    try:
        per_subquery = _fetch_hybrid_candidates(
            list(resolved_analysis.subqueries), embeddings, match_count
        )
    except Exception as error:
        if "match_knowledge_documents_hybrid" not in str(error):
            raise
        if trace is not None:
            trace["mode"] = "dense_fallback"
        return _retrieve_dense_fallback(
            question,
            k=result_limit,
            threshold=threshold,
            candidate_k=match_count,
            score_margin=score_margin,
        )
    if trace is not None:
        candidates = sorted(
            (chunk for _, chunks in per_subquery for chunk in chunks),
            key=lambda chunk: (chunk.rrf_score, chunk.similarity, chunk.lexical_score), reverse=True,
        )
        trace["ranked_sources"] = [chunk.source or "" for chunk in candidates]
    if not any(subquery.source for subquery, _ in per_subquery):
        generic_candidates = [
            chunk
            for _, chunks in per_subquery
            for chunk in chunks
        ]
        return select_retrieved_chunks(
            generic_candidates,
            k=result_limit,
            threshold=threshold,
            score_margin=score_margin,
        )
    return _select_hybrid_chunks(
        per_subquery,
        k=result_limit,
        threshold=threshold,
        score_margin=score_margin,
    )
