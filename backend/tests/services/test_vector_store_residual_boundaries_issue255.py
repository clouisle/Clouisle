import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.services.usage_tracker import QuotaExceededError
from app.services.vector_store import VectorStore

vector_store = importlib.import_module("app.services.vector_store")
KB_ID = UUID("00000000-0000-0000-0000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.mark.asyncio
async def test_embedding_boundaries_use_team_model_and_preserve_provider_errors(
    monkeypatch,
):
    manager = SimpleNamespace(
        team_embed=AsyncMock(side_effect=[[[0.1, 0.2]], [[0.3, 0.4]]])
    )
    monkeypatch.setattr(vector_store, "_get_model_manager", lambda: manager)
    store = VectorStore(embedding_model_id="embedding-model", team_id="team-id")

    assert await store.embed_texts([]) == []
    assert await store.embed_texts(["document"]) == [[0.1, 0.2]]
    assert await store.embed_query("query") == [0.3, 0.4]

    manager.team_embed.side_effect = QuotaExceededError(
        "quota exceeded", quota_type="daily_token"
    )
    with pytest.raises(QuotaExceededError):
        await store.embed_texts(["document"])

    manager.team_embed.side_effect = RuntimeError("provider unavailable")
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await store.embed_query("query")


@pytest.mark.asyncio
async def test_store_chunks_with_progress_reports_success_and_failure(monkeypatch):
    chunks = []

    async def create_chunk(**values):
        chunk = SimpleNamespace(
            id=f"chunk-{len(chunks)}",
            status=values["status"],
            error_message=None,
            save=AsyncMock(),
        )
        chunks.append(chunk)
        return chunk

    monkeypatch.setattr(vector_store.DocumentChunk, "create", create_chunk)
    ensure_dimension = AsyncMock()
    monkeypatch.setattr(vector_store, "_ensure_kb_dimension", ensure_dimension)

    store = VectorStore()
    store.embed_texts = AsyncMock(
        side_effect=[[[0.1, 0.2]], RuntimeError("embedding failed")]
    )
    store._store_embedding = AsyncMock()
    progress = AsyncMock()
    document = SimpleNamespace(id=DOCUMENT_ID, knowledge_base_id=KB_ID)

    result = await store.store_chunks_with_progress(
        document,
        [
            {"content": "good", "chunk_index": 0},
            {"content": "bad", "chunk_index": 1},
        ],
        progress_callback=progress,
    )

    assert result == chunks
    assert [chunk.status for chunk in chunks] == ["embedded", "failed"]
    assert chunks[1].error_message == "document_process_failed"
    ensure_dimension.assert_awaited_once_with(KB_ID, 2)
    store._store_embedding.assert_awaited_once()
    assert [call.args for call in progress.await_args_list] == [(1, 0, 2), (1, 1, 2)]

    assert await store.store_chunks_with_progress(document, []) == []


class Query:
    def __init__(self, values):
        self.values = values

    async def values_list(self, *_args, **_kwargs):
        return self.values


@pytest.mark.asyncio
async def test_update_chunk_vector_resolves_optional_kb_and_handles_failure(
    monkeypatch,
):
    chunk = SimpleNamespace(
        id="chunk-id",
        document_id=DOCUMENT_ID,
        content="content",
        embedding_id=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        vector_store.Document,
        "filter",
        lambda **kwargs: Query([KB_ID] if kwargs == {"id": DOCUMENT_ID} else []),
    )
    ensure_dimension = AsyncMock()
    monkeypatch.setattr(vector_store, "_ensure_kb_dimension", ensure_dimension)

    store = VectorStore()
    store.embed_query = AsyncMock(return_value=[0.1, 0.2])
    store._store_embedding = AsyncMock()

    assert await store.update_chunk_vector(chunk) is True
    ensure_dimension.assert_awaited_once_with(KB_ID, 2)
    assert store._store_embedding.await_args.kwargs["payload"]["kb_id"] == str(KB_ID)

    store.embed_query.side_effect = RuntimeError("model unavailable")
    assert await store.update_chunk_vector(chunk, KB_ID) is False


@pytest.mark.asyncio
async def test_embedding_stats_cover_database_and_qdrant_boundaries(monkeypatch):
    connection = SimpleNamespace(execute_query=AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(
        vector_store.Tortoise, "get_connection", Mock(return_value=connection)
    )
    get_dimension = AsyncMock(return_value=None)
    monkeypatch.setattr(vector_store, "get_kb_embedding_dimension", get_dimension)
    collection_exists = AsyncMock(return_value=False)
    monkeypatch.setattr(vector_store, "_collection_exists", collection_exists)

    store = VectorStore()
    assert await store.get_embedding_stats() == {
        "total": 0,
        "with_embedding": 0,
        "without_embedding": 0,
    }
    assert connection.execute_query.await_args.args[1] == []
    get_dimension.assert_not_awaited()

    connection.execute_query.return_value = (None, [{"total": "4"}])
    assert await store.get_embedding_stats(KB_ID) == {
        "total": 4,
        "with_embedding": 0,
        "without_embedding": 4,
    }
    assert connection.execute_query.await_args.args[1] == [str(KB_ID)]
    collection_exists.assert_not_awaited()

    get_dimension.return_value = 3
    assert (await store.get_embedding_stats(KB_ID))["dimension"] == 3

    collection_exists.return_value = True
    client = SimpleNamespace(count=AsyncMock(return_value=SimpleNamespace(count=2)))
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        vector_store, "_build_qdrant_filter", Mock(return_value="kb-filter")
    )

    assert await store.get_embedding_stats(KB_ID) == {
        "total": 4,
        "with_embedding": 2,
        "without_embedding": 2,
        "dimension": 3,
    }
    client.count.assert_awaited_once_with(
        collection_name="kb_dim_3", count_filter="kb-filter", exact=True
    )
