import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.services.vector_store import (
    DimensionMismatchError,
    EmbeddingRequestTimeoutError,
)
from app.tasks.knowledge_base import (
    _clear_task_metadata,
    _get_embedding_error,
    _is_finished_task,
    _is_stale_task,
    backfill_lexical_index_task,
    embed_document_chunks_task,
    index_document_lexically_task,
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


def test_task_guards_require_matching_task_ownership_and_terminal_status():
    document = SimpleNamespace(metadata={"task_id": "current"}, status="completed")

    assert _is_stale_task(document, None) is False
    assert _is_stale_task(document, "current") is False
    assert _is_stale_task(document, "other") is True
    assert _is_finished_task(document, None) is False
    assert _is_finished_task(document, "other") is False
    assert _is_finished_task(document, "current") is True

    document.status = "processing"
    assert _is_finished_task(document, "current") is False


def test_embedding_errors_translate_timeout_and_generic_failures(monkeypatch):
    document = SimpleNamespace(uploaded_by_id="user-id")
    translations = []

    def fake_translate(key, **kwargs):
        translations.append((key, kwargs))
        return f"translated:{key}"

    monkeypatch.setattr(f"{MODULE}.t", fake_translate)

    assert _get_embedding_error(document, EmbeddingRequestTimeoutError(), "zh") == (
        "translated:request_timeout"
    )
    assert _get_embedding_error(document, RuntimeError()) == (
        "translated:unknown_error_generic"
    )
    assert translations == [
        ("request_timeout", {"lang": "zh"}),
        ("unknown_error_generic", {"lang": "en"}),
    ]


def test_clear_task_metadata_preserves_unrelated_values():
    document = SimpleNamespace(
        metadata={
            "embed_progress": {"embedded": 1},
            "task_name": "embed_document_chunks_task",
            "task_args": ["document-id"],
            "clean_text": False,
        }
    )

    _clear_task_metadata(document)

    assert document.metadata == {"clean_text": False}


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
        patch(f"{MODULE}._index_document_lexically", new=AsyncMock()) as lexical,
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
    lexical.assert_awaited_once_with(document.id)


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
            f"{MODULE}._process_document",
            new=AsyncMock(return_value={"status": "success"}),
        ) as process,
    ):
        result = reprocess_document_task.run(str(document.id))

    assert result == {"status": "success"}
    assert document.knowledge_base.total_chunks == 0
    assert document.knowledge_base.total_tokens == 0
    assert document.chunk_count == document.token_count == 0
    process.assert_awaited_once_with(str(document.id), None)


def test_url_task_delegates_to_process_task():
    document_id = str(uuid4())
    with patch(
        f"{MODULE}._process_document",
        new=AsyncMock(return_value={"status": "success"}),
    ) as process:
        assert process_url_document_task.run(document_id) == {"status": "success"}
    process.assert_awaited_once_with(document_id, None)


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


def test_rechunk_file_success_persists_progress_and_cleans_metadata():
    document = make_document()
    document.metadata["rechunk_settings"] = {}
    created = [chunk("embedded", 8)]
    vector_store = MagicMock()
    vector_store.delete_document_vectors = AsyncMock(return_value=2)

    async def store_chunks(_document, _chunks, *, kb_id, progress_callback, **_kw):
        assert kb_id == document.knowledge_base.id
        await progress_callback(1, 0, 1)
        return created

    vector_store.store_chunks_with_progress = AsyncMock(side_effect=store_chunks)

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(
            f"{MODULE}.document_processor.extract_text",
            new=AsyncMock(return_value=("text", {})),
        ) as extract,
        patch(f"{MODULE}.document_processor.delete_media_assets") as delete_assets,
        patch("app.services.document_processor.chunk_text", return_value=["chunk"]),
        patch(f"{MODULE}._send_doc_indexed_notification", new=AsyncMock()) as notify,
        patch(f"{MODULE}._index_document_lexically", new=AsyncMock()) as lexical,
    ):
        result = rechunk_document_task.run(str(document.id))

    assert result["status"] == "success"
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.chunk_count == 1
    assert document.token_count == 8
    assert document.metadata == {"task_id": None, "rechunk_settings": {}}
    extract.assert_awaited_once_with(
        document.file_path,
        document.doc_type,
        clean_text=True,
        kb_id=document.knowledge_base.id,
        document_id=document.id,
    )
    delete_assets.assert_called_once_with(document.knowledge_base.id, document.id)
    assert any(
        call.kwargs == {"update_fields": ["metadata"]}
        for call in document.save.await_args_list
    )
    notify.assert_awaited_once()
    lexical.assert_awaited_once_with(document.id)


def test_rechunk_dimension_failure_cleans_task_metadata():
    document = make_document(source="url")
    vector_store = MagicMock()
    vector_store.delete_document_vectors = AsyncMock(return_value=2)
    vector_store.store_chunks_with_progress = AsyncMock(
        side_effect=DimensionMismatchError("wrong dimension")
    )

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(
            f"{MODULE}.document_processor.fetch_url_content",
            new=AsyncMock(return_value=("text", {})),
        ),
        patch("app.services.document_processor.chunk_text", return_value=["chunk"]),
        patch(f"{MODULE}._send_doc_failed_notification", new=AsyncMock()) as notify,
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = rechunk_document_task.run(str(document.id))

    assert result["error_type"] == "dimension_mismatch"
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {"task_id": None}
    assert document.chunk_count == document.token_count == 0
    notify.assert_awaited_once()


def test_reprocess_storage_failure_does_not_persist_counter_reset():
    document = make_document()
    vector_store = MagicMock()
    vector_store.delete_document_vectors = AsyncMock(
        side_effect=RuntimeError("storage unavailable")
    )

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        pytest.raises(RuntimeError, match="storage unavailable"),
    ):
        reprocess_document_task.run(str(document.id))

    assert document.chunk_count == 2
    assert document.token_count == 20
    document.save.assert_not_awaited()
    document.knowledge_base.save.assert_not_awaited()


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
        patch(f"{MODULE}._index_document_lexically", new=AsyncMock()),
    ):
        result = retry_failed_chunks_task.run(str(document.id))

    assert result["status"] == "success"
    assert result["retried_count"] == 0
    assert document.status == DocumentStatus.COMPLETED.value


@pytest.mark.parametrize("provider_fails", [False, True])
def test_retry_failed_chunks_persists_success_or_provider_failure(provider_fails):
    document = make_document(status=DocumentStatus.ERROR.value)
    failed_chunk = chunk("failed", 7)
    completed_document = SimpleNamespace(chunk_count=2, token_count=20)
    vector_store = MagicMock()
    vector_store.add_chunk_vector = AsyncMock(
        side_effect=RuntimeError("provider down") if provider_fails else None
    )

    def filter_chunks(**kwargs):
        if kwargs.get("status") == "failed":
            return Query(items=[failed_chunk])
        if kwargs.get("status") == "embedded":
            return Query(count=1)
        return Query(count=2)

    def filter_documents(**kwargs):
        if "status" in kwargs:
            return Query(items=[completed_document])
        return Query(first=document)

    with (
        patch(f"{MODULE}.Document.filter", side_effect=filter_documents),
        patch(f"{MODULE}.DocumentChunk.filter", side_effect=filter_chunks),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(f"{MODULE}._send_doc_indexed_notification", new=AsyncMock()) as indexed,
        patch(f"{MODULE}._send_doc_failed_notification", new=AsyncMock()) as failed,
        patch(f"{MODULE}._index_document_lexically", new=AsyncMock()) as lexical,
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunks_task.run(str(document.id))

    assert result["status"] == ("error" if provider_fails else "success")
    assert document.status == (
        DocumentStatus.ERROR.value if provider_fails else DocumentStatus.COMPLETED.value
    )
    assert document.metadata == {"task_id": None}
    if provider_fails:
        assert failed_chunk.status == "failed"
        assert failed_chunk.error_message == "provider down"
        failed.assert_awaited_once()
        indexed.assert_not_awaited()
        lexical.assert_not_awaited()
    else:
        assert failed_chunk.status == "embedded"
        assert failed_chunk.error_message is None
        assert document.knowledge_base.total_chunks == 2
        assert document.knowledge_base.total_tokens == 20
        indexed.assert_awaited_once()
        failed.assert_not_awaited()
        lexical.assert_awaited_once_with(document.id)


def test_retry_failed_chunks_handles_progress_persistence_failure():
    document = make_document(status=DocumentStatus.ERROR.value)
    failed_chunk = chunk("failed")
    vector_store = MagicMock()
    vector_store.add_chunk_vector = AsyncMock()

    async def save(**kwargs):
        if kwargs == {"update_fields": ["metadata"]}:
            raise RuntimeError("database unavailable")

    document.save = AsyncMock(side_effect=save)

    def filter_chunks(**kwargs):
        if kwargs.get("status") == "failed":
            return Query(items=[failed_chunk])
        if kwargs.get("status") == "embedded":
            return Query(count=0)
        return Query(count=1)

    with (
        patch(f"{MODULE}.Document.filter", return_value=Query(first=document)),
        patch(f"{MODULE}.DocumentChunk.filter", side_effect=filter_chunks),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunks_task.run(str(document.id))

    assert result["status"] == "error"
    assert result["message"] == "document_processing_failed_generic"
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {"task_id": None}
    assert document.save.await_count == 3


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


@pytest.mark.parametrize("remaining_failed", [0, 1])
def test_retry_one_chunk_persists_full_or_partial_success(remaining_failed):
    document = make_document(status=DocumentStatus.ERROR.value)
    failed_chunk = chunk("failed")
    other_failed = chunk("failed")
    vector_store = MagicMock()
    vector_store.add_chunk_vector = AsyncMock()

    def filter_chunks(**kwargs):
        if "id" in kwargs:
            return Query(first=failed_chunk)
        if kwargs.get("status") == "failed":
            return Query(first=other_failed, count=remaining_failed)
        return Query(count=2)

    def filter_documents(**kwargs):
        if "status" in kwargs:
            return Query(values=[{"sum_chunks": 4, "sum_tokens": 40}])
        return Query(first=document)

    with (
        patch(f"{MODULE}.Document.filter", side_effect=filter_documents),
        patch(f"{MODULE}.DocumentChunk.filter", side_effect=filter_chunks),
        patch(f"{MODULE}.VectorStore", return_value=vector_store),
        patch(f"{MODULE}._send_doc_indexed_notification", new=AsyncMock()) as notify,
        patch(f"{MODULE}._index_document_lexically", new=AsyncMock()) as lexical,
        patch(f"{MODULE}.t", side_effect=lambda key, **_kwargs: key),
    ):
        result = retry_failed_chunk_task.run(str(document.id), str(failed_chunk.id))

    assert result["status"] == ("partial_success" if remaining_failed else "success")
    assert failed_chunk.status == "embedded"
    assert failed_chunk.error_message is None
    assert document.metadata == {"task_id": None}
    if remaining_failed:
        assert document.status == DocumentStatus.ERROR.value
        assert result["remaining_failed"] == 1
        assert document.error_message == "chunks_still_failed_after_retry"
        notify.assert_not_awaited()
    else:
        assert document.status == DocumentStatus.COMPLETED.value
        assert document.knowledge_base.total_chunks == 4
        assert document.knowledge_base.total_tokens == 40
        notify.assert_awaited_once()
        lexical.assert_awaited_once_with(document.id)


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


def test_lexical_index_task_preserves_document_status_contract():
    with patch(f"{MODULE}.index_document", new=AsyncMock(return_value=3)) as index:
        result = index_document_lexically_task.run("doc-id")

    assert result == {"status": "success", "document_id": "doc-id", "indexed": 3}
    index.assert_awaited_once_with("doc-id")


def test_lexical_backfill_resumes_and_reconciles():
    checkpoint = uuid4()
    item = SimpleNamespace(
        id=uuid4(),
        document=SimpleNamespace(),
    )
    query = Query(items=[item], count=4)
    query.limit = MagicMock(return_value=query)
    store = AsyncMock()
    store.__aenter__.return_value = store
    store.backfill_batch.return_value = SimpleNamespace(
        indexed=1, checkpoint=str(item.id)
    )
    store.reconcile.return_value = SimpleNamespace(
        expected=4, actual=4, repaired=0, deleted=0, matches=True
    )

    with (
        patch(f"{MODULE}.DocumentChunk.filter", return_value=query) as chunks,
        patch(f"{MODULE}.chunk_document", return_value={"chunk_id": str(item.id)}),
        patch(f"{MODULE}.LexicalStore", return_value=store),
    ):
        result = backfill_lexical_index_task.run(str(checkpoint), 2, True)

    assert result == {
        "status": "success",
        "scanned": 1,
        "affected": 1,
        "indexed": 1,
        "checkpoint": str(item.id),
        "complete": True,
        "reconciliation": {
            "expected": 4,
            "actual": 4,
            "repaired": 0,
            "deleted": 0,
            "matches": True,
        },
    }
    assert chunks.call_args_list[0].kwargs["id__gt"] == checkpoint
    store.reconcile.assert_awaited_once_with()


def test_lexical_backfill_dispatches_continuation_without_checkpoint():
    items = [SimpleNamespace(id=uuid4(), document=SimpleNamespace()) for _ in range(2)]
    query = Query(items=items)
    query.limit = MagicMock(return_value=query)
    store = AsyncMock()
    store.__aenter__.return_value = store
    store.backfill_batch.return_value = SimpleNamespace(
        indexed=2, checkpoint=str(items[-1].id)
    )

    with (
        patch(f"{MODULE}.DocumentChunk.filter", return_value=query) as chunks,
        patch(f"{MODULE}.chunk_document", return_value={"chunk_id": "chunk"}),
        patch(f"{MODULE}.LexicalStore", return_value=store),
        patch.object(backfill_lexical_index_task, "apply_async") as dispatch,
    ):
        result = backfill_lexical_index_task.run(None, 2, False)

    assert result["complete"] is False
    assert result["scanned"] == 2
    assert "id__gt" not in chunks.call_args.kwargs
    dispatch.assert_called_once_with(
        kwargs={
            "checkpoint": str(items[-1].id),
            "batch_size": 2,
            "reconcile": False,
        }
    )
    store.reconcile.assert_not_awaited()


def test_lexical_backfill_complete_without_reconciliation():
    query = Query(items=[])
    query.limit = MagicMock(return_value=query)
    store = AsyncMock()
    store.__aenter__.return_value = store
    store.backfill_batch.return_value = SimpleNamespace(indexed=0, checkpoint=None)

    with (
        patch(f"{MODULE}.DocumentChunk.filter", return_value=query),
        patch(f"{MODULE}.LexicalStore", return_value=store),
        patch.object(backfill_lexical_index_task, "apply_async") as dispatch,
    ):
        result = backfill_lexical_index_task.run(None, 2, False)

    assert result == {
        "status": "success",
        "scanned": 0,
        "affected": 0,
        "indexed": 0,
        "checkpoint": None,
        "complete": True,
    }
    dispatch.assert_not_called()
    store.reconcile.assert_not_awaited()
