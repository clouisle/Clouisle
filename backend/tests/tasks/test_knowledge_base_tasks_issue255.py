import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.tasks import knowledge_base


class Query:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


@pytest.mark.asyncio
async def test_indexed_notification_uses_team_locale_and_swallows_failure(monkeypatch):
    document = SimpleNamespace(
        id=uuid4(),
        uploaded_by_id=None,
        name="guide.pdf",
        knowledge_base_id=uuid4(),
    )
    send = AsyncMock(side_effect=RuntimeError("notification unavailable"))
    monkeypatch.setattr(
        knowledge_base, "get_default_language", AsyncMock(return_value="zh")
    )
    monkeypatch.setattr(knowledge_base.AutoNotificationService, "send_to_team", send)

    await knowledge_base._send_doc_indexed_notification(
        document, "Handbook", uuid4(), 3, 42
    )

    assert send.await_args.kwargs["title"]
    assert send.await_args.kwargs["content"]


def test_reprocess_missing_document_returns_localized_error(monkeypatch):
    document_id = uuid4()
    monkeypatch.setattr(knowledge_base.Document, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(
        knowledge_base, "get_default_language", AsyncMock(return_value="en")
    )

    result = knowledge_base.reprocess_document_task.run(str(document_id))

    assert result["status"] == "error"
    assert result["message"]


def test_reprocess_resets_stats_then_delegates_processing(monkeypatch):
    document_id = uuid4()
    kb = SimpleNamespace(
        total_chunks=2,
        total_tokens=5,
        save=AsyncMock(),
    )
    document = SimpleNamespace(
        id=document_id,
        knowledge_base=kb,
        chunk_count=7,
        token_count=11,
        metadata={},
        status=DocumentStatus.PENDING.value,
        save=AsyncMock(),
    )
    vector_store = SimpleNamespace(delete_document_vectors=AsyncMock(return_value=4))
    process = Mock(return_value={"status": "success"})
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(document)
    )
    monkeypatch.setattr(knowledge_base, "VectorStore", lambda: vector_store)
    monkeypatch.setattr(knowledge_base, "process_document_task", process)

    result = knowledge_base.reprocess_document_task.run(str(document_id))

    assert result == {"status": "success"}
    assert (kb.total_chunks, kb.total_tokens) == (0, 0)
    assert (document.chunk_count, document.token_count) == (0, 0)
    process.assert_called_once_with(str(document_id))


@pytest.mark.parametrize(
    ("metadata", "status", "expected"),
    [
        ({"task_id": "newer"}, DocumentStatus.PENDING.value, "stale"),
        ({"task_id": "current"}, DocumentStatus.COMPLETED.value, "already_finished"),
    ],
)
def test_retry_failed_chunks_stops_for_invalid_task_state(
    monkeypatch, metadata, status, expected
):
    document_id = uuid4()
    document = SimpleNamespace(id=document_id, metadata=metadata, status=status)
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(document)
    )
    lexical_index = AsyncMock()
    monkeypatch.setattr(knowledge_base, "_index_document_lexically", lexical_index)
    knowledge_base.retry_failed_chunks_task.push_request(id="current")
    try:
        result = knowledge_base.retry_failed_chunks_task.run(str(document_id))
    finally:
        knowledge_base.retry_failed_chunks_task.pop_request()

    assert result["status"] == expected
    assert result["document_id"] == str(document_id)
    if expected == "already_finished":
        lexical_index.assert_awaited_once_with(document_id)
    else:
        lexical_index.assert_not_awaited()


def test_embed_task_creates_event_loop_when_none_exists(monkeypatch):
    loop = Mock()
    loop.run_until_complete.return_value = {"status": "success"}
    monkeypatch.setattr(asyncio, "get_event_loop", Mock(side_effect=RuntimeError))
    monkeypatch.setattr(asyncio, "new_event_loop", Mock(return_value=loop))
    set_loop = Mock()
    monkeypatch.setattr(asyncio, "set_event_loop", set_loop)
    knowledge_base.embed_document_chunks_task.push_request(id="task-id")
    try:
        result = knowledge_base.embed_document_chunks_task.run(str(uuid4()))
    finally:
        knowledge_base.embed_document_chunks_task.pop_request()

    assert result == {"status": "success"}
    set_loop.assert_called_once_with(loop)
    loop.run_until_complete.assert_called_once()
    loop.run_until_complete.call_args.args[0].close()
