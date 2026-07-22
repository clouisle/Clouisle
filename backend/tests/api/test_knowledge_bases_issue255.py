from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.knowledge_base import ProcessWithChunksRequest, SearchRequest
from app.schemas.response import BusinessError
from app.services.vector_store import DimensionMismatchError


class Query:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


class Task:
    name = "process"

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def apply_async(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error


@pytest.mark.anyio
async def test_dispatch_document_task_records_and_cleans_up_failed_dispatch(
    monkeypatch,
):
    monkeypatch.setattr(knowledge_bases, "uuid4", lambda: "task-id")
    doc = SimpleNamespace(metadata=None, save=AsyncMock())
    task = Task()

    task_id = await knowledge_bases._dispatch_document_task(doc, task, "doc-id")

    assert task_id == "task-id"
    assert doc.metadata == {
        "task_id": "task-id",
        "task_name": "process",
        "task_args": ["doc-id"],
    }
    assert task.calls == [{"args": ("doc-id",), "task_id": "task-id"}]

    failed_task = Task(RuntimeError("broker unavailable"))
    with pytest.raises(RuntimeError, match="broker unavailable"):
        await knowledge_bases._dispatch_document_task(doc, failed_task, "doc-id")
    assert doc.metadata == {}
    assert doc.save.await_args.kwargs == {"update_fields": ["metadata"]}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("invalid", knowledge_bases.KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB),
        (0, knowledge_bases.KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
        (10**9, knowledge_bases.KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB),
        (25, 25),
    ],
)
async def test_upload_limit_normalizes_site_setting(monkeypatch, stored, expected):
    monkeypatch.setattr(
        knowledge_bases.SiteSetting, "get_value", AsyncMock(return_value=stored)
    )

    assert await knowledge_bases.get_kb_document_max_upload_size_mb() == expected


def test_error_serialization_only_exposes_safe_messages(monkeypatch):
    monkeypatch.setattr(
        knowledge_bases, "has_translation", lambda value: value == "translated_key"
    )
    monkeypatch.setattr(
        knowledge_bases, "is_safe_user_visible_error", lambda value: value == "safe"
    )
    monkeypatch.setattr(knowledge_bases, "t", lambda key: f"translated:{key}")

    assert knowledge_bases.serialize_knowledge_base_error(None) is None
    assert knowledge_bases.serialize_knowledge_base_error("   ") is None
    assert knowledge_bases.serialize_knowledge_base_error(" translated_key ") == (
        "translated:translated_key"
    )
    assert knowledge_bases.serialize_document_error(" safe ") == "safe"
    assert knowledge_bases.serialize_chunk_error("secret") == "translated:unknown_error"


@pytest.mark.anyio
async def test_team_and_kb_access_enforce_membership_and_admin(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    member = SimpleNamespace(role="member")
    monkeypatch.setattr(knowledge_bases.Team, "filter", lambda **_kwargs: Query(team))
    monkeypatch.setattr(
        knowledge_bases.TeamMember, "filter", lambda **_kwargs: Query(member)
    )

    assert await knowledge_bases.check_team_access(team.id, user) is team
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.check_team_access(team.id, user, require_admin=True)
    assert caught.value.msg_key == "team_admin_required"

    kb = SimpleNamespace(team=team, created_by=SimpleNamespace(id=user.id))
    kb_query = Query(kb)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: kb_query
    )
    assert (
        await knowledge_bases.check_kb_access(uuid4(), user, require_write=True) is kb
    )

    kb.created_by.id = uuid4()
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.check_kb_access(uuid4(), user, require_write=True)
    assert caught.value.msg_key == "team_admin_required"


@pytest.mark.anyio
async def test_model_authorization_validates_type_and_team_grant(monkeypatch):
    team_id, model_id = uuid4(), uuid4()
    model = SimpleNamespace(id=model_id, name="Embedding", model_type="rerank")
    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: Query(model))
    monkeypatch.setattr(
        knowledge_bases.TeamModel, "filter", lambda **_kwargs: Query(None)
    )

    assert (
        await knowledge_bases.ensure_team_authorized_model(team_id, None, "embedding")
        is None
    )
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.ensure_team_authorized_model(
            team_id, model_id, "embedding"
        )
    assert caught.value.msg_key == "model_type_mismatch"

    model.model_type = "embedding"
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.ensure_team_authorized_model(
            team_id, model_id, "embedding"
        )
    assert caught.value.msg_key == "model_not_authorized"

    monkeypatch.setattr(
        knowledge_bases.TeamModel, "filter", lambda **_kwargs: Query(object())
    )
    assert (
        await knowledge_bases.ensure_team_authorized_model(
            team_id, model_id, "embedding"
        )
        is model
    )


@pytest.mark.anyio
async def test_search_forwards_explicit_rerank_overrides(monkeypatch):
    kb_id = uuid4()
    kb = SimpleNamespace(
        embedding_model_id=uuid4(), rerank_model_id=uuid4(), team_id=uuid4()
    )
    search = AsyncMock(return_value=[{"content": "answer", "score": 0.9}])
    vector_store = SimpleNamespace(search=search)

    def vector_store_factory(**_kwargs):
        return vector_store

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(knowledge_bases, "VectorStore", vector_store_factory)
    request = SearchRequest(query="question", rerank_enabled=False, top_k=3)

    response = await knowledge_bases.search_knowledge_base(
        kb_id, request, SimpleNamespace()
    )

    assert response["data"]["total"] == 1
    assert search.await_args.kwargs["rerank_overrides"] == {"rerank_enabled": False}
    assert search.await_args.kwargs["top_k"] == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (DimensionMismatchError("wrong dimension"), "kb_embedding_dimension_mismatch"),
        (RuntimeError("offline"), "vector_search_failed"),
    ],
)
async def test_search_converts_vector_errors(monkeypatch, error, message):
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
        lambda **_kwargs: SimpleNamespace(search=AsyncMock(side_effect=error)),
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.search_knowledge_base(
            uuid4(), SearchRequest(query="question"), SimpleNamespace()
        )
    assert caught.value.msg_key == message


@pytest.mark.anyio
async def test_process_with_chunks_creates_trimmed_chunks_and_dispatches(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="guide",
        status=knowledge_bases.DocumentStatus.PENDING.value,
        metadata=None,
        error_message="old",
        chunk_count=0,
        token_count=0,
        save=AsyncMock(),
    )
    created = []

    async def create_chunk(**kwargs):
        chunk = SimpleNamespace(id=uuid4(), **kwargs)
        created.append(chunk)
        return chunk

    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(
        knowledge_bases.Document,
        "get",
        lambda **_kwargs: Query(doc),
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=AsyncMock()),
    )
    monkeypatch.setattr(knowledge_bases.DocumentChunk, "create", create_chunk)
    dispatch = AsyncMock(return_value="task-id")
    monkeypatch.setattr(knowledge_bases, "_dispatch_document_task", dispatch)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases,
        "serialize_document",
        AsyncMock(return_value={"id": str(doc_id)}),
    )

    response = await knowledge_bases.process_document_with_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        request=SimpleNamespace(),
        process_request=ProcessWithChunksRequest(
            chunks=[
                {"content": "  eight chars  ", "chunk_index": 0},
                {"content": "   ", "chunk_index": 1},
            ]
        ),
        current_user=SimpleNamespace(),
    )

    assert response["data"] == {"id": str(doc_id)}
    assert [chunk.content for chunk in created] == ["eight chars"]
    assert doc.chunk_count == 1
    assert doc.token_count == 2
    dispatch.assert_awaited_once()
