from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.models.knowledge_base import DocumentStatus
from app.schemas.response import BusinessError
from app.services.vector_store import DimensionMismatchError


class Query:
    def __init__(self, value=None, items=None, count=0):
        self.value = value
        self.items = items or []
        self.count_value = count
        self.deleted = False

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def first(self):
        return self.value

    async def count(self):
        return self.count_value

    async def delete(self):
        self.deleted = True

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@pytest.mark.asyncio
async def test_delete_document_cleans_task_vectors_media_file_and_stats(monkeypatch):
    from app.core.celery import celery_app

    kb_id, doc_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="kb",
        document_count=1,
        total_chunks=2,
        total_tokens=3,
        save=AsyncMock(),
    )
    doc = SimpleNamespace(
        id=doc_id,
        name="guide.pdf",
        status=DocumentStatus.PENDING.value,
        metadata={"task_id": "old-task"},
        file_path="kb/guide.pdf",
        chunk_count=4,
        token_count=5,
        delete=AsyncMock(),
    )
    vectors = SimpleNamespace(delete_document_vectors=AsyncMock())

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(
        celery_app.control, "revoke", Mock(side_effect=RuntimeError("down"))
    )
    monkeypatch.setattr(knowledge_bases, "VectorStore", lambda: vectors)
    monkeypatch.setattr(
        knowledge_bases.document_processor, "delete_media_assets", Mock()
    )
    monkeypatch.setattr(knowledge_bases.document_processor, "delete_file", AsyncMock())
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())

    result = await knowledge_bases.delete_document(
        kb_id, doc_id, SimpleNamespace(), SimpleNamespace()
    )

    celery_app.control.revoke.assert_called_once_with("old-task", terminate=True)
    vectors.delete_document_vectors.assert_awaited_once_with(doc_id)
    knowledge_bases.document_processor.delete_media_assets.assert_called_once_with(
        kb_id, doc_id
    )
    knowledge_bases.document_processor.delete_file.assert_awaited_once_with(
        "kb/guide.pdf"
    )
    assert (kb.document_count, kb.total_chunks, kb.total_tokens) == (0, 0, 0)
    doc.delete.assert_awaited_once()
    assert result["data"] == {"id": str(doc_id)}


@pytest.mark.asyncio
async def test_preview_chunks_uses_file_and_url_sources(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(file_path="guide.txt", source_url=None, doc_type="txt")
    extract = AsyncMock(return_value=("file text", {}))
    fetch = AsyncMock(return_value=("url text", {}))
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(knowledge_bases.document_processor, "extract_text", extract)
    monkeypatch.setattr(knowledge_bases.document_processor, "fetch_url_content", fetch)
    monkeypatch.setattr(
        import_module("app.services.document_processor"),
        "chunk_text",
        lambda text, **_kwargs: [
            {
                "chunk_index": 0,
                "content": text,
                "token_count": 2,
                "char_count": len(text),
            }
        ],
    )
    preview = SimpleNamespace(
        clean_text=True, separator="\n", chunk_size=100, chunk_overlap=10
    )

    result = await knowledge_bases.preview_document_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        preview_in=preview,
        current_user=SimpleNamespace(),
    )
    assert result["data"].total_chunks == 1
    extract.assert_awaited_once()

    doc.file_path = None
    doc.source_url = "https://example.test"
    result = await knowledge_bases.preview_document_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        preview_in=preview,
        current_user=SimpleNamespace(),
    )
    assert result["data"].chunks[0].content == "url text"
    fetch.assert_awaited_once_with("https://example.test", clean_text=True)


@pytest.mark.asyncio
async def test_batch_processing_validation_and_dispatch_failure(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="doc",
        status=DocumentStatus.PROCESSING.value,
        metadata={},
        error_message=None,
        chunk_count=0,
        token_count=0,
        save=AsyncMock(),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document_with_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            request=SimpleNamespace(),
            process_request=SimpleNamespace(chunks=[]),
            current_user=SimpleNamespace(),
        )
    assert exc.value.msg_key == "document_is_processing"

    doc.status = DocumentStatus.PENDING.value
    chunks = Query()
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk, "filter", lambda **_kwargs: chunks
    )
    monkeypatch.setattr(
        knowledge_bases,
        "_dispatch_document_task",
        AsyncMock(side_effect=OSError("broker")),
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document_with_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            request=SimpleNamespace(),
            process_request=SimpleNamespace(chunks=[]),
            current_user=SimpleNamespace(),
        )
    assert exc.value.msg_key == "document_process_failed"
    assert chunks.deleted is True
    assert doc.status == DocumentStatus.ERROR.value
    assert doc.error_message == "document_process_failed"


@pytest.mark.asyncio
async def test_chunk_create_and_update_cover_vector_paths(monkeypatch):
    kb_id, doc_id, chunk_id = uuid4(), uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        embedding_model_id=uuid4(),
        team_id=uuid4(),
        total_chunks=1,
        total_tokens=4,
        save=AsyncMock(),
    )
    doc = SimpleNamespace(chunk_count=1, token_count=4, save=AsyncMock())
    existing = SimpleNamespace(chunk_index=1, save=AsyncMock())
    created = SimpleNamespace(
        id=chunk_id,
        content="eight chars",
        chunk_index=1,
        token_count=2,
        save=AsyncMock(),
    )
    vectors = SimpleNamespace(
        add_chunk_vector=AsyncMock(), update_chunk_vector=AsyncMock()
    )

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )

    def chunk_filter(**kwargs):
        return Query(created if "id" in kwargs else None, [existing])

    monkeypatch.setattr(knowledge_bases.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk, "create", AsyncMock(return_value=created)
    )
    monkeypatch.setattr(knowledge_bases, "VectorStore", lambda **_kwargs: vectors)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases, "serialize_chunk", AsyncMock(return_value={"id": chunk_id})
    )

    result = await knowledge_bases.create_document_chunk(
        kb_id=kb_id,
        doc_id=doc_id,
        chunk_in=SimpleNamespace(content="eight chars"),
        request=SimpleNamespace(),
        after_index=0,
        current_user=SimpleNamespace(),
    )
    assert existing.chunk_index == 2
    vectors.add_chunk_vector.assert_awaited_once_with(kb_id, created)
    assert result["data"] == {"id": chunk_id}

    vectors.update_chunk_vector.side_effect = DimensionMismatchError("changed")
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.update_document_chunk(
            kb_id=kb_id,
            doc_id=doc_id,
            chunk_id=chunk_id,
            chunk_in=SimpleNamespace(content="four"),
            request=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )
    assert exc.value.msg_key == "kb_embedding_dimension_mismatch"
    assert created.token_count == 1


@pytest.mark.asyncio
async def test_reprocess_and_rechunk_lifecycle_dispatch(monkeypatch):
    from app.core.celery import celery_app

    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="doc",
        status=DocumentStatus.PENDING.value,
        metadata={"task_id": "old-task"},
        error_message="old",
        save=AsyncMock(),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(knowledge_bases.Document, "get", lambda **_kwargs: Query(doc))
    monkeypatch.setattr(celery_app.control, "revoke", Mock())
    dispatch = AsyncMock(return_value="task")
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases, "serialize_document", AsyncMock(return_value={"id": doc_id})
    )

    await knowledge_bases.reprocess_document(
        kb_id, doc_id, SimpleNamespace(), SimpleNamespace()
    )
    celery_app.control.revoke.assert_called_once_with("old-task", terminate=True)
    assert doc.status == DocumentStatus.PENDING.value

    await knowledge_bases.rechunk_document(
        kb_id=kb_id,
        doc_id=doc_id,
        rechunk_in=SimpleNamespace(chunk_size=80, chunk_overlap=8, separator=None),
        request=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )
    assert doc.metadata["rechunk_settings"] == {
        "chunk_size": 80,
        "chunk_overlap": 8,
        "separator": None,
    }
    assert dispatch.await_count == 2


@pytest.mark.asyncio
async def test_search_without_models_or_overrides(monkeypatch):
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        knowledge_bases,
        "check_kb_access",
        AsyncMock(
            return_value=SimpleNamespace(
                embedding_model_id=None, rerank_model_id=None, team_id=None
            )
        ),
    )
    monkeypatch.setattr(
        knowledge_bases,
        "VectorStore",
        lambda **kwargs: SimpleNamespace(search=search, constructor_kwargs=kwargs),
    )
    search_in = SimpleNamespace(
        query="missing",
        search_mode="hybrid",
        top_k=4,
        score_threshold=0.1,
        filter_doc_ids=None,
        model_fields_set=set(),
    )

    result = await knowledge_bases.search_knowledge_base(
        uuid4(), search_in, SimpleNamespace()
    )

    assert result["data"]["total"] == 0
    assert search.await_args.kwargs["rerank_overrides"] is None
