"""Recoverable ingestion worker sharing the already-warmed local model."""
import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from time import monotonic
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


ORIGINALS_BUCKET = "knowledge-originals"
# Uploads are saved as drafts within seconds; a day protects slow imports.
ORPHAN_UPLOAD_GRACE = timedelta(hours=24)
ORPHAN_SWEEP_INTERVAL_SECONDS = 3600


def sweep_orphan_uploads(client, now: datetime | None = None) -> int:
    """Remove uploaded originals that no revision ever referenced.

    An upload is stored before its draft is saved, so a failed save leaves the
    file behind. Referenced originals, including old revisions, are kept.
    """
    now = now or datetime.now(timezone.utc)
    rows = client.table("knowledge_revisions").select("file_path").not_.is_("file_path", "null").execute().data or []
    referenced = {row["file_path"] for row in rows}
    bucket = client.storage.from_(ORIGINALS_BUCKET)
    options = {"limit": 1000}
    orphans = []
    # Layout: <admin id>/<upload id>/original.<ext>
    for owner in bucket.list("", options):
        for upload in bucket.list(owner["name"], options):
            folder = f"{owner['name']}/{upload['name']}"
            for item in bucket.list(folder, options):
                path = f"{folder}/{item['name']}"
                created = item.get("created_at")
                if path in referenced or not created:
                    continue
                if now - datetime.fromisoformat(created.replace("Z", "+00:00")) > ORPHAN_UPLOAD_GRACE:
                    orphans.append(path)
    if orphans:
        bucket.remove(orphans)
        logger.info("fincoach_knowledge_orphan_uploads_removed count=%s", len(orphans))
    return len(orphans)


async def run_worker(stop: asyncio.Event) -> None:
    next_sweep = 0.0
    while not stop.is_set():
        if monotonic() >= next_sweep:
            next_sweep = monotonic() + ORPHAN_SWEEP_INTERVAL_SECONDS
            try:
                await run_in_threadpool(lambda: sweep_orphan_uploads(get_supabase()))
            except Exception:
                logger.exception("fincoach_knowledge_orphan_sweep_failed")
        try:
            worked = await run_in_threadpool(worker_tick)
        except Exception:
            logger.exception("fincoach_knowledge_worker_unavailable")
            worked = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=1 if worked else 5)
        except asyncio.TimeoutError:
            pass
