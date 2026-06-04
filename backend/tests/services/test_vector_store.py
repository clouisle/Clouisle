import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
