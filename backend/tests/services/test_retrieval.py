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


def install_store(
    monkeypatch,
    search,
    lexical_hits=None,
    *,
    rerank_config=None,
    rerank_results=None,
):
    stores = []

    def factory(**kwargs):
        store = SimpleNamespace(
            search=search,
            kwargs=kwargs,
            _resolve_rerank_config=AsyncMock(
                return_value=rerank_config
                or {
                    "enabled": False,
                    "model_id": None,
                    "candidate_k": 10,
                    "score_threshold": None,
                }
            ),
            _rerank_results=AsyncMock(
                side_effect=rerank_results or (lambda **values: values["results"])
            ),
        )
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
    assert [timing.stage for timing in response.timings] == [
        "recall",
        "rerank",
        "context",
        "total",
    ]
    assert all(timing.latency_ms >= 0 for timing in response.timings)
    dense_store = next(
        store for store in stores if store.kwargs.get("embedding_model_id")
    )
    assert dense_store.kwargs == {
        "embedding_model_id": str(MODEL_ID),
        "rerank_model_id": str(MODEL_ID),
        "team_id": str(TEAM_ID),
    }
    assert search.await_args.kwargs["filter_doc_ids"] == [DOC_1]
    assert search.await_args.kwargs["embedding_dimension"] == 1536
    assert search.await_args.kwargs["search_mode"] == "vector"
    assert search.await_args.kwargs["rerank_overrides"] == {"rerank_enabled": False}


@pytest.mark.asyncio
async def test_single_target_inherits_kb_retrieval_defaults(monkeypatch):
    search = AsyncMock(return_value=[])
    hit = retrieval.SearchHit("lexical", 8.0, {"document_id": str(DOC_1)})
    install_store(monkeypatch, search, [hit])

    response = await retrieval.retrieve(
        request(
            target(
                settings={
                    "search_mode": "fulltext",
                    "top_k": 2,
                    "score_threshold": 0.7,
                    "dense_weight": 0.25,
                    "lexical_weight": 1.5,
                    "rrf_k": 20,
                }
            )
        )
    )

    assert response.results[0]["chunk_id"] == "lexical"
    retrieval.LexicalStore().search.assert_awaited_once()
    search.assert_not_awaited()


def test_null_kb_global_defaults_fall_back_to_system_defaults():
    effective = retrieval._effective_request(
        request(
            target(
                settings={
                    "dense_weight": None,
                    "lexical_weight": None,
                    "rrf_k": None,
                }
            )
        )
    )

    assert effective.dense_weight == 1
    assert effective.lexical_weight == 1
    assert effective.rrf_k == 60


@pytest.mark.asyncio
async def test_explicit_configuration_overrides_kb_defaults(monkeypatch):
    search = AsyncMock(return_value=[])
    stores = install_store(monkeypatch, search)

    await retrieval.retrieve(
        request(
            target(
                settings={
                    "search_mode": "fulltext",
                    "top_k": 9,
                    "score_threshold": 0.2,
                    "dense_weight": 4,
                    "lexical_weight": 3,
                    "rrf_k": 10,
                },
                search_mode="vector",
                top_k=2,
                score_threshold=0.7,
            ),
            search_mode="hybrid",
            top_k=5,
            dense_weight=2,
            lexical_weight=1,
            rrf_k=30,
        )
    )

    assert search.await_args.kwargs["search_mode"] == "vector"
    assert search.await_args.kwargs["top_k"] == 2
    assert search.await_args.kwargs["score_threshold"] == 0.7
    assert stores


@pytest.mark.asyncio
async def test_multi_target_ignores_conflicting_global_kb_defaults(monkeypatch):
    dense = AsyncMock(
        return_value=[{"chunk_id": "dense", "document_id": "doc", "score": 0.9}]
    )
    hits = [retrieval.SearchHit("lexical", 20.0, {"document_id": "doc"})]
    install_store(monkeypatch, dense, hits)
    targets = (
        target(KB_1, settings={"dense_weight": 0, "lexical_weight": 5, "rrf_k": 1}),
        target(KB_2, settings={"dense_weight": 5, "lexical_weight": 0, "rrf_k": 2}),
    )

    first = await retrieval.retrieve(request(*targets, top_k=4))
    second = await retrieval.retrieve(request(*reversed(targets), top_k=4))

    assert [(item["kb_id"], item["chunk_id"]) for item in first.results] == [
        (item["kb_id"], item["chunk_id"]) for item in second.results
    ]
    assert {item["chunk_id"] for item in first.results} == {"dense", "lexical"}


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
        retrieval.RetrievalDiagnostic(KB_1, "timeout", stage="recall"),
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
        retrieval.RetrievalDiagnostic(KB_1, "failed", "RuntimeError", "dense_recall"),
    )
    assert "provider unavailable" not in response.diagnostics[0].detail

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
        source={
            "document_id": str(DOC_1),
            "name": "Policy.pdf",
            "content": "match",
        },
    )
    install_store(monkeypatch, search, [hit])
    selected = target(
        embedding_model_id=None,
        allowed_document_ids=frozenset({DOC_1, DOC_2}),
        document_ids=frozenset({DOC_1}),
    )

    response = await retrieval.retrieve(request(selected, search_mode="fulltext"))

    assert response.results[0]["score"] == 12.5
    assert response.results[0]["document_name"] == "Policy.pdf"
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
    dense = AsyncMock(side_effect=RuntimeError("qdrant secret response"))
    install_store(monkeypatch, dense)
    lexical = retrieval.LexicalStore()
    lexical.search.side_effect = ValueError("opensearch secret response")

    with pytest.raises(retrieval.RetrievalError) as hybrid_error:
        await retrieval.retrieve(request())
    hybrid_detail = hybrid_error.value.diagnostics[0].detail
    assert hybrid_detail == "dense=RuntimeError; lexical=ValueError"
    assert "qdrant secret response" not in hybrid_detail
    assert "opensearch secret response" not in hybrid_detail

    with pytest.raises(retrieval.RetrievalError) as fulltext_error:
        await retrieval.retrieve(request(search_mode="fulltext"))
    assert fulltext_error.value.diagnostics[0].detail == "ValueError"
    assert (
        "opensearch secret response" not in fulltext_error.value.diagnostics[0].detail
    )


@pytest.mark.asyncio
async def test_global_rerank_runs_once_after_cross_kb_ranking(monkeypatch):
    async def search(**kwargs):
        return [
            {
                "chunk_id": f"chunk-{kwargs['kb_id']}",
                "document_id": str(DOC_1),
                "content": str(kwargs["kb_id"]),
                "score": 0.8 if kwargs["kb_id"] == KB_1 else 0.9,
            }
        ]

    async def rerank(**values):
        assert [item["kb_id"] for item in values["results"]] == [
            str(KB_2),
            str(KB_1),
        ]
        reranked = list(reversed(values["results"]))
        for rank, item in enumerate(reranked, 1):
            item.update(
                score=1 / rank,
                rerank_score=1 / rank,
                rerank_rank=rank,
                final_score_stage="rerank",
            )
        return reranked

    stores = install_store(
        monkeypatch,
        search,
        rerank_config={
            "enabled": True,
            "model_id": str(MODEL_ID),
            "candidate_k": 20,
            "score_threshold": None,
        },
        rerank_results=rerank,
    )

    response = await retrieval.retrieve(
        request(
            target(KB_1, rerank_model_id=MODEL_ID),
            target(KB_2, rerank_model_id=MODEL_ID),
            search_mode="vector",
        )
    )

    assert [item["kb_id"] for item in response.results] == [str(KB_1), str(KB_2)]
    rerank_stores = [
        store
        for store in stores
        if store.kwargs.get("rerank_model_id")
        and not store.kwargs.get("embedding_model_id")
    ]
    assert len(rerank_stores) == 1
    rerank_stores[0]._rerank_results.assert_awaited_once()
    rerank_call = rerank_stores[0]._rerank_results.await_args.kwargs
    assert [item["kb_id"] for item in rerank_call["results"]] == [
        str(KB_2),
        str(KB_1),
    ]
    assert rerank_call["rerank_score_threshold"] is None


@pytest.mark.asyncio
async def test_global_rerank_failure_fails_closed_with_stage_diagnostic(monkeypatch):
    search = AsyncMock(
        return_value=[
            {
                "chunk_id": "chunk-1",
                "document_id": str(DOC_1),
                "content": "content",
                "score": 0.8,
            }
        ]
    )
    install_store(
        monkeypatch,
        search,
        rerank_config={
            "enabled": True,
            "model_id": str(MODEL_ID),
            "candidate_k": 10,
            "score_threshold": 0.5,
        },
        rerank_results=RuntimeError("reranker down"),
    )

    with pytest.raises(retrieval.RetrievalError, match="rerank failed") as exc_info:
        await retrieval.retrieve(
            request(target(rerank_model_id=MODEL_ID), search_mode="vector")
        )

    assert exc_info.value.diagnostics == (
        retrieval.RetrievalDiagnostic(KB_1, "failed", "RuntimeError", "rerank"),
    )
    assert "reranker down" not in str(exc_info.value.diagnostics)


class ChunkQuery:
    def __init__(self, chunks):
        self.chunks = chunks

    def prefetch_related(self, *_relations):
        return self

    def __await__(self):
        async def result():
            return self.chunks

        return result().__await__()


@pytest.mark.asyncio
async def test_context_expansion_enforces_scope_document_and_token_budgets(
    monkeypatch,
):
    document = SimpleNamespace(id=DOC_1, knowledge_base_id=KB_1)
    chunks = {
        "seed": SimpleNamespace(
            id="seed",
            document_id=DOC_1,
            document=document,
            chunk_index=1,
            content="seed",
            token_count=2,
        ),
        "left": SimpleNamespace(
            id="left",
            document_id=DOC_1,
            document=document,
            chunk_index=0,
            content="left",
            token_count=2,
        ),
        "right": SimpleNamespace(
            id="right",
            document_id=DOC_1,
            document=document,
            chunk_index=2,
            content="right",
            token_count=2,
        ),
    }

    def filter_chunks(**filters):
        if "id__in" in filters:
            return ChunkQuery([chunks[value] for value in filters["id__in"]])
        return ChunkQuery([chunks["left"], chunks["right"]])

    monkeypatch.setattr(retrieval.DocumentChunk, "filter", filter_chunks)
    search = AsyncMock(
        return_value=[
            {
                "chunk_id": "seed",
                "document_id": str(DOC_1),
                "content": "seed",
                "score": 0.8,
            }
        ]
    )
    install_store(monkeypatch, search)

    response = await retrieval.retrieve(
        request(
            target(allowed_document_ids=frozenset({DOC_1})),
            search_mode="vector",
            expand_adjacent=True,
            max_documents=1,
            max_chunks_per_document=2,
            context_token_budget=4,
        )
    )

    result = response.results[0]
    assert result["content"] == "seed\n\nleft"
    assert result["citation_chunk_ids"] == ["seed", "left"]
    assert [chunk["chunk_index"] for chunk in result["context_chunks"]] == [1, 0]
    assert "rerank_score" not in result["context_chunks"][0]


@pytest.mark.asyncio
async def test_context_aggregates_ranked_chunks_by_document_and_skips_extra_documents(
    monkeypatch,
):
    first_document = SimpleNamespace(id=DOC_1, knowledge_base_id=KB_1)
    second_document = SimpleNamespace(id=DOC_2, knowledge_base_id=KB_1)
    chunks = [
        SimpleNamespace(
            id="first",
            document_id=DOC_1,
            document=first_document,
            chunk_index=0,
            content="first",
            token_count=1,
        ),
        SimpleNamespace(
            id="second",
            document_id=DOC_1,
            document=first_document,
            chunk_index=1,
            content="second",
            token_count=1,
        ),
        SimpleNamespace(
            id="other-document",
            document_id=DOC_2,
            document=second_document,
            chunk_index=0,
            content="other",
            token_count=1,
        ),
    ]
    monkeypatch.setattr(
        retrieval.DocumentChunk, "filter", lambda **_filters: ChunkQuery(chunks)
    )
    results = [
        {
            "chunk_id": chunk_id,
            "kb_id": str(KB_1),
            "document_id": str(DOC_1),
            "score": score,
        }
        for chunk_id, score in (("missing", 1.0), ("first", 0.9), ("second", 0.8))
    ]
    results.append(
        {
            "chunk_id": "other-document",
            "kb_id": str(KB_1),
            "document_id": str(DOC_2),
            "score": 0.7,
        }
    )

    assembled = await retrieval._assemble_context(results, request(max_documents=1))

    assert len(assembled) == 1
    assert assembled[0]["content"] == "first\n\nsecond"
    assert assembled[0]["citation_chunk_ids"] == ["first", "second"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selected_target",
    [
        target(KB_2),
        target(document_ids=frozenset({DOC_2})),
        target(allowed_document_ids=frozenset({DOC_2})),
    ],
)
async def test_context_revalidates_target_and_document_scope(
    monkeypatch, selected_target
):
    document = SimpleNamespace(id=DOC_1, knowledge_base_id=KB_1)
    chunk = SimpleNamespace(
        id="seed",
        document_id=DOC_1,
        document=document,
        chunk_index=0,
        content="seed",
        token_count=1,
    )
    monkeypatch.setattr(
        retrieval.DocumentChunk, "filter", lambda **_filters: ChunkQuery([chunk])
    )

    assembled = await retrieval._assemble_context(
        [
            {
                "chunk_id": "seed",
                "kb_id": str(selected_target.kb_id),
                "document_id": str(DOC_1),
                "score": 1.0,
            }
        ],
        request(selected_target, max_documents=1),
    )

    assert assembled == []


@pytest.mark.asyncio
async def test_context_budget_rejects_seed_instead_of_citing_only_neighbor(monkeypatch):
    document = SimpleNamespace(id=DOC_1, knowledge_base_id=KB_1)
    seed = SimpleNamespace(
        id="seed",
        document_id=DOC_1,
        document=document,
        chunk_index=1,
        content="seed",
        token_count=5,
    )
    neighbor = SimpleNamespace(
        id="neighbor",
        document_id=DOC_1,
        document=document,
        chunk_index=2,
        content="neighbor",
        token_count=1,
    )

    def filter_chunks(**filters):
        return ChunkQuery([seed] if "id__in" in filters else [neighbor])

    monkeypatch.setattr(retrieval.DocumentChunk, "filter", filter_chunks)
    assembled = await retrieval._assemble_context(
        [
            {
                "chunk_id": "seed",
                "kb_id": str(KB_1),
                "document_id": str(DOC_1),
                "score": 1.0,
            }
        ],
        request(expand_adjacent=True, context_token_budget=1),
    )

    assert assembled == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"max_documents": 0}, "max_documents must be positive"),
        (
            {"max_chunks_per_document": 0},
            "max_chunks_per_document must be positive",
        ),
        ({"context_token_budget": 0}, "context_token_budget must be positive"),
    ],
)
def test_rejects_invalid_context_limits(overrides, message):
    with pytest.raises(ValueError, match=message):
        request(**overrides)
