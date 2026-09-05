import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest

from app.services.vector_store import VectorStore


@pytest.fixture
def vs_mod():

    return sys.modules["app.services.vector_store"]


@pytest.mark.asyncio
async def test_store_chunks_with_progress_batch_mode_success(monkeypatch, vs_mod):
    store = VectorStore()
    kb_id = uuid4()
    doc_id = uuid4()
    document = SimpleNamespace(id=doc_id, knowledge_base_id=kb_id)

    created_objs = []

    async def _create(**kwargs):
        chunk = SimpleNamespace(
            id=uuid4(),
            status=kwargs.get("status"),
            error_message=None,
            metadata=kwargs.get("metadata"),
            save=AsyncMock(),
        )
        created_objs.append(chunk)
        return chunk

    monkeypatch.setattr(vs_mod, "DocumentChunk", SimpleNamespace(create=_create))
    monkeypatch.setattr(vs_mod, "_ensure_kb_dimension", AsyncMock())
    store.embed_texts = AsyncMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    store._batch_store_embeddings = AsyncMock()

    progress_calls = []

    async def _progress(embedded, failed, total):
        progress_calls.append((embedded, failed, total))

    chunks_data = [
        {"content": "chunk 1", "chunk_index": 0, "token_count": 10},
        {"content": "chunk 2", "chunk_index": 1, "token_count": 12},
    ]

    res = await store.store_chunks_with_progress(
        document,
        chunks_data,
        kb_id=kb_id,
        progress_callback=_progress,
        batch_size=2,
    )

    assert len(res) == 2
    assert all(c.status == "embedded" for c in res)
    assert progress_calls == [(2, 0, 2)]
    store._batch_store_embeddings.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_chunks_with_progress_batch_mode_fallback(monkeypatch, vs_mod):
    store = VectorStore()
    kb_id = uuid4()
    doc_id = uuid4()
    document = SimpleNamespace(id=doc_id, knowledge_base_id=kb_id)

    created_objs = []

    async def _create(**kwargs):
        chunk = SimpleNamespace(
            id=uuid4(),
            status=kwargs.get("status"),
            error_message=None,
            metadata=kwargs.get("metadata"),
            save=AsyncMock(),
        )
        created_objs.append(chunk)
        return chunk

    monkeypatch.setattr(vs_mod, "DocumentChunk", SimpleNamespace(create=_create))
    monkeypatch.setattr(vs_mod, "_ensure_kb_dimension", AsyncMock())
    # Batch embedding fails, then fallback single embeds: 1st succeeds, 2nd fails
    store.embed_texts = AsyncMock(
        side_effect=[
            RuntimeError("batch error"),
            [[0.1, 0.2]],
            RuntimeError("single error"),
        ]
    )
    store._store_embedding = AsyncMock()

    progress_calls = []

    async def _progress(embedded, failed, total):
        progress_calls.append((embedded, failed, total))

    chunks_data = [
        {"content": "chunk 1", "chunk_index": 0},
        {"content": "chunk 2", "chunk_index": 1},
    ]

    res = await store.store_chunks_with_progress(
        document,
        chunks_data,
        kb_id=kb_id,
        progress_callback=_progress,
        batch_size=2,
    )

    assert len(res) == 2
    assert res[0].status == "embedded"
    assert res[1].status == "failed"
    assert progress_calls == [(1, 1, 2)]


@pytest.mark.asyncio
async def test_add_chunk_vectors_batch_empty_and_success(monkeypatch, vs_mod):
    store = VectorStore()
    kb_id = uuid4()

    # Empty list
    assert await store.add_chunk_vectors_batch(kb_id, []) == []

    # Embeddings empty
    store.embed_texts = AsyncMock(return_value=[])
    dummy_chunk = SimpleNamespace(
        id=uuid4(), content="text", document_id=uuid4(), save=AsyncMock()
    )
    assert await store.add_chunk_vectors_batch(kb_id, [dummy_chunk]) == []

    # Success
    store.embed_texts = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    store._batch_store_embeddings = AsyncMock()
    monkeypatch.setattr(vs_mod, "_ensure_kb_dimension", AsyncMock())

    chunk1 = SimpleNamespace(
        id=uuid4(), content="c1", document_id=uuid4(), save=AsyncMock()
    )
    chunk2 = SimpleNamespace(
        id=uuid4(), content="c2", document_id=uuid4(), save=AsyncMock()
    )

    res = await store.add_chunk_vectors_batch(kb_id, [chunk1, chunk2])
    assert len(res) == 2
    assert chunk1.status == "embedded"
    assert chunk2.status == "embedded"
    chunk1.save.assert_awaited_once()
    chunk2.save.assert_awaited_once()
