from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.memory import EntityType, RelationType
from app.services import memory as memory_module
from app.services.memory import MemoryService


def _query(first_result):
    return SimpleNamespace(first=AsyncMock(return_value=first_result))


@pytest.mark.asyncio
async def test_create_entity_persists_defaults_and_adds_embedding(monkeypatch):
    user_id = uuid4()
    entity = SimpleNamespace(name="Python", entity_type=EntityType.SKILL)
    entity_filter = MagicMock(return_value=_query(None))
    create = AsyncMock(return_value=entity)
    add_embedding = AsyncMock()
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", entity_filter)
    monkeypatch.setattr(memory_module.MemoryEntity, "create", create)
    monkeypatch.setattr(MemoryService, "_add_entity_embedding", add_embedding)

    result = await MemoryService.create_entity(user_id, "Python", "skill")

    assert result is entity
    entity_filter.assert_called_once_with(
        user_id=user_id, name="Python", entity_type=EntityType.SKILL
    )
    create.assert_awaited_once_with(
        user_id=user_id,
        name="Python",
        entity_type=EntityType.SKILL,
        description="",
        properties={},
        source_conversation_id=None,
        source_message_id=None,
        embedding_model_id=None,
    )
    add_embedding.assert_awaited_once_with(entity)


@pytest.mark.asyncio
async def test_create_entity_updates_existing_entity(monkeypatch):
    user_id = uuid4()
    existing = SimpleNamespace(id=uuid4())
    update = AsyncMock(return_value=existing)
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query(existing))
    )
    monkeypatch.setattr(MemoryService, "update_entity", update)

    result = await MemoryService.create_entity(
        user_id, "Python", EntityType.SKILL, "experienced", {"level": "senior"}
    )

    assert result is existing
    update.assert_awaited_once_with(
        user_id=user_id,
        entity_id=existing.id,
        description="experienced",
        properties={"level": "senior"},
    )


@pytest.mark.asyncio
async def test_update_entity_merges_fields_and_refreshes_embedding(monkeypatch):
    user_id = uuid4()
    entity = SimpleNamespace(
        name="Python",
        description="uses daily",
        properties={"level": "intermediate"},
        save=AsyncMock(),
    )
    refresh_embedding = AsyncMock()
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query(entity))
    )
    monkeypatch.setattr(MemoryService, "_update_entity_embedding", refresh_embedding)

    result = await MemoryService.update_entity(
        user_id, uuid4(), "for APIs", {"level": "advanced", "years": 5}
    )

    assert result is entity
    assert entity.description == "uses daily\nfor APIs"
    assert entity.properties == {"level": "advanced", "years": 5}
    entity.save.assert_awaited_once()
    refresh_embedding.assert_awaited_once_with(entity)


@pytest.mark.asyncio
async def test_update_entity_rejects_entity_outside_user_scope(monkeypatch):
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query(None))
    )

    with pytest.raises(ValueError, match="memory_entity_not_found"):
        await MemoryService.update_entity(uuid4(), uuid4(), "ignored")


@pytest.mark.asyncio
async def test_delete_entity_removes_embedding_before_persistence(monkeypatch):
    user_id = uuid4()
    entity = SimpleNamespace(
        name="Python",
        embedding_id="point-id",
        embedding_model_id="model-id",
        delete=AsyncMock(),
    )
    delete_embedding = AsyncMock()
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query(entity))
    )
    monkeypatch.setattr(MemoryService, "_delete_entity_embedding", delete_embedding)

    await MemoryService.delete_entity(user_id, uuid4())

    delete_embedding.assert_awaited_once_with("point-id", "model-id")
    entity.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_relation_requires_source_owned_by_user(monkeypatch):
    entity_filter = MagicMock(return_value=_query(None))
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", entity_filter)

    with pytest.raises(ValueError, match="memory_source_entity_not_found"):
        await MemoryService.create_relation(uuid4(), uuid4(), uuid4(), "related_to")

    assert entity_filter.call_count == 2


@pytest.mark.asyncio
async def test_create_relation_persists_enum_and_defaults(monkeypatch):
    user_id = uuid4()
    source_id, target_id = uuid4(), uuid4()
    source = SimpleNamespace(name="Python")
    target = SimpleNamespace(name="FastAPI")
    relation = SimpleNamespace()
    entity_filter = MagicMock(side_effect=[_query(source), _query(target)])
    relation_filter = MagicMock(return_value=_query(None))
    create = AsyncMock(return_value=relation)
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", entity_filter)
    monkeypatch.setattr(memory_module.MemoryRelation, "filter", relation_filter)
    monkeypatch.setattr(memory_module.MemoryRelation, "create", create)

    result = await MemoryService.create_relation(
        user_id, source_id, target_id, "related_to", "used together"
    )

    assert result is relation
    create.assert_awaited_once_with(
        user_id=user_id,
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type=RelationType.RELATED_TO,
        description="used together",
        properties={},
        source_conversation_id=None,
        source_message_id=None,
    )


@pytest.mark.asyncio
async def test_delete_relation_rejects_missing_relation(monkeypatch):
    monkeypatch.setattr(
        memory_module.MemoryRelation, "filter", MagicMock(return_value=_query(None))
    )

    with pytest.raises(ValueError, match="memory_relation_not_found"):
        await MemoryService.delete_relation(uuid4(), uuid4())
