from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentStatus
from app.tasks import knowledge_base


class Query:
    def __init__(self, first=None):
        self.value = first

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


@pytest.fixture
def document():
    return SimpleNamespace(
        id=uuid4(),
        metadata={"task_id": "current"},
        status=DocumentStatus.COMPLETED.value,
        save=AsyncMock(),
    )


def run_with_task_id(task, *args):
    task.push_request(id="current")
    try:
        return task.run(*args)
    finally:
        task.pop_request()


def test_clear_task_metadata_accepts_empty_metadata(document):
    document.metadata = None

    knowledge_base._clear_task_metadata(document)

    assert document.metadata is None


def test_process_document_skips_already_finished_task(monkeypatch, document):
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(document)
    )
    lexical_index = AsyncMock()
    monkeypatch.setattr(knowledge_base, "_index_document_lexically", lexical_index)

    result = run_with_task_id(
        knowledge_base.process_document_task,
        str(document.id),
    )

    assert result == {
        "status": "already_finished",
        "document_id": str(document.id),
        "document_status": DocumentStatus.COMPLETED.value,
    }
    lexical_index.assert_awaited_once_with(document.id)


@pytest.mark.parametrize(
    ("metadata", "status", "expected"),
    [
        ({"task_id": "newer"}, DocumentStatus.PENDING.value, "stale"),
        ({"task_id": "current"}, DocumentStatus.ERROR.value, "already_finished"),
    ],
)
def test_reprocess_document_skips_invalid_task_state(
    monkeypatch, document, metadata, status, expected
):
    document.metadata = metadata
    document.status = status
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(document)
    )

    result = run_with_task_id(
        knowledge_base.reprocess_document_task,
        str(document.id),
    )

    assert result["status"] == expected
    document.save.assert_not_awaited()


@pytest.mark.parametrize(
    "task",
    [
        knowledge_base.rechunk_document_task,
        knowledge_base.retry_failed_chunks_task,
        knowledge_base.retry_failed_chunk_task,
    ],
)
def test_document_tasks_report_missing_document(monkeypatch, task):
    document_id = str(uuid4())
    monkeypatch.setattr(knowledge_base.Document, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(
        knowledge_base, "get_default_language", AsyncMock(return_value="en")
    )
    monkeypatch.setattr(
        knowledge_base, "t", lambda key, **kwargs: f"{key}:{kwargs['lang']}"
    )
    args = (
        (document_id, str(uuid4()))
        if task is knowledge_base.retry_failed_chunk_task
        else (document_id,)
    )

    result = task.run(*args)

    assert result == {"status": "error", "message": "document_not_found:en"}


@pytest.mark.asyncio
async def test_embed_existing_chunks_skips_already_finished(monkeypatch, document):
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(document)
    )
    lexical_index = AsyncMock()
    monkeypatch.setattr(knowledge_base, "_index_document_lexically", lexical_index)

    result = await knowledge_base._embed_existing_document_chunks(
        str(document.id), "current"
    )

    assert result["status"] == "already_finished"
    lexical_index.assert_awaited_once_with(document.id)


def test_retry_single_chunk_skips_stale_task(monkeypatch, document):
    document.metadata = {"task_id": "newer"}
    document.status = DocumentStatus.PENDING.value
    monkeypatch.setattr(
        knowledge_base.Document, "filter", lambda **_kwargs: Query(document)
    )

    result = run_with_task_id(
        knowledge_base.retry_failed_chunk_task,
        str(document.id),
        str(uuid4()),
    )

    assert result == {"status": "stale", "document_id": str(document.id)}
