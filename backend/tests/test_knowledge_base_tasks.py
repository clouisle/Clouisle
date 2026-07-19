import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.services.vector_store import DimensionMismatchError
from app.tasks.knowledge_base import (
    embed_document_chunks_task,
    process_document_task,
    process_url_document_task,
    rechunk_document_task,
    reprocess_document_task,
    retry_failed_chunk_task,
    retry_failed_chunks_task,
)

MODULE = "app.tasks.knowledge_base"


@pytest.fixture(autouse=True)
def celery_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()
    asyncio.set_event_loop(None)


class Query:
    def __init__(self, *, first=None, count=0, items=None, values=None):
        self._first = first
        self._count = count
        self._items = items or []
        self._values = values or []

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def annotate(self, **_kwargs):
        return self

    async def first(self):
        return self._first

    async def count(self):
        return self._count

    async def all(self):
        return self._items

    async def values(self, *_args):
        return self._values

    def __await__(self):
        async def result():
            return self._items

        return result().__await__()


@contextmanager
def task_id(task, value):
    original = task.request
    task.push_request(id=value)
    try:
        yield
    finally:
        task.pop_request()
        assert task.request is original


def make_document(*, source="file", status=DocumentStatus.PENDING.value):
    kb = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        name="KB",
        settings={},
        embedding_model_id=uuid4(),
        total_chunks=10,
        total_tokens=100,
        save=AsyncMock(),
    )
    document = SimpleNamespace(
        id=uuid4(),
        knowledge_base=kb,
        knowledge_base_id=kb.id,
        uploaded_by=SimpleNamespace(locale="zh"),
        uploaded_by_id=uuid4(),
        name="guide.txt",
        doc_type="txt",
        file_path="/tmp/guide.txt" if source == "file" else None,
        source_url="https://example.com" if source == "url" else None,
        metadata={"task_id": None, "task_name": "process", "task_args": []},
        status=status,
        error_message=None,
        chunk_count=2,
        token_count=20,
        processed_at=None,
        save=AsyncMock(),
    )
    return document


def chunk(status="embedded", tokens=5):
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        token_count=tokens,
        error_message="old error",
        save=AsyncMock(),
    )


def test_process_document_reports_missing_document():
    with (
        patch(f"{MODULE}.Document.filter", return_value=Query()),
        patch(f"{MODULE}.get_default_language", new=AsyncMock(return_value="en")),
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = process_document_task.run(str(uuid4()))

    assert result == {"status": "error", "message": "document_not_found"}


def test_process_document_ignores_stale_task_before_processing():
    document = make_document()
    document.metadata["task_id"] = "current-task"

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        task_id(process_document_task, "stale-task"),
    ):
        result = process_document_task.run(str(document.id))

    assert result == {"status": "stale", "document_id": str(document.id)}
    document.save.assert_not_awaited()


def test_process_document_embeds_existing_chunks_without_extracting():
    document = make_document()
    expected = {"status": "success", "embedded_count": 2}
    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", return_value=Query(count=2)),
        patch(
            f"{MODULE}._embed_existing_document_chunks",
            new=AsyncMock(return_value=expected),
        ) as embed,
        task_id(process_document_task, "task-1"),
    ):
        result = process_document_task.run(str(document.id))

    assert result == expected
    embed.assert_awaited_once_with(str(document.id), "task-1")


def test_process_document_happy_path_updates_document_and_kb():
    document = make_document()
    created = [chunk(tokens=7), chunk(tokens=11)]
    vector_store = MagicMock()
    vector_store.store_chunks_with_progress = AsyncMock(return_value=created)

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", return_value=Query(count=0)),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(
            f"{MODULE}.document_processor.extract_text",
            new=AsyncMock(return_value=("text", {"author": "Ada"})),
        ),
        patch(f"{MODULE}.document_processor.delete_media_assets") as delete_assets,
        patch(
            "app.services.document_processor.chunk_text", return_value=["a", "b"]
        ) as split,
        patch(f"{MODULE}._send_doc_indexed_notification", new=AsyncMock()) as notify,
    ):
        result = process_document_task.run(str(document.id))

    assert result == {
        "status": "success",
        "document_id": str(document.id),
        "chunk_count": 2,
        "token_count": 18,
    }
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.metadata == {"task_id": None, "author": "Ada"}
    assert document.knowledge_base.total_chunks == 12
    assert document.knowledge_base.total_tokens == 118
    delete_assets.assert_called_once_with(document.knowledge_base.id, document.id)
    split.assert_called_once_with(
        "text", chunk_size=1000, chunk_overlap=100, separators=None
    )
    notify.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (DimensionMismatchError("wrong dimension"), "dimension_mismatch"),
        (RuntimeError("boom"), None),
    ],
)
def test_process_document_handles_processing_errors(error, error_type):
    document = make_document(source="none")
    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", return_value=Query(count=0)),
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
        patch(f"{MODULE}._send_doc_failed_notification", new=AsyncMock()) as notify,
        patch(f"{MODULE}.document_processor.fetch_url_content", side_effect=error),
    ):
        document.source_url = "https://example.com"
        result = process_document_task.run(str(document.id))

    assert result["status"] == "error"
    assert result.get("error_type") == error_type
    assert document.status == DocumentStatus.ERROR.value
    assert "task_name" not in document.metadata
    notify.assert_awaited_once()


def test_reprocess_clamps_stats_and_starts_processing():
    document = make_document()
    document.chunk_count = 20
    document.token_count = 200
    vector_store = MagicMock()
    vector_store.delete_document_vectors = AsyncMock(return_value=3)

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(
            f"{MODULE}.process_document_task", return_value={"status": "success"}
        ) as process,
    ):
        result = reprocess_document_task.run(str(document.id))

    assert result == {"status": "success"}
    assert document.knowledge_base.total_chunks == 0
    assert document.knowledge_base.total_tokens == 0
    assert document.chunk_count == document.token_count == 0
    process.assert_called_once_with(str(document.id))


def test_url_task_delegates_to_process_task():
    with patch(
        f"{MODULE}.process_document_task", return_value={"status": "success"}
    ) as process:
        assert process_url_document_task.run("doc-id") == {"status": "success"}
    process.assert_called_once_with("doc-id")


def test_rechunk_uses_requested_settings_and_reports_partial_failure():
    document = make_document(source="url")
    document.metadata["rechunk_settings"] = {
        "chunk_size": 50,
        "chunk_overlap": 5,
        "separator": "|",
        "clean_text": False,
    }
    vector_store = MagicMock()
    vector_store.delete_document_vectors = AsyncMock(return_value=2)
    vector_store.store_chunks_with_progress = AsyncMock(
        return_value=[chunk("embedded", 4), chunk("failed", 6)]
    )

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(
            f"{MODULE}.document_processor.fetch_url_content",
            new=AsyncMock(return_value=("text", {})),
        ) as fetch,
        patch(
            "app.services.document_processor.chunk_text", return_value=["a", "b"]
        ) as split,
        patch(f"{MODULE}._send_doc_indexed_notification", new=AsyncMock()),
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = rechunk_document_task.run(str(document.id))

    assert result["status"] == "success"
    assert result["chunk_size"] == 50
    assert document.status == DocumentStatus.ERROR.value
    fetch.assert_awaited_once_with(document.source_url, clean_text=False)
    split.assert_called_once_with(
        "text", chunk_size=50, chunk_overlap=5, separators=["|"]
    )


def test_embed_entrypoint_passes_celery_task_id():
    expected = {"status": "success"}
    with (
        patch(
            f"{MODULE}._embed_existing_document_chunks",
            new=AsyncMock(return_value=expected),
        ) as embed,
        task_id(embed_document_chunks_task, "embed-1"),
    ):
        assert embed_document_chunks_task.run("doc-id") == expected
    embed.assert_awaited_once_with("doc-id", "embed-1")


def test_retry_failed_chunks_succeeds_when_nothing_needs_retry():
    document = make_document(status=DocumentStatus.ERROR.value)

    def filter_chunks(**kwargs):
        return Query(items=[]) if kwargs.get("status") == "failed" else Query()

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", side_effect=filter_chunks),
        patch(f"{MODULE}.get_default_language", new=AsyncMock(return_value="en")),
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunks_task.run(str(document.id))

    assert result["status"] == "success"
    assert result["retried_count"] == 0
    assert document.status == DocumentStatus.COMPLETED.value


def test_retry_one_chunk_rejects_missing_or_cross_document_chunk():
    document = make_document()
    chunk_id = uuid4()

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", return_value=Query()) as filter_chunks,
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunk_task.run(str(document.id), str(chunk_id))

    assert result["status"] == "error"
    assert result["message"] == "chunk_not_found"
    filter_chunks.assert_called_once_with(id=chunk_id, document_id=document.id)


def test_retry_one_chunk_rejects_non_failed_chunk():
    document = make_document()
    existing_chunk = chunk("embedded")

    def filter_chunks(**kwargs):
        return Query(first=existing_chunk if "id" in kwargs else None)

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", side_effect=filter_chunks),
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunk_task.run(str(document.id), str(existing_chunk.id))

    assert result["status"] == "error"
    assert result["message"] == "chunk_not_failed"


def test_retry_one_chunk_failure_restores_error_state():
    document = make_document(status=DocumentStatus.ERROR.value)
    failed_chunk = chunk("failed")
    vector_store = MagicMock()
    vector_store.add_chunk_vector = AsyncMock(side_effect=RuntimeError("provider down"))

    def filter_chunks(**kwargs):
        if "id" in kwargs:
            return Query(first=failed_chunk)
        return Query(count=2 if "status" not in kwargs else 1)

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", side_effect=filter_chunks),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(f"{MODULE}._send_doc_failed_notification", new=AsyncMock()) as notify,
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunk_task.run(str(document.id), str(failed_chunk.id))

    assert result["status"] == "error"
    assert failed_chunk.status == "failed"
    assert failed_chunk.error_message == "provider down"
    assert document.status == DocumentStatus.ERROR.value
    notify.assert_awaited_once()
