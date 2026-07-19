import importlib
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

vector_store = importlib.import_module("app.services.vector_store")


KB_ID = UUID("00000000-0000-0000-0000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000002")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000003")


class Query:
    def __init__(self, *, values=None, deleted=0):
        self.values = values or []
        self.deleted = deleted

    async def values_list(self, *_args, **_kwargs):
        return self.values

    async def delete(self):
        return self.deleted


@pytest.mark.asyncio
async def test_delete_document_removes_qdrant_points_before_chunks(monkeypatch):
    filters = []

    def document_filter(**kwargs):
        assert kwargs == {"id": DOCUMENT_ID}
        return Query(values=[KB_ID])

    def chunk_filter(**kwargs):
        assert kwargs == {"document_id": DOCUMENT_ID}
        return Query(deleted=3)

    async def delete_filter(collection, q_filter):
        filters.append((collection, q_filter))

    monkeypatch.setattr(vector_store.Document, "filter", document_filter)
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=1536)
    )
    monkeypatch.setattr(
        vector_store, "_collection_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(vector_store, "_delete_qdrant_filter", delete_filter)

    deleted = await vector_store.VectorStore().delete_document_vectors(DOCUMENT_ID)

    assert deleted == 3
    assert len(filters) == 1
    collection, q_filter = filters[0]
    assert collection == "kb_dim_1536"
    assert q_filter.must[0].key == "document_id"
    assert q_filter.must[0].match.value == str(DOCUMENT_ID)


@pytest.mark.asyncio
async def test_delete_document_without_owner_still_cleans_orphaned_chunks(monkeypatch):
    delete_filter = AsyncMock()
    get_dimension = AsyncMock()
    monkeypatch.setattr(vector_store.Document, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(
        vector_store.DocumentChunk,
        "filter",
        lambda **_kwargs: Query(deleted=2),
    )
    monkeypatch.setattr(vector_store, "get_kb_embedding_dimension", get_dimension)
    monkeypatch.setattr(vector_store, "_delete_qdrant_filter", delete_filter)

    deleted = await vector_store.VectorStore().delete_document_vectors(DOCUMENT_ID)

    assert deleted == 2
    get_dimension.assert_not_awaited()
    delete_filter.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_chunk_removes_vector_and_reports_database_deletion(monkeypatch):
    def chunk_filter(**kwargs):
        if kwargs == {"id": CHUNK_ID}:
            return Query(values=[DOCUMENT_ID], deleted=1)
        raise AssertionError(kwargs)

    monkeypatch.setattr(vector_store.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        vector_store.Document,
        "filter",
        lambda **kwargs: (
            Query(values=[KB_ID]) if kwargs == {"id": DOCUMENT_ID} else Query()
        ),
    )
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=768)
    )
    monkeypatch.setattr(
        vector_store, "_collection_exists", AsyncMock(return_value=True)
    )
    delete_points = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_points", delete_points)

    deleted = await vector_store.VectorStore().delete_chunk_vector(CHUNK_ID)

    assert deleted is True
    delete_points.assert_awaited_once_with("kb_dim_768", [str(CHUNK_ID)])


@pytest.mark.asyncio
async def test_delete_missing_chunk_skips_remote_cleanup_and_returns_false(monkeypatch):
    delete_points = AsyncMock()
    monkeypatch.setattr(
        vector_store.DocumentChunk,
        "filter",
        lambda **_kwargs: Query(deleted=0),
    )
    monkeypatch.setattr(vector_store, "_delete_qdrant_points", delete_points)

    deleted = await vector_store.VectorStore().delete_chunk_vector(CHUNK_ID)

    assert deleted is False
    delete_points.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_kb_cleans_collection_and_all_document_chunks(monkeypatch):
    document_ids = [DOCUMENT_ID, UUID("00000000-0000-0000-0000-000000000004")]
    observed_chunk_filters = []

    def document_filter(**kwargs):
        assert kwargs == {"knowledge_base_id": KB_ID}
        return Query(values=document_ids)

    def chunk_filter(**kwargs):
        observed_chunk_filters.append(kwargs)
        return Query(deleted=5)

    monkeypatch.setattr(vector_store.Document, "filter", document_filter)
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=1024)
    )
    monkeypatch.setattr(
        vector_store, "_collection_exists", AsyncMock(return_value=True)
    )
    delete_filter = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_filter", delete_filter)

    deleted = await vector_store.VectorStore().delete_kb_vectors(KB_ID)

    assert deleted == 5
    assert observed_chunk_filters == [{"document_id__in": document_ids}]
    delete_filter.assert_awaited_once()
    collection, q_filter = delete_filter.await_args.args
    assert collection == "kb_dim_1024"
    assert q_filter.must[0].key == "kb_id"
    assert q_filter.must[0].match.value == str(KB_ID)


@pytest.mark.asyncio
async def test_delete_empty_kb_skips_chunk_query_but_cleans_existing_collection(
    monkeypatch,
):
    monkeypatch.setattr(vector_store.Document, "filter", lambda **_kwargs: Query())
    chunk_filter = AsyncMock()
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=384)
    )
    monkeypatch.setattr(
        vector_store, "_collection_exists", AsyncMock(return_value=True)
    )
    delete_filter = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_filter", delete_filter)

    deleted = await vector_store.VectorStore().delete_kb_vectors(KB_ID)

    assert deleted == 0
    chunk_filter.assert_not_called()
    delete_filter.assert_awaited_once()
