import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
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


def install_store(monkeypatch, search, lexical_hits=None):
    stores = []

    def factory(**kwargs):
        store = SimpleNamespace(search=search, kwargs=kwargs)
        stores.append(store)
        return store

    lexical = MagicMock()
    lexical.search = AsyncMock(return_value=lexical_hits or [])
    lexical.__aenter__ = AsyncMock(return_value=lexical)
    lexical.__aexit__ = AsyncMock(return_value=None)
    lexical.__aenter__.return_value = lexical
    monkeypatch.setattr(retrieval, "VectorStore", factory)
    monkeypatch.setattr(retrieval, "LexicalStore", lambda: lexical)
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

    response = await retrieval.retrieve(request(selected, search_mode="vector"))

    assert response.results[0] == {
        "chunk_id": "chunk-1",
        "document_id": str(DOC_1),
        "score": 0.8,
        "dense_score": 0.7,
        "dense_rank": 1,
        "final_score_stage": "dense",
        "search_type": "vector",
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
    assert search.await_args.kwargs["search_mode"] == "vector"
    assert search.await_args.kwargs["rerank_overrides"] == {"rerank_enabled": False}


@pytest.mark.asyncio
async def test_target_can_override_association_search_configuration(monkeypatch):
    search = AsyncMock(return_value=[])
    stores = install_store(monkeypatch, search)

    await retrieval.retrieve(
        request(
            target(search_mode="vector", top_k=2, score_threshold=0.7),
            search_mode="hybrid",
            top_k=5,
        )
    )

    assert search.await_args.kwargs["search_mode"] == "vector"
    assert search.await_args.kwargs["top_k"] == 2
    assert search.await_args.kwargs["score_threshold"] == 0.7
    assert stores


def test_rejects_invalid_target_configuration():
    with pytest.raises(ValueError, match="within allowed_document_ids"):
        target(
            allowed_document_ids=frozenset({DOC_1}),
            document_ids=frozenset({DOC_1, DOC_2}),
        )
    with pytest.raises(ValueError, match="unsupported search mode"):
        target(search_mode="semantic")
    with pytest.raises(ValueError, match="top_k must be positive"):
        target(top_k=0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"query": "  "}, "query must not be empty"),
        ({"search_mode": "semantic"}, "unsupported search mode"),
        ({"top_k": 0}, "top_k must be positive"),
        ({"timeout_seconds": 0}, "timeout_seconds must be positive"),
        ({"dense_weight": -1}, "weights must be nonnegative"),
        ({"lexical_weight": -1}, "weights must be nonnegative"),
        (
            {"dense_weight": 0, "lexical_weight": 0},
            "at least one retrieval weight must be positive",
        ),
        ({"rrf_k": 0}, "rrf_k must be positive"),
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
    response = await retrieval.retrieve(
        request(target(KB_1), target(KB_2), search_mode="vector")
    )

    assert [item["chunk_id"] for item in response.results] == ["ok"]
    assert response.diagnostics == (
        retrieval.RetrievalDiagnostic(KB_1, "failed", "provider unavailable"),
    )

    async def fail(**_kwargs):
        raise RuntimeError("provider unavailable")

    install_store(monkeypatch, fail)
    with pytest.raises(retrieval.RetrievalError, match="all retrieval targets failed"):
        await retrieval.retrieve(
            request(target(KB_1), target(KB_2), search_mode="vector")
        )


@pytest.mark.asyncio
async def test_fulltext_returns_raw_bm25_and_applies_all_scopes(monkeypatch):
    search = AsyncMock()
    hit = retrieval.SearchHit(
        chunk_id="chunk-1",
        score=12.5,
        source={"document_id": str(DOC_1), "content": "match"},
    )
    install_store(monkeypatch, search, [hit])
    selected = target(
        embedding_model_id=None,
        allowed_document_ids=frozenset({DOC_1, DOC_2}),
        document_ids=frozenset({DOC_1}),
    )

    response = await retrieval.retrieve(request(selected, search_mode="fulltext"))

    assert response.results[0]["score"] == 12.5
    assert response.results[0]["lexical_score"] == 12.5
    assert response.results[0]["lexical_rank"] == 1
    assert response.results[0]["final_score_stage"] == "lexical"
    lexical = retrieval.LexicalStore()
    lexical.search.assert_awaited_once_with(
        "question",
        team_id=str(TEAM_ID),
        kb_ids=[str(KB_1)],
        document_ids=[str(DOC_1)],
        limit=5,
    )
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_hybrid_without_embedding_model_uses_lexical_only(monkeypatch):
    dense = AsyncMock()
    hit = retrieval.SearchHit(
        chunk_id="lexical",
        score=8.0,
        source={"document_id": str(DOC_1)},
    )
    install_store(monkeypatch, dense, [hit])

    response = await retrieval.retrieve(
        request(target(embedding_model_id=None), search_mode="hybrid")
    )

    assert response.results[0]["chunk_id"] == "lexical"
    assert response.results[0]["degradation_reasons"] == [
        {"channel": "dense", "error": "RuntimeError"}
    ]
    dense.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_document_scope_does_not_query_stores(monkeypatch):
    search = AsyncMock()
    install_store(monkeypatch, search)

    response = await retrieval.retrieve(
        request(target(allowed_document_ids=frozenset()))
    )

    assert response.results == ()
    search.assert_not_awaited()
    retrieval.LexicalStore().search.assert_not_awaited()


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

    response = await retrieval.retrieve(
        request(target(KB_2), target(KB_1), top_k=3, search_mode="vector")
    )

    assert [(item["kb_id"], item["chunk_id"]) for item in response.results] == [
        (str(KB_2), "top"),
        (str(KB_1), "b"),
        (str(KB_2), "a"),
    ]


@pytest.mark.asyncio
async def test_hybrid_weighted_rrf_preserves_channel_fields_and_ties(monkeypatch):
    dense = AsyncMock(
        return_value=[
            {"chunk_id": "b", "document_id": "doc", "score": 0.9},
            {"chunk_id": "shared", "document_id": "doc", "score": 0.8},
        ]
    )
    hits = [
        retrieval.SearchHit("a", 20.0, {"document_id": "doc"}),
        retrieval.SearchHit("shared", 10.0, {"document_id": "doc"}),
    ]
    install_store(monkeypatch, dense, hits)

    response = await retrieval.retrieve(
        request(dense_weight=2.0, lexical_weight=1.0, rrf_k=60, top_k=3)
    )

    assert [item["chunk_id"] for item in response.results] == ["shared", "b", "a"]
    shared = response.results[0]
    assert shared["dense_score"] == 0.8
    assert shared["dense_rank"] == 2
    assert shared["lexical_score"] == 10.0
    assert shared["lexical_rank"] == 2
    assert shared["fusion_score"] == pytest.approx(3 / 62)
    assert shared["fusion_rank"] == 1
    assert shared["final_score_stage"] == "fusion"


@pytest.mark.asyncio
async def test_hybrid_weighted_rrf_allows_zero_weight_channel(monkeypatch):
    dense = AsyncMock(
        return_value=[{"chunk_id": "dense", "document_id": "doc", "score": 0.9}]
    )
    hits = [retrieval.SearchHit("lexical", 20.0, {"document_id": "doc"})]
    install_store(monkeypatch, dense, hits)

    response = await retrieval.retrieve(request(dense_weight=0.0, lexical_weight=1.0))

    assert [item["chunk_id"] for item in response.results] == ["lexical"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failing_channel", "healthy_chunk"), [("dense", "lex"), ("lexical", "dense")]
)
async def test_hybrid_degrades_to_healthy_channel(
    monkeypatch, failing_channel, healthy_chunk
):
    dense = AsyncMock(
        side_effect=RuntimeError("qdrant down") if failing_channel == "dense" else None,
        return_value=[{"chunk_id": "dense", "document_id": "doc", "score": 0.8}],
    )
    lexical_hits = (
        []
        if failing_channel == "lexical"
        else [retrieval.SearchHit("lex", 9.0, {"document_id": "doc"})]
    )
    install_store(monkeypatch, dense, lexical_hits)
    if failing_channel == "lexical":
        lexical = retrieval.LexicalStore()
        lexical.search.side_effect = RuntimeError("opensearch down")

    response = await retrieval.retrieve(request())

    assert response.results[0]["chunk_id"] == healthy_chunk
    assert response.results[0]["degradation_reasons"] == [
        {"channel": failing_channel, "error": "RuntimeError"}
    ]


@pytest.mark.asyncio
async def test_hybrid_dual_failure_and_fulltext_failure_are_explicit(monkeypatch):
    dense = AsyncMock(side_effect=RuntimeError("qdrant down"))
    install_store(monkeypatch, dense)
    lexical = retrieval.LexicalStore()
    lexical.search.side_effect = RuntimeError("opensearch down")

    with pytest.raises(retrieval.RetrievalError) as hybrid_error:
        await retrieval.retrieve(request())
    assert "both retrieval channels failed" in hybrid_error.value.diagnostics[0].detail

    with pytest.raises(retrieval.RetrievalError) as fulltext_error:
        await retrieval.retrieve(request(search_mode="fulltext"))
    assert fulltext_error.value.diagnostics[0].detail == "opensearch down"
