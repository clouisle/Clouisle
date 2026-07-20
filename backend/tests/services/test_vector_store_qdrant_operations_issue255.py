import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.services.vector_store import DimensionMismatchError, VectorStore

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

    assert await store._vector_search(KB_ID, "query", 1) == []

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
        {"chunk_id": "high", "score": 0.9},
        {"chunk_id": "low", "score": 0.1},
    ]
    monkeypatch.setattr(store, "_vector_search", AsyncMock(return_value=vector_results))
    monkeypatch.setattr(
        store, "_fulltext_search", AsyncMock(return_value=vector_results)
    )

    assert await store.search(
        KB_ID, "query", search_mode="vector", top_k=1, score_threshold=0.5
    ) == [{"chunk_id": "high", "score": 0.9}]
    assert store.embedding_dimension == 2
    assert await store.search(KB_ID, "query", search_mode="fulltext", top_k=1) == [
        {"chunk_id": "high", "score": 0.9}
    ]

    store._vector_search.side_effect = DimensionMismatchError("wrong dimension")
    assert await store.search(KB_ID, "query", search_mode="hybrid", top_k=1) == [
        {"chunk_id": "high", "score": 0.5, "search_type": "hybrid"}
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
