from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.memory import EntityType
from app.services import memory
from app.services.memory import MemoryService


class FirstQuery:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


class AllQuery:
    def __init__(self, value):
        self.value = value

    async def all(self):
        return self.value


@pytest.mark.anyio
async def test_memory_service_qdrant_client_caches_instance(monkeypatch):
    client = object()

    def constructor(**_kwargs):
        return client

    monkeypatch.setattr(memory, "_qdrant_client", None)
    monkeypatch.setattr(memory, "AsyncQdrantClient", constructor)

    assert await memory._get_qdrant_client() is client
    assert await memory._get_qdrant_client() is client


@pytest.mark.anyio
async def test_memory_service_ensure_collection_covers_cached_and_create(
    monkeypatch,
):
    client = SimpleNamespace(
        get_collection=AsyncMock(side_effect=RuntimeError("missing")),
        create_collection=AsyncMock(),
        create_payload_index=AsyncMock(),
    )
    fake_models = SimpleNamespace(
        VectorParams=lambda **kwargs: kwargs,
        Distance=SimpleNamespace(COSINE="cosine"),
        PayloadSchemaType=SimpleNamespace(KEYWORD="keyword"),
    )
    monkeypatch.setattr(memory, "qmodels", fake_models)
    monkeypatch.setattr(memory, "_memory_collections", set())
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))

    assert await memory._ensure_memory_collection(8) == "memory_entities_dim_8"
    assert await memory._ensure_memory_collection(8) == "memory_entities_dim_8"
    client.get_collection.assert_awaited_once()
    client.create_collection.assert_awaited_once()
    client.create_payload_index.assert_awaited_once()


@pytest.mark.anyio
async def test_memory_service_update_entity_sets_initial_description(monkeypatch):
    entity = SimpleNamespace(
        id=uuid4(),
        name="Ada",
        description="",
        properties={"old": 1},
        embedding_id=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **_kwargs: FirstQuery(entity),
    )
    monkeypatch.setattr(
        MemoryService,
        "_update_entity_embedding",
        AsyncMock(),
    )

    result = await MemoryService.update_entity(
        uuid4(), entity.id, description="new", properties={"extra": 2}
    )

    assert result.description == "new"
    assert result.properties == {"old": 1, "extra": 2}
    entity.save.assert_awaited_once()


@pytest.mark.anyio
async def test_memory_service_delete_entity_without_embedding(monkeypatch):
    entity = SimpleNamespace(
        name="Ada",
        embedding_id=None,
        embedding_model_id=None,
        delete=AsyncMock(),
    )
    delete_embedding = AsyncMock()
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **_kwargs: FirstQuery(entity),
    )
    monkeypatch.setattr(MemoryService, "_delete_entity_embedding", delete_embedding)

    await MemoryService.delete_entity(uuid4(), uuid4())

    delete_embedding.assert_not_awaited()
    entity.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_memory_service_search_covers_embedding_and_qdrant_failures(monkeypatch):
    from app.llm import model_manager

    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(side_effect=RuntimeError("model down")),
    )
    assert await MemoryService.search_entities(uuid4(), "query") == []

    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1], "model_id": None}),
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="c")
    )
    monkeypatch.setattr(
        memory,
        "qmodels",
        SimpleNamespace(
            FieldCondition=lambda **kwargs: kwargs,
            MatchValue=lambda **kwargs: kwargs,
            Filter=lambda **kwargs: kwargs,
        ),
    )
    monkeypatch.setattr(
        memory,
        "_get_qdrant_client",
        AsyncMock(
            return_value=SimpleNamespace(
                query_points=AsyncMock(side_effect=RuntimeError("qdrant down"))
            )
        ),
    )
    assert (
        await MemoryService.search_entities(
            uuid4(), "query", entity_type=EntityType.PERSON
        )
        == []
    )


@pytest.mark.anyio
async def test_memory_service_search_updates_access_tracking(monkeypatch):
    from app.llm import model_manager

    entity = SimpleNamespace(access_count=2, last_accessed_at=None, save=AsyncMock())
    point_id = uuid4()
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1, 0.2]}),
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="c")
    )
    monkeypatch.setattr(
        memory,
        "qmodels",
        SimpleNamespace(
            FieldCondition=lambda **kwargs: kwargs,
            MatchValue=lambda **kwargs: kwargs,
            Filter=lambda **kwargs: kwargs,
        ),
    )
    monkeypatch.setattr(
        memory,
        "_get_qdrant_client",
        AsyncMock(
            return_value=SimpleNamespace(
                query_points=AsyncMock(
                    return_value=SimpleNamespace(
                        points=[SimpleNamespace(id=point_id, score=1, payload={})]
                    )
                )
            )
        ),
    )
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **_kwargs: AllQuery([entity]),
    )

    assert await MemoryService.search_entities(uuid4(), "query") == [entity]
    assert entity.access_count == 3
    assert entity.last_accessed_at is not None
    entity.save.assert_awaited_once()
