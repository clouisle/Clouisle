from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.datastructures import URL

from app.api.v1.endpoints import knowledge_bases as kb_api
from app.models.knowledge_base import DocumentStatus
from app.schemas.knowledge_base import (
    ChunkPreviewRequest,
    DocumentChunkUpdate,
    ProcessRequest,
    SearchRequest,
)
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, *, first=None, items=None, count=0):
        self.first_item = first
        self.items = list(items or [])
        self.count_value = count
        self.filters = []
        self.updated = None

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def exclude(self, **kwargs):
        self.filters.append({"exclude": kwargs})
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    async def first(self):
        return self.first_item

    async def all(self):
        return self.items

    async def count(self):
        return self.count_value

    async def delete(self):
        self.deleted = True
        return len(self.items)

    async def update(self, **kwargs):
        self.updated = kwargs
        return self.count_value

    def __await__(self):
        async def _result():
            return self.first_item if self.first_item is not None else self.items

        return _result().__await__()


class Recorder:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
        self.saved = []
        self.deleted = False

    async def save(self, *args, **kwargs):
        self.saved.append({"args": args, "kwargs": kwargs})

    async def delete(self):
        self.deleted = True


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid4(), is_superuser=False, roles=[], locale="en")


@pytest.fixture
def team():
    return SimpleNamespace(id=uuid4(), name="Team")


@pytest.fixture
def fake_request():
    return SimpleNamespace(url=URL("/api/v1/knowledge-bases"))


@pytest.fixture
def auditless(monkeypatch):
    async def fake_log(**_kwargs):
        return None

    monkeypatch.setattr(kb_api.AuditLogService, "log", fake_log)


def model_obj(model_type="embedding"):
    return SimpleNamespace(
        id=uuid4(),
        name="Model",
        provider="provider",
        model_id="model",
        model_type=model_type,
    )


def kb_obj(team):
    now = datetime.now(UTC)
    return Recorder(
        id=uuid4(),
        name="KB",
        description=None,
        icon=None,
        team=team,
        team_id=team.id,
        created_by=None,
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        settings=None,
        document_count=1,
        total_chunks=2,
        total_tokens=8,
        created_at=now,
        updated_at=now,
    )


def doc_obj(
    kb, *, status=DocumentStatus.PENDING.value, metadata=None, file_path="doc.txt"
):
    now = datetime.now(UTC)
    return Recorder(
        id=uuid4(),
        knowledge_base_id=kb.id,
        knowledge_base=kb,
        name="doc.txt",
        doc_type="txt",
        file_path=file_path,
        file_size=4,
        source_url=None,
        status=status,
        error_message="unsafe internal trace",
        chunk_count=2,
        token_count=8,
        metadata=metadata,
        uploaded_by=None,
        created_at=now,
        updated_at=now,
        processed_at=None,
    )


def chunk_obj(doc, index=0, status="embedded"):
    return Recorder(
        id=uuid4(),
        document_id=doc.id,
        document=doc,
        content="chunk text",
        chunk_index=index,
        token_count=2,
        metadata=None,
        status=status,
        error_message=None,
        created_at=datetime.now(UTC),
    )


def allow_kb_access(monkeypatch, kb):
    async def fake_check_kb_access(*_args, **_kwargs):
        return kb

    monkeypatch.setattr(kb_api, "check_kb_access", fake_check_kb_access)


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(kb_api, name, AsyncMock())


@pytest.mark.anyio
async def test_admin_dependency_enforces_actions_only_on_admin_routes(user):
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/admin/knowledge-bases"))

    with pytest.raises(BusinessError) as exc_info:
        await kb_api.require_kb_update(request, user)

    assert exc_info.value.code == ResponseCode.PERMISSION_DENIED
    assert exc_info.value.kwargs["permission"] == "admin:knowledge-base:update"

    request.url.path = "/api/v1/knowledge-bases"
    assert await kb_api.require_kb_update(request, user) is user


@pytest.mark.anyio
async def test_team_access_admin_role_and_missing_team_branches(
    monkeypatch, user, team
):
    monkeypatch.setattr(kb_api.Team, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.check_team_access(team.id, user)
    assert exc_info.value.code == ResponseCode.TEAM_NOT_FOUND

    monkeypatch.setattr(kb_api.Team, "filter", lambda **_kwargs: Query(first=team))
    monkeypatch.setattr(kb_api.TeamMember, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.check_team_access(team.id, user)
    assert exc_info.value.code == ResponseCode.NOT_TEAM_MEMBER

    member = SimpleNamespace(role="member")
    monkeypatch.setattr(
        kb_api.TeamMember, "filter", lambda **_kwargs: Query(first=member)
    )
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.check_team_access(team.id, user, require_admin=True)
    assert exc_info.value.code == ResponseCode.TEAM_ADMIN_REQUIRED

    member.role = "admin"
    assert await kb_api.check_team_access(team.id, user, require_admin=True) is team


@pytest.mark.anyio
async def test_model_authorization_rejects_missing_wrong_type_and_disabled(
    monkeypatch, team
):
    model_id = uuid4()
    monkeypatch.setattr(kb_api.Model, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.ensure_team_authorized_model(team.id, model_id, "embedding")
    assert exc_info.value.code == ResponseCode.MODEL_NOT_FOUND

    monkeypatch.setattr(
        kb_api.Model, "filter", lambda **_kwargs: Query(first=model_obj("rerank"))
    )
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.ensure_team_authorized_model(team.id, model_id, "embedding")
    assert exc_info.value.msg_key == "model_type_mismatch"

    model = model_obj("embedding")
    monkeypatch.setattr(kb_api.Model, "filter", lambda **_kwargs: Query(first=model))
    monkeypatch.setattr(kb_api.TeamModel, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.ensure_team_authorized_model(team.id, model_id, "embedding")
    assert exc_info.value.code == ResponseCode.MODEL_NOT_AUTHORIZED

    monkeypatch.setattr(
        kb_api.TeamModel, "filter", lambda **_kwargs: Query(first=object())
    )
    assert (
        await kb_api.ensure_team_authorized_model(team.id, model_id, "embedding")
        is model
    )


@pytest.mark.anyio
async def test_process_document_metadata_and_dispatch_failure_are_tolerated(
    monkeypatch, user, team, fake_request, auditless
):
    kb = kb_obj(team)
    doc = doc_obj(kb)
    allow_kb_access(monkeypatch, kb)
    monkeypatch.setattr(kb_api.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(kb_api.Document, "get", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(
        kb_api,
        "_dispatch_document_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )

    result = await kb_api.process_document(
        kb.id,
        doc.id,
        fake_request,
        ProcessRequest(
            chunk_size=200, chunk_overlap=20, separator="\n", clean_text=False
        ),
        user,
    )

    assert result["data"]["status"] == DocumentStatus.PROCESSING.value
    assert doc.metadata == {
        "chunk_size": 200,
        "chunk_overlap": 20,
        "separator": "\n",
        "clean_text": False,
    }

    doc.status = DocumentStatus.COMPLETED.value
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.process_document(kb.id, doc.id, fake_request, None, user)
    assert exc_info.value.msg_key == "document_not_pending"


@pytest.mark.anyio
async def test_preview_chunks_handles_file_url_no_source_and_extractor_failure(
    monkeypatch, user, team
):
    kb = kb_obj(team)
    doc = doc_obj(kb, file_path="doc.txt")
    allow_kb_access(monkeypatch, kb)
    monkeypatch.setattr(kb_api.Document, "filter", lambda **_kwargs: Query(first=doc))

    async def extract_text(*_args, **_kwargs):
        return "alpha beta gamma", {}

    monkeypatch.setattr(kb_api.document_processor, "extract_text", extract_text)
    result = await kb_api.preview_document_chunks(
        kb_id=kb.id,
        doc_id=doc.id,
        preview_in=ChunkPreviewRequest(chunk_size=100, chunk_overlap=0),
        current_user=user,
    )
    assert result["data"].total_chunks >= 1

    doc.file_path = None
    doc.source_url = "https://example.test"

    async def fetch_url_content(*_args, **_kwargs):
        return "url body", {}

    monkeypatch.setattr(
        kb_api.document_processor, "fetch_url_content", fetch_url_content
    )
    result = await kb_api.preview_document_chunks(
        kb_id=kb.id,
        doc_id=doc.id,
        preview_in=ChunkPreviewRequest(chunk_size=100, chunk_overlap=0),
        current_user=user,
    )
    assert result["data"].total_chunks >= 1

    doc.source_url = None
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.preview_document_chunks(
            kb_id=kb.id,
            doc_id=doc.id,
            preview_in=ChunkPreviewRequest(chunk_size=100, chunk_overlap=0),
            current_user=user,
        )
    assert exc_info.value.msg_key == "document_no_source"

    doc.file_path = "doc.txt"

    async def broken_extract(*_args, **_kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(kb_api.document_processor, "extract_text", broken_extract)
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.preview_document_chunks(
            kb_id=kb.id,
            doc_id=doc.id,
            preview_in=ChunkPreviewRequest(chunk_size=100, chunk_overlap=0),
            current_user=user,
        )
    assert exc_info.value.msg_key == "chunk_preview_failed"


@pytest.mark.anyio
async def test_update_chunk_maps_vector_dimension_and_generic_failures(
    monkeypatch, user, team, fake_request, auditless
):
    kb = kb_obj(team)
    doc = doc_obj(kb)
    chunk = chunk_obj(doc)
    allow_kb_access(monkeypatch, kb)
    monkeypatch.setattr(kb_api.Document, "filter", lambda **_kwargs: Query(first=doc))
    monkeypatch.setattr(
        kb_api.DocumentChunk, "filter", lambda **_kwargs: Query(first=chunk)
    )

    class VectorStore:
        def __init__(self, *_args, **_kwargs):
            pass

        async def update_chunk_vector(self, *_args, **_kwargs):
            raise kb_api.DimensionMismatchError("bad dim")

    monkeypatch.setattr(kb_api, "VectorStore", VectorStore)
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.update_document_chunk(
            kb_id=kb.id,
            doc_id=doc.id,
            chunk_id=chunk.id,
            chunk_in=DocumentChunkUpdate(content="new content"),
            request=fake_request,
            current_user=user,
        )
    assert exc_info.value.msg_key == "kb_embedding_dimension_mismatch"

    async def generic_failure(self, *_args, **_kwargs):
        raise RuntimeError("vector down")

    monkeypatch.setattr(VectorStore, "update_chunk_vector", generic_failure)
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.update_document_chunk(
            kb_id=kb.id,
            doc_id=doc.id,
            chunk_id=chunk.id,
            chunk_in=DocumentChunkUpdate(content="newer content"),
            request=fake_request,
            current_user=user,
        )
    assert exc_info.value.msg_key == "vector_update_failed"


@pytest.mark.anyio
async def test_search_passes_rerank_overrides_and_maps_vector_errors(
    monkeypatch, user, team
):
    kb = kb_obj(team)
    allow_kb_access(monkeypatch, kb)
    retrieve = AsyncMock(
        return_value=SimpleNamespace(results=({"content": "hit", "score": 0.9},))
    )
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)
    result = await kb_api.search_knowledge_base(
        kb.id,
        SearchRequest(query="q", rerank_enabled=False, rerank_score_threshold=None),
        user,
    )
    assert result["data"]["total"] == 1
    assert retrieve.await_args.args[0].rerank_overrides == {
        "rerank_enabled": False,
        "rerank_score_threshold": None,
    }

    retrieve.side_effect = kb_api.DimensionMismatchError("bad dim")
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.search_knowledge_base(kb.id, SearchRequest(query="q"), user)
    assert exc_info.value.msg_key == "kb_embedding_dimension_mismatch"

    retrieve.side_effect = RuntimeError("qdrant down")
    with pytest.raises(BusinessError) as exc_info:
        await kb_api.search_knowledge_base(kb.id, SearchRequest(query="q"), user)
    assert exc_info.value.msg_key == "vector_search_failed"


@pytest.mark.anyio
async def test_delete_document_ignores_cleanup_failures_and_updates_counts(
    monkeypatch, user, team, fake_request, auditless
):
    kb = kb_obj(team)
    doc = doc_obj(
        kb, status=DocumentStatus.PROCESSING.value, metadata={"task_id": "task-1"}
    )
    allow_kb_access(monkeypatch, kb)
    monkeypatch.setattr(kb_api.Document, "filter", lambda **_kwargs: Query(first=doc))

    class VectorStore:
        async def delete_document_vectors(self, doc_id):
            assert doc_id == doc.id

    monkeypatch.setattr(kb_api, "VectorStore", lambda: VectorStore())

    async def to_thread(*_args, **_kwargs):
        return None

    monkeypatch.setattr(kb_api.asyncio, "to_thread", to_thread)

    async def delete_file(path):
        assert path == doc.file_path

    monkeypatch.setattr(kb_api.document_processor, "delete_file", delete_file)

    result = await kb_api.delete_document(kb.id, doc.id, fake_request, user)

    assert result["data"] == {"id": str(doc.id)}
    assert doc.deleted is True
    assert kb.document_count == 0
    assert kb.total_chunks == 0
    assert kb.total_tokens == 0


def test_error_serializers_translate_safe_and_unknown(monkeypatch):
    monkeypatch.setattr(kb_api, "has_translation", lambda value: value == "known.key")
    monkeypatch.setattr(kb_api, "t", lambda key, **_kwargs: f"translated:{key}")
    monkeypatch.setattr(
        kb_api, "is_safe_user_visible_error", lambda value: value == "safe"
    )

    assert kb_api.serialize_knowledge_base_error(None) is None
    assert kb_api.serialize_knowledge_base_error("   ") is None
    assert kb_api.serialize_knowledge_base_error("known.key") == "translated:known.key"
    assert kb_api.serialize_document_error("safe") == "safe"
    assert kb_api.serialize_chunk_error("stack trace") == "translated:unknown_error"
