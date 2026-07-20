import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.services.vector_store import EmbeddingRequestTimeoutError, VectorStore

vector_store_module = importlib.import_module("app.services.vector_store")


class HangingModelManager:
    async def embed(self, texts, model_id=None):
        await asyncio.sleep(1)
        return []

    async def embed_query(self, text, model_id=None):
        await asyncio.sleep(1)
        return []


@pytest.mark.asyncio
async def test_embed_texts_converts_timeout(monkeypatch):
    monkeypatch.setattr(vector_store_module, "EMBEDDING_REQUEST_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(vector_store_module, "_get_model_manager", HangingModelManager)

    store = VectorStore()

    with pytest.raises(EmbeddingRequestTimeoutError):
        await store.embed_texts(["slow"])


@pytest.mark.asyncio
async def test_embed_query_converts_timeout(monkeypatch):
    monkeypatch.setattr(vector_store_module, "EMBEDDING_REQUEST_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(vector_store_module, "_get_model_manager", HangingModelManager)

    store = VectorStore()

    with pytest.raises(EmbeddingRequestTimeoutError):
        await store.embed_query("slow")


@pytest.mark.asyncio
async def test_add_chunk_vector_uses_timed_embed_texts(monkeypatch):
    calls = []
    chunk = SimpleNamespace(
        id="chunk-id",
        document_id="document-id",
        content="content",
        embedding_id=None,
    )
    chunk.save = AsyncMock()

    async def fake_embed_texts(self, texts):
        calls.append(texts)
        return [[0.1, 0.2, 0.3]]

    async def fake_ensure_kb_dimension(kb_id, dimension):
        assert str(kb_id) == "00000000-0000-0000-0000-000000000001"
        assert dimension == 3

    async def fake_store_embedding(
        self, chunk_id, embedding, dimension=None, payload=None
    ):
        assert chunk_id == "chunk-id"
        assert embedding == [0.1, 0.2, 0.3]
        assert dimension == 3
        assert payload == {
            "kb_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "document-id",
        }

    monkeypatch.setattr(VectorStore, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(
        vector_store_module, "_ensure_kb_dimension", fake_ensure_kb_dimension
    )
    monkeypatch.setattr(VectorStore, "_store_embedding", fake_store_embedding)

    store = VectorStore()

    result = await store.add_chunk_vector(
        UUID("00000000-0000-0000-0000-000000000001"),
        chunk,
    )

    assert result is True
    assert calls == [["content"]]
    assert (
        chunk.embedding_id == "kb_00000000-0000-0000-0000-000000000001_chunk_chunk-id"
    )
    chunk.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_chunk_vector_propagates_embedding_failure(monkeypatch):
    chunk = SimpleNamespace(content="content", save=AsyncMock())
    monkeypatch.setattr(
        VectorStore,
        "embed_texts",
        AsyncMock(side_effect=RuntimeError("model unavailable")),
    )

    with pytest.raises(RuntimeError, match="model unavailable"):
        await VectorStore().add_chunk_vector(
            UUID("00000000-0000-0000-0000-000000000001"), chunk
        )

    chunk.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_chunk_vector_resolves_kb_and_stores_embedding(monkeypatch):
    kb_id = UUID("00000000-0000-0000-0000-000000000001")
    chunk = SimpleNamespace(
        id="chunk-id",
        document_id="document-id",
        content="updated content",
        embedding_id=None,
        save=AsyncMock(),
    )
    values_list = AsyncMock(return_value=[kb_id])
    filter_query = SimpleNamespace(values_list=values_list)
    monkeypatch.setattr(
        vector_store_module.Document, "filter", Mock(return_value=filter_query)
    )
    monkeypatch.setattr(VectorStore, "embed_query", AsyncMock(return_value=[0.1, 0.2]))
    ensure_dimension = AsyncMock()
    monkeypatch.setattr(vector_store_module, "_ensure_kb_dimension", ensure_dimension)
    store_embedding = AsyncMock()
    monkeypatch.setattr(VectorStore, "_store_embedding", store_embedding)

    assert await VectorStore().update_chunk_vector(chunk) is True
    values_list.assert_awaited_once_with("knowledge_base_id", flat=True)
    ensure_dimension.assert_awaited_once_with(kb_id, 2)
    assert chunk.embedding_id == "chunk_chunk-id_updated"
    chunk.save.assert_awaited_once()
    store_embedding.assert_awaited_once_with(
        "chunk-id",
        [0.1, 0.2],
        dimension=2,
        payload={"kb_id": str(kb_id), "document_id": "document-id"},
    )


@pytest.mark.asyncio
async def test_update_chunk_vector_returns_false_on_storage_failure(monkeypatch):
    chunk = SimpleNamespace(
        id="chunk-id",
        document_id="document-id",
        content="content",
        embedding_id=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(VectorStore, "embed_query", AsyncMock(return_value=[0.1]))
    monkeypatch.setattr(
        VectorStore,
        "_store_embedding",
        AsyncMock(side_effect=RuntimeError("qdrant unavailable")),
    )

    assert await VectorStore().update_chunk_vector(chunk, kb_id="not-a-uuid") is False
    assert chunk.embedding_id == "chunk_chunk-id_updated"
    chunk.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_embedding_stats_counts_kb_vectors(monkeypatch):
    kb_id = UUID("00000000-0000-0000-0000-000000000001")
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(None, [{"total": 5}])))
    monkeypatch.setattr(
        vector_store_module.Tortoise, "get_connection", Mock(return_value=conn)
    )
    monkeypatch.setattr(
        vector_store_module, "get_kb_embedding_dimension", AsyncMock(return_value=3)
    )
    monkeypatch.setattr(
        vector_store_module, "_collection_exists", AsyncMock(return_value=True)
    )
    client = SimpleNamespace(count=AsyncMock(return_value=SimpleNamespace(count=2)))
    monkeypatch.setattr(
        vector_store_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        vector_store_module,
        "_build_qdrant_filter",
        Mock(return_value="kb-filter"),
    )

    result = await VectorStore().get_embedding_stats(kb_id)

    assert result == {
        "total": 5,
        "with_embedding": 2,
        "without_embedding": 3,
        "dimension": 3,
    }
    conn.execute_query.assert_awaited_once()
    assert conn.execute_query.await_args.args[1] == [str(kb_id)]
    client.count.assert_awaited_once_with(
        collection_name="kb_dim_3",
        count_filter="kb-filter",
        exact=True,
    )


@pytest.mark.asyncio
async def test_get_embedding_stats_handles_empty_unscoped_database(monkeypatch):
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(
        vector_store_module.Tortoise, "get_connection", Mock(return_value=conn)
    )

    result = await VectorStore().get_embedding_stats()

    assert result == {"total": 0, "with_embedding": 0, "without_embedding": 0}
    conn.execute_query.assert_awaited_once()
    assert conn.execute_query.await_args.args[1] == []


@pytest.mark.asyncio
async def test_get_embedding_stats_skips_missing_collection(monkeypatch):
    kb_id = UUID("00000000-0000-0000-0000-000000000001")
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(None, [{"total": 2}])))
    monkeypatch.setattr(
        vector_store_module.Tortoise, "get_connection", Mock(return_value=conn)
    )
    monkeypatch.setattr(
        vector_store_module, "get_kb_embedding_dimension", AsyncMock(return_value=3)
    )
    monkeypatch.setattr(
        vector_store_module, "_collection_exists", AsyncMock(return_value=False)
    )
    get_client = AsyncMock()
    monkeypatch.setattr(vector_store_module, "_get_qdrant_client", get_client)

    assert await VectorStore().get_embedding_stats(kb_id) == {
        "total": 2,
        "with_embedding": 0,
        "without_embedding": 2,
        "dimension": 3,
    }
    get_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_migrate_existing_chunks_is_noop():
    assert await VectorStore().migrate_existing_chunks(
        batch_size=1,
        kb_id=UUID("00000000-0000-0000-0000-000000000001"),
    ) == {"processed": 0, "success": 0, "failed": 0, "skipped": 0}
