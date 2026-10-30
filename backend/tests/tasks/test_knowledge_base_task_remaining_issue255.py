import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.tasks import knowledge_base


class Query:
    def __init__(self, *, first=None, count=0):
        self.first_value = first
        self.count_value = count

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value


@pytest.fixture
def document():
    kb = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        name="Knowledge",
        settings={},
        embedding_model_id=None,
        total_chunks=0,
        total_tokens=0,
        save=AsyncMock(),
    )
    return SimpleNamespace(
        id=uuid4(),
        name="Guide",
        knowledge_base=kb,
        knowledge_base_id=kb.id,
        uploaded_by=None,
        uploaded_by_id=None,
        status=DocumentStatus.PENDING.value,
        metadata={"task_name": "queued"},
        file_path="guide.txt",
        source_url=None,
        doc_type="txt",
        chunk_count=0,
        token_count=0,
        error_message=None,
        processed_at=None,
        save=AsyncMock(),
    )


def test_get_chunk_error_uses_provider_detail_for_internal_sentinel(
    monkeypatch, document
):
    chunk = SimpleNamespace(
        error_message="document_process_failed",
        metadata={"error_detail": "provider rejected the request"},
    )
    monkeypatch.setattr(knowledge_base, "t", lambda key, **_kwargs: key)

    assert (
        knowledge_base._get_chunk_error(document, chunk)
        == "provider rejected the request"
    )


def test_process_document_all_failed_records_progress_and_error(monkeypatch, document):
    chunks = [
        SimpleNamespace(status="failed", token_count=2),
        SimpleNamespace(status="failed", token_count=3),
    ]

    class Store:
        async def store_chunks_with_progress(
            self, _document, _chunks, *, kb_id, progress_callback, **_kwargs
        ):
            assert kb_id == document.knowledge_base.id
            await progress_callback(0, 2, 2)
            return chunks

    failed_notification = AsyncMock()
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=document)
    )
    monkeypatch.setattr(
        knowledge_base.DocumentChunk, "filter", lambda **_kwargs: Query()
    )
    monkeypatch.setattr(
        knowledge_base.document_processor,
        "delete_media_assets",
        AsyncMock(),
    )
    monkeypatch.setattr(
        knowledge_base.document_processor,
        "extract_text",
        AsyncMock(return_value=("text", {})),
    )
    monkeypatch.setattr(knowledge_base, "VectorStore", lambda **_kwargs: Store())
    monkeypatch.setattr(
        knowledge_base, "_send_doc_failed_notification", failed_notification
    )
    monkeypatch.setattr(knowledge_base, "t", lambda key, **_kwargs: key)

    result = knowledge_base.process_document_task.run(str(document.id))

    assert result["status"] == "error"
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {}
    assert (document.chunk_count, document.token_count) == (2, 5)
    assert {"update_fields": ["metadata"]} in [
        call.kwargs for call in document.save.await_args_list
    ]
    failed_notification.assert_awaited_once()


@pytest.mark.parametrize(
    ("metadata", "status", "expected"),
    [
        ({"task_id": "newer"}, DocumentStatus.PENDING.value, "stale"),
    ],
)
def test_rechunk_stops_for_invalid_task_state(
    monkeypatch, document, metadata, status, expected
):
    document.metadata = metadata
    document.status = status
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=document)
    )
    knowledge_base.rechunk_document_task.push_request(id="current")
    try:
        result = knowledge_base.rechunk_document_task.run(str(document.id))
    finally:
        knowledge_base.rechunk_document_task.pop_request()

    assert result["status"] == expected
    assert result["document_id"] == str(document.id)
    document.save.assert_not_awaited()


def test_rechunk_returns_staged_error_and_preserves_document(monkeypatch, document):
    document.metadata = {"task_id": "current", "rechunk_settings": {}}
    expected = {
        "status": "error",
        "document_id": str(document.id),
        "error_type": "processing_failed",
        "preserved_previous_version": True,
    }
    staged = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=document)
    )
    monkeypatch.setattr(
        "app.services.kb_rechunk_staging.rechunk_document_staged", staged
    )
    knowledge_base.rechunk_document_task.push_request(id="current")
    try:
        result = knowledge_base.rechunk_document_task.run(str(document.id))
    finally:
        knowledge_base.rechunk_document_task.pop_request()

    assert result == expected
    document.save.assert_not_awaited()
    staged.assert_awaited_once()


def test_retry_single_chunk_guards_and_creates_event_loop(monkeypatch, document):
    chunk_id = uuid4()
    document.metadata = {"task_id": "current"}
    document.status = DocumentStatus.COMPLETED.value
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(first=document)
    )
    lexical_index = AsyncMock()
    monkeypatch.setattr(knowledge_base, "_index_document_lexically", lexical_index)
    chunk_filter = Mock()
    monkeypatch.setattr(knowledge_base.DocumentChunk, "filter", chunk_filter)
    loop = Mock()
    loop.run_until_complete.side_effect = lambda coroutine: asyncio.run(coroutine)
    policy = Mock()
    policy.get_event_loop.side_effect = RuntimeError
    monkeypatch.setattr(asyncio, "get_event_loop_policy", Mock(return_value=policy))
    monkeypatch.setattr(asyncio, "new_event_loop", Mock(return_value=loop))
    set_event_loop = Mock()
    monkeypatch.setattr(asyncio, "set_event_loop", set_event_loop)
    knowledge_base.retry_failed_chunk_task.push_request(id="current")
    try:
        result = knowledge_base.retry_failed_chunk_task.run(
            str(document.id), str(chunk_id)
        )
    finally:
        knowledge_base.retry_failed_chunk_task.pop_request()

    assert result["status"] == "already_finished"
    chunk_filter.assert_not_called()
    lexical_index.assert_awaited_once_with(document.id)
    set_event_loop.assert_called_once_with(loop)
    loop.run_until_complete.assert_called_once()


def test_get_worker_loop_replaces_closed_policy_loop(monkeypatch):
    closed_loop = Mock()
    closed_loop.is_closed.return_value = True
    policy = Mock()
    policy.get_event_loop.return_value = closed_loop
    new_loop = Mock()

    monkeypatch.setattr(asyncio, "get_event_loop_policy", Mock(return_value=policy))
    monkeypatch.setattr(asyncio, "new_event_loop", Mock(return_value=new_loop))
    set_event_loop = Mock()
    monkeypatch.setattr(asyncio, "set_event_loop", set_event_loop)

    assert knowledge_base._get_worker_loop() is new_loop
    set_event_loop.assert_called_once_with(new_loop)


def test_get_chunk_error_preserves_non_sentinel_message(monkeypatch, document):
    chunk = SimpleNamespace(
        error_message="provider rejected the request",
        metadata={"error_detail": "less specific detail"},
    )
    monkeypatch.setattr(knowledge_base, "t", lambda key, **_kwargs: key)

    assert (
        knowledge_base._get_chunk_error(document, chunk)
        == "provider rejected the request"
    )
