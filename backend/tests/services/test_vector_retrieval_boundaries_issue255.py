import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.services.vector_store import (
    DimensionMismatchError,
    VectorSearchUnavailableError,
    VectorStore,
)

vector_store_module = importlib.import_module("app.services.vector_store")


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


@pytest.fixture(autouse=True)
def qdrant_models(monkeypatch):
    monkeypatch.setattr(
        vector_store_module,
        "qmodels",
        SimpleNamespace(
            FieldCondition=Model,
            Filter=Model,
            MatchAny=Model,
            MatchValue=Model,
        ),
    )


class Query:
    def __init__(self, entities):
        self.entities = entities

    def prefetch_related(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self.entities

        return resolve().__await__()


@pytest.mark.asyncio
async def test_vector_retrieval_transforms_scores_metadata_and_scopes_documents(
    monkeypatch,
):
    kb_id = UUID("00000000-0000-0000-0000-000000000001")
    document_id = UUID("00000000-0000-0000-0000-000000000002")
    first_id = UUID("00000000-0000-0000-0000-000000000003")
    second_id = UUID("00000000-0000-0000-0000-000000000004")
    calls = {}
    chunks = [
        SimpleNamespace(
            id=first_id,
            document_id=document_id,
            document=SimpleNamespace(name="Guide"),
            content="First result",
            metadata='{"source": "manual"}',
        ),
        SimpleNamespace(
            id=second_id,
            document_id=document_id,
            document=None,
            content="Second result",
            metadata="not-json",
        ),
    ]

    async def qdrant_search(**kwargs):
        calls.update(kwargs)
        return [
            SimpleNamespace(id=first_id, score=-1.0),
            SimpleNamespace(id=second_id, score=1.0),
        ]

    def chunk_filter(**kwargs):
        calls["chunk_filter"] = kwargs
        return Query(chunks)

    store = VectorStore(embedding_dimension=3)
    monkeypatch.setattr(store, "embed_query", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    monkeypatch.setattr(
        vector_store_module, "_ensure_collection", AsyncMock(return_value="kb_3")
    )
    monkeypatch.setattr(vector_store_module, "_qdrant_search", qdrant_search)
    monkeypatch.setattr(vector_store_module.DocumentChunk, "filter", chunk_filter)
    monkeypatch.setattr(vector_store_module.settings, "QDRANT_DISTANCE", "cosine")

    results = await store._vector_search(kb_id, "find the guide", 4, [document_id])

    assert calls["collection"] == "kb_3"
    assert calls["query_embedding"] == [0.1, 0.2, 0.3]
    assert calls["limit"] == 4
    conditions = calls["query_filter"].must
    assert [(condition.key, condition.match.value) for condition in conditions[:1]] == [
        ("kb_id", str(kb_id))
    ]
    assert conditions[1].key == "document_id"
    assert conditions[1].match.any == [str(document_id)]
    assert calls["chunk_filter"] == {
        "id__in": [str(first_id), str(second_id)],
        "status": "embedded",
        "document__status": "completed",
        "document__knowledge_base__status": "active",
    }
    assert results == [
        {
            "chunk_id": first_id,
            "document_id": document_id,
            "document_name": "Guide",
            "content": "First result",
            "score": 0.0,
            "metadata": {"source": "manual"},
            "search_type": "vector",
            "dense_score": 0.0,
            "dense_rank": 1,
            "final_score_stage": "dense",
        },
        {
            "chunk_id": second_id,
            "document_id": document_id,
            "document_name": None,
            "content": "Second result",
            "score": 1.0,
            "metadata": None,
            "search_type": "vector",
            "dense_score": 1.0,
            "dense_rank": 2,
            "final_score_stage": "dense",
        },
    ]


@pytest.mark.asyncio
async def test_vector_retrieval_validates_query_embedding_dimension(monkeypatch):
    store = VectorStore(embedding_dimension=3)
    query_provider = AsyncMock(return_value=[0.1, 0.2])
    monkeypatch.setattr(store, "embed_query", query_provider)
    ensure_collection = AsyncMock()
    monkeypatch.setattr(vector_store_module, "_ensure_collection", ensure_collection)

    with pytest.raises(DimensionMismatchError, match="Query embedding dimension 2"):
        await store._vector_search(UUID(int=1), "query", 5)

    query_provider.assert_awaited_once_with("query")
    ensure_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_vector_retrieval_returns_empty_for_embedding_failure_or_no_points(
    monkeypatch,
):
    store = VectorStore(embedding_dimension=3)
    monkeypatch.setattr(
        store, "embed_query", AsyncMock(side_effect=RuntimeError("down"))
    )
    ensure_collection = AsyncMock()
    monkeypatch.setattr(vector_store_module, "_ensure_collection", ensure_collection)

    with pytest.raises(VectorSearchUnavailableError, match="query_embedding_failed"):
        await store._vector_search(UUID(int=1), "query", 5)
    ensure_collection.assert_not_awaited()

    monkeypatch.setattr(store, "embed_query", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    monkeypatch.setattr(
        vector_store_module, "_ensure_collection", AsyncMock(return_value="kb_3")
    )
    monkeypatch.setattr(
        vector_store_module, "_qdrant_search", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        vector_store_module.DocumentChunk,
        "filter",
        lambda **_kwargs: pytest.fail("database lookup must be skipped for no points"),
    )

    assert await store._vector_search(UUID(int=1), "query", 5) == []


@pytest.mark.asyncio
async def test_hybrid_retrieval_falls_back_when_vector_provider_fails(monkeypatch):
    store = VectorStore(embedding_dimension=3)
    fallback = [{"chunk_id": "fulltext", "score": 0.8, "search_type": "fulltext"}]
    monkeypatch.setattr(vector_store_module, "get_kb_embedding_dimension", AsyncMock())
    monkeypatch.setattr(
        store,
        "_resolve_rerank_config",
        AsyncMock(
            return_value={
                "enabled": False,
                "model_id": None,
                "candidate_k": 5,
                "fail_open": True,
                "score_threshold": None,
            }
        ),
    )
    monkeypatch.setattr(
        store, "_vector_search", AsyncMock(side_effect=RuntimeError("Qdrant down"))
    )
    fulltext_search = AsyncMock(return_value=fallback)
    monkeypatch.setattr(store, "_fulltext_search", fulltext_search)

    assert await store.search(UUID(int=1), "query", search_mode="hybrid") == [
        {
            "chunk_id": "fulltext",
            "score": 1 / 61,
            "search_type": "hybrid",
            "lexical_score": 0.8,
            "lexical_rank": 1,
            "fusion_score": 1 / 61,
            "fusion_rank": 1,
            "final_score_stage": "fusion",
            "degradation_reasons": ["vector_unavailable"],
        }
    ]
    fulltext_search.assert_awaited_once()


@pytest.mark.asyncio
async def test_vector_retrieval_keeps_mapping_metadata_and_euclidean_scores(
    monkeypatch,
):
    chunk_id = UUID(int=3)
    document_id = UUID(int=2)
    chunk = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        document=SimpleNamespace(name="Guide"),
        content="Result",
        metadata={"page": 1},
    )
    store = VectorStore(embedding_dimension=2)
    monkeypatch.setattr(store, "embed_query", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(
        vector_store_module, "_ensure_collection", AsyncMock(return_value="kb_2")
    )
    monkeypatch.setattr(
        vector_store_module,
        "_qdrant_search",
        AsyncMock(return_value=[SimpleNamespace(id=chunk_id, score=3.0)]),
    )
    monkeypatch.setattr(
        vector_store_module.DocumentChunk, "filter", lambda **_kwargs: Query([chunk])
    )
    monkeypatch.setattr(vector_store_module.settings, "QDRANT_DISTANCE", "euclid")

    assert await store._vector_search(UUID(int=1), "query", 1) == [
        {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_name": "Guide",
            "content": "Result",
            "score": 0.25,
            "metadata": {"page": 1},
            "search_type": "vector",
            "dense_score": 0.25,
            "dense_rank": 1,
            "final_score_stage": "dense",
        }
    ]


@pytest.mark.asyncio
async def test_search_without_dimension_or_results_skips_optional_branches(monkeypatch):
    store = VectorStore()
    monkeypatch.setattr(
        vector_store_module, "get_kb_embedding_dimension", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        store,
        "_resolve_rerank_config",
        AsyncMock(
            return_value={
                "enabled": True,
                "model_id": "reranker",
                "candidate_k": 2,
                "fail_open": True,
                "score_threshold": None,
            }
        ),
    )
    monkeypatch.setattr(store, "_vector_search", AsyncMock(return_value=[]))
    rerank = AsyncMock()
    monkeypatch.setattr(store, "_rerank_results", rerank)

    assert await store.search(UUID(int=1), "query", search_mode="vector") == []
    assert store.embedding_dimension is None
    rerank.assert_not_awaited()
