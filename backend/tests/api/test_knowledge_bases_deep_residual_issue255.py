import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.knowledge_base import ChunkPreviewRequest, ProcessWithChunksRequest
from app.schemas.response import BusinessError


class Query:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    async def count(self):
        return self.value


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(knowledge_bases, name, AsyncMock())


@pytest.mark.anyio
async def test_access_helpers_cover_missing_and_privileged_paths(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    monkeypatch.setattr(knowledge_bases.Team, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.check_team_access(uuid4(), user)
    assert caught.value.msg_key == "team_not_found"

    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(knowledge_bases.Team, "filter", lambda **_kwargs: Query(team))
    monkeypatch.setattr(knowledge_bases.TeamMember, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.check_team_access(team.id, user)
    assert caught.value.msg_key == "not_team_member"

    user.is_superuser = True
    assert await knowledge_bases.check_team_access(team.id, user, True) is team

    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: Query()
    )
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.check_kb_access(uuid4(), user)
    assert caught.value.msg_key == "kb_not_found"

    kb = SimpleNamespace(team=team, created_by=None)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", lambda **_kwargs: Query(kb)
    )
    assert await knowledge_bases.check_kb_access(uuid4(), user, True, False) is kb


@pytest.mark.anyio
async def test_model_info_helpers_cover_empty_missing_and_present(monkeypatch):
    model_id = uuid4()
    model = SimpleNamespace(
        id=model_id, name="Model", provider="local", model_id="model-v1"
    )
    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: Query())

    assert await knowledge_bases.get_embedding_model_info(None) is None
    assert await knowledge_bases.get_embedding_model_info(model_id) is None
    assert await knowledge_bases.get_rerank_model_info(None) is None
    assert await knowledge_bases.get_rerank_model_info(model_id) is None
    assert knowledge_bases._build_model_info(None) is None

    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: Query(model))
    embedding = await knowledge_bases.get_embedding_model_info(model_id)
    rerank = await knowledge_bases.get_rerank_model_info(model_id)
    assert embedding and embedding.name == "Model"
    assert rerank and rerank.provider == "local"
    assert knowledge_bases._build_model_info(model) == {
        "id": model_id,
        "name": "Model",
        "provider": "local",
        "model_id": "model-v1",
    }


@pytest.mark.anyio
async def test_model_authorization_rejects_missing_model(monkeypatch):
    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.ensure_team_authorized_model(
            uuid4(), uuid4(), "embedding"
        )

    assert caught.value.msg_key == "model_not_found"


@pytest.mark.anyio
async def test_preview_chunks_covers_no_source_file_url_and_failure(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(id=doc_id, file_path=None, source_url=None, doc_type="txt")
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    preview = ChunkPreviewRequest(chunk_size=100, chunk_overlap=10, clean_text=True)

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.preview_document_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            preview_in=preview,
            current_user=SimpleNamespace(),
        )
    assert caught.value.msg_key == "document_no_source"

    chunks = [
        {
            "chunk_index": 0,
            "content": "content",
            "token_count": 2,
            "char_count": 7,
        }
    ]
    processor_module = importlib.import_module("app.services.document_processor")
    monkeypatch.setattr(
        processor_module, "chunk_text", lambda *_args, **_kwargs: chunks
    )
    doc.file_path = "stored/file.txt"
    extract = AsyncMock(return_value=("content", {}))
    monkeypatch.setattr(knowledge_bases.document_processor, "extract_text", extract)
    response = await knowledge_bases.preview_document_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        preview_in=preview,
        current_user=SimpleNamespace(),
    )
    assert response["data"].total_chunks == 1
    extract.assert_awaited_once()

    doc.file_path = None
    doc.source_url = "https://example.test"
    fetch = AsyncMock(return_value=("content", {}))
    monkeypatch.setattr(knowledge_bases.document_processor, "fetch_url_content", fetch)
    await knowledge_bases.preview_document_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        preview_in=preview,
        current_user=SimpleNamespace(),
    )
    fetch.assert_awaited_once()

    fetch.side_effect = RuntimeError("offline")
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.preview_document_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            preview_in=preview,
            current_user=SimpleNamespace(),
        )
    assert caught.value.msg_key == "chunk_preview_failed"


@pytest.mark.anyio
async def test_process_with_chunks_covers_processing_and_failed_dispatch(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        name="guide",
        status=knowledge_bases.DocumentStatus.PROCESSING.value,
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
    request = ProcessWithChunksRequest(
        chunks=[{"content": "content", "chunk_index": 0}]
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.process_document_with_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            request=SimpleNamespace(),
            process_request=request,
            current_user=SimpleNamespace(),
        )
    assert caught.value.msg_key == "document_is_processing"

    doc.status = knowledge_bases.DocumentStatus.COMPLETED.value
    doc.metadata = {"task_id": "old-task"}
    delete_vectors = AsyncMock(side_effect=RuntimeError("vector store unavailable"))
    vector_store_module = importlib.import_module("app.services.vector_store")
    monkeypatch.setattr(
        vector_store_module.vector_store, "delete_document_vectors", delete_vectors
    )
    monkeypatch.setattr(
        knowledge_bases.DocumentChunk,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=AsyncMock()),
    )
    monkeypatch.setattr(
        knowledge_bases,
        "_dispatch_document_task",
        AsyncMock(side_effect=RuntimeError()),
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.process_document_with_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            request=SimpleNamespace(),
            process_request=request,
            current_user=SimpleNamespace(),
        )
    assert caught.value.msg_key == "document_process_failed"
    assert doc.status == knowledge_bases.DocumentStatus.ERROR.value
    assert doc.error_message == "document_process_failed"
    delete_vectors.assert_awaited_once_with(doc_id)


@pytest.mark.anyio
async def test_download_and_media_reject_invalid_storage_paths(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(file_path="outside.txt", doc_type="txt", name="outside.txt")
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(
        knowledge_bases.document_processor,
        "_storage_key",
        lambda _path: (_ for _ in ()).throw(ValueError()),
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.download_document(kb_id, doc_id, SimpleNamespace())
    assert caught.value.msg_key == "file_not_found"

    monkeypatch.setattr(
        knowledge_bases.document_processor,
        "get_media_asset_path",
        lambda *_args: Path("/definitely/missing/image.png"),
    )
    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.get_document_media(
            kb_id, doc_id, "image.png", SimpleNamespace()
        )
    assert caught.value.msg_key == "file_not_found"
