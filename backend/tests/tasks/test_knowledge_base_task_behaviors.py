from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.models.knowledge_base import DocumentStatus
from app.services.vector_store import EmbeddingRequestTimeoutError
from app.tasks import knowledge_base


class Query:
    def __init__(self, *, first=None, all=None, count=None, ordered=None):
        self._first = first
        self._all = all
        self._count = count
        self._ordered = ordered

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self._ordered

        return resolve().__await__()

    async def first(self):
        return self._first

    async def all(self):
        return self._all

    async def count(self):
        return self._count


def make_document(*, status="pending", metadata=None):
    document = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        name="guide.txt",
        uploaded_by=None,
        uploaded_by_id=None,
        knowledge_base_id=UUID("00000000-0000-0000-0000-000000000002"),
        knowledge_base=SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            team_id=UUID("00000000-0000-0000-0000-000000000003"),
            name="Guides",
            embedding_model_id=None,
            total_chunks=0,
            total_tokens=0,
            save=AsyncMock(),
        ),
        status=status,
        metadata=metadata or {},
        chunk_count=0,
        token_count=0,
        error_message=None,
        processed_at=None,
        save=AsyncMock(),
    )
    return document


def make_chunk(chunk_id, *, status="pending", token_count=3):
    return SimpleNamespace(
        id=chunk_id,
        status=status,
        token_count=token_count,
        error_message=None,
        save=AsyncMock(),
    )


def test_process_document_skips_stale_task(monkeypatch):
    document = make_document(metadata={"task_id": "current-task"})
    monkeypatch.setattr(
        knowledge_base.Document,
        "filter",
        lambda **_kwargs: Query(first=document),
    )

    result = knowledge_base.process_document_task.apply(
        args=(str(document.id),), task_id="old-task"
    ).result

    assert result == {"status": "stale", "document_id": str(document.id)}
    document.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_embed_existing_chunks_completes_and_cleans_task_metadata(monkeypatch):
    document = make_document(
        metadata={
            "task_id": "task-1",
            "embed_progress": {"embedded": 0},
            "task_name": "embed_document_chunks",
            "task_args": ["guide.txt"],
        }
    )
    embedded = make_chunk("embedded", status="embedded", token_count=2)
    pending = make_chunk("pending", token_count=5)

    def document_filter(**kwargs):
        if "id" in kwargs:
            return Query(first=document)
        return Query(all=[document])

    def chunk_filter(**kwargs):
        if kwargs.get("status") == "embedded":
            return Query(count=1)
        return Query(ordered=[embedded, pending])

    class Store:
        def __init__(self, **_kwargs):
            pass

        async def add_chunk_vector(self, kb_id, chunk):
            assert kb_id == document.knowledge_base.id
            assert chunk is pending

    indexed_notification = AsyncMock()
    monkeypatch.setattr(knowledge_base.Document, "filter", document_filter)
    monkeypatch.setattr(knowledge_base.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(knowledge_base, "VectorStore", Store)
    monkeypatch.setattr(
        knowledge_base, "_send_doc_indexed_notification", indexed_notification
    )
    monkeypatch.setattr(knowledge_base, "_index_document_lexically", AsyncMock())

    result = await knowledge_base._embed_existing_document_chunks(
        str(document.id), "task-1"
    )

    assert result == {
        "status": "success",
        "document_id": str(document.id),
        "embedded_count": 2,
        "total_chunks": 2,
    }
    assert pending.status == "embedded"
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.metadata == {"task_id": "task-1"}
    assert document.knowledge_base.total_chunks == 2
    assert document.knowledge_base.total_tokens == 7
    indexed_notification.assert_awaited_once()
    knowledge_base._index_document_lexically.assert_awaited_once_with(document.id)


@pytest.mark.asyncio
async def test_embed_existing_chunks_reports_total_failure_and_cleans_metadata(
    monkeypatch,
):
    document = make_document(
        metadata={"embed_progress": {"embedded": 0}, "task_name": "embed"}
    )
    failed = make_chunk("failed")

    def document_filter(**kwargs):
        return Query(first=document)

    def chunk_filter(**kwargs):
        if kwargs.get("status") == "embedded":
            return Query(count=0)
        return Query(ordered=[failed])

    class Store:
        def __init__(self, **_kwargs):
            pass

        async def add_chunk_vector(self, _kb_id, _chunk):
            raise EmbeddingRequestTimeoutError("timed out")

    failed_notification = AsyncMock()
    monkeypatch.setattr(knowledge_base.Document, "filter", document_filter)
    monkeypatch.setattr(knowledge_base.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(knowledge_base, "VectorStore", Store)
    monkeypatch.setattr(
        knowledge_base, "_send_doc_failed_notification", failed_notification
    )

    result = await knowledge_base._embed_existing_document_chunks(
        str(document.id), None
    )

    assert result["status"] == "error"
    assert result["embedded_count"] == 0
    assert failed.status == "failed"
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {}
    failed_notification.assert_awaited_once()
