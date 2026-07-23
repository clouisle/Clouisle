from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.memory import EntityType, RelationType
from app.services import memory
from app.services.memory import MemoryService


class FirstQuery:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


@pytest.mark.anyio
async def test_optional_qdrant_dependency_errors(monkeypatch):
    monkeypatch.setattr(memory, "AsyncQdrantClient", None)
    monkeypatch.setattr(memory, "_qdrant_client", None)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        await memory._get_qdrant_client()

    monkeypatch.setattr(memory, "qmodels", None)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        await memory._ensure_memory_collection(3)


@pytest.mark.anyio
async def test_create_entity_converts_type_and_reuses_existing(monkeypatch):
    existing = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", lambda **_kwargs: FirstQuery(existing)
    )
    update = AsyncMock(return_value="updated")
    monkeypatch.setattr(MemoryService, "update_entity", update)

    result = await MemoryService.create_entity(uuid4(), "Ada", "person")

    assert result == "updated"
    assert update.await_args.kwargs["entity_id"] == existing.id


@pytest.mark.anyio
async def test_update_entity_skips_empty_changes(monkeypatch):
    entity = SimpleNamespace(
        name="Ada", description="old", properties={"old": 1}, save=AsyncMock()
    )
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", lambda **_kwargs: FirstQuery(entity)
    )
    update_embedding = AsyncMock()
    monkeypatch.setattr(MemoryService, "_update_entity_embedding", update_embedding)

    await MemoryService.update_entity(uuid4(), uuid4(), description="", properties={})

    assert entity.description == "old"
    assert entity.properties == {"old": 1}
    update_embedding.assert_awaited_once_with(entity)


@pytest.mark.anyio
async def test_create_relation_converts_type_and_returns_existing(monkeypatch):
    source = SimpleNamespace(id=uuid4())
    target = SimpleNamespace(id=uuid4())
    existing = SimpleNamespace(id=uuid4())
    values = iter([source, target])
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", lambda **_kwargs: FirstQuery(next(values))
    )
    monkeypatch.setattr(
        memory.MemoryRelation, "filter", lambda **_kwargs: FirstQuery(existing)
    )

    result = await MemoryService.create_relation(
        uuid4(), source.id, target.id, RelationType.KNOWS.value
    )

    assert result is existing


@pytest.mark.anyio
async def test_add_embedding_rejects_missing_qdrant_models(monkeypatch):
    from app.llm import model_manager

    entity = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        name="Ada",
        description="",
        entity_type=EntityType.PERSON,
    )
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1], "model_id": "model"}),
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(memory, "qmodels", None)

    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        await MemoryService._add_entity_embedding(entity)
