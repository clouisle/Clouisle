from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.models.knowledge_base import DocumentStatus
from app.schemas.response import BusinessError


class Query:
    def __init__(self, *, first=None, items=None, count=0):
        self.first_value = first
        self.items = items or []
        self.count_value = count
        self.deleted = False
        self.updated = None

    def prefetch_related(self, *_args):
        return self

    def using_db(self, _connection):
        return self

    def select_for_update(self):
        return self

    def order_by(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    async def delete(self):
        self.deleted = True

    async def update(self, **kwargs):
        self.updated = kwargs

    def __await__(self):
        async def result():
            return self.items if self.items else self.first_value

        return result().__await__()


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(knowledge_bases, name, AsyncMock())


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


@pytest.mark.asyncio
async def test_model_info_and_team_model_authorization_branches(monkeypatch):
    model_id = uuid4()
    team_id = uuid4()
    model = SimpleNamespace(
        id=model_id,
        name="embed",
        provider="local",
        model_id="embed-v1",
        model_type="embedding",
    )

    monkeypatch.setattr(
        knowledge_bases.Model,
        "filter",
        lambda **kwargs: Query(first=model if kwargs["id"] == model_id else None),
    )

    assert await knowledge_bases.get_embedding_model_info(None) is None
    assert await knowledge_bases.get_rerank_model_info(uuid4()) is None
    info = await knowledge_bases.get_embedding_model_info(model_id)
    assert info.model_id == "embed-v1"
    assert knowledge_bases._build_model_info(model)["provider"] == "local"
    assert knowledge_bases._build_model_info(None) is None

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.ensure_team_authorized_model(
            team_id, uuid4(), "embedding"
        )
    assert exc.value.msg_key == "model_not_found"

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.ensure_team_authorized_model(team_id, model_id, "rerank")
    assert exc.value.msg_key == "model_type_mismatch"

    monkeypatch.setattr(
        knowledge_bases.TeamModel, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.ensure_team_authorized_model(
            team_id, model_id, "embedding"
        )
    assert exc.value.msg_key == "model_not_authorized"

    monkeypatch.setattr(
        knowledge_bases.TeamModel,
        "filter",
        lambda **_kwargs: Query(first=SimpleNamespace()),
    )
    assert (
        await knowledge_bases.ensure_team_authorized_model(
            team_id, model_id, "embedding"
        )
        is model
    )


@pytest.mark.asyncio
async def test_team_and_kb_access_errors(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    team_id = uuid4()

    monkeypatch.setattr(knowledge_bases.Team, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.check_team_access(team_id, user)
    assert exc.value.msg_key == "team_not_found"

    team = SimpleNamespace(id=team_id)
    monkeypatch.setattr(
        knowledge_bases.Team, "filter", lambda **_kwargs: Query(first=team)
    )
    monkeypatch.setattr(
        knowledge_bases.TeamMember, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.check_team_access(team_id, user)
    assert exc.value.msg_key == "not_team_member"

    membership = SimpleNamespace(role="member")
    monkeypatch.setattr(
        knowledge_bases.TeamMember,
        "filter",
        lambda **_kwargs: Query(first=membership),
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.check_team_access(team_id, user, require_admin=True)
    assert exc.value.msg_key == "team_admin_required"

    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: Query()
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.check_kb_access(uuid4(), user)
    assert exc.value.msg_key == "kb_not_found"


@pytest.mark.asyncio
async def test_process_with_chunks_cancels_old_task_and_batches_nonempty_chunks(
    monkeypatch,
):
    from app.core.celery import celery_app
    from app.services.vector_store import vector_store

    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="doc",
        status=DocumentStatus.COMPLETED.value,
        metadata={"task_id": "old-task"},
        error_message="old",
        chunk_count=0,
        token_count=0,
        save=AsyncMock(),
    )
    chunks_query = Query()
    created = []

    async def create_chunk(**kwargs):
        chunk = SimpleNamespace(id=uuid4(), **kwargs)
        created.append(chunk)
        return chunk

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_bases.Document, "get", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk, "filter", lambda **_kwargs: chunks_query
    )
    monkeypatch.setattr(knowledge_bases.DocumentChunk, "create", create_chunk)
    monkeypatch.setattr(celery_app.control, "revoke", Mock())
    monkeypatch.setattr(vector_store, "delete_document_vectors", AsyncMock())
    dispatch = AsyncMock(return_value="new-task")
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases, "serialize_document", AsyncMock(return_value={"id": doc_id})
    )

    request = SimpleNamespace(
        chunks=[
            SimpleNamespace(content="  first chunk  ", chunk_index=0),
            SimpleNamespace(content="   ", chunk_index=1),
            SimpleNamespace(content="second", chunk_index=2),
        ]
    )
    result = await knowledge_bases.process_document_with_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        request=SimpleNamespace(),
        process_request=request,
        current_user=SimpleNamespace(),
    )

    celery_app.control.revoke.assert_called_once_with("old-task", terminate=True)
    vector_store.delete_document_vectors.assert_awaited_once_with(doc_id)
    assert chunks_query.deleted is True
    assert [chunk.content for chunk in created] == ["first chunk", "second"]
    assert (doc.chunk_count, doc.token_count) == (2, 3)
    dispatch.assert_awaited_once()
    assert result["data"]["id"] == doc_id


@pytest.mark.asyncio
async def test_process_with_chunks_handles_batch_tracking_and_dispatch_failure(
    monkeypatch,
):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="doc",
        status=DocumentStatus.PENDING.value,
        metadata={},
        chunk_count=0,
        token_count=0,
        save=AsyncMock(),
    )
    kb = SimpleNamespace(
        id=kb_id,
        name="KB",
        team_id=uuid4(),
        model="gpt",
        embedding_model="embed",
        embedding_dimension=1536,
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(first=doc),
    )
    monkeypatch.setattr(
        knowledge_bases.Document,
        "get",
        lambda **_kwargs: Query(first=doc),
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk,
        "filter",
        lambda **_kwargs: Query(),
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk,
        "create",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases, "serialize_document", AsyncMock(return_value={"id": doc_id})
    )

    class FakeRedis:
        def __init__(self):
            self.store = {}
            self.deleted = []

        async def set(self, key, val, **kwargs):
            self.store[key] = int(val)

        async def sadd(self, key, val):
            return 1

        async def decr(self, key):
            curr = self.store.get(key, 0)
            val = curr - 1
            self.store[key] = val
            return val

    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "app.core.redis.get_redis",
        AsyncMock(return_value=fake_redis),
    )

    # 1. Success dispatch with batch_id and batch_total
    request = SimpleNamespace(
        chunks=[SimpleNamespace(content="first chunk", chunk_index=0)],
        batch_id="batch-123",
        batch_total=1,
    )
    dispatch = AsyncMock(return_value="task-success")
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch)
    res = await knowledge_bases.process_document_with_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        request=SimpleNamespace(),
        process_request=request,
        current_user=SimpleNamespace(locale="zh"),
    )
    assert res["data"]["id"] == doc_id
    assert fake_redis.store.get("kb_batch:batch-123:remain") == 1
    assert fake_redis.store.get("kb_batch:batch-123:total") == 1
    assert dispatch.await_args.kwargs["task_kwargs"] == {"batch_id": "batch-123"}
    # 2. Dispatch failure triggering batch decr and completion notification
    doc.status = DocumentStatus.PENDING.value
    dispatch_fail = AsyncMock(side_effect=RuntimeError("celery down"))
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch_fail)
    notify_batch = AsyncMock()
    monkeypatch.setattr(
        "app.tasks.knowledge_base._send_batch_completion_notification",
        notify_batch,
    )

    with pytest.raises(BusinessError):
        await knowledge_bases.process_document_with_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            request=SimpleNamespace(),
            process_request=request,
            current_user=SimpleNamespace(locale="zh"),
        )

    assert doc.status == DocumentStatus.ERROR.value
    notify_batch.assert_awaited_once()
    assert notify_batch.await_args.kwargs["batch_id"] == "batch-123"


@pytest.mark.asyncio
async def test_retry_failed_chunks_dispatches_batch_and_single_failure_resets_status(
    monkeypatch,
):
    kb_id, doc_id, chunk_id = uuid4(), uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="doc",
        status=DocumentStatus.ERROR.value,
        metadata={},
        error_message="failed",
        save=AsyncMock(),
    )
    chunk = SimpleNamespace(id=chunk_id, status="failed", chunk_index=3)

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_bases.Document, "get", lambda **_kwargs: Query(first=doc)
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk,
        "filter",
        lambda **kwargs: Query(
            first=chunk if "id" in kwargs else None,
            count=2 if kwargs.get("status") == "failed" else 0,
        ),
    )
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases, "serialize_document", AsyncMock(return_value={"id": doc_id})
    )

    dispatch = AsyncMock(return_value="batch-task")
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch)
    await knowledge_bases.retry_failed_chunks(
        kb_id, doc_id, SimpleNamespace(), SimpleNamespace()
    )
    assert doc.status == DocumentStatus.PROCESSING.value
    dispatch.assert_awaited_once()

    doc.status = DocumentStatus.ERROR.value
    dispatch.reset_mock(side_effect=True)
    dispatch.side_effect = RuntimeError("broker down")
    await knowledge_bases.retry_failed_chunk(
        kb_id, doc_id, chunk_id, SimpleNamespace(), SimpleNamespace()
    )
    assert doc.status == DocumentStatus.ERROR.value
    assert doc.error_message == "task_dispatch_failed"
    assert dispatch.await_args.args[-2:] == (str(doc_id), str(chunk_id))


@pytest.mark.asyncio
async def test_delete_chunk_updates_stats_and_bulk_reindexes(monkeypatch):
    kb_id, doc_id, chunk_id = uuid4(), uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        team_id=uuid4(),
        embedding_model_id=None,
        total_chunks=0,
        total_tokens=2,
        save=AsyncMock(),
    )
    doc = SimpleNamespace(
        status=DocumentStatus.PENDING.value,
        chunk_count=0,
        token_count=1,
        save=AsyncMock(),
    )
    chunk = SimpleNamespace(
        id=chunk_id,
        chunk_index=2,
        token_count=5,
        delete=AsyncMock(),
    )
    reindex_query = Query()
    doc_query = Query(first=doc)
    kb_query = Query(first=kb)

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(knowledge_bases.Document, "filter", lambda **_kwargs: doc_query)

    def chunk_filter(**kwargs):
        if "id" in kwargs:
            return Query(first=chunk)
        return reindex_query

    monkeypatch.setattr(knowledge_bases.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: kb_query
    )
    vector_store = SimpleNamespace(delete_chunk_vector=AsyncMock(side_effect=OSError()))
    monkeypatch.setattr(knowledge_bases, "VectorStore", lambda **_kwargs: vector_store)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())

    result = await knowledge_bases.delete_document_chunk(
        kb_id, doc_id, chunk_id, SimpleNamespace(), SimpleNamespace()
    )

    assert set(kb_query.updated) == {"total_chunks", "total_tokens"}
    assert set(doc_query.updated) == {"chunk_count", "token_count"}
    chunk.delete.assert_awaited_once()
    assert set(reindex_query.updated) == {"chunk_index"}
    assert result["data"] == {"id": str(chunk_id)}
