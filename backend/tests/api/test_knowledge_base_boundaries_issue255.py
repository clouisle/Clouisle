from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.knowledge_base import SearchRequest, SearchResponse
from app.schemas.response import BusinessError, Response, ResponseCode
from app.services.retrieval import RetrievalDiagnostic, RetrievalError
from app.services.vector_store import DimensionMismatchError


def _query_with_first(value):
    query = MagicMock()
    query.first = AsyncMock(return_value=value)
    return query


@pytest.mark.anyio
async def test_dispatch_document_task_records_and_rolls_back_metadata(monkeypatch):
    doc = SimpleNamespace(metadata=None, save=AsyncMock())
    task = SimpleNamespace(name="process-document", apply_async=MagicMock())
    monkeypatch.setattr(knowledge_bases, "uuid4", lambda: "task-id")

    task_id = await knowledge_bases._dispatch_document_task(doc, task, "doc-id")

    assert task_id == "task-id"
    assert doc.metadata == {
        "task_id": "task-id",
        "task_name": "process-document",
        "task_args": ["doc-id"],
    }
    task.apply_async.assert_called_once_with(args=("doc-id",), task_id="task-id")

    task.apply_async.side_effect = RuntimeError("broker unavailable")
    with pytest.raises(RuntimeError, match="broker unavailable"):
        await knowledge_bases._dispatch_document_task(doc, task, "doc-id")

    assert doc.metadata == {}
    doc.save.assert_awaited_with(update_fields=["metadata"])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("team", "membership", "require_admin", "expected_code"),
    [
        (None, None, False, ResponseCode.TEAM_NOT_FOUND),
        (SimpleNamespace(id="team"), None, False, ResponseCode.NOT_TEAM_MEMBER),
        (
            SimpleNamespace(id="team"),
            SimpleNamespace(role="member"),
            True,
            ResponseCode.TEAM_ADMIN_REQUIRED,
        ),
    ],
)
async def test_check_team_access_rejects_missing_or_unauthorized_users(
    monkeypatch, team, membership, require_admin, expected_code
):
    team_filter = MagicMock(return_value=_query_with_first(team))
    member_filter = MagicMock(return_value=_query_with_first(membership))
    monkeypatch.setattr(knowledge_bases.Team, "filter", team_filter)
    monkeypatch.setattr(knowledge_bases.TeamMember, "filter", member_filter)
    knowledge_bases._kb_access_mode.set("platform")
    user = SimpleNamespace(is_superuser=False)

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.check_team_access(
            uuid4(), user, require_admin=require_admin
        )

    assert exc_info.value.code == expected_code


@pytest.mark.anyio
async def test_check_kb_access_allows_owner_write_but_requires_admin_otherwise(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    kb = SimpleNamespace(
        created_by=SimpleNamespace(id=user.id), team=SimpleNamespace(id=uuid4())
    )
    query = _query_with_first(kb)
    query.prefetch_related.return_value = query
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", MagicMock(return_value=query)
    )
    check_team = AsyncMock(return_value=kb.team)
    monkeypatch.setattr(knowledge_bases, "check_team_access", check_team)
    knowledge_bases._kb_access_mode.set("platform")

    assert (
        await knowledge_bases.check_kb_access(uuid4(), user, require_write=True) is kb
    )
    check_team.assert_awaited_once_with(kb.team.id, user)

    check_team.reset_mock()
    await knowledge_bases.check_kb_access(
        uuid4(), user, require_write=True, allow_owner_write=False
    )
    assert check_team.await_args_list[1].kwargs == {"require_admin": True}


@pytest.mark.anyio
async def test_download_document_uses_storage_backend_and_rejects_missing_object(
    monkeypatch,
):
    kb_id, doc_id = uuid4(), uuid4()
    user = SimpleNamespace()
    doc = SimpleNamespace(file_path="uploads/file.pdf", doc_type="pdf", name="file.pdf")
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        MagicMock(return_value=_query_with_first(doc)),
    )
    monkeypatch.setattr(
        knowledge_bases.document_processor, "_storage_key", lambda _: "file.pdf"
    )
    monkeypatch.setattr(
        knowledge_bases.document_processor, "_storage_root", lambda: "/uploads"
    )
    response = object()
    storage = SimpleNamespace(
        exists=AsyncMock(return_value=False), response=AsyncMock(return_value=response)
    )
    monkeypatch.setattr(
        knowledge_bases, "get_upload_storage_backend", AsyncMock(return_value=storage)
    )

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.download_document(kb_id, doc_id, user)
    assert exc_info.value.msg_key == "file_not_found"

    storage.exists.return_value = True
    assert await knowledge_bases.download_document(kb_id, doc_id, user) is response
    storage.response.assert_awaited_once_with(
        "file.pdf", content_type="application/pdf", filename="file.pdf"
    )


@pytest.mark.anyio
async def test_search_passes_explicit_rerank_overrides(monkeypatch):
    kb_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        embedding_dimension=None,
        team_id=uuid4(),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    retrieve = AsyncMock(return_value=SimpleNamespace(results=({"score": 0.9},)))
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)
    search_in = SearchRequest(query="policy", rerank_enabled=False, top_k=3)

    result = await knowledge_bases.search_knowledge_base(
        kb_id, search_in, SimpleNamespace()
    )

    assert result["data"]["total"] == 1
    request = retrieve.await_args.args[0]
    assert request.query == "policy"
    assert request.search_mode == "hybrid"
    assert request.top_k == 3
    assert request.score_threshold == 0.0
    assert request.rerank_overrides == {"rerank_enabled": False}
    assert request.targets[0].document_ids is None


@pytest.mark.anyio
async def test_search_fulltext_result_matches_response_model(monkeypatch):
    kb_id = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        team_id=uuid4(),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        "app.services.retrieval.retrieve",
        AsyncMock(
            return_value=SimpleNamespace(
                results=(
                    {
                        "chunk_id": str(chunk_id),
                        "document_id": str(document_id),
                        "document_name": "Policy.pdf",
                        "content": "match",
                        "score": 12.5,
                        "metadata": {},
                        "search_type": "fulltext",
                        "lexical_score": 12.5,
                        "lexical_rank": 1,
                        "final_score_stage": "lexical",
                    },
                ),
                diagnostics=(),
                timings=(),
            )
        ),
    )

    result = await knowledge_bases.search_knowledge_base(
        kb_id,
        SearchRequest(query="policy", search_mode="fulltext"),
        SimpleNamespace(),
    )

    response = Response[SearchResponse].model_validate(result)
    assert response.data is not None
    assert response.data.results[0].document_name == "Policy.pdf"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "code", "msg_key", "data"),
    [
        (
            DimensionMismatchError("expected 3, got 4"),
            ResponseCode.VALIDATION_ERROR,
            "kb_embedding_dimension_mismatch",
            {"retrieval_error_category": "configuration_mismatch"},
        ),
        (
            RetrievalError(
                "all retrieval targets failed",
                (
                    RetrievalDiagnostic(
                        uuid4(), "failed", DimensionMismatchError.__name__
                    ),
                ),
            ),
            ResponseCode.VALIDATION_ERROR,
            "kb_embedding_dimension_mismatch",
            {"retrieval_error_category": "configuration_mismatch"},
        ),
        (
            RetrievalError(
                "all retrieval targets failed",
                (
                    RetrievalDiagnostic(
                        uuid4(),
                        "failed",
                        "dense=DimensionMismatchError; lexical=LexicalStoreError",
                    ),
                ),
            ),
            ResponseCode.VALIDATION_ERROR,
            "kb_embedding_dimension_mismatch",
            {"retrieval_error_category": "configuration_mismatch"},
        ),
        (
            RetrievalError("all retrieval targets failed", ()),
            ResponseCode.UNKNOWN_ERROR,
            "vector_search_failed",
            {"retrieval_error_category": "unknown", "stage": None},
        ),
    ],
)
async def test_search_translates_vector_store_failures(
    monkeypatch, failure, code, msg_key, data
):
    kb = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        team_id=uuid4(),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        "app.services.retrieval.retrieve", AsyncMock(side_effect=failure)
    )

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.search_knowledge_base(
            uuid4(), SearchRequest(query="policy"), SimpleNamespace()
        )

    assert exc_info.value.code == code
    assert exc_info.value.msg_key == msg_key
    assert exc_info.value.data == data


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("detail", "code", "category"),
    [
        (
            "AuthenticationError",
            ResponseCode.MODEL_NOT_AUTHORIZED,
            "provider_authentication",
        ),
        ("RateLimitError", ResponseCode.RATE_LIMITED, "quota_or_rate_limit"),
        (
            "InsufficientQuotaError",
            ResponseCode.MODEL_QUOTA_EXCEEDED,
            "quota_or_rate_limit",
        ),
        ("ModelNotFoundError", ResponseCode.MODEL_NOT_FOUND, "model_configuration"),
        ("ModelDisabledError", ResponseCode.UNKNOWN_ERROR, "model_configuration"),
        ("LexicalStoreError", ResponseCode.UNKNOWN_ERROR, "lexical_unavailable"),
        (
            "VectorSearchUnavailableError",
            ResponseCode.UNKNOWN_ERROR,
            "provider_unavailable",
        ),
        (
            "dense=ProviderError; lexical=ProviderError",
            ResponseCode.UNKNOWN_ERROR,
            "provider_unavailable",
        ),
        (
            "dense=AuthenticationError; lexical=LexicalStoreError",
            ResponseCode.UNKNOWN_ERROR,
            "unknown",
        ),
        ("UnexpectedProviderBody", ResponseCode.UNKNOWN_ERROR, "unknown"),
    ],
)
async def test_search_returns_safe_retrieval_error_categories(
    monkeypatch, detail, code, category
):
    kb_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        team_id=uuid4(),
    )
    failure = RetrievalError(
        "all retrieval targets failed",
        (RetrievalDiagnostic(kb_id, "failed", detail),),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        "app.services.retrieval.retrieve", AsyncMock(side_effect=failure)
    )

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.search_knowledge_base(
            kb_id, SearchRequest(query="policy"), SimpleNamespace()
        )

    assert exc_info.value.code == code
    assert exc_info.value.data == {
        "retrieval_error_category": category,
        "stage": None,
    }
    assert detail not in str(exc_info.value.data)


@pytest.mark.anyio
async def test_search_error_category_never_returns_raw_diagnostics(monkeypatch):
    kb_id = uuid4()
    raw_detail = "https://internal.invalid secret-token provider response"
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        team_id=uuid4(),
    )
    failure = RetrievalError(
        "all retrieval targets failed",
        (RetrievalDiagnostic(kb_id, "failed", raw_detail),),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        "app.services.retrieval.retrieve", AsyncMock(side_effect=failure)
    )

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.search_knowledge_base(
            kb_id, SearchRequest(query="policy"), SimpleNamespace()
        )

    assert exc_info.value.data == {
        "retrieval_error_category": "unknown",
        "stage": None,
    }
    assert raw_detail not in str(exc_info.value.data)


@pytest.mark.anyio
async def test_search_logs_sanitized_retrieval_diagnostics(monkeypatch):
    kb_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        team_id=uuid4(),
    )
    diagnostic_detail = "dense=VectorSearchUnavailableError; lexical=LexicalStoreError"
    failure = RetrievalError(
        "all retrieval targets failed",
        (RetrievalDiagnostic(kb_id, "failed", diagnostic_detail),),
    )
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        "app.services.retrieval.retrieve", AsyncMock(side_effect=failure)
    )
    log_exception = MagicMock()
    monkeypatch.setattr(knowledge_bases.logger, "exception", log_exception)

    with pytest.raises(BusinessError) as exc_info:
        await knowledge_bases.search_knowledge_base(
            kb_id, SearchRequest(query="policy"), SimpleNamespace()
        )

    assert exc_info.value.msg_key == "vector_search_failed"
    log_exception.assert_called_once_with(
        "Knowledge retrieval failed: kb_id=%s diagnostics=%s",
        kb_id,
        [
            {
                "kb_id": str(kb_id),
                "code": "failed",
                "detail": diagnostic_detail,
                "stage": None,
            }
        ],
    )


def test_upload_size_and_error_serialization_boundaries(monkeypatch):
    monkeypatch.setattr(
        knowledge_bases, "has_translation", lambda value: value == "known_key"
    )
    monkeypatch.setattr(knowledge_bases, "t", lambda value: f"translated:{value}")
    monkeypatch.setattr(
        knowledge_bases,
        "is_safe_user_visible_error",
        lambda value: value == "safe detail",
    )

    assert (
        knowledge_bases.serialize_knowledge_base_error("  known_key ")
        == "translated:known_key"
    )
    assert (
        knowledge_bases.serialize_knowledge_base_error(" safe detail ") == "safe detail"
    )
    assert (
        knowledge_bases.serialize_knowledge_base_error("internal secret")
        == "translated:unknown_error"
    )
    assert knowledge_bases.serialize_knowledge_base_error("   ") is None
