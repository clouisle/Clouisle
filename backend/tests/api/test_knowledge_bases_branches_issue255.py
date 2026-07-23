import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.models import (
    KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services.vector_store import DimensionMismatchError


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("invalid", KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB - 1, KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB + 1, KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB),
        (42, 42),
    ],
)
async def test_upload_limit_normalizes_site_setting(monkeypatch, configured, expected):
    monkeypatch.setattr(
        knowledge_bases.SiteSetting,
        "get_value",
        AsyncMock(return_value=configured),
    )

    assert await knowledge_bases.get_kb_document_max_upload_size_mb() == expected


@pytest.mark.parametrize(
    ("message", "translated", "safe", "expected"),
    [
        (None, False, False, None),
        ("   ", False, False, None),
        ("known_key", True, False, "translated"),
        ("Safe detail", False, True, "Safe detail"),
        ("secret detail", False, False, "unknown"),
    ],
)
def test_serialize_knowledge_base_error_hides_unsafe_details(
    monkeypatch, message, translated, safe, expected
):
    monkeypatch.setattr(knowledge_bases, "has_translation", lambda _value: translated)
    monkeypatch.setattr(
        knowledge_bases, "is_safe_user_visible_error", lambda _value: safe
    )
    monkeypatch.setattr(
        knowledge_bases,
        "t",
        lambda key: "translated" if key == "known_key" else "unknown",
    )

    assert knowledge_bases.serialize_knowledge_base_error(message) == expected


@pytest.mark.anyio
async def test_dispatch_document_task_records_and_rolls_back_metadata():
    doc = SimpleNamespace(metadata=None, save=AsyncMock())
    task = SimpleNamespace(name="process", apply_async=Mock())

    task_id = await knowledge_bases._dispatch_document_task(doc, task, "doc-id")

    assert doc.metadata == {
        "task_id": task_id,
        "task_name": "process",
        "task_args": ["doc-id"],
    }
    task.apply_async.assert_called_once_with(args=("doc-id",), task_id=task_id)

    task.apply_async.side_effect = RuntimeError("broker unavailable")
    with pytest.raises(RuntimeError, match="broker unavailable"):
        await knowledge_bases._dispatch_document_task(doc, task, "doc-id")
    assert doc.metadata == {}
    doc.save.assert_awaited_with(update_fields=["metadata"])


@pytest.mark.anyio
async def test_ensure_team_authorized_model_covers_validation(monkeypatch):
    team_id, model_id = uuid4(), uuid4()
    model = SimpleNamespace(name="Reranker", model_type="rerank")
    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: Query(model))
    monkeypatch.setattr(
        knowledge_bases.TeamModel,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace()),
    )

    assert (
        await knowledge_bases.ensure_team_authorized_model(team_id, None, "embedding")
        is None
    )
    assert (
        await knowledge_bases.ensure_team_authorized_model(team_id, model_id, "rerank")
        is model
    )

    with pytest.raises(BusinessError) as mismatch:
        await knowledge_bases.ensure_team_authorized_model(
            team_id, model_id, "embedding"
        )
    assert mismatch.value.code == ResponseCode.VALIDATION_ERROR

    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as missing:
        await knowledge_bases.ensure_team_authorized_model(team_id, model_id, "rerank")
    assert missing.value.code == ResponseCode.MODEL_NOT_FOUND


@pytest.mark.anyio
@pytest.mark.parametrize("use_file", [True, False])
async def test_preview_document_chunks_uses_available_source(monkeypatch, use_file):
    kb_id, doc_id = uuid4(), uuid4()
    doc = SimpleNamespace(
        file_path="document.txt" if use_file else None,
        source_url=None if use_file else "https://example.test/document",
        doc_type="txt",
    )
    extract = AsyncMock(return_value=("preview text", {}))
    fetch = AsyncMock(return_value=("preview text", {}))
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document, "filter", lambda **_kwargs: Query(doc)
    )
    monkeypatch.setattr(knowledge_bases.document_processor, "extract_text", extract)
    monkeypatch.setattr(knowledge_bases.document_processor, "fetch_url_content", fetch)
    processor_module = importlib.import_module("app.services.document_processor")
    monkeypatch.setattr(
        processor_module,
        "chunk_text",
        lambda *_args, **_kwargs: [
            {
                "chunk_index": 0,
                "content": "preview text",
                "token_count": 3,
                "char_count": 12,
            }
        ],
    )
    preview = SimpleNamespace(
        clean_text=True, chunk_size=100, chunk_overlap=10, separator=None
    )

    response = await knowledge_bases.preview_document_chunks(
        kb_id=kb_id,
        doc_id=doc_id,
        preview_in=preview,
        current_user=SimpleNamespace(),
    )

    assert response["data"].total_chunks == 1
    assert extract.await_count == int(use_file)
    assert fetch.await_count == int(not use_file)


@pytest.mark.anyio
async def test_preview_document_chunks_rejects_missing_source(monkeypatch):
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace(file_path=None, source_url=None)),
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.preview_document_chunks(
            kb_id=uuid4(),
            doc_id=uuid4(),
            preview_in=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )
    assert exc.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (DimensionMismatchError("wrong dimension"), ResponseCode.VALIDATION_ERROR),
        (RuntimeError("search unavailable"), ResponseCode.UNKNOWN_ERROR),
    ],
)
async def test_search_maps_vector_store_errors(monkeypatch, failure, expected_code):
    kb = SimpleNamespace(
        id=uuid4(),
        name="kb",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        team_id=uuid4(),
    )
    retrieve = AsyncMock(side_effect=failure)
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)
    search = SimpleNamespace(
        query="query",
        search_mode="hybrid",
        top_k=5,
        score_threshold=0.1,
        filter_doc_ids=None,
        model_fields_set=set(),
    )

    with pytest.raises(BusinessError) as exc:
        await knowledge_bases.search_knowledge_base(uuid4(), search, SimpleNamespace())
    assert exc.value.code == expected_code


@pytest.mark.anyio
async def test_search_passes_explicit_rerank_overrides(monkeypatch):
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
    retrieve = AsyncMock(return_value=SimpleNamespace(results=({"content": "match"},)))
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)
    search = SimpleNamespace(
        query="query",
        search_mode="hybrid",
        top_k=5,
        score_threshold=0.1,
        filter_doc_ids=None,
        rerank_enabled=True,
        rerank_candidate_k=None,
        rerank_fail_open=None,
        rerank_score_threshold=None,
        model_fields_set={"rerank_enabled"},
    )

    response = await knowledge_bases.search_knowledge_base(
        kb_id, search, SimpleNamespace()
    )

    assert response["data"]["total"] == 1
    assert retrieve.await_args.args[0].rerank_overrides == {"rerank_enabled": True}
