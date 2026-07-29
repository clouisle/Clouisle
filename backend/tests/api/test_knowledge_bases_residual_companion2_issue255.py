from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases as kb_endpoint
from app.models.knowledge_base import DocumentStatus
from app.schemas.knowledge_base import (
    DocumentChunkUpdate,
    ProcessRequest,
    SearchRequest,
)
from app.schemas.response import BusinessError


class Query:
    def __init__(self, *, first=None, items=(), count=0):
        self.first_value = first
        self.items = list(items)
        self.count_value = count
        self.filters = []
        self.updated = None

    def prefetch_related(self, *_args):
        return self

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def order_by(self, *_args):
        return self

    def offset(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def all(self):
        return self.items

    async def count(self):
        return self.count_value

    async def update(self, **kwargs):
        self.updated = kwargs
        return 1

    async def delete(self):
        return 1

    def __await__(self):
        async def resolve():
            return self.first_value if self.first_value is not None else self.items

        return resolve().__await__()


def user():
    return SimpleNamespace(
        id=uuid4(), username="user", avatar_url=None, is_superuser=True
    )


def request():
    return SimpleNamespace(url=SimpleNamespace(path="/api/v1/knowledge-bases"))


def team():
    return SimpleNamespace(id=uuid4(), name="Team", avatar_url=None)


def kb(**overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        id=uuid4(),
        name="Docs",
        description=None,
        icon=None,
        team=team(),
        team_id=uuid4(),
        created_by=user(),
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        settings=None,
        document_count=1,
        total_chunks=0,
        total_tokens=0,
        created_at=now,
        updated_at=now,
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def doc(**overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        name="doc.txt",
        doc_type="txt",
        file_path="/tmp/doc.txt",
        file_size=4,
        source_url=None,
        status=DocumentStatus.PENDING.value,
        error_message=None,
        chunk_count=2,
        token_count=8,
        metadata={},
        uploaded_by=user(),
        created_at=now,
        updated_at=now,
        processed_at=None,
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def chunk(**overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        id=uuid4(),
        document_id=uuid4(),
        content="old text",
        chunk_index=3,
        token_count=2,
        metadata={},
        status="embedded",
        error_message=None,
        created_at=now,
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(kb_endpoint, name, AsyncMock())


@pytest.mark.asyncio
async def test_upload_document_rejects_missing_filename_before_storage(monkeypatch):
    save_file = AsyncMock()
    monkeypatch.setattr(kb_endpoint, "check_kb_access", AsyncMock(return_value=kb()))
    monkeypatch.setattr(kb_endpoint.document_processor, "save_file", save_file)

    with pytest.raises(BusinessError) as exc_info:
        await kb_endpoint.upload_document(
            uuid4(),
            request(),
            SimpleNamespace(filename="", content_type="text/plain"),
            user(),
        )

    assert exc_info.value.msg_key == "file_name_required"
    save_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_document_cleans_processing_task_file_vectors_and_stats(
    monkeypatch,
):
    existing_kb = kb(document_count=0, total_chunks=1, total_tokens=3)
    existing_doc = doc(
        status=DocumentStatus.PROCESSING.value,
        metadata={"task_id": "task-1"},
        chunk_count=5,
        token_count=9,
    )
    revoked = []
    vector_store = SimpleNamespace(delete_document_vectors=AsyncMock())
    monkeypatch.setattr(
        kb_endpoint, "check_kb_access", AsyncMock(return_value=existing_kb)
    )
    monkeypatch.setattr(
        kb_endpoint.Document, "filter", lambda **_kwargs: Query(first=existing_doc)
    )
    monkeypatch.setattr(kb_endpoint, "VectorStore", lambda: vector_store)
    monkeypatch.setattr(kb_endpoint.document_processor, "delete_file", AsyncMock())
    monkeypatch.setattr(
        kb_endpoint.document_processor, "delete_media_assets", lambda *_args: None
    )
    monkeypatch.setattr(kb_endpoint.AuditLogService, "log", AsyncMock())

    import app.core.celery as celery_module

    monkeypatch.setattr(
        celery_module.celery_app.control,
        "revoke",
        lambda task_id, terminate: revoked.append((task_id, terminate)),
    )

    response = await kb_endpoint.delete_document(
        existing_kb.id, existing_doc.id, request(), user()
    )

    assert response["data"] == {"id": str(existing_doc.id)}
    assert revoked == [("task-1", True)]
    vector_store.delete_document_vectors.assert_awaited_once_with(existing_doc.id)
    kb_endpoint.document_processor.delete_file.assert_awaited_once_with(
        existing_doc.file_path
    )
    assert (
        existing_kb.document_count,
        existing_kb.total_chunks,
        existing_kb.total_tokens,
    ) == (
        0,
        0,
        0,
    )
    existing_doc.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_document_applies_optional_settings_and_ignores_dispatch_failure(
    monkeypatch,
):
    existing_doc = doc(metadata=None)
    monkeypatch.setattr(kb_endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        kb_endpoint.Document, "filter", lambda **_kwargs: Query(first=existing_doc)
    )
    monkeypatch.setattr(
        kb_endpoint.Document,
        "get",
        lambda **_kwargs: Query(first=existing_doc),
    )
    monkeypatch.setattr(
        kb_endpoint, "_dispatch_document_task", AsyncMock(side_effect=RuntimeError)
    )
    monkeypatch.setattr(kb_endpoint.AuditLogService, "log", AsyncMock())

    response = await kb_endpoint.process_document(
        uuid4(),
        existing_doc.id,
        request(),
        ProcessRequest(
            chunk_size=200, chunk_overlap=20, separator="\n", clean_text=True
        ),
        user(),
    )

    assert response["msg"] == "Document processing started"
    assert existing_doc.metadata == {
        "chunk_size": 200,
        "chunk_overlap": 20,
        "separator": "\n",
        "clean_text": True,
    }
    assert existing_doc.status == DocumentStatus.PROCESSING.value
    assert existing_doc.error_message is None


@pytest.mark.asyncio
async def test_search_maps_dimension_and_generic_vector_failures(monkeypatch):
    existing_kb = kb(embedding_model_id=uuid4(), rerank_model_id=uuid4())
    monkeypatch.setattr(
        kb_endpoint, "check_kb_access", AsyncMock(return_value=existing_kb)
    )

    retrieve = AsyncMock(
        side_effect=kb_endpoint.DimensionMismatchError("bad dimension")
    )
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)
    search_in = SearchRequest(query="hello", rerank_enabled=True)
    with pytest.raises(BusinessError) as exc_info:
        await kb_endpoint.search_knowledge_base(existing_kb.id, search_in, user())
    assert exc_info.value.msg_key == "kb_embedding_dimension_mismatch"

    retrieve.side_effect = RuntimeError
    with pytest.raises(BusinessError) as exc_info:
        await kb_endpoint.search_knowledge_base(existing_kb.id, search_in, user())
    assert exc_info.value.msg_key == "vector_search_failed"


@pytest.mark.asyncio
async def test_update_delete_create_chunk_vector_error_branches(monkeypatch):
    existing_kb = kb(total_chunks=0, total_tokens=1)
    existing_doc = doc(chunk_count=0, token_count=1)
    existing_chunk = chunk(token_count=4, status="embedded")
    monkeypatch.setattr(
        kb_endpoint, "check_kb_access", AsyncMock(return_value=existing_kb)
    )
    monkeypatch.setattr(kb_endpoint.AuditLogService, "log", AsyncMock())

    chunk_query = Query(first=existing_chunk)

    def filter_chunks(**kwargs):
        if kwargs.get("document_id") == existing_doc.id and "id" not in kwargs:
            return Query(items=[existing_chunk])
        return chunk_query

    monkeypatch.setattr(
        kb_endpoint.Document, "filter", lambda **_kwargs: Query(first=existing_doc)
    )
    monkeypatch.setattr(kb_endpoint.DocumentChunk, "filter", filter_chunks)
    monkeypatch.setattr(
        kb_endpoint.DocumentChunk,
        "create",
        AsyncMock(
            return_value=chunk(content="new chunk", token_count=2, chunk_index=4)
        ),
    )

    class Store:
        async def update_chunk_vector(self, *_args, **_kwargs):
            raise kb_endpoint.DimensionMismatchError("bad")

        async def delete_chunk_vector(self, *_args, **_kwargs):
            raise RuntimeError

        async def add_chunk_vector(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(kb_endpoint, "VectorStore", lambda **_kwargs: Store())

    with pytest.raises(BusinessError) as exc_info:
        await kb_endpoint.update_document_chunk(
            kb_id=existing_kb.id,
            doc_id=existing_doc.id,
            chunk_id=existing_chunk.id,
            chunk_in=DocumentChunkUpdate(content="updated text"),
            request=request(),
            current_user=user(),
        )
    assert exc_info.value.msg_key == "kb_embedding_dimension_mismatch"

    delete_response = await kb_endpoint.delete_document_chunk(
        existing_kb.id, existing_doc.id, existing_chunk.id, request(), user()
    )
    assert delete_response["data"] == {"id": str(existing_chunk.id)}
    assert existing_kb.total_chunks == 0
    assert existing_doc.chunk_count == 0
    existing_chunk.delete.assert_awaited_once()

    create_response = await kb_endpoint.create_document_chunk(
        kb_id=existing_kb.id,
        doc_id=existing_doc.id,
        chunk_in=DocumentChunkUpdate(content="new chunk text"),
        request=request(),
        after_index=3,
        current_user=user(),
    )
    assert create_response["data"]["content"] == "new chunk"
    existing_chunk.save.assert_awaited_once()
