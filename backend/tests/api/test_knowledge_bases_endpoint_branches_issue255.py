from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.models.knowledge_base import DocumentStatus
from app.schemas.knowledge_base import DocumentChunkUpdate, ProcessRequest
from app.schemas.response import BusinessError, ResponseCode
from app.services.vector_store import DimensionMismatchError


class Query:
    def __init__(self, *, first=None, items=None):
        self.first_result = first
        self.items = items or []
        self.offset_value = None
        self.limit_value = None

    def using_db(self, _connection):
        return self

    def select_for_update(self):
        return self

    async def get(self):
        return self.first_result

    async def update(self, **_values):
        return 1

    async def first(self):
        return self.first_result

    def order_by(self, *_args):
        return self

    async def count(self):
        return len(self.items)

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def __await__(self):
        async def result():
            return self.items

        return result().__await__()


@pytest.fixture(autouse=True)
def transaction_context(monkeypatch):
    connection = object()

    class Transaction:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(knowledge_bases, "in_transaction", Transaction)
    return connection


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(knowledge_bases, name, AsyncMock())


@pytest.mark.asyncio
async def test_process_document_covers_validation_settings_and_dispatch_fallback(
    monkeypatch,
):
    kb_id, doc_id = uuid4(), uuid4()
    user = SimpleNamespace(id=uuid4())
    request = SimpleNamespace()
    check_access = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "check_kb_access", check_access)

    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document(kb_id, doc_id, request, None, user)
    assert exc.value.code == ResponseCode.DOCUMENT_NOT_FOUND

    non_pending = SimpleNamespace(status=DocumentStatus.COMPLETED.value)
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(first=non_pending),
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document(kb_id, doc_id, request, None, user)
    assert exc.value.msg_key == "document_not_pending"

    doc = SimpleNamespace(
        id=doc_id,
        name="guide.pdf",
        status=DocumentStatus.PENDING.value,
        metadata=None,
        error_message="old error",
        save=AsyncMock(),
    )
    reloaded = SimpleNamespace(id=doc_id)
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    get_query = SimpleNamespace(prefetch_related=AsyncMock(return_value=reloaded))
    monkeypatch.setattr(knowledge_bases.Document, "get", lambda **_kwargs: get_query)
    dispatch = AsyncMock(side_effect=RuntimeError("worker unavailable"))
    audit = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", audit)
    monkeypatch.setattr(
        knowledge_bases,
        "serialize_document",
        AsyncMock(return_value={"id": str(doc_id)}),
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document(
            kb_id,
            doc_id,
            request,
            ProcessRequest(
                chunk_size=400,
                chunk_overlap=40,
                separator="\n\n",
                clean_text=False,
            ),
            user,
        )
    assert exc.value.msg_key == "task_dispatch_failed"
    assert dispatch.await_args.kwargs["status"] == DocumentStatus.PROCESSING.value
    assert dispatch.await_args.kwargs["metadata_updates"] == {
        "chunk_size": 400,
        "chunk_overlap": 40,
        "separator": "\n\n",
        "clean_text": False,
    }
    audit.assert_not_awaited()

    doc.status = DocumentStatus.PENDING.value
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document(
            kb_id, doc_id, request, ProcessRequest(), user
        )
    assert exc.value.msg_key == "task_dispatch_failed"
    assert dispatch.await_args.kwargs["metadata_updates"] == {}

    doc.status = DocumentStatus.PENDING.value
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.process_document(kb_id, doc_id, request, None, user)
    assert exc.value.msg_key == "task_dispatch_failed"
    assert dispatch.await_args.kwargs["metadata_updates"] == {}
    assert dispatch.await_count == 3


@pytest.mark.asyncio
async def test_list_document_chunks_covers_not_found_and_pagination(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=None)
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.list_document_chunks(kb_id, doc_id, 1, 50, user)
    assert exc.value.code == ResponseCode.DOCUMENT_NOT_FOUND

    chunks = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    query = Query(items=chunks)
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(first=SimpleNamespace(id=doc_id)),
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk, "filter", lambda **_kwargs: query
    )
    monkeypatch.setattr(
        knowledge_bases,
        "serialize_chunk",
        AsyncMock(side_effect=[{"index": 1}, {"index": 2}]),
    )

    result = await knowledge_bases.list_document_chunks(kb_id, doc_id, 2, 10, user)

    assert result["data"] == {
        "items": [{"index": 1}, {"index": 2}],
        "total": 2,
        "page": 2,
        "page_size": 10,
    }
    assert query.offset_value == 10
    assert query.limit_value == 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vector_error", "expected_code", "expected_key"),
    [
        (
            DimensionMismatchError("wrong size"),
            ResponseCode.VALIDATION_ERROR,
            "kb_embedding_dimension_mismatch",
        ),
        (
            RuntimeError("storage down"),
            ResponseCode.UNKNOWN_ERROR,
            "vector_update_failed",
        ),
        (None, None, None),
    ],
)
async def test_update_document_chunk_covers_resource_and_vector_paths(
    monkeypatch, vector_error, expected_code, expected_key
):
    kb_id, doc_id, chunk_id = uuid4(), uuid4(), uuid4()
    request = SimpleNamespace()
    user = SimpleNamespace(id=uuid4())
    kb = SimpleNamespace(
        id=kb_id,
        embedding_model_id=None,
        team_id=None,
        total_tokens=20,
        save=AsyncMock(),
    )
    doc = SimpleNamespace(token_count=10, save=AsyncMock())
    chunk = SimpleNamespace(
        id=chunk_id,
        chunk_index=3,
        token_count=1,
        content="old",
        save=AsyncMock(),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))

    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.update_document_chunk(
            kb_id=kb_id,
            doc_id=doc_id,
            chunk_id=chunk_id,
            chunk_in=DocumentChunkUpdate(content="updated content"),
            request=request,
            current_user=user,
        )
    assert exc.value.code == ResponseCode.DOCUMENT_NOT_FOUND

    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.update_document_chunk(
            kb_id=kb_id,
            doc_id=doc_id,
            chunk_id=chunk_id,
            chunk_in=DocumentChunkUpdate(content="updated content"),
            request=request,
            current_user=user,
        )
    assert exc.value.code == ResponseCode.CHUNK_NOT_FOUND

    monkeypatch.setattr(
        knowledge_bases.DocumentChunk,
        "filter",
        lambda **_kwargs: Query(first=chunk),
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: Query(first=kb)
    )
    update_vector = AsyncMock(side_effect=vector_error)
    monkeypatch.setattr(
        knowledge_bases,
        "VectorStore",
        lambda **_kwargs: SimpleNamespace(update_chunk_vector=update_vector),
    )
    audit = AsyncMock()
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", audit)
    monkeypatch.setattr(
        knowledge_bases,
        "serialize_chunk",
        AsyncMock(return_value={"id": str(chunk_id)}),
    )

    if vector_error:
        with pytest.raises(BusinessError) as exc:
            await knowledge_bases.update_document_chunk(
                kb_id=kb_id,
                doc_id=doc_id,
                chunk_id=chunk_id,
                chunk_in=DocumentChunkUpdate(content="updated content"),
                request=request,
                current_user=user,
            )
        assert exc.value.code == expected_code
        assert exc.value.msg_key == expected_key
        audit.assert_not_awaited()
    else:
        result = await knowledge_bases.update_document_chunk(
            kb_id=kb_id,
            doc_id=doc_id,
            chunk_id=chunk_id,
            chunk_in=DocumentChunkUpdate(content="updated content"),
            request=request,
            current_user=user,
        )
        assert result["data"] == {"id": str(chunk_id)}
        assert chunk.content == "updated content"
        assert chunk.token_count == 3
        audit.assert_awaited_once()
