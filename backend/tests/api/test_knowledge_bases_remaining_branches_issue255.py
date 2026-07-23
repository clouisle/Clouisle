from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases as endpoint
from app.models.knowledge_base import DocumentStatus
from app.schemas.knowledge_base import (
    DocumentChunkUpdate,
    DocumentUpdate,
    KnowledgeBaseUpdate,
    RechunkRequest,
)
from app.schemas.response import BusinessError


class Query:
    def __init__(self, *, first=None, items=(), count=0, awaited=None):
        self.first_value = first
        self.items = list(items)
        self.count_value = count
        self.awaited = self.items if awaited is None else awaited
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def exclude(self, **_kwargs):
        return self

    def prefetch_related(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    def order_by(self, *_args):
        return self

    def values_list(self, *_args, **_kwargs):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    async def all(self):
        return self.items

    async def delete(self):
        return None

    async def update(self, **_kwargs):
        return None

    def __await__(self):
        async def resolve():
            return self.awaited

        return resolve().__await__()


def user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


def document(*, status=DocumentStatus.COMPLETED.value, metadata=None, **overrides):
    values = {
        "id": uuid4(),
        "name": "document.txt",
        "status": status,
        "metadata": metadata,
        "file_path": None,
        "chunk_count": 2,
        "token_count": 8,
        "error_message": None,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def assert_error(awaitable, msg_key):
    with pytest.raises(BusinessError) as exc_info:
        await awaitable
    assert exc_info.value.msg_key == msg_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current_user", "kwargs", "expected_filters"),
    [
        (user(superuser=True), {}, []),
        (
            user(),
            {"own_only": True, "search": "docs", "status": ["active"]},
            ["team_id__in", "created_by", "name__icontains", "status__in"],
        ),
    ],
)
async def test_list_knowledge_bases_optional_filters(
    monkeypatch, current_user, kwargs, expected_filters
):
    query = Query()
    monkeypatch.setattr(endpoint.KnowledgeBase, "all", lambda: query)
    monkeypatch.setattr(endpoint.TeamMember, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(endpoint.Model, "filter", lambda **_kwargs: Query())

    result = await endpoint.list_knowledge_bases(current_user=current_user, **kwargs)

    assert result["data"]["items"] == []
    assert [next(iter(item)) for item in query.filters] == expected_filters


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kb_in",
    [
        KnowledgeBaseUpdate(),
        KnowledgeBaseUpdate(rerank_model_id=None, status="processing"),
    ],
)
async def test_update_knowledge_base_omitted_and_nullable_fields(monkeypatch, kb_in):
    kb_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        team=SimpleNamespace(id=uuid4()),
        embedding_model_id=None,
        rerank_model_id=uuid4(),
        save=AsyncMock(),
    )
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        endpoint.KnowledgeBase, "get", lambda **_kwargs: Query(awaited=kb)
    )
    monkeypatch.setattr(endpoint, "kb_with_model_info", AsyncMock(return_value={}))
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.update_knowledge_base(
        kb_id=kb_id,
        kb_in=kb_in,
        request=SimpleNamespace(),
        current_user=user(),
    )

    assert getattr(kb, "status", None) is None
    if "rerank_model_id" in kb_in.model_fields_set:
        assert kb.rerank_model_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected_filters"),
    [({}, []), ({"search": "a", "status": ["pending"], "doc_type": ["txt"]}, 3)],
)
async def test_list_documents_optional_filters(monkeypatch, kwargs, expected_filters):
    query = Query()
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: query)

    result = await endpoint.list_documents(kb_id=uuid4(), current_user=user(), **kwargs)

    assert result["data"]["items"] == []
    assert len(query.filters) == (
        expected_filters if isinstance(expected_filters, int) else 0
    )


@pytest.mark.asyncio
async def test_update_document_without_name_skips_save(monkeypatch):
    doc_id = uuid4()
    doc = document()
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(endpoint.Document, "get", lambda **_kwargs: Query(awaited=doc))
    monkeypatch.setattr(endpoint, "serialize_document", AsyncMock(return_value={}))
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.update_document(
        kb_id=uuid4(),
        doc_id=doc_id,
        doc_in=DocumentUpdate(),
        request=SimpleNamespace(),
        current_user=user(),
    )

    doc.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [DocumentStatus.COMPLETED.value, DocumentStatus.PENDING.value]
)
async def test_delete_document_without_task_or_file(monkeypatch, status):
    kb = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        document_count=1,
        total_chunks=2,
        total_tokens=8,
        save=AsyncMock(),
    )
    doc = document(status=status, metadata={})
    vector_store = SimpleNamespace(delete_document_vectors=AsyncMock())
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(endpoint, "VectorStore", lambda: vector_store)
    monkeypatch.setattr(endpoint.asyncio, "to_thread", AsyncMock())
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.delete_document(
        kb_id=kb.id,
        doc_id=doc.id,
        request=SimpleNamespace(),
        current_user=user(),
    )

    vector_store.delete_document_vectors.assert_awaited_once_with(doc.id)
    doc.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_document_media_returns_existing_asset(monkeypatch, tmp_path):
    doc = document()
    asset = tmp_path / "image.png"
    asset.write_bytes(b"png")
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(
        endpoint.document_processor,
        "get_media_asset_path",
        lambda *_args: asset,
    )

    response = await endpoint.get_document_media(uuid4(), doc.id, "image.png", user())

    assert response.path == asset
    assert response.media_type == "image/png"


@pytest.mark.asyncio
async def test_preview_chunks_rejects_missing_document(monkeypatch):
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query())

    await assert_error(
        endpoint.preview_document_chunks(
            kb_id=uuid4(),
            doc_id=uuid4(),
            preview_in=SimpleNamespace(),
            current_user=user(),
        ),
        "document_not_found",
    )


@pytest.mark.asyncio
async def test_reprocess_without_existing_task(monkeypatch):
    doc = document(metadata={})
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(endpoint.Document, "get", lambda **_kwargs: Query(awaited=doc))
    monkeypatch.setattr(endpoint, "_dispatch_document_task", AsyncMock())
    monkeypatch.setattr(endpoint, "serialize_document", AsyncMock(return_value={}))
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.reprocess_document(
        kb_id=uuid4(),
        doc_id=doc.id,
        request=SimpleNamespace(),
        current_user=user(),
    )

    assert doc.status == DocumentStatus.PENDING.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "doc_status", "chunk", "count", "msg_key"),
    [
        (
            "retry_failed_chunks",
            DocumentStatus.COMPLETED.value,
            None,
            1,
            "document_not_in_error_state",
        ),
        (
            "retry_failed_chunks",
            DocumentStatus.ERROR.value,
            None,
            0,
            "no_failed_chunks",
        ),
        (
            "retry_failed_chunk",
            DocumentStatus.PROCESSING.value,
            None,
            0,
            "document_processing",
        ),
        (
            "retry_failed_chunk",
            DocumentStatus.COMPLETED.value,
            None,
            0,
            "chunk_not_found",
        ),
        (
            "retry_failed_chunk",
            DocumentStatus.COMPLETED.value,
            SimpleNamespace(status="embedded"),
            0,
            "chunk_not_failed",
        ),
    ],
)
async def test_retry_guards(
    monkeypatch, function_name, doc_status, chunk, count, msg_key
):
    doc = document(status=doc_status)
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(
        endpoint.DocumentChunk,
        "filter",
        lambda **_kwargs: Query(first=chunk, count=count),
    )
    function = getattr(endpoint, function_name)
    kwargs = {
        "kb_id": uuid4(),
        "doc_id": doc.id,
        "request": SimpleNamespace(),
        "current_user": user(),
    }
    if function_name == "retry_failed_chunk":
        kwargs["chunk_id"] = uuid4()

    await assert_error(function(**kwargs), msg_key)


@pytest.mark.asyncio
async def test_delete_chunk_rejects_missing_chunk(monkeypatch):
    doc = document()
    monkeypatch.setattr(
        endpoint, "check_kb_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(endpoint.DocumentChunk, "filter", lambda **_kwargs: Query())

    await assert_error(
        endpoint.delete_document_chunk(
            kb_id=uuid4(),
            doc_id=doc.id,
            chunk_id=uuid4(),
            request=SimpleNamespace(),
            current_user=user(),
        ),
        "chunk_not_found",
    )


@pytest.mark.asyncio
async def test_create_chunk_appends_when_after_index_omitted(monkeypatch):
    kb = SimpleNamespace(
        id=uuid4(),
        embedding_model_id=None,
        team_id=None,
        total_chunks=0,
        total_tokens=0,
        save=AsyncMock(),
    )
    doc = document(chunk_count=0, token_count=0)
    chunk = SimpleNamespace(id=uuid4(), chunk_index=0)
    vector_store = SimpleNamespace(add_chunk_vector=AsyncMock())
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(endpoint.DocumentChunk, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(endpoint.DocumentChunk, "create", AsyncMock(return_value=chunk))
    monkeypatch.setattr(endpoint, "VectorStore", lambda **_kwargs: vector_store)
    monkeypatch.setattr(endpoint, "serialize_chunk", AsyncMock(return_value={}))
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.create_document_chunk(
        kb_id=kb.id,
        doc_id=doc.id,
        chunk_in=DocumentChunkUpdate(content="four"),
        request=SimpleNamespace(),
        current_user=user(),
    )

    assert doc.chunk_count == 1
    vector_store.add_chunk_vector.assert_awaited_once()


@pytest.mark.asyncio
async def test_rechunk_guards_processing_and_initializes_metadata(monkeypatch):
    processing = document(status=DocumentStatus.PROCESSING.value)
    completed = document(status=DocumentStatus.COMPLETED.value, metadata=None)
    documents = iter([processing, completed])
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        endpoint.Document,
        "filter",
        lambda **_kwargs: Query(first=next(documents)),
    )
    monkeypatch.setattr(
        endpoint.Document, "get", lambda **_kwargs: Query(awaited=completed)
    )
    monkeypatch.setattr(endpoint, "_dispatch_document_task", AsyncMock())
    monkeypatch.setattr(endpoint, "serialize_document", AsyncMock(return_value={}))
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())
    rechunk_in = RechunkRequest(chunk_size=200, chunk_overlap=20)
    kwargs = {
        "kb_id": uuid4(),
        "doc_id": processing.id,
        "rechunk_in": rechunk_in,
        "request": SimpleNamespace(),
        "current_user": user(),
    }

    await assert_error(endpoint.rechunk_document(**kwargs), "document_processing")
    kwargs["doc_id"] = completed.id
    await endpoint.rechunk_document(**kwargs)

    assert completed.metadata["rechunk_settings"] == {
        "chunk_size": 200,
        "chunk_overlap": 20,
        "separator": None,
    }
