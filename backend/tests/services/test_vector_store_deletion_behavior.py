import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.vector_store import VectorStore


@pytest.mark.asyncio
async def test_delete_document_vectors_scopes_qdrant_and_deletes_chunks(monkeypatch):
    vector_store_module = importlib.import_module("app.services.vector_store")

    document_id = uuid4()
    kb_id = uuid4()
    document_query = MagicMock()
    document_query.values_list = AsyncMock(return_value=[kb_id])
    chunk_query = MagicMock()
    chunk_query.delete = AsyncMock(return_value=2)
    delete_filter = AsyncMock()

    class Model:
        def __init__(self, **values):
            self.__dict__.update(values)

    monkeypatch.setattr(
        vector_store_module,
        "qmodels",
        SimpleNamespace(FieldCondition=Model, Filter=Model, MatchValue=Model),
    )
    monkeypatch.setattr(
        vector_store_module.Document, "filter", MagicMock(return_value=document_query)
    )
    monkeypatch.setattr(
        vector_store_module.DocumentChunk, "filter", MagicMock(return_value=chunk_query)
    )
    monkeypatch.setattr(
        vector_store_module, "get_kb_embedding_dimension", AsyncMock(return_value=3)
    )
    monkeypatch.setattr(
        vector_store_module, "_collection_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(vector_store_module, "_delete_qdrant_filter", delete_filter)
    monkeypatch.setattr(
        vector_store_module.settings, "QDRANT_COLLECTION_PREFIX", "test"
    )

    assert await VectorStore().delete_document_vectors(document_id) == 2
    assert delete_filter.await_args.args[0] == "test_3"
    assert delete_filter.await_args.args[1].must[0].key == "document_id"
    assert delete_filter.await_args.args[1].must[0].match.value == str(document_id)
    vector_store_module.DocumentChunk.filter.assert_called_once_with(
        document_id=document_id
    )
    chunk_query.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_chunk_vector_removes_qdrant_point_and_chunk(monkeypatch):
    vector_store_module = importlib.import_module("app.services.vector_store")

    chunk_id = uuid4()
    document_id = uuid4()
    kb_id = uuid4()
    chunk_lookup = MagicMock()
    chunk_lookup.values_list = AsyncMock(return_value=[document_id])
    chunk_delete = MagicMock()
    chunk_delete.delete = AsyncMock(return_value=1)
    document_query = MagicMock()
    document_query.values_list = AsyncMock(return_value=[kb_id])
    delete_points = AsyncMock()

    monkeypatch.setattr(
        vector_store_module.DocumentChunk,
        "filter",
        MagicMock(side_effect=[chunk_lookup, chunk_delete]),
    )
    monkeypatch.setattr(
        vector_store_module.Document, "filter", MagicMock(return_value=document_query)
    )
    monkeypatch.setattr(
        vector_store_module, "get_kb_embedding_dimension", AsyncMock(return_value=3)
    )
    monkeypatch.setattr(
        vector_store_module, "_collection_exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(vector_store_module, "_delete_qdrant_points", delete_points)
    monkeypatch.setattr(
        vector_store_module.settings, "QDRANT_COLLECTION_PREFIX", "test"
    )

    assert await VectorStore().delete_chunk_vector(chunk_id) is True
    delete_points.assert_awaited_once_with("test_3", [str(chunk_id)])
    vector_store_module.DocumentChunk.filter.assert_has_calls(
        [
            ((), {"id": chunk_id}),
            ((), {"id": chunk_id}),
        ]
    )
    chunk_delete.delete.assert_awaited_once()
