"""Recoverable ingestion worker sharing the already-warmed local model."""
import asyncio
from collections import OrderedDict
from hashlib import sha256
import logging
import math
from datetime import datetime, timedelta, timezone
from time import monotonic
from starlette.concurrency import run_in_threadpool
from app.admin.documents import build_revision_chunks
from app.embeddings import _model, embed_texts
from app.supabase_client import get_supabase

logger = logging.getLogger("uvicorn.error")


class ExactEmbeddingCache:
    """Bounded, process-local reuse for the same text and loaded model."""

    def __init__(self, model_provider=_model, capacity=128):
        self._model_provider = model_provider
        self._capacity = capacity
        self._model_ref = None
        self._settings = None
        self._entries = OrderedDict()

    def encode(self, texts, encode):
        model = self._model_provider()
        # Invalidate when the inference model, tokenizer or relevant settings
        # change. The cache never changes the model or the text being embedded.
        settings = (id(getattr(model, 'tokenizer', None)),
                    str(getattr(model, 'device', None)),
                    str(getattr(model, 'dtype', None)),
                    getattr(model, 'max_seq_length', None), 'normalize=True')
        if model is not self._model_ref or settings != self._settings:
            self._entries.clear()
            self._model_ref, self._settings = model, settings
        keys = [sha256(text.encode('utf-8')).digest() for text in texts]
        missing = {}
        for key, text in zip(keys, texts):
            if key not in self._entries:
                missing.setdefault(key, text)
        if missing:
            vectors = encode(list(missing.values()))
            if (len(vectors) != len(missing) or any(len(v) != 1024
                    or not all(math.isfinite(x) for x in v) for v in vectors)):
                raise ValueError('Incomplete or invalid embedding batch.')
            for key, vector in zip(missing, vectors):
                self._entries[key] = tuple(vector)
        result = [list(self._entries[key]) for key in keys]
        for key in keys:
            self._entries.move_to_end(key)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)
        return result


def process_revision(client, revision: dict, cache=None) -> None:
    started = monotonic()
    chunks = build_revision_chunks(revision, revision["source_key"])
    rows = []
    logger.info('fincoach_knowledge_processing_started revision=%s chunks=%s attempt=%s',
                revision['id'], len(chunks), revision.get('attempts'))
    # Renew leases between small batches; a crashed worker cannot publish a
    # partial replacement. The finish RPC writes only this revision atomically.
    for offset in range(0, len(chunks), 4):
        batch = chunks[offset:offset + 4]
        batch_started = monotonic()
        texts = [chunk.content for chunk in batch]
        vectors = cache.encode(texts, embed_texts) if cache is not None else embed_texts(texts)
        if len(vectors) != len(batch) or any(len(v) != 1024 or not all(math.isfinite(x) for x in v) for v in vectors):
            raise ValueError("Incomplete or invalid embedding batch.")
        rows.extend(dict(title=c.title, content=c.content, source=c.source, page_number=None, chunk_index=c.chunk_index, content_hash=c.content_hash, embedding=v) for c, v in zip(batch, vectors))
        client.rpc("admin_renew_knowledge_lease", {"p_revision": revision["id"], "p_lease": revision["lease_token"]}).execute()
        logger.info('fincoach_knowledge_batch_completed revision=%s batch=%s elapsed_ms=%.1f',
                    revision['id'], offset // 4 + 1, (monotonic() - batch_started) * 1000)
    if not rows:
        raise ValueError("No knowledge chunks were produced.")
    client.rpc("admin_finish_knowledge_revision", {"p_revision": revision["id"], "p_lease": revision["lease_token"], "p_chunks": rows}).execute()
    logger.info('fincoach_knowledge_processing_completed revision=%s chunks=%s elapsed_ms=%.1f',
                revision['id'], len(rows), (monotonic() - started) * 1000)


def worker_tick(cache=None) -> bool:
    client = get_supabase()
    revision = client.rpc("admin_claim_knowledge_revision", {}).execute().data
    if not revision:
        return False
    try:
        process_revision(client, revision, cache)
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
    sweep_task = None
    cache = ExactEmbeddingCache()

    async def run_sweep():
        try:
            await run_in_threadpool(lambda: sweep_orphan_uploads(get_supabase()))
        except Exception:
            logger.exception("fincoach_knowledge_orphan_sweep_failed")

    try:
        while not stop.is_set():
            if monotonic() >= next_sweep and (sweep_task is None or sweep_task.done()):
                next_sweep = monotonic() + ORPHAN_SWEEP_INTERVAL_SECONDS
                # Run at most one cleanup concurrently, so slow storage cannot
                # prevent the worker from claiming a queued document.
                sweep_task = asyncio.create_task(run_sweep())
            try:
                worked = await run_in_threadpool(worker_tick, cache)
            except Exception:
                logger.exception("fincoach_knowledge_worker_unavailable")
                worked = False
            try:
                await asyncio.wait_for(stop.wait(), timeout=1 if worked else 5)
            except asyncio.TimeoutError:
                pass
    finally:
        if sweep_task is not None and not sweep_task.done():
            # Cancellation does not forcibly stop an in-flight storage call.
            # The existing 24-hour grace still protects unreferenced uploads.
            sweep_task.cancel()
            try:
                await sweep_task
            except asyncio.CancelledError:
                pass
