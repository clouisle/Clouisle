from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases as endpoint
from app.models.knowledge_base import DocumentStatus
from app.schemas.knowledge_base import (
    ChunkPreviewRequest,
    ProcessRequest,
    SearchRequest,
)
from app.schemas.response import BusinessError


class Query:
    def __init__(self, first=None):
        self.first_value = first

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    def __await__(self):
        async def resolve():
            return self.first_value

        return resolve().__await__()


class Saved(SimpleNamespace):
    async def save(self, *_, **__):
        self.saved = True


@pytest.mark.asyncio
async def test_dispatch_document_task_rolls_back_metadata_when_task_submit_fails():
    doc = Saved(metadata={"keep": "yes"})
    task = SimpleNamespace(name="process", apply_async=Mock(side_effect=RuntimeError))

    with pytest.raises(RuntimeError):
        await endpoint._dispatch_document_task(doc, task, "doc-id")

    assert doc.metadata == {"keep": "yes"}
    assert doc.saved is True


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("bad", endpoint.KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB),
        (0, endpoint.KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
        (9999, endpoint.KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB),
    ],
)
@pytest.mark.asyncio
async def test_upload_limit_setting_falls_back_and_clamps(
    monkeypatch, setting, expected
):
    monkeypatch.setattr(
        endpoint.SiteSetting, "get_value", AsyncMock(return_value=setting)
    )

    assert await endpoint.get_kb_document_max_upload_size_mb() == expected


@pytest.mark.parametrize(
    ("error_message", "expected"),
    [("   ", None), ("internal stack trace", "unknown_error")],
)
def test_error_serialization_hides_blank_and_unsafe_messages(
    monkeypatch, error_message, expected
):
    monkeypatch.setattr(endpoint, "has_translation", lambda _value: False)
    monkeypatch.setattr(endpoint, "is_safe_user_visible_error", lambda _value: False)
    monkeypatch.setattr(endpoint, "t", lambda key: key)

    assert endpoint.serialize_knowledge_base_error(error_message) == expected


@pytest.mark.asyncio
async def test_process_document_applies_only_provided_chunk_settings(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = Saved(
        id=doc_id,
        name="doc.txt",
        metadata=None,
        status=DocumentStatus.PENDING.value,
        error_message="old",
    )
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        endpoint,
        "Document",
        SimpleNamespace(
            filter=lambda **_kwargs: Query(doc), get=lambda **_kwargs: Query(doc)
        ),
    )
    monkeypatch.setattr(endpoint, "_dispatch_document_task", AsyncMock())
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        endpoint, "serialize_document", AsyncMock(return_value={"id": str(doc_id)})
    )

    response = await endpoint.process_document(
        kb_id,
        doc_id,
        SimpleNamespace(),
        ProcessRequest(
            chunk_size=321, chunk_overlap=None, separator="\n", clean_text=False
        ),
        SimpleNamespace(),
    )

    assert doc.status == DocumentStatus.PROCESSING.value
    assert doc.error_message is None
    assert doc.metadata == {"chunk_size": 321, "separator": "\n", "clean_text": False}
    assert response["data"]["id"] == str(doc_id)


@pytest.mark.asyncio
async def test_preview_chunks_uses_url_source_and_separator(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        id=doc_id, file_path=None, source_url="https://example.test", doc_type="url"
    )
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        endpoint, "Document", SimpleNamespace(filter=lambda **_kwargs: Query(doc))
    )
    monkeypatch.setattr(
        endpoint.document_processor,
        "fetch_url_content",
        AsyncMock(return_value=("alpha|beta", {})),
    )

    def chunk_text(text, *, chunk_size, chunk_overlap, separators):
        assert (text, chunk_size, chunk_overlap, separators) == (
            "alpha|beta",
            100,
            1,
            ["|"],
        )
        return [
            {"chunk_index": 0, "content": "alpha", "token_count": 1, "char_count": 5}
        ]

    monkeypatch.setattr(
        import_module("app.services.document_processor"), "chunk_text", chunk_text
    )

    response = await endpoint.preview_document_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        preview_in=ChunkPreviewRequest(chunk_size=100, chunk_overlap=1, separator="|"),
        current_user=SimpleNamespace(),
    )

    assert response["data"].total_chunks == 1
    assert response["data"].total_tokens == 1


@pytest.mark.asyncio
async def test_search_maps_vector_failures_and_passes_explicit_rerank_overrides(
    monkeypatch,
):
    kb_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="kb",
        status="active",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        embedding_dimension=None,
        team_id=uuid4(),
    )
    retrieve = AsyncMock(
        side_effect=[
            endpoint.DimensionMismatchError("bad dim"),
            SimpleNamespace(results=("hit",)),
        ]
    )
    monkeypatch.setattr(endpoint, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)

    with pytest.raises(BusinessError) as exc_info:
        await endpoint.search_knowledge_base(
            kb_id, SearchRequest(query="q"), SimpleNamespace()
        )
    assert exc_info.value.msg_key == "kb_embedding_dimension_mismatch"

    response = await endpoint.search_knowledge_base(
        kb_id,
        SearchRequest(query="q", rerank_enabled=False),
        SimpleNamespace(),
    )

    assert response["data"]["results"] == ("hit",)
    assert retrieve.await_args.args[0].rerank_overrides == {"rerank_enabled": False}
