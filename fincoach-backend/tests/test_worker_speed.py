"""Regression tests for database-compatible knowledge ingestion improvements."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.admin import worker


def test_repeated_document_chunks_reuse_identical_vectors(monkeypatch):
    chunks = [SimpleNamespace(title='Guide', content='a financial guide', source='guide',
                              chunk_index=0, content_hash='hash')]
    monkeypatch.setattr(worker, 'build_revision_chunks', lambda revision, source: chunks)
    calls = []
    def encode(texts):
        calls.append(list(texts))
        return [[0.25] * 1024 for _ in texts]
    monkeypatch.setattr(worker, 'embed_texts', encode)
    model = object()
    cache = worker.ExactEmbeddingCache(model_provider=lambda: model)
    client = MagicMock()
    revision = {'id': 'revision', 'lease_token': 'token', 'source_key': 'guide'}
    worker.process_revision(client, revision, cache)
    first = client.rpc.call_args.args[1]['p_chunks']
    worker.process_revision(client, revision, cache)
    second = client.rpc.call_args.args[1]['p_chunks']
    assert first == second and calls == [['a financial guide']]


def test_cache_invalidates_for_changed_model_and_rejects_invalid_vectors():
    models = [object()]
    cache = worker.ExactEmbeddingCache(model_provider=lambda: models[0], capacity=2)
    calls = []
    def encode(texts):
        calls.append(texts)
        return [[0.5] * 1024 for _ in texts]
    cache.encode(['text'], encode)
    cache.encode(['text'], encode)
    models[0] = object()
    cache.encode(['text'], encode)
    assert calls == [['text'], ['text']]
    with pytest.raises(ValueError):
        cache.encode(['invalid'], lambda texts: [[float('nan')] * 1024])
    assert len(cache._entries) == 1


def test_cleanup_does_not_block_worker(monkeypatch):
    started, release, tick_ran = threading.Event(), threading.Event(), threading.Event()
    def slow_sweep(client):
        started.set()
        assert release.wait(timeout=5)
    async def scenario():
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        def tick(*args):
            assert started.wait(timeout=2)
            tick_ran.set()
            loop.call_soon_threadsafe(stop.set)
            return False
        monkeypatch.setattr(worker, 'get_supabase', lambda: None)
        monkeypatch.setattr(worker, 'sweep_orphan_uploads', slow_sweep)
        monkeypatch.setattr(worker, 'worker_tick', tick)
        task = asyncio.create_task(worker.run_worker(stop))
        try:
            assert await asyncio.to_thread(tick_ran.wait, 1), 'cleanup blocked ingestion'
        finally:
            release.set()
            await asyncio.wait_for(task, timeout=5)
    asyncio.run(scenario())
