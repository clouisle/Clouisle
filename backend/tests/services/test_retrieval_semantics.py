from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import importlib

import pytest

from app.services.vector_store import VectorSearchUnavailableError, VectorStore

module = importlib.import_module("app.services.vector_store")


def result(chunk_id, score, channel):
    return {
        "chunk_id": chunk_id,
        "document_id": uuid4(),
        "document_name": "Guide",
        "content": "content",
        "score": score,
        "search_type": channel,
    }


class QueryResult:
    def __init__(self, rows):
        self.rows = rows
        self.filter = Mock(return_value=self)
        self.limit = Mock(return_value=self)

    def prefetch_related(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def configured(store, monkeypatch):
    monkeypatch.setattr(module, "get_kb_embedding_dimension", AsyncMock(return_value=3))
    monkeypatch.setattr(
        store,
        "_resolve_rerank_config",
        AsyncMock(
            return_value={
                "enabled": False,
                "model_id": None,
                "candidate_k": 10,
                "fail_open": True,
                "score_threshold": None,
            }
        ),
    )


@pytest.mark.anyio
async def test_search_rejects_invalid_mode_before_configuration(monkeypatch):
    store = VectorStore()
    dimension = AsyncMock()
    rerank_config = AsyncMock()
    monkeypatch.setattr(module, "get_kb_embedding_dimension", dimension)
    monkeypatch.setattr(store, "_resolve_rerank_config", rerank_config)

    with pytest.raises(ValueError, match="Unsupported search mode"):
        await store.search(uuid4(), "query", search_mode="typo")

    dimension.assert_not_awaited()
    rerank_config.assert_not_awaited()


@pytest.mark.anyio
async def test_threshold_only_filters_dense_candidates(monkeypatch):
    store = VectorStore()
    configured(store, monkeypatch)
    dense_low = result("dense-low", 0.2, "vector") | {"dense_score": 0.2}
    dense_high = result("dense-high", 0.8, "vector") | {"dense_score": 0.8}
    lexical = result("lexical", 0.1, "fulltext") | {"lexical_score": 0.1}
    monkeypatch.setattr(
        store, "_vector_search", AsyncMock(return_value=[dense_low, dense_high])
    )
    monkeypatch.setattr(store, "_fulltext_search", AsyncMock(return_value=[lexical]))

    vector = await store.search(uuid4(), "query", "vector", score_threshold=0.5)
    fulltext = await store.search(uuid4(), "query", "fulltext", score_threshold=0.9)
    hybrid = await store.search(uuid4(), "query", "hybrid", score_threshold=0.5)

    assert [item["chunk_id"] for item in vector] == ["dense-high"]
    assert [item["chunk_id"] for item in fulltext] == ["lexical"]
    assert {item["chunk_id"] for item in hybrid} == {"dense-high", "lexical"}
    assert all(item["final_score_stage"] == "fusion" for item in hybrid)


@pytest.mark.anyio
async def test_vector_failure_is_explicit_and_hybrid_degrades(monkeypatch):
    store = VectorStore()
    configured(store, monkeypatch)
    unavailable = AsyncMock(side_effect=VectorSearchUnavailableError("offline"))
    lexical = result("lexical", 0.7, "fulltext") | {"lexical_score": 0.7}
    monkeypatch.setattr(store, "_vector_search", unavailable)
    monkeypatch.setattr(store, "_fulltext_search", AsyncMock(return_value=[lexical]))

    with pytest.raises(VectorSearchUnavailableError):
        await store.search(uuid4(), "query", "vector")

    hybrid = await store.search(uuid4(), "query", "hybrid")
    assert hybrid[0]["degradation_reasons"] == ["vector_unavailable"]

    monkeypatch.setattr(
        store, "_fulltext_search", AsyncMock(side_effect=RuntimeError("db"))
    )
    with pytest.raises(RuntimeError, match="all_retrievers_unavailable"):
        await store.search(uuid4(), "query", "hybrid")


def test_rrf_preserves_channel_scores_ranks_and_raw_fusion_score():
    shared = uuid4()
    dense_only = uuid4()
    lexical_only = uuid4()
    dense = [result(shared, 0.8, "vector"), result(dense_only, 0.7, "vector")]
    lexical = [result(shared, 12.5, "fulltext"), result(lexical_only, 10.0, "fulltext")]

    merged = VectorStore()._merge_results_rrf(dense, lexical)

    assert merged[0]["chunk_id"] == shared
    assert merged[0]["dense_score"] == 0.8
    assert merged[0]["dense_rank"] == 1
    assert merged[0]["lexical_score"] == 12.5
    assert merged[0]["lexical_rank"] == 1
    assert merged[0]["fusion_score"] == pytest.approx(2 / 61)
    assert merged[0]["score"] == merged[0]["fusion_score"]
    assert merged[0]["fusion_rank"] == 1


@pytest.mark.anyio
async def test_retrievers_filter_authoritative_statuses(monkeypatch):
    store = VectorStore()
    monkeypatch.setattr(store, "embed_query", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(
        module, "_ensure_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(
        module,
        "_qdrant_search",
        AsyncMock(return_value=[SimpleNamespace(id="chunk", score=0.8)]),
    )
    dense_query = QueryResult([])
    monkeypatch.setattr(module.DocumentChunk, "filter", Mock(return_value=dense_query))

    await store._vector_search(uuid4(), "query", 5, embedding_dimension=2)
    dense_filter = module.DocumentChunk.filter.call_args.kwargs
    assert dense_filter["status"] == "embedded"
    assert dense_filter["document__status"] == "completed"
    assert dense_filter["document__knowledge_base__status"] == "active"

    lexical_query = QueryResult([])
    monkeypatch.setattr(
        module.DocumentChunk, "filter", Mock(return_value=lexical_query)
    )
    await store._fulltext_search(uuid4(), "moon", 5)
    lexical_filter = module.DocumentChunk.filter.call_args.kwargs
    assert "status" not in lexical_filter
    assert lexical_filter["document__status"] == "completed"
    assert lexical_filter["document__knowledge_base__status"] == "active"
