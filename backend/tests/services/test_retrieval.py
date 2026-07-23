import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services import retrieval

KB_1 = UUID("00000000-0000-0000-0000-000000000001")
KB_2 = UUID("00000000-0000-0000-0000-000000000002")
TEAM_ID = UUID("00000000-0000-0000-0000-000000000003")
MODEL_ID = UUID("00000000-0000-0000-0000-000000000004")
DOC_1 = UUID("00000000-0000-0000-0000-000000000005")
DOC_2 = UUID("00000000-0000-0000-0000-000000000006")


def target(kb_id=KB_1, **overrides):
    values = {
        "kb_id": kb_id,
        "kb_name": f"kb-{kb_id}",
        "team_id": TEAM_ID,
        "status": "active",
        "embedding_model_id": MODEL_ID,
    }
    values.update(overrides)
    return retrieval.RetrievalTarget(**values)


def request(*targets, **overrides):
    values = {"query": "question", "targets": targets or (target(),)}
    values.update(overrides)
    return retrieval.RetrievalRequest(**values)


def install_store(monkeypatch, search):
    stores = []

    def factory(**kwargs):
        store = SimpleNamespace(search=search, kwargs=kwargs)
        stores.append(store)
        return store

    monkeypatch.setattr(retrieval, "VectorStore", factory)
    return stores


@pytest.mark.asyncio
async def test_success_preserves_raw_fields_and_forwards_target_configuration(
    monkeypatch,
):
    search = AsyncMock(
        return_value=[
            {
                "chunk_id": "chunk-1",
                "document_id": str(DOC_1),
                "score": 0.8,
                "dense_score": 0.7,
                "dense_rank": 2,
                "final_score_stage": "fusion",
            }
        ]
    )
    stores = install_store(monkeypatch, search)
    selected = target(
        allowed_document_ids=frozenset({DOC_1, DOC_2}),
        document_ids=frozenset({DOC_1}),
        rerank_model_id=MODEL_ID,
        embedding_dimension=1536,
    )

    response = await retrieval.retrieve(request(selected))

    assert response.results[0] == {
        "chunk_id": "chunk-1",
        "document_id": str(DOC_1),
        "score": 0.8,
        "dense_score": 0.7,
        "dense_rank": 2,
        "final_score_stage": "fusion",
        "kb_id": str(KB_1),
        "kb_name": selected.kb_name,
    }
    assert response.diagnostics == ()
    assert stores[0].kwargs == {
        "embedding_model_id": str(MODEL_ID),
        "rerank_model_id": str(MODEL_ID),
        "team_id": str(TEAM_ID),
    }
    assert search.await_args.kwargs["filter_doc_ids"] == [DOC_1]
    assert search.await_args.kwargs["embedding_dimension"] == 1536


@pytest.mark.asyncio
async def test_target_can_override_association_search_configuration(monkeypatch):
    search = AsyncMock(return_value=[])
    install_store(monkeypatch, search)

    await retrieval.retrieve(
        request(
            target(search_mode="fulltext", top_k=2, score_threshold=0.7),
            search_mode="hybrid",
            top_k=5,
        )
    )

    assert search.await_args.kwargs["search_mode"] == "fulltext"
    assert search.await_args.kwargs["top_k"] == 2
    assert search.await_args.kwargs["score_threshold"] == 0.7


def test_rejects_document_scope_wider_than_authorized_target():
    with pytest.raises(ValueError, match="within allowed_document_ids"):
        target(
            allowed_document_ids=frozenset({DOC_1}),
            document_ids=frozenset({DOC_1, DOC_2}),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"query": "  "}, "query must not be empty"),
        ({"search_mode": "semantic"}, "unsupported search mode"),
        ({"top_k": 0}, "top_k must be positive"),
        ({"timeout_seconds": 0}, "timeout_seconds must be positive"),
    ],
)
def test_rejects_invalid_request(overrides, message):
    with pytest.raises(ValueError, match=message):
        request(**overrides)


@pytest.mark.asyncio
async def test_timeout_has_explicit_diagnostic_and_fails_single_target(monkeypatch):
    async def slow_search(**_kwargs):
        await asyncio.sleep(1)

    install_store(monkeypatch, slow_search)

    with pytest.raises(
        retrieval.RetrievalError, match="all retrieval targets failed"
    ) as exc_info:
        await retrieval.retrieve(request(timeout_seconds=0.001))

    assert exc_info.value.diagnostics == (
        retrieval.RetrievalDiagnostic(KB_1, "timeout"),
    )


@pytest.mark.asyncio
async def test_one_target_failure_isolated_but_dual_failure_raises(monkeypatch):
    async def search(**kwargs):
        if kwargs["kb_id"] == KB_1:
            raise RuntimeError("provider unavailable")
        return [{"chunk_id": "ok", "document_id": str(DOC_2), "score": 0.5}]

    install_store(monkeypatch, search)
    response = await retrieval.retrieve(request(target(KB_1), target(KB_2)))

    assert [item["chunk_id"] for item in response.results] == ["ok"]
    assert response.diagnostics == (
        retrieval.RetrievalDiagnostic(KB_1, "failed", "RuntimeError"),
    )

    async def fail(**_kwargs):
        raise RuntimeError("provider unavailable")

    install_store(monkeypatch, fail)
    with pytest.raises(retrieval.RetrievalError, match="all retrieval targets failed"):
        await retrieval.retrieve(request(target(KB_1), target(KB_2)))


@pytest.mark.asyncio
async def test_lexical_only_target_runs_without_embedding_model(monkeypatch):
    search = AsyncMock(return_value=[])
    stores = install_store(monkeypatch, search)

    response = await retrieval.retrieve(
        request(target(embedding_model_id=None), search_mode="fulltext")
    )

    assert response.diagnostics == ()
    assert stores[0].kwargs["embedding_model_id"] is None
    search.assert_awaited_once()


@pytest.mark.asyncio
async def test_vector_only_missing_model_and_inactive_target_fail_explicitly(
    monkeypatch,
):
    search = AsyncMock()
    install_store(monkeypatch, search)

    with pytest.raises(retrieval.RetrievalError, match="all retrieval targets failed"):
        await retrieval.retrieve(
            request(
                target(KB_1, embedding_model_id=None),
                target(KB_2, status="archived"),
                search_mode="vector",
            )
        )
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_order_and_truncate_are_deterministic(monkeypatch):
    async def search(**kwargs):
        if kwargs["kb_id"] == KB_1:
            return [
                {"chunk_id": "b", "document_id": "doc", "score": 0.9},
                {"chunk_id": "low", "document_id": "doc", "score": 0.1},
            ]
        return [
            {"chunk_id": "a", "document_id": "doc", "score": 0.9},
            {"chunk_id": "top", "document_id": "doc", "score": 1.0},
        ]

    install_store(monkeypatch, search)

    response = await retrieval.retrieve(request(target(KB_2), target(KB_1), top_k=3))

    assert [(item["kb_id"], item["chunk_id"]) for item in response.results] == [
        (str(KB_2), "top"),
        (str(KB_1), "b"),
        (str(KB_2), "a"),
    ]
