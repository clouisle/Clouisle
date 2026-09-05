import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.services.vector_store import (
    DimensionMismatchError,
    VectorSearchUnavailableError,
    VectorStore,
)

vector_store = importlib.import_module("app.services.vector_store")
KB_ID = UUID("00000000-0000-0000-0000-000000000001")


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


@pytest.fixture(autouse=True)
def qdrant_models(monkeypatch):
    models = SimpleNamespace(
        Distance=SimpleNamespace(COSINE="cosine", DOT="dot", EUCLID="euclid"),
        FieldCondition=Model,
        Filter=Model,
        FilterSelector=Model,
        MatchAny=Model,
        MatchValue=Model,
        PayloadSchemaType=SimpleNamespace(KEYWORD="keyword"),
        PointIdsList=Model,
        PointStruct=Model,
        VectorParams=Model,
    )
    monkeypatch.setattr(vector_store, "qmodels", models)
    vector_store._qdrant_collections.clear()
    vector_store._qdrant_payload_indexes.clear()
    return models


@pytest.mark.parametrize(
    ("setting", "expected"),
    [("cos", "cosine"), ("inner", "dot"), ("l2", "euclid")],
)
def test_qdrant_distance_aliases(monkeypatch, setting, expected):
    monkeypatch.setattr(vector_store.settings, "QDRANT_DISTANCE", setting)
    assert vector_store._qdrant_distance() == expected


@pytest.mark.asyncio
async def test_qdrant_client_is_created_once(monkeypatch):
    client = object()
    factory = Mock(return_value=client)
    monkeypatch.setattr(vector_store, "AsyncQdrantClient", factory)
    monkeypatch.setattr(vector_store, "_qdrant_client", None)

    assert await vector_store._get_qdrant_client() is client
    assert await vector_store._get_qdrant_client() is client
    factory.assert_called_once_with(
        url=vector_store.settings.QDRANT_URL,
        api_key=vector_store.settings.QDRANT_API_KEY,
        timeout=60.0,
    )


@pytest.mark.asyncio
async def test_qdrant_client_requires_dependency(monkeypatch):
    monkeypatch.setattr(vector_store, "AsyncQdrantClient", None)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        await vector_store._get_qdrant_client()


@pytest.mark.asyncio
async def test_collection_lookup_caches_success_and_handles_provider_failure(
    monkeypatch,
):
    client = SimpleNamespace(get_collection=AsyncMock())
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    assert await vector_store._collection_exists("kb_3") is True
    assert await vector_store._collection_exists("kb_3") is True
    client.get_collection.assert_awaited_once_with("kb_3")

    client.get_collection.side_effect = RuntimeError("qdrant down")
    assert await vector_store._collection_exists("missing") is False


@pytest.mark.asyncio
async def test_ensure_collection_creates_missing_collection_and_tolerates_index_failure(
    monkeypatch,
):
    client = SimpleNamespace(
        get_collection=AsyncMock(side_effect=LookupError("missing")),
        create_collection=AsyncMock(),
        create_payload_index=AsyncMock(side_effect=RuntimeError("unsupported")),
    )
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(vector_store.settings, "QDRANT_COLLECTION_PREFIX", "test")
    monkeypatch.setattr(vector_store.settings, "QDRANT_DISTANCE", "dot")

    assert await vector_store._ensure_collection(3) == "test_3"
    assert await vector_store._ensure_collection(3) == "test_3"
    config = client.create_collection.await_args.kwargs["vectors_config"]
    assert (config.size, config.distance) == (3, "dot")
    assert client.create_payload_index.await_count == 2


@pytest.mark.asyncio
async def test_qdrant_delete_helpers_cover_empty_success_and_provider_failure(
    monkeypatch, caplog
):
    client = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    await vector_store._delete_qdrant_points("kb_3", [])
    client.delete.assert_not_awaited()

    await vector_store._delete_qdrant_points("kb_3", ["one"])
    assert client.delete.await_args.kwargs["points_selector"].points == ["one"]

    client.delete.side_effect = RuntimeError("qdrant down")
    await vector_store._delete_qdrant_filter("kb_3", Model(must=[]))
    assert "Failed to delete Qdrant points" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "expected"),
    [
        (
            SimpleNamespace(
                query_points=AsyncMock(return_value=SimpleNamespace(result=["query"]))
            ),
            ["query"],
        ),
        (
            SimpleNamespace(
                search_points=AsyncMock(return_value=SimpleNamespace(points=["points"]))
            ),
            ["points"],
        ),
        (SimpleNamespace(search=AsyncMock(return_value=["legacy"])), ["legacy"]),
    ],
)
async def test_qdrant_search_supports_client_api_variants(
    monkeypatch, client, expected
):
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    assert (
        await vector_store._qdrant_search("kb_3", [0.1], 2, Model(must=[])) == expected
    )


@pytest.mark.asyncio
async def test_qdrant_search_retries_old_query_points_signature(monkeypatch):
    query_points = AsyncMock(
        side_effect=[TypeError("old client"), SimpleNamespace(points=["hit"])]
    )
    monkeypatch.setattr(
        vector_store,
        "_get_qdrant_client",
        AsyncMock(return_value=SimpleNamespace(query_points=query_points)),
    )

    assert await vector_store._qdrant_search("kb_3", [0.1], 1, Model()) == ["hit"]
    assert query_points.await_args.kwargs["query_vector"] == [0.1]


@pytest.mark.asyncio
async def test_qdrant_search_rejects_client_without_search_api(monkeypatch):
    monkeypatch.setattr(
        vector_store,
        "_get_qdrant_client",
        AsyncMock(return_value=SimpleNamespace()),
    )
    with pytest.raises(AttributeError, match="no query/search method"):
        await vector_store._qdrant_search("kb_3", [0.1], 1, Model())


@pytest.mark.asyncio
async def test_batch_store_embeddings_handles_boundaries_and_payloads(monkeypatch):
    client = SimpleNamespace(
        upsert=AsyncMock(return_value=SimpleNamespace(status="completed"))
    )
    ensure_collection = AsyncMock(return_value="kb_2")
    monkeypatch.setattr(vector_store, "_ensure_collection", ensure_collection)
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    store = VectorStore()

    await store._batch_store_embeddings([], [])
    ensure_collection.assert_not_awaited()

    ids = [uuid4(), uuid4()]
    await store._batch_store_embeddings(
        ids, [[0.1, 0.2], [0.3, 0.4]], payloads=[{"kb_id": "one"}]
    )
    points = client.upsert.await_args.kwargs["points"]
    assert store._detected_dimension == 2
    assert [point.payload for point in points] == [{"kb_id": "one"}, {}]

    client.upsert.side_effect = RuntimeError("qdrant down")
    with pytest.raises(RuntimeError, match="qdrant down"):
        await store._batch_store_embeddings([uuid4()], [[0.1, 0.2]])


@pytest.mark.asyncio
async def test_embedding_provider_team_paths_and_failures(monkeypatch):
    manager = SimpleNamespace(
        team_embed=AsyncMock(return_value=[[0.1, 0.2]]),
        embed=AsyncMock(side_effect=RuntimeError("provider unavailable")),
        embed_query=AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )
    monkeypatch.setattr(vector_store, "_get_model_manager", Mock(return_value=manager))
    store = VectorStore(embedding_model_id="model", team_id="team")

    assert await store.embed_texts([]) == []
    assert await store.embed_texts(["text"]) == [[0.1, 0.2]]
    assert await store.embed_query("query") == [0.1, 0.2]
    assert manager.team_embed.await_count == 2

    plain_store = VectorStore()
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await plain_store.embed_texts(["text"])
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await plain_store.embed_query("query")


@pytest.mark.asyncio
async def test_vector_search_resolves_missing_dimension_and_skips_unknown_points(
    monkeypatch,
):
    store = VectorStore()
    get_dimension = AsyncMock(side_effect=[None, 2])
    monkeypatch.setattr(vector_store, "get_kb_embedding_dimension", get_dimension)

    with pytest.raises(
        VectorSearchUnavailableError, match="embedding_dimension_unavailable"
    ):
        await store._vector_search(KB_ID, "query", 1)

    monkeypatch.setattr(store, "embed_query", AsyncMock(return_value=[0.1, 0.2]))
    monkeypatch.setattr(
        vector_store, "_ensure_collection", AsyncMock(return_value="kb_2")
    )
    monkeypatch.setattr(
        vector_store,
        "_qdrant_search",
        AsyncMock(return_value=[SimpleNamespace(id=uuid4(), score=0.5)]),
    )

    async def no_chunks():
        return []

    query = SimpleNamespace(prefetch_related=Mock(return_value=no_chunks()))
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", Mock(return_value=query))

    assert await store._vector_search(KB_ID, "query", 1) == []


@pytest.mark.asyncio
async def test_search_modes_apply_threshold_limit_and_dimension_fallback(monkeypatch):
    store = VectorStore()
    config = {
        "enabled": False,
        "model_id": None,
        "candidate_k": 3,
        "fail_open": True,
        "score_threshold": None,
    }
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=2)
    )
    monkeypatch.setattr(store, "_resolve_rerank_config", AsyncMock(return_value=config))
    vector_results = [
        {"chunk_id": "high", "score": 0.9, "dense_score": 0.9},
        {"chunk_id": "low", "score": 0.1, "dense_score": 0.1},
    ]
    lexical_results = [
        {"chunk_id": "high", "score": 0.9, "lexical_score": 0.9},
        {"chunk_id": "low", "score": 0.1, "lexical_score": 0.1},
    ]
    monkeypatch.setattr(store, "_vector_search", AsyncMock(return_value=vector_results))
    monkeypatch.setattr(
        store, "_fulltext_search", AsyncMock(return_value=lexical_results)
    )

    assert await store.search(
        KB_ID, "query", search_mode="vector", top_k=1, score_threshold=0.5
    ) == [{"chunk_id": "high", "score": 0.9, "dense_score": 0.9}]
    assert store.embedding_dimension == 2
    assert await store.search(KB_ID, "query", search_mode="fulltext", top_k=1) == [
        {"chunk_id": "high", "score": 0.9, "lexical_score": 0.9}
    ]

    store._vector_search.side_effect = DimensionMismatchError("wrong dimension")
    assert await store.search(KB_ID, "query", search_mode="hybrid", top_k=1) == [
        {
            "chunk_id": "high",
            "score": 1 / 61,
            "lexical_score": 0.9,
            "lexical_rank": 1,
            "search_type": "hybrid",
            "fusion_score": 1 / 61,
            "fusion_rank": 1,
            "final_score_stage": "fusion",
            "degradation_reasons": ["vector_unavailable"],
        }
    ]


@pytest.mark.asyncio
async def test_update_chunk_vector_handles_missing_owner_and_embedding_failure(
    monkeypatch,
):
    chunk = SimpleNamespace(
        id="chunk", document_id="missing", content="content", save=AsyncMock()
    )
    query = SimpleNamespace(values_list=AsyncMock(return_value=[]))
    monkeypatch.setattr(vector_store.Document, "filter", Mock(return_value=query))
    monkeypatch.setattr(VectorStore, "embed_query", AsyncMock(return_value=[0.1]))
    store_embedding = AsyncMock()
    monkeypatch.setattr(VectorStore, "_store_embedding", store_embedding)

    assert await VectorStore().update_chunk_vector(chunk) is True
    store_embedding.assert_awaited_once_with(
        "chunk",
        [0.1],
        dimension=1,
        payload={"kb_id": "", "document_id": "missing"},
    )

    monkeypatch.setattr(
        VectorStore, "embed_query", AsyncMock(side_effect=RuntimeError("provider down"))
    )
    assert await VectorStore().update_chunk_vector(chunk, KB_ID) is False


@pytest.mark.asyncio
async def test_kb_dimension_lifecycle_rejects_missing_and_mismatched_models(
    monkeypatch,
):
    missing = AsyncMock(return_value=None)
    monkeypatch.setattr(vector_store.KnowledgeBase, "get_or_none", missing)
    assert await vector_store.get_kb_embedding_dimension(KB_ID) is None
    assert await vector_store.set_kb_embedding_dimension(KB_ID, 3) is False

    kb = SimpleNamespace(embedding_dimension=2, save=AsyncMock())
    monkeypatch.setattr(
        vector_store.KnowledgeBase, "get_or_none", AsyncMock(return_value=kb)
    )
    assert await vector_store.get_kb_embedding_dimension(KB_ID) == 2
    assert await vector_store.set_kb_embedding_dimension(KB_ID, 2) is True
    assert await vector_store.set_kb_embedding_dimension(KB_ID, 3) is False
    with pytest.raises(DimensionMismatchError, match="KB uses 2"):
        await vector_store._ensure_kb_dimension(KB_ID, 3)
    assert await vector_store._ensure_kb_dimension(KB_ID, 2) == 2

    kb.embedding_dimension = None
    assert await vector_store.set_kb_embedding_dimension(KB_ID, 4) is True
    kb.save.assert_awaited_once()

    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=None)
    )
    set_dimension = AsyncMock(return_value=True)
    monkeypatch.setattr(vector_store, "set_kb_embedding_dimension", set_dimension)
    assert await vector_store._ensure_kb_dimension(KB_ID, 5) == 5
    set_dimension.assert_awaited_once_with(KB_ID, 5)


@pytest.mark.asyncio
async def test_rerank_configuration_overrides_and_result_boundaries(monkeypatch):
    kb = SimpleNamespace(
        settings={
            "rerank_enabled": False,
            "rerank_candidate_k": 4,
            "rerank_fail_open": False,
            "rerank_score_threshold": "0.5",
        },
        rerank_model_id=uuid4(),
    )
    monkeypatch.setattr(
        vector_store.KnowledgeBase, "get_or_none", AsyncMock(return_value=kb)
    )
    store = VectorStore()
    config = await store._resolve_rerank_config(
        KB_ID,
        {
            "rerank_enabled": True,
            "rerank_candidate_k": 8,
            "rerank_fail_open": True,
            "rerank_score_threshold": None,
        },
    )
    assert config == {
        "model_id": str(kb.rerank_model_id),
        "enabled": True,
        "candidate_k": 8,
        "score_threshold": None,
    }
    assert await store._rerank_results("query", [], "model", None) == []

    response = SimpleNamespace(
        results=[
            SimpleNamespace(index=1, score=0.9, reason="best"),
            SimpleNamespace(index=0, score=0.4, reason=None),
        ]
    )
    manager = SimpleNamespace(rerank=AsyncMock(return_value=response))
    monkeypatch.setattr(vector_store, "_get_model_manager", Mock(return_value=manager))
    results = await store._rerank_results(
        "query",
        [
            {"content": "first", "score": 0.8, "search_type": "vector"},
            {"content": "second", "score": 0.7},
            {"content": "unranked", "score": 0.6},
        ],
        "model",
        0.5,
    )
    assert results == [
        {
            "content": "second",
            "score": 0.9,
            "original_score": 0.7,
            "rerank_score": 0.9,
            "search_type": "retrieval+rerank",
            "rerank_reason": "best",
            "rerank_rank": 1,
            "final_score_stage": "rerank",
        }
    ]

    manager.rerank.side_effect = RuntimeError("provider down")
    recalled = [{"content": "original", "score": 0.5}]
    with pytest.raises(RuntimeError, match="provider down"):
        await store._rerank_results("query", recalled, "model", None)

    team_manager = SimpleNamespace(
        team_rerank=AsyncMock(side_effect=RuntimeError("team provider down"))
    )
    monkeypatch.setattr(
        vector_store, "_get_model_manager", Mock(return_value=team_manager)
    )
    team_store = VectorStore(team_id="team")
    with pytest.raises(RuntimeError, match="team provider down"):
        await team_store._rerank_results("query", recalled, "model", None)


@pytest.mark.asyncio
async def test_team_rerank_and_search_apply_candidate_window(monkeypatch):
    response = SimpleNamespace(
        results=[SimpleNamespace(index=0, score=0.75, reason=None)]
    )
    manager = SimpleNamespace(team_rerank=AsyncMock(return_value=response))
    monkeypatch.setattr(vector_store, "_get_model_manager", Mock(return_value=manager))
    store = VectorStore(team_id="team", rerank_model_id="reranker")
    monkeypatch.setattr(
        vector_store.KnowledgeBase,
        "get_or_none",
        AsyncMock(return_value=SimpleNamespace(settings={}, rerank_model_id=None)),
    )
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        store,
        "_vector_search",
        AsyncMock(return_value=[{"content": "hit", "score": 0.6}]),
    )

    assert await store.search(KB_ID, "query", search_mode="vector", top_k=1) == [
        {
            "content": "hit",
            "score": 0.75,
            "original_score": 0.6,
            "rerank_score": 0.75,
            "search_type": "retrieval+rerank",
            "rerank_rank": 1,
            "final_score_stage": "rerank",
        }
    ]
    assert store._vector_search.await_args.args[2] == 10
    manager.team_rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_chunks_batches_records_payloads_and_propagates_qdrant_failure(
    monkeypatch,
):
    document = SimpleNamespace(id=uuid4(), knowledge_base_id=KB_ID)
    created = []

    async def create_chunk(**values):
        chunk = SimpleNamespace(id=uuid4(), **values)
        created.append(chunk)
        return chunk

    monkeypatch.setattr(vector_store.DocumentChunk, "create", create_chunk)
    store = VectorStore()
    monkeypatch.setattr(
        store, "embed_texts", AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    )
    ensure_dimension = AsyncMock()
    monkeypatch.setattr(vector_store, "_ensure_kb_dimension", ensure_dimension)
    batch_store = AsyncMock()
    monkeypatch.setattr(store, "_batch_store_embeddings", batch_store)
    chunks = [
        {"content": "one", "chunk_index": 0, "token_count": 2},
        {"content": "two", "chunk_index": 1, "metadata": {"page": 2}},
    ]

    assert await store.store_chunks(document, []) == []
    assert await store.store_chunks(document, chunks) == created
    ensure_dimension.assert_awaited_once_with(KB_ID, 2)
    assert [chunk.embedding_id for chunk in created] == [
        f"doc_{document.id}_chunk_0",
        f"doc_{document.id}_chunk_1",
    ]
    assert batch_store.await_args.args[:3] == (
        [chunk.id for chunk in created],
        [[0.1, 0.2], [0.3, 0.4]],
        2,
    )
    assert batch_store.await_args.kwargs["payloads"] == [
        {"kb_id": str(KB_ID), "document_id": str(document.id)},
        {"kb_id": str(KB_ID), "document_id": str(document.id)},
    ]

    batch_store.side_effect = RuntimeError("qdrant down")
    with pytest.raises(RuntimeError, match="qdrant down"):
        await store.store_chunks(document, chunks[:1])


@pytest.mark.asyncio
async def test_fulltext_search_applies_document_filter_scores_and_limit(monkeypatch):
    document_id = uuid4()
    chunks = [
        SimpleNamespace(
            id=uuid4(),
            document_id=document_id,
            document=SimpleNamespace(id=document_id, name="Guide"),
            content="Setup guide",
            metadata={"page": 1},
        ),
        SimpleNamespace(
            id=uuid4(),
            document_id=document_id,
            document=SimpleNamespace(id=document_id, name="Guide"),
            content="Unrelated",
            metadata=None,
        ),
    ]

    class ChunkQuery:
        def __init__(self):
            self.filters = []
            self.limit_value = None

        def prefetch_related(self, *_args):
            return self

        def filter(self, *args, **kwargs):
            self.filters.append((args, kwargs))
            return self

        def limit(self, value):
            self.limit_value = value

            async def resolve():
                return chunks

            return resolve()

    query = ChunkQuery()
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", Mock(return_value=query))
    store = VectorStore()
    monkeypatch.setattr(store, "_extract_search_terms", Mock(return_value=["setup"]))

    results = await store._fulltext_search(KB_ID, "setup", 2, [document_id])

    assert results == [
        {
            "chunk_id": chunks[0].id,
            "document_id": document_id,
            "document_name": "Guide",
            "content": "Setup guide",
            "score": 1.0,
            "metadata": {"page": 1},
            "search_type": "fulltext",
            "lexical_score": 1.0,
            "lexical_rank": 1,
            "final_score_stage": "lexical",
        }
    ]
    assert query.filters[0] == ((), {"document_id__in": [document_id]})
    assert query.filters[1][0]
    assert query.limit_value == 6


@pytest.mark.asyncio
async def test_deletion_skips_remote_calls_for_missing_dimensions_and_collections(
    monkeypatch,
):
    chunk_query = SimpleNamespace(values_list=AsyncMock(return_value=[KB_ID]))
    monkeypatch.setattr(
        vector_store.DocumentChunk,
        "filter",
        Mock(return_value=chunk_query),
    )
    monkeypatch.setattr(
        vector_store.Document,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[KB_ID]))),
    )
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=None)
    )
    delete_points = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_points", delete_points)

    assert await VectorStore().delete_chunk_vector(uuid4()) is False
    delete_points.assert_not_awaited()

    documents = SimpleNamespace(values_list=AsyncMock(return_value=[]))
    monkeypatch.setattr(vector_store.Document, "filter", Mock(return_value=documents))
    assert await VectorStore().delete_kb_vectors(KB_ID) == 0


def test_qdrant_dependency_filter_and_score_boundaries(monkeypatch, qdrant_models):
    monkeypatch.setattr(vector_store, "qmodels", None)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        vector_store._qdrant_distance()
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        vector_store._build_qdrant_filter(KB_ID, None)

    monkeypatch.setattr(vector_store, "qmodels", qdrant_models)
    document_ids = [uuid4(), uuid4()]
    q_filter = vector_store._build_qdrant_filter(KB_ID, document_ids)
    assert q_filter.must[0].match.value == str(KB_ID)
    assert q_filter.must[1].match.any == [str(value) for value in document_ids]

    monkeypatch.setattr(vector_store.settings, "QDRANT_DISTANCE", "euclid")
    assert vector_store._normalize_qdrant_score(3.0) == 0.25
    monkeypatch.setattr(vector_store.settings, "QDRANT_DISTANCE", "dot")
    assert vector_store._normalize_qdrant_score(3.0) == 3.0


@pytest.mark.asyncio
async def test_collection_and_payload_index_existing_boundaries(monkeypatch):
    client = SimpleNamespace(
        get_collection=AsyncMock(return_value=object()),
        create_collection=AsyncMock(),
        create_payload_index=AsyncMock(),
    )
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    collection = vector_store._collection_name(7)
    assert await vector_store._ensure_collection(7) == collection
    client.create_collection.assert_not_awaited()
    await vector_store._ensure_payload_index(collection, "kb_id")
    assert client.create_payload_index.await_count == 2

    monkeypatch.setattr(vector_store, "qmodels", None)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        await vector_store._ensure_collection(8)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        await vector_store._ensure_payload_index("kb_8", "kb_id")


@pytest.mark.asyncio
async def test_embedding_storage_dimension_boundaries(monkeypatch):
    client = SimpleNamespace(
        upsert=AsyncMock(return_value=SimpleNamespace(status="completed"))
    )
    ensure_collection = AsyncMock(return_value="kb_2")
    monkeypatch.setattr(vector_store, "_ensure_collection", ensure_collection)
    monkeypatch.setattr(
        vector_store, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    store = VectorStore()

    chunk_id = uuid4()
    await store._store_embedding(chunk_id, [0.1, 0.2])
    assert store._detected_dimension == 2
    assert client.upsert.await_args.kwargs["points"][0].payload == {}

    with pytest.raises(ValueError, match="Cannot determine embedding dimension"):
        await VectorStore()._batch_store_embeddings([uuid4()], [[]])


@pytest.mark.asyncio
async def test_mutation_paths_delete_existing_remote_vectors(monkeypatch):
    document_id = uuid4()
    chunk_id = uuid4()
    values = [
        SimpleNamespace(values_list=AsyncMock(return_value=[document_id])),
        SimpleNamespace(delete=AsyncMock(return_value=1)),
    ]
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", Mock(side_effect=values))
    monkeypatch.setattr(
        vector_store.Document,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[KB_ID]))),
    )
    monkeypatch.setattr(
        vector_store, "get_kb_embedding_dimension", AsyncMock(return_value=3)
    )
    monkeypatch.setattr(
        vector_store, "_collection_exists", AsyncMock(return_value=True)
    )
    delete_points = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_points", delete_points)

    assert await VectorStore().delete_chunk_vector(chunk_id) is True
    delete_points.assert_awaited_once_with(
        vector_store._collection_name(3), [str(chunk_id)]
    )

    documents = SimpleNamespace(values_list=AsyncMock(return_value=[document_id]))
    chunks = SimpleNamespace(delete=AsyncMock(return_value=2))
    monkeypatch.setattr(vector_store.Document, "filter", Mock(return_value=documents))
    monkeypatch.setattr(vector_store.DocumentChunk, "filter", Mock(return_value=chunks))
    delete_filter = AsyncMock()
    monkeypatch.setattr(vector_store, "_delete_qdrant_filter", delete_filter)

    assert await VectorStore().delete_kb_vectors(KB_ID) == 2
    delete_filter.assert_awaited_once()
