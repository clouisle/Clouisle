import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.services.upload_gateway import UploadGatewayError
from app.services.vector_store import DimensionMismatchError
from app.tasks import knowledge_base as kb_tasks


class Query:
    def __init__(self, *, first=None, rows=None, count=0):
        self.first_value = first
        self.rows = [] if rows is None else rows
        self.count_value = count

    def prefetch_related(self, *args):
        return self

    async def first(self):
        return self.first_value

    def order_by(self, *args):
        return self._rows()

    async def _rows(self):
        return self.rows

    async def count(self):
        return self.count_value

    async def all(self):
        return self.rows

    def annotate(self, **kwargs):
        return self

    async def values(self, *args):
        return self.rows


def make_document(*, status="pending", metadata=None, uploaded=True):
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
        name="Document",
        knowledge_base=kb,
        knowledge_base_id=kb.id,
        uploaded_by_id=uuid4() if uploaded else None,
        uploaded_by=SimpleNamespace(locale="zh") if uploaded else None,
        status=status,
        metadata={} if metadata is None else metadata,
        file_path="document.txt",
        source_url=None,
        doc_type="txt",
        chunk_count=0,
        token_count=0,
        error_message=None,
        processed_at=None,
        save=AsyncMock(),
    )


def make_chunk(*, status="pending", tokens=4):
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        token_count=tokens,
        error_message=None,
        save=AsyncMock(),
    )


def test_task_identity_guards_and_metadata_cleanup():
    document = make_document(
        status=DocumentStatus.COMPLETED.value,
        metadata={
            "task_id": "current",
            "embed_progress": {},
            "task_name": "process",
            "task_args": [],
            "keep": True,
        },
    )

    assert kb_tasks._is_stale_task(document, "old") is True
    assert kb_tasks._is_stale_task(document, None) is False
    assert kb_tasks._is_finished_task(document, "current") is True
    assert kb_tasks._is_finished_task(document, "old") is False

    kb_tasks._clear_task_metadata(document)
    assert document.metadata == {"task_id": "current", "keep": True}


@pytest.mark.asyncio
async def test_notifications_select_user_or_team_and_ignore_delivery_errors():
    user_document = make_document()
    team_document = make_document(uploaded=False)

    with (
        patch.object(
            kb_tasks.AutoNotificationService, "send_to_user", new=AsyncMock()
        ) as send_user,
        patch.object(
            kb_tasks.AutoNotificationService, "send_to_team", new=AsyncMock()
        ) as send_team,
        patch.object(
            kb_tasks, "get_default_language", new=AsyncMock(return_value="en")
        ),
        patch.object(kb_tasks, "t", side_effect=lambda key, **kwargs: key),
    ):
        await kb_tasks._send_doc_indexed_notification(
            user_document, "Knowledge", user_document.knowledge_base.team_id, 2, 8, "zh"
        )
        await kb_tasks._send_doc_failed_notification(
            team_document,
            "Knowledge",
            team_document.knowledge_base.team_id,
            "x" * 600,
        )
        send_user.side_effect = RuntimeError("notification unavailable")
        await kb_tasks._send_doc_failed_notification(
            user_document, "Knowledge", user_document.knowledge_base.team_id, "failure"
        )

    send_user.assert_awaited()
    send_team.assert_awaited_once()
    assert len(send_team.await_args.kwargs["data"]["error"]) == 500


def test_process_document_returns_localized_not_found_error():
    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query()),
        patch.object(
            kb_tasks, "get_default_language", new=AsyncMock(return_value="zh")
        ),
        patch.object(
            kb_tasks,
            "t",
            side_effect=lambda key, **kwargs: f"{key}:{kwargs['lang']}",
        ),
    ):
        result = kb_tasks.process_document_task.run(str(uuid4()))

    assert result == {"status": "error", "message": "document_not_found:zh"}


def test_process_document_retries_transient_upload_gateway_failure():
    gateway_error = UploadGatewayError("api unavailable")
    retry_signal = RuntimeError("retry queued")

    def raise_gateway(coroutine):
        coroutine.close()
        raise gateway_error

    with (
        patch.object(kb_tasks, "_run_async", side_effect=raise_gateway),
        patch.object(
            kb_tasks.process_document_task, "retry", side_effect=retry_signal
        ) as retry,
        pytest.raises(RuntimeError, match="retry queued"),
    ):
        kb_tasks.process_document_task.run(str(uuid4()))

    retry.assert_called_once_with(exc=gateway_error)


def test_reprocess_document_retries_transient_upload_gateway_failure():
    gateway_error = UploadGatewayError("api unavailable")
    retry_signal = RuntimeError("retry queued")

    def raise_gateway(coroutine):
        coroutine.close()
        raise gateway_error

    with (
        patch.object(kb_tasks, "_run_async", side_effect=raise_gateway),
        patch.object(
            kb_tasks.reprocess_document_task, "retry", side_effect=retry_signal
        ) as retry,
        pytest.raises(RuntimeError, match="retry queued"),
    ):
        kb_tasks.reprocess_document_task.run(str(uuid4()))

    retry.assert_called_once_with(exc=gateway_error)


@pytest.mark.asyncio
async def test_upload_gateway_retry_exhaustion_marks_document_failed():
    document = make_document(
        status=DocumentStatus.PROCESSING.value,
        metadata={
            "task_id": "current",
            "embed_progress": {"embedded": 1},
            "task_name": "process_document_task",
            "task_args": ["document"],
            "keep": True,
        },
    )
    notify = AsyncMock()
    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(
            kb_tasks,
            "_get_generic_processing_error",
            return_value="gateway unavailable",
        ),
        patch.object(kb_tasks, "_send_doc_failed_notification", new=notify),
    ):
        result = await kb_tasks._finish_upload_gateway_retry_exhaustion(
            str(document.id),
            "current",
            UploadGatewayError("api unavailable"),
        )

    assert result == {
        "status": "error",
        "document_id": str(document.id),
        "message": "gateway unavailable",
    }
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {"task_id": "current", "keep": True}
    document.save.assert_awaited_once()
    notify.assert_awaited_once_with(
        document=document,
        kb_name=document.knowledge_base.name,
        team_id=document.knowledge_base.team_id,
        error="gateway unavailable",
        user_locale="zh",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "metadata", "task_id", "expected_status"),
    [
        (DocumentStatus.PROCESSING.value, {"task_id": "new"}, "old", "stale"),
        (
            DocumentStatus.ERROR.value,
            {"task_id": "current"},
            "current",
            "already_finished",
        ),
    ],
)
async def test_upload_gateway_retry_exhaustion_preserves_newer_or_finished_task(
    status, metadata, task_id, expected_status
):
    document = make_document(status=status, metadata=metadata)
    notify = AsyncMock()
    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(kb_tasks, "_send_doc_failed_notification", new=notify),
    ):
        result = await kb_tasks._finish_upload_gateway_retry_exhaustion(
            str(document.id),
            task_id,
            UploadGatewayError("api unavailable"),
        )

    assert result["status"] == expected_status
    document.save.assert_not_awaited()
    notify.assert_not_awaited()


def test_upload_gateway_retry_exhaustion_does_not_queue_another_retry():
    error = UploadGatewayError("api unavailable")
    task = SimpleNamespace(
        request=SimpleNamespace(retries=3),
        max_retries=3,
        retry=MagicMock(),
    )
    finish = AsyncMock(return_value={"status": "error"})

    with (
        patch.object(kb_tasks, "_finish_upload_gateway_retry_exhaustion", new=finish),
        patch.object(
            kb_tasks, "_run_async", side_effect=lambda coro: asyncio.run(coro)
        ),
    ):
        result = kb_tasks._retry_upload_gateway_or_mark_document_failed(
            task,
            "document-id",
            "task-id",
            error,
        )

    assert result == {"status": "error"}
    finish.assert_awaited_once_with("document-id", "task-id", error)
    task.retry.assert_not_called()


def test_rechunk_document_retries_transient_upload_gateway_failure():
    gateway_error = UploadGatewayError("api unavailable")
    retry_signal = RuntimeError("retry queued")

    def raise_gateway(coroutine):
        coroutine.close()
        raise gateway_error

    with (
        patch.object(kb_tasks, "_run_async", side_effect=raise_gateway),
        patch.object(
            kb_tasks.rechunk_document_task, "retry", side_effect=retry_signal
        ) as retry,
        pytest.raises(RuntimeError, match="retry queued"),
    ):
        kb_tasks.rechunk_document_task.run(str(uuid4()))

    retry.assert_called_once_with(exc=gateway_error)


def test_process_document_success_updates_document_and_kb():
    document = make_document(metadata={"clean_text": False, "task_name": "queued"})
    chunks = [make_chunk(tokens=3), make_chunk(tokens=5)]
    for chunk in chunks:
        chunk.status = "embedded"
    vector_store = MagicMock()
    vector_store.store_chunks_with_progress = AsyncMock(return_value=chunks)

    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(kb_tasks.DocumentChunk, "filter", return_value=Query(count=0)),
        patch.object(
            kb_tasks.document_processor,
            "delete_media_assets",
            new=AsyncMock(),
        ),
        patch.object(
            kb_tasks.document_processor,
            "extract_text",
            new=AsyncMock(return_value=("text", {"source": "file"})),
        ) as extract_text,
        patch("app.services.document_processor.chunk_text", return_value=["a", "b"]),
        patch.object(kb_tasks, "VectorStore", return_value=vector_store),
        patch.object(
            kb_tasks, "_index_document_lexically", new=AsyncMock()
        ) as lexical_index,
        patch.object(
            kb_tasks, "_send_doc_indexed_notification", new=AsyncMock()
        ) as notify,
    ):
        result = kb_tasks.process_document_task.run(str(document.id))

    assert result == {
        "status": "success",
        "document_id": str(document.id),
        "chunk_count": 2,
        "token_count": 8,
    }
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.metadata == {"clean_text": False, "source": "file"}
    assert (document.chunk_count, document.token_count) == (2, 8)
    assert (
        document.knowledge_base.total_chunks,
        document.knowledge_base.total_tokens,
    ) == (2, 8)
    assert extract_text.await_args.kwargs["clean_text"] is False
    notify.assert_awaited_once()
    lexical_index.assert_awaited_once_with(document.id)


def test_process_document_generic_error_notifies_and_cleans_metadata():
    document = make_document(metadata={"task_name": "queued", "embed_progress": {}})

    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(kb_tasks.DocumentChunk, "filter", return_value=Query(count=0)),
        patch.object(
            kb_tasks.document_processor,
            "extract_text",
            new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
        ),
        patch.object(
            kb_tasks,
            "t",
            side_effect=lambda key, **kwargs: f"{key}:{kwargs['lang']}",
        ),
        patch.object(
            kb_tasks, "_send_doc_failed_notification", new=AsyncMock()
        ) as notify,
    ):
        result = kb_tasks.process_document_task.run(str(document.id))

    assert result == {
        "status": "error",
        "document_id": str(document.id),
        "message": "document_processing_failed_generic:zh",
    }
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {}
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_indexed_notification_for_uploader_uses_user_locale():
    document = make_document()

    with (
        patch.object(
            kb_tasks.AutoNotificationService, "send_to_user", new=AsyncMock()
        ) as send_user,
        patch.object(
            kb_tasks.AutoNotificationService, "send_to_team", new=AsyncMock()
        ) as send_team,
        patch.object(
            kb_tasks,
            "t",
            side_effect=lambda key, **kwargs: f"{key}:{kwargs['lang']}",
        ),
    ):
        await kb_tasks._send_doc_indexed_notification(
            document, "Knowledge", document.knowledge_base.team_id, 2, 8, "zh"
        )

    send_team.assert_not_awaited()
    send_user.assert_awaited_once()
    assert send_user.await_args.kwargs["title"] == "notify_kb_doc_indexed_title:zh"
    assert send_user.await_args.kwargs["content"] == "notify_kb_doc_indexed_content:zh"


def test_process_document_dimension_mismatch_is_specific_and_cleans_metadata():
    document = make_document(metadata={"task_name": "queued", "embed_progress": {}})

    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(kb_tasks.DocumentChunk, "filter", return_value=Query(count=0)),
        patch.object(
            kb_tasks.document_processor,
            "delete_media_assets",
            new=AsyncMock(),
        ),
        patch.object(
            kb_tasks.document_processor,
            "extract_text",
            new=AsyncMock(side_effect=DimensionMismatchError("wrong dimensions")),
        ),
        patch.object(kb_tasks, "t", side_effect=lambda key, **kwargs: key),
        patch.object(
            kb_tasks, "_send_doc_failed_notification", new=AsyncMock()
        ) as notify,
    ):
        result = kb_tasks.process_document_task.run(str(document.id))

    assert result["status"] == "error"
    assert result["error_type"] == "dimension_mismatch"
    assert document.status == DocumentStatus.ERROR.value
    assert document.error_message == "kb_embedding_dimension_mismatch"
    assert document.metadata == {}
    notify.assert_awaited_once()


def test_reprocess_clamps_stats_and_delegates_to_processing():
    document = make_document()
    document.chunk_count = 7
    document.token_count = 70
    document.knowledge_base.total_chunks = 3
    document.knowledge_base.total_tokens = 30
    vector_store = MagicMock()
    vector_store.delete_document_vectors = AsyncMock(return_value=7)

    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(kb_tasks, "VectorStore", return_value=vector_store),
        patch.object(
            kb_tasks,
            "_process_document",
            new=AsyncMock(return_value={"status": "success"}),
        ) as process,
    ):
        result = kb_tasks.reprocess_document_task.run(str(document.id))

    assert result == {"status": "success"}
    assert (
        document.knowledge_base.total_chunks,
        document.knowledge_base.total_tokens,
    ) == (0, 0)
    assert (document.chunk_count, document.token_count) == (0, 0)
    process.assert_awaited_once_with(str(document.id), None)


@pytest.mark.asyncio
async def test_embed_existing_chunks_skips_stale_task_before_vector_work():
    document = make_document(metadata={"task_id": "new"})

    with (
        patch.object(kb_tasks.Document, "filter", return_value=Query(first=document)),
        patch.object(kb_tasks.DocumentChunk, "filter") as chunks_filter,
    ):
        result = await kb_tasks._embed_existing_document_chunks(str(document.id), "old")

    assert result == {"status": "stale", "document_id": str(document.id)}
    chunks_filter.assert_not_called()


@pytest.mark.asyncio
async def test_embed_existing_chunks_handles_partial_failure_and_refreshes_stats():
    document = make_document(metadata={"embed_progress": {}, "task_name": "queued"})
    good = make_chunk(status="embedded", tokens=3)
    bad = make_chunk(tokens=5)
    completed_doc = SimpleNamespace(chunk_count=1, token_count=3)
    vector_store = MagicMock()
    vector_store.add_chunk_vector = AsyncMock(
        side_effect=RuntimeError("provider failed")
    )

    def document_filter(**kwargs):
        if "id" in kwargs:
            return Query(first=document)
        return Query(rows=[completed_doc])

    def chunk_filter(**kwargs):
        if kwargs.get("status") == "embedded":
            return Query(count=1)
        return Query(rows=[good, bad])

    with (
        patch.object(kb_tasks.Document, "filter", side_effect=document_filter),
        patch.object(kb_tasks.DocumentChunk, "filter", side_effect=chunk_filter),
        patch.object(kb_tasks, "VectorStore", return_value=vector_store),
        patch.object(
            kb_tasks, "_send_doc_failed_notification", new=AsyncMock()
        ) as notify,
        patch.object(kb_tasks, "t", side_effect=lambda key, **kwargs: key),
    ):
        result = await kb_tasks._embed_existing_document_chunks(str(document.id), None)

    assert result["status"] == "error"
    assert result["embedded_count"] == 1
    assert result["failed_count"] == 1
    assert bad.status == "failed"
    assert document.status == DocumentStatus.ERROR.value
    assert document.metadata == {}
    assert (
        document.knowledge_base.total_chunks,
        document.knowledge_base.total_tokens,
    ) == (1, 3)
    notify.assert_awaited_once()


def test_process_url_and_embed_wrappers_forward_arguments():
    document_id = str(uuid4())
    with patch.object(
        kb_tasks, "_process_document", new=AsyncMock(return_value={"status": "success"})
    ) as process:
        assert kb_tasks.process_url_document_task.run(document_id) == {
            "status": "success"
        }
    process.assert_awaited_once_with(document_id, None)

    with patch.object(
        kb_tasks,
        "_embed_existing_document_chunks",
        new=AsyncMock(return_value={"status": "success"}),
    ) as embed:
        assert kb_tasks.embed_document_chunks_task.run(document_id) == {
            "status": "success"
        }
    embed.assert_awaited_once_with(document_id, None)
