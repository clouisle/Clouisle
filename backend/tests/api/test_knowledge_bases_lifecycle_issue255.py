from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(knowledge_bases, name, AsyncMock())


class Query:
    def __init__(self, value=None):
        self.value = value

    def exclude(self, **_kwargs):
        return self

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


@pytest.mark.anyio
async def test_create_knowledge_base_happy_path_and_duplicate(monkeypatch):
    team_id, kb_id = uuid4(), uuid4()
    team = SimpleNamespace(id=team_id)
    user = SimpleNamespace(id=uuid4())
    request = SimpleNamespace()
    created = SimpleNamespace(id=kb_id)
    loaded = SimpleNamespace(id=kb_id, name="Handbook")
    create = AsyncMock(return_value=created)
    audit = AsyncMock()

    monkeypatch.setattr(
        knowledge_bases, "check_team_access", AsyncMock(return_value=team)
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: Query()
    )
    monkeypatch.setattr(knowledge_bases.KnowledgeBase, "create", create)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "get", lambda **_kwargs: Query(loaded)
    )
    authorize = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "ensure_team_authorized_model", authorize)
    monkeypatch.setattr(
        knowledge_bases, "kb_with_model_info", AsyncMock(return_value={"id": kb_id})
    )
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", audit)
    kb_in = SimpleNamespace(
        team_id=team_id,
        name="Handbook",
        description="Team docs",
        icon="book",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        settings=SimpleNamespace(model_dump=lambda: {"top_k": 5}),
    )

    response = await knowledge_bases.create_knowledge_base(
        kb_in=kb_in, request=request, current_user=user
    )

    assert response["data"] == {"id": kb_id}
    assert authorize.await_count == 2
    assert create.await_args.kwargs["settings"] == {"top_k": 5}
    audit.assert_awaited_once()

    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace()),
    )
    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.create_knowledge_base(
            kb_in=kb_in, request=request, current_user=user
        )
    assert exc.value.msg_key == "kb_name_exists"


@pytest.mark.anyio
async def test_update_knowledge_base_updates_mutable_fields(monkeypatch):
    kb_id, team_id, rerank_id = uuid4(), uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Old",
        description=None,
        icon=None,
        status="active",
        settings=None,
        embedding_model_id=uuid4(),
        rerank_model_id=None,
        team=SimpleNamespace(id=team_id),
        save=AsyncMock(),
    )
    loaded = SimpleNamespace(id=kb_id, name="New")
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: Query()
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "get", lambda **_kwargs: Query(loaded)
    )
    authorize = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "ensure_team_authorized_model", authorize)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases,
        "kb_with_model_info",
        AsyncMock(return_value={"name": "New"}),
    )
    update = SimpleNamespace(
        name="New",
        description="Updated",
        icon="new-icon",
        embedding_model_id=kb.embedding_model_id,
        rerank_model_id=rerank_id,
        settings=SimpleNamespace(model_dump=lambda: {"top_k": 8}),
        status="archived",
        model_fields_set={"embedding_model_id", "rerank_model_id"},
    )

    response = await knowledge_bases.update_knowledge_base(
        kb_id=kb_id,
        kb_in=update,
        request=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )

    assert response["data"] == {"name": "New"}
    assert (kb.name, kb.description, kb.icon, kb.status) == (
        "New",
        "Updated",
        "new-icon",
        "archived",
    )
    assert kb.settings == {"top_k": 8}
    assert kb.rerank_model_id == rerank_id
    authorize.assert_awaited_once_with(team_id, rerank_id, "rerank")
    kb.save.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("url_document", [False, True])
async def test_create_document_from_upload_or_url(monkeypatch, url_document):
    kb_id, doc_id = uuid4(), uuid4()
    kb = SimpleNamespace(id=kb_id, name="Handbook", document_count=2, save=AsyncMock())
    user = SimpleNamespace(id=uuid4())
    created = SimpleNamespace(id=doc_id)
    loaded = SimpleNamespace(id=doc_id, name="Guide")
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(knowledge_bases.Document, "create", create)
    monkeypatch.setattr(
        knowledge_bases.Document, "get", lambda **_kwargs: Query(loaded)
    )
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases,
        "serialize_document",
        AsyncMock(return_value={"id": str(doc_id)}),
    )

    if url_document:
        response = await knowledge_bases.add_url_document(
            kb_id,
            SimpleNamespace(name="Guide", source_url="https://example.test/guide"),
            SimpleNamespace(),
            user,
        )
        assert create.await_args.kwargs["source_url"] == "https://example.test/guide"
    else:
        monkeypatch.setattr(
            knowledge_bases.document_processor,
            "get_document_type",
            Mock(return_value="txt"),
        )
        monkeypatch.setattr(
            knowledge_bases.document_processor,
            "get_storage_path",
            Mock(return_value="kb/guide.txt"),
        )
        monkeypatch.setattr(
            knowledge_bases.document_processor, "save_file", AsyncMock()
        )
        monkeypatch.setattr(
            knowledge_bases,
            "get_kb_document_max_upload_size_mb",
            AsyncMock(return_value=1),
        )
        file = SimpleNamespace(
            filename="guide.txt",
            content_type="text/plain",
            read=AsyncMock(return_value=b"guide"),
        )
        response = await knowledge_bases.upload_document(
            kb_id, SimpleNamespace(), file, user
        )
        assert create.await_args.kwargs["file_path"] == "kb/guide.txt"
        assert create.await_args.kwargs["file_size"] == 5

    assert response["data"] == {"id": str(doc_id)}
    assert kb.document_count == 3
    kb.save.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_document_cleans_storage_vectors_and_statistics(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        team_id=uuid4(),
        document_count=1,
        total_chunks=2,
        total_tokens=6,
        save=AsyncMock(),
    )
    doc = SimpleNamespace(
        id=doc_id,
        name="Guide",
        status=knowledge_bases.DocumentStatus.PENDING.value,
        metadata={"task_id": "task-id"},
        file_path="kb/guide.txt",
        chunk_count=4,
        token_count=10,
        delete=AsyncMock(),
    )
    revoke = Mock(side_effect=RuntimeError("worker unavailable"))
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    store = SimpleNamespace(delete_document_vectors=AsyncMock())
    monkeypatch.setattr(knowledge_bases, "VectorStore", lambda: store)
    monkeypatch.setattr(
        knowledge_bases.document_processor, "delete_media_assets", AsyncMock()
    )
    monkeypatch.setattr(knowledge_bases.document_processor, "delete_file", AsyncMock())
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", AsyncMock())
    from app.core.celery import celery_app

    monkeypatch.setattr(celery_app.control, "revoke", revoke)

    response = await knowledge_bases.delete_document(
        kb_id, doc_id, SimpleNamespace(), SimpleNamespace()
    )

    assert response["data"] == {"id": str(doc_id)}
    revoke.assert_called_once_with("task-id", terminate=True)
    store.delete_document_vectors.assert_awaited_once_with(doc_id)
    knowledge_bases.document_processor.delete_file.assert_awaited_once_with(
        "kb/guide.txt"
    )
    assert (kb.document_count, kb.total_chunks, kb.total_tokens) == (0, 0, 0)
    doc.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_download_document_uses_storage_backend(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        file_path="uploads/kb/guide.pdf", doc_type="pdf", name="guide.pdf"
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(
        knowledge_bases.document_processor,
        "_storage_key",
        Mock(return_value="kb/guide.pdf"),
    )
    monkeypatch.setattr(
        knowledge_bases.document_processor, "_storage_root", Mock(return_value="root")
    )
    expected = SimpleNamespace()
    storage = SimpleNamespace(
        exists=AsyncMock(return_value=True), response=AsyncMock(return_value=expected)
    )
    monkeypatch.setattr(
        knowledge_bases,
        "get_upload_storage_backend",
        AsyncMock(return_value=storage),
    )

    response = await knowledge_bases.download_document(kb_id, doc_id, SimpleNamespace())

    assert response is expected
    storage.response.assert_awaited_once_with(
        "kb/guide.pdf", content_type="application/pdf", filename="guide.pdf"
    )
