"""Typed pgvector retrieval for shared Malaysian finance knowledge."""

from dataclasses import dataclass
from typing import Any

from app.config import RETRIEVE_K, RETRIEVE_THRESHOLD
from app.embeddings import embed_query


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


def retrieve(question: str, k: int = RETRIEVE_K, threshold: float = RETRIEVE_THRESHOLD) -> list[RetrievedChunk]:
    match_count = max(1, min(10, int(k)))
    response = get_supabase().rpc(
        "match_knowledge_documents",
        {"query_embedding": embed_query(question), "match_count": match_count},
    ).execute()
    chunks = [RetrievedChunk(
        id=int(row["id"]),
        title=row.get("title"),
        source=row.get("source"),
        page_number=row.get("page_number"),
        chunk_index=row.get("chunk_index"),
        content=row["content"],
        similarity=float(row.get("similarity") or 0),
    ) for row in (response.data or [])]
    return [chunk for chunk in chunks if chunk.similarity >= threshold]
