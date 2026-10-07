"""Recoverable ingestion worker sharing the already-warmed local model."""
import asyncio
import logging
import math
from starlette.concurrency import run_in_threadpool
from app.admin.documents import build_revision_chunks
from app.embeddings import embed_texts
from app.supabase_client import get_supabase

logger = logging.getLogger("uvicorn.error")


def process_revision(client, revision: dict) -> None:
    chunks = build_revision_chunks(revision, revision["source_key"])
    rows = []
    # Renew leases between small batches; a crashed worker cannot publish a
    # partial replacement. The finish RPC writes only this revision atomically.
    for offset in range(0, len(chunks), 4):
        batch = chunks[offset:offset + 4]
        vectors = embed_texts([chunk.content for chunk in batch])
        if len(vectors) != len(batch) or any(len(v) != 1024 or not all(math.isfinite(x) for x in v) for v in vectors):
            raise ValueError("Incomplete or invalid embedding batch.")
        rows.extend(dict(title=c.title, content=c.content, source=c.source, page_number=None, chunk_index=c.chunk_index, content_hash=c.content_hash, embedding=v) for c, v in zip(batch, vectors))
        client.rpc("admin_renew_knowledge_lease", {"p_revision": revision["id"], "p_lease": revision["lease_token"]}).execute()
    if not rows:
        raise ValueError("No knowledge chunks were produced.")
    client.rpc("admin_finish_knowledge_revision", {"p_revision": revision["id"], "p_lease": revision["lease_token"], "p_chunks": rows}).execute()


def worker_tick() -> bool:
    client = get_supabase()
    revision = client.rpc("admin_claim_knowledge_revision", {}).execute().data
    if not revision:
        return False
    try:
        process_revision(client, revision)
    except Exception:
        logger.exception("fincoach_knowledge_processing_failed revision=%s", revision["id"])
        client.rpc("admin_fail_knowledge_revision", {"p_revision": revision["id"], "p_lease": revision["lease_token"]}).execute()
    return True


async def run_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            worked = await run_in_threadpool(worker_tick)
        except Exception:
            logger.exception("fincoach_knowledge_worker_unavailable")
            worked = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=1 if worked else 5)
        except asyncio.TimeoutError:
            pass
