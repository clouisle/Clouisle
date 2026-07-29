from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.tasks import knowledge_base


class Query:
    def __init__(self, *, first=None, rows=None, count=0, error=None):
        self.first_value = first
        self.rows = rows or []
        self.count_value = count
        self.error = error

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    def order_by(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            if self.error:
                raise self.error
            return self.rows

        return resolve().__await__()

    async def count(self):
        return self.count_value

    async def all(self):
        return self.rows


class Record(SimpleNamespace):
    async def save(self, **kwargs):
        self.saved.append(kwargs)


def document(*, task_id="task-1"):
    kb = Record(
        id=uuid4(),
        team_id=uuid4(),
        embedding_model_id=uuid4(),
        name="Knowledge base",
        total_chunks=0,
        total_tokens=0,
        saved=[],
    )
    return Record(
        id=uuid4(),
        knowledge_base=kb,
        knowledge_base_id=kb.id,
        uploaded_by=SimpleNamespace(locale="en"),
        uploaded_by_id=uuid4(),
        name="guide.pdf",
        status=DocumentStatus.PROCESSING.value,
        metadata={
            "task_id": task_id,
            "task_name": "embed_document_chunks_task",
            "task_args": ["unused"],
            "embed_progress": {"embedded": 0, "failed": 0, "total": 0},
        },
        error_message=None,
        chunk_count=0,
        token_count=0,
        processed_at=None,
        saved=[],
    )


def chunk(index, *, status="pending", tokens=4):
    return Record(
        id=uuid4(),
        chunk_index=index,
        status=status,
        token_count=tokens,
        error_message=None,
        saved=[],
    )


@pytest.fixture(autouse=True)
def isolate_dependencies(monkeypatch):
    monkeypatch.setattr(knowledge_base, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        knowledge_base, "get_default_language", AsyncMock(return_value="en")
    )
    monkeypatch.setattr(knowledge_base, "_send_doc_indexed_notification", AsyncMock())
    monkeypatch.setattr(knowledge_base, "_send_doc_failed_notification", AsyncMock())
    monkeypatch.setattr(knowledge_base, "_index_document_lexically", AsyncMock())


@pytest.mark.asyncio
async def test_embed_existing_chunks_returns_localized_error_when_document_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=None)
    )

    result = await knowledge_base._embed_existing_document_chunks(str(uuid4()), None)

    assert result == {"status": "error", "message": "document_not_found"}
    knowledge_base.get_default_language.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_existing_chunks_skips_stale_task_without_loading_chunks(
    monkeypatch,
):
    doc = document(task_id="new-task")
    chunk_filter = AsyncMock()
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(knowledge_base.DocumentChunk, "filter", chunk_filter)

    result = await knowledge_base._embed_existing_document_chunks(
        str(doc.id), "old-task"
    )

    assert result == {"status": "stale", "document_id": str(doc.id)}
    chunk_filter.assert_not_called()
    assert doc.saved == []


@pytest.mark.asyncio
async def test_embed_existing_chunks_marks_document_error_when_no_chunks(monkeypatch):
    doc = document()
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_base.DocumentChunk, "filter", lambda **_kwargs: Query()
    )

    result = await knowledge_base._embed_existing_document_chunks(str(doc.id), "task-1")

    assert result == {
        "status": "success",
        "message": "no_chunks_to_embed",
        "embedded_count": 0,
    }
    assert doc.status == DocumentStatus.ERROR.value
    assert doc.error_message == "no_chunks_to_embed"
    assert doc.saved == [{}]


@pytest.mark.asyncio
async def test_embed_existing_chunks_completes_pending_chunks_and_cleans_task_metadata(
    monkeypatch,
):
    doc = document()
    chunks = [chunk(0, status="embedded", tokens=3), chunk(1, tokens=5)]
    add_chunk_vector = AsyncMock()

    def document_filter(**kwargs):
        if kwargs == {"id": doc.id}:
            return Query(first=doc)
        assert kwargs == {
            "knowledge_base_id": doc.knowledge_base.id,
            "status": DocumentStatus.COMPLETED.value,
        }
        return Query(rows=[doc])

    def chunk_filter(**kwargs):
        assert kwargs["document_id"] == doc.id
        if kwargs.get("status") == "embedded":
            return Query(count=1)
        return Query(rows=chunks)

    monkeypatch.setattr(knowledge_base.Document, "filter", document_filter)
    monkeypatch.setattr(knowledge_base.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        knowledge_base,
        "VectorStore",
        lambda **_kwargs: SimpleNamespace(add_chunk_vector=add_chunk_vector),
    )

    result = await knowledge_base._embed_existing_document_chunks(str(doc.id), "task-1")

    assert result == {
        "status": "success",
        "document_id": str(doc.id),
        "embedded_count": 2,
        "total_chunks": 2,
    }
    add_chunk_vector.assert_awaited_once_with(doc.knowledge_base.id, chunks[1])
    assert chunks[1].status == "embedded"
    assert chunks[1].saved == [{"update_fields": ["status", "error_message"]}]
    assert doc.status == DocumentStatus.COMPLETED.value
    assert (doc.chunk_count, doc.token_count) == (2, 8)
    assert doc.processed_at is not None
    assert doc.metadata == {"task_id": "task-1"}
    assert (doc.knowledge_base.total_chunks, doc.knowledge_base.total_tokens) == (2, 8)
    knowledge_base._send_doc_indexed_notification.assert_awaited_once()
    knowledge_base._index_document_lexically.assert_awaited_once_with(doc.id)


@pytest.mark.asyncio
async def test_embed_existing_chunks_persists_partial_provider_failure(monkeypatch):
    doc = document()
    chunks = [chunk(0), chunk(1, tokens=6)]
    add_chunk_vector = AsyncMock(
        side_effect=[None, RuntimeError("provider unavailable")]
    )

    def document_filter(**kwargs):
        if kwargs == {"id": doc.id}:
            return Query(first=doc)
        return Query(rows=[])

    def chunk_filter(**kwargs):
        return Query(count=0) if "status" in kwargs else Query(rows=chunks)

    monkeypatch.setattr(knowledge_base.Document, "filter", document_filter)
    monkeypatch.setattr(knowledge_base.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        knowledge_base,
        "VectorStore",
        lambda **_kwargs: SimpleNamespace(add_chunk_vector=add_chunk_vector),
    )

    result = await knowledge_base._embed_existing_document_chunks(str(doc.id), "task-1")

    assert result["status"] == "error"
    assert result["embedded_count"] == result["failed_count"] == 1
    assert [item.status for item in chunks] == ["embedded", "failed"]
    assert doc.status == DocumentStatus.ERROR.value
    assert (doc.chunk_count, doc.token_count) == (2, 10)
    assert doc.metadata == {"task_id": "task-1"}
    knowledge_base._send_doc_failed_notification.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["provider", "chunk_query"])
async def test_embed_existing_chunks_persists_error_and_cleans_task_metadata_on_failure(
    monkeypatch, failure_point
):
    doc = document()
    pending = chunk(0)

    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_base.DocumentChunk,
        "filter",
        lambda **kwargs: (
            Query(error=RuntimeError("database unavailable"))
            if failure_point == "chunk_query"
            else Query(rows=[pending])
            if "status" not in kwargs
            else Query(count=0)
        ),
    )
    add_chunk_vector = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    monkeypatch.setattr(
        knowledge_base,
        "VectorStore",
        lambda **_kwargs: SimpleNamespace(add_chunk_vector=add_chunk_vector),
    )

    result = await knowledge_base._embed_existing_document_chunks(str(doc.id), "task-1")

    assert result["status"] == "error"
    assert doc.status == DocumentStatus.ERROR.value
    assert doc.metadata == {"task_id": "task-1"}
    assert doc.saved[-1] == {}
    knowledge_base._send_doc_failed_notification.assert_awaited_once()

    if failure_point == "provider":
        assert pending.status == "failed"
        assert pending.error_message == "provider unavailable"
        assert pending.saved == [{"update_fields": ["status", "error_message"]}]
        assert result["embedded_count"] == 0
    else:
        add_chunk_vector.assert_not_awaited()
        assert result["message"] == "document_processing_failed_generic"
