import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.services.vector_store import EmbeddingRequestTimeoutError, VectorStore

vector_store_module = importlib.import_module("app.services.vector_store")


@pytest.fixture
def qdrant_models(monkeypatch):
    class Model:
        def __init__(self, **values):
            self.__dict__.update(values)

    models = SimpleNamespace(
        Distance=SimpleNamespace(COSINE="cosine", DOT="dot", EUCLID="euclid"),
        FieldCondition=Model,
        Filter=Model,
        MatchAny=Model,
        MatchValue=Model,
        PayloadSchemaType=SimpleNamespace(KEYWORD="keyword"),
        PointStruct=Model,
        VectorParams=Model,
    )
    monkeypatch.setattr(vector_store_module, "qmodels", models)
    return models


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


def test_build_qdrant_filter_scopes_kb_and_optional_documents(qdrant_models):
    kb_id = uuid4()
    document_ids = [uuid4(), uuid4()]

    kb_filter = vector_store_module._build_qdrant_filter(kb_id, None)
    document_filter = vector_store_module._build_qdrant_filter(kb_id, document_ids)

    assert kb_filter.must[0].key == "kb_id"
    assert kb_filter.must[0].match.value == str(kb_id)
    assert len(kb_filter.must) == 1
    assert document_filter.must[1].key == "document_id"
    assert document_filter.must[1].match.any == [str(value) for value in document_ids]


def test_qdrant_distance_rejects_unsupported_setting(monkeypatch, qdrant_models):
    monkeypatch.setattr(vector_store_module.settings, "QDRANT_DISTANCE", "manhattan")

    with pytest.raises(ValueError, match="Unsupported Qdrant distance: manhattan"):
        vector_store_module._qdrant_distance()


@pytest.mark.asyncio
async def test_store_embedding_creates_collection_indexes_and_upserts(
    monkeypatch, qdrant_models
):
    class FakeQdrantClient:
        def __init__(self):
            self.collections = set()
            self.indexes = []
            self.points = []

        async def get_collection(self, collection):
            if collection not in self.collections:
                raise LookupError(collection)

        async def create_collection(self, collection_name, vectors_config):
            self.collections.add(collection_name)
            assert vectors_config.size == 3

        async def create_payload_index(self, collection_name, field_name, field_schema):
            self.indexes.append((collection_name, field_name, field_schema))

        async def upsert(self, collection_name, points):
            self.points.extend(points)
            return SimpleNamespace(status="completed")

    client = FakeQdrantClient()
    monkeypatch.setattr(
        vector_store_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        vector_store_module.settings, "QDRANT_COLLECTION_PREFIX", "test"
    )
    vector_store_module._qdrant_collections.clear()
    vector_store_module._qdrant_payload_indexes.clear()
    chunk_id = uuid4()

    await VectorStore()._store_embedding(
        chunk_id,
        [0.1, 0.2, 0.3],
        payload={"kb_id": "kb", "document_id": "document"},
    )

    assert client.collections == {"test_3"}
    assert [index[1] for index in client.indexes] == ["kb_id", "document_id"]
    assert len(client.points) == 1
    assert client.points[0].id == str(chunk_id)
    assert client.points[0].vector == [0.1, 0.2, 0.3]
    assert client.points[0].payload == {
        "kb_id": "kb",
        "document_id": "document",
    }


@pytest.mark.asyncio
async def test_qdrant_search_retries_with_legacy_query_vector(monkeypatch):
    client = SimpleNamespace(
        query_points=AsyncMock(
            side_effect=[TypeError, SimpleNamespace(points=["legacy-hit"])]
        )
    )
    monkeypatch.setattr(
        vector_store_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    result = await vector_store_module._qdrant_search("collection", [0.1], 2, "filter")

    assert result == ["legacy-hit"]
    assert client.query_points.await_args_list[0].kwargs["query"] == [0.1]
    assert client.query_points.await_args_list[1].kwargs["query_vector"] == [0.1]


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
    monkeypatch.setattr(
        vector_store_module.Document,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=values_list)),
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
        vector_store_module, "_build_qdrant_filter", Mock(return_value="kb-filter")
    )

    result = await VectorStore().get_embedding_stats(kb_id)

    assert result == {
        "total": 5,
        "with_embedding": 2,
        "without_embedding": 3,
        "dimension": 3,
    }
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

    assert await VectorStore().get_embedding_stats() == {
        "total": 0,
        "with_embedding": 0,
        "without_embedding": 0,
    }
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
