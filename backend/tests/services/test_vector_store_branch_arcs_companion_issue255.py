import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.services.vector_store import DimensionMismatchError, VectorStore

vector_store = importlib.import_module("app.services.vector_store")
KB_ID = UUID("00000000-0000-0000-0000-000000000001")


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


class Query:
    def __init__(self, values=None, deleted=0):
        self.values = values or []
        self.deleted = deleted

    async def values_list(self, *_args, **_kwargs):
        return self.values

    async def delete(self):
        return self.deleted


@pytest.mark.asyncio
async def test_configuration_and_storage_skip_optional_fallbacks(monkeypatch):
    monkeypatch.setattr(
        vector_store.KnowledgeBase, "get_or_none", AsyncMock(return_value=None)
    )
    config = await VectorStore()._resolve_rerank_config(KB_ID, {"unused": True})
    assert config["score_threshold"] is None

    ensure_collection = AsyncMock(return_value="kb_2")
    client = SimpleNamespace(
        upsert=AsyncMock(return_value=SimpleNamespace(status="completed"))
    )
    monkeypatch.setattr(vector_store, "_ensure_collection", ensure_collection)
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(vector_store, "qmodels", SimpleNamespace(PointStruct=Model))

    store = VectorStore(embedding_dimension=2)
    await store._store_embedding(uuid4(), [0.1, 0.2])

    assert store._detected_dimension is None
    ensure_collection.assert_awaited_once_with(2)


def test_cosine_score_and_repeated_rrf_results(monkeypatch):
    monkeypatch.setattr(vector_store.settings, "QDRANT_DISTANCE", "cosine")
    assert vector_store._normalize_qdrant_score(-2.0) == 0.0

    repeated = [
        {"chunk_id": "same", "score": 0.9},
        {"chunk_id": "same", "score": 0.8},
    ]
    assert VectorStore()._merge_results_rrf(repeated, [])[0]["chunk_id"] == "same"


@pytest.mark.asyncio
async def test_store_chunks_handles_missing_embeddings_and_non_uuid_owner(monkeypatch):
    document = SimpleNamespace(id=uuid4(), knowledge_base_id="legacy-kb")
    store = VectorStore()
    store.embed_texts = AsyncMock(side_effect=[[], [[0.1]]])
    store._batch_store_embeddings = AsyncMock()
    created = []

    async def create_chunk(**values):
        chunk = SimpleNamespace(id=uuid4(), **values)
        created.append(chunk)
        return chunk

    monkeypatch.setattr(vector_store.DocumentChunk, "create", create_chunk)
    ensure_dimension = AsyncMock()
    monkeypatch.setattr(vector_store, "_ensure_kb_dimension", ensure_dimension)

    assert (
        await store.store_chunks(document, [{"content": "missing", "chunk_index": 0}])
        == []
    )
    assert (
        await store.store_chunks(document, [{"content": "available", "chunk_index": 1}])
        == created
    )
    ensure_dimension.assert_not_awaited()


@pytest.mark.asyncio
async def test_progress_without_callback_completes_loop(monkeypatch):
    chunk = SimpleNamespace(id=uuid4(), save=AsyncMock())
    monkeypatch.setattr(
        vector_store.DocumentChunk, "create", AsyncMock(return_value=chunk)
    )
    store = VectorStore()
    store.embed_texts = AsyncMock(return_value=[[0.1]])
    store._store_embedding = AsyncMock()

    result = await store.store_chunks_with_progress(
        SimpleNamespace(id=uuid4(), knowledge_base_id="legacy-kb"),
        [{"content": "text", "chunk_index": 0}],
    )

    assert result == [chunk]
    assert chunk.status == "embedded"


@pytest.mark.asyncio
async def test_search_with_explicit_dimension_and_no_results(monkeypatch):
    store = VectorStore()
    store._resolve_rerank_config = AsyncMock(
        return_value={
            "enabled": False,
            "model_id": None,
            "candidate_k": 1,
            "fail_open": True,
            "score_threshold": None,
        }
    )
    store._vector_search = AsyncMock(return_value=[])
    get_dimension = AsyncMock()
    monkeypatch.setattr(vector_store, "get_kb_embedding_dimension", get_dimension)

    assert (
        await store.search(KB_ID, "query", search_mode="vector", embedding_dimension=2)
        == []
    )
    get_dimension.assert_not_awaited()


@pytest.mark.asyncio
async def test_vector_search_mismatch_empty_and_metadata_paths(monkeypatch):
    store = VectorStore(embedding_dimension=2)
    store.embed_query = AsyncMock(return_value=[0.1])
    with pytest.raises(DimensionMismatchError):
        await store._vector_search(KB_ID, "query", 3)

    store.embed_query.return_value = [0.1, 0.2]
    monkeypatch.setattr(
        vector_store, "_ensure_collection", AsyncMock(return_value="kb_2")
    )
    monkeypatch.setattr(
        vector_store, "_build_qdrant_filter", Mock(return_value="filter")
    )
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(vector_store, "_qdrant_search", search)
    assert await store._vector_search(KB_ID, "query", 3) == []

    chunks = [
        SimpleNamespace(
            id="plain",
            document_id="doc",
            document=SimpleNamespace(name="Plain"),
            content="plain",
            metadata={"page": 1},
        ),
        SimpleNamespace(
            id="json",
            document_id="doc",
            document=None,
            content="json",
            metadata='{"page": 2}',
        ),
        SimpleNamespace(
            id="invalid",
            document_id="doc",
            document=SimpleNamespace(name="Invalid"),
            content="invalid",
            metadata="{",
        ),
    ]
    search.return_value = [SimpleNamespace(id=chunk.id, score=0.5) for chunk in chunks]

    async def resolve_chunks():
        return chunks

    query = SimpleNamespace(prefetch_related=Mock(return_value=resolve_chunks()))
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", Mock(return_value=query))

    results = await store._vector_search(KB_ID, "query", 3)
    assert [result["metadata"] for result in results] == [
        {"page": 1},
        {"page": 2},
        None,
    ]
    assert results[1]["document_name"] is None


@pytest.mark.asyncio
async def test_fulltext_search_skips_optional_filters(monkeypatch):
    class ChunkQuery:
        def prefetch_related(self, *_args):
            return self

        def filter(self, *_args, **_kwargs):
            raise AssertionError("no filters expected")

        async def limit(self, _value):
            return []

    monkeypatch.setattr(
        vector_store.DocumentChunk, "filter", Mock(return_value=ChunkQuery())
    )
    store = VectorStore()
    store._extract_search_terms = Mock(return_value=[])

    assert await store._fulltext_search(KB_ID, "", 1) == []


def test_semantic_similarity_skips_empty_ngram_windows(monkeypatch):
    assert VectorStore()._estimate_semantic_similarity("x", "unrelated") == 0.0

    monkeypatch.setattr(vector_store, "range", lambda *_args: [], raising=False)
    assert VectorStore()._estimate_semantic_similarity("xy", "unrelated") == 0.0


@pytest.mark.asyncio
async def test_deletions_skip_remote_cleanup_at_each_boundary(monkeypatch):
    store = VectorStore()
    delete_filter = AsyncMock()
    delete_points = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_filter", delete_filter)
    monkeypatch.setattr(vector_store, "_delete_qdrant_points", delete_points)
    monkeypatch.setattr(
        vector_store.DocumentChunk, "filter", Mock(return_value=Query(deleted=1))
    )

    monkeypatch.setattr(vector_store.Document, "filter", Mock(return_value=Query()))
    assert await store.delete_document_vectors(uuid4()) == 1

    monkeypatch.setattr(
        vector_store.Document, "filter", Mock(return_value=Query([KB_ID]))
    )
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=2)
    )
    monkeypatch.setattr(
        vector_store, "_collection_exists", AsyncMock(return_value=False)
    )
    assert await store.delete_document_vectors(uuid4()) == 1

    monkeypatch.setattr(
        vector_store.DocumentChunk,
        "filter",
        Mock(side_effect=[Query(), Query(deleted=0)]),
    )
    assert await store.delete_chunk_vector(uuid4()) is False

    monkeypatch.setattr(
        vector_store.DocumentChunk,
        "filter",
        Mock(side_effect=[Query([uuid4()]), Query(deleted=1)]),
    )
    assert await store.delete_chunk_vector(uuid4()) is True

    delete_filter.assert_not_awaited()
    delete_points.assert_not_awaited()
