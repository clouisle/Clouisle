from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import memories
from app.models.memory import EntityType, RelationType
from app.schemas.memory import (
    CreateEntityRequest,
    CreateRelationRequest,
    UpdateEntityRequest,
)
from app.schemas.response import BusinessError, ResponseCode


def _entity(user_id=None, **overrides):
    values = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "name": "Python",
        "entity_type": EntityType.SKILL,
        "description": "Used daily",
        "properties": {"level": "advanced"},
        "source_conversation_id": None,
        "source_message_id": None,
        "access_count": 2,
        "last_accessed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _relation(user_id=None, **overrides):
    values = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "source_entity_id": uuid4(),
        "target_entity_id": uuid4(),
        "relation_type": RelationType.USES,
        "description": None,
        "properties": {},
        "source_conversation_id": None,
        "source_message_id": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _query(items, total=None):
    query = MagicMock()
    query.filter.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.count = AsyncMock(return_value=len(items) if total is None else total)
    query.all = AsyncMock(return_value=items)
    query.first = AsyncMock(return_value=items[0] if items else None)
    return query


def _assert_error(exc, code, key):
    assert exc.value.code == code
    assert exc.value.msg_key == key


@pytest.mark.asyncio
async def test_entity_list_and_get_branches(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    entity = _entity(user.id)
    relation = _relation(user.id, source_entity_id=entity.id)
    listed = _query([entity], total=3)
    monkeypatch.setattr(memories.MemoryEntity, "filter", MagicMock(return_value=listed))

    result = await memories.list_entities(user, EntityType.SKILL, page=2, page_size=1)

    assert result["data"].items[0].name == "Python"
    assert result["data"].total == 3
    listed.filter.assert_called_once_with(entity_type=EntityType.SKILL)
    listed.offset.assert_called_once_with(1)

    unfiltered = _query([])
    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=unfiltered)
    )
    result = await memories.list_entities(user, entity_type=None, page=1, page_size=20)
    assert result["data"].items == []
    unfiltered.filter.assert_not_called()

    entity_query = _query([entity])
    relation_queries = [_query([relation]), _query([])]
    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=entity_query)
    )
    monkeypatch.setattr(
        memories.MemoryRelation, "filter", MagicMock(side_effect=relation_queries)
    )

    result = await memories.get_entity(entity.id, user)
    assert result["data"]["entity"].id == entity.id
    assert len(result["data"]["outgoing_relations"]) == 1
    assert result["data"]["incoming_relations"] == []

    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=_query([]))
    )
    with pytest.raises(BusinessError) as exc:
        await memories.get_entity(entity.id, user)
    _assert_error(exc, ResponseCode.NOT_FOUND, "memory_entity_not_found")


@pytest.mark.asyncio
async def test_create_and_update_entity_branches(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    request = MagicMock()
    entity = _entity(user.id)
    monkeypatch.setattr(
        memories.MemoryService, "create_entity", AsyncMock(return_value=entity)
    )
    audit = AsyncMock()
    monkeypatch.setattr(memories.AuditLogService, "log", audit)

    result = await memories.create_entity(
        request,
        CreateEntityRequest(
            name="Python",
            entity_type=EntityType.SKILL,
            properties={"level": "advanced"},
        ),
        user,
    )
    assert result["data"].id == entity.id
    audit.assert_awaited_once()

    memories.MemoryService.create_entity.side_effect = RuntimeError("embedding failed")
    with pytest.raises(BusinessError) as exc:
        await memories.create_entity(
            request,
            CreateEntityRequest(name="Rust", entity_type=EntityType.SKILL),
            user,
        )
    _assert_error(exc, ResponseCode.INTERNAL_ERROR, "memory_entity_create_failed")

    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=_query([entity]))
    )
    update_embedding = AsyncMock()
    monkeypatch.setattr(
        memories.MemoryService, "_update_entity_embedding", update_embedding
    )
    audit.reset_mock()
    body = UpdateEntityRequest(
        name="Python 3", description="Updated", properties={"years": 5}
    )

    result = await memories.update_entity(entity.id, request, body, user)
    assert result["data"].name == "Python 3"
    assert entity.properties == {"level": "advanced", "years": 5}
    entity.save.assert_awaited_once()
    update_embedding.assert_awaited_once_with(entity)
    audit.assert_awaited_once()

    entity.save.reset_mock()
    update_embedding.reset_mock()
    await memories.update_entity(
        entity.id, request, UpdateEntityRequest(properties={"active": True}), user
    )
    assert entity.properties["active"] is True
    entity.save.assert_awaited_once()
    update_embedding.assert_not_awaited()

    await memories.update_entity(
        entity.id, request, UpdateEntityRequest(description=""), user
    )
    update_embedding.assert_not_awaited()

    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=_query([]))
    )
    with pytest.raises(BusinessError) as exc:
        await memories.update_entity(entity.id, request, UpdateEntityRequest(), user)
    _assert_error(exc, ResponseCode.NOT_FOUND, "memory_entity_not_found")

    monkeypatch.setattr(
        memories.MemoryEntity,
        "filter",
        MagicMock(side_effect=RuntimeError("database unavailable")),
    )
    with pytest.raises(BusinessError) as exc:
        await memories.update_entity(entity.id, request, UpdateEntityRequest(), user)
    _assert_error(exc, ResponseCode.INTERNAL_ERROR, "memory_entity_update_failed")


@pytest.mark.asyncio
async def test_delete_entity_success_and_errors(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    request = MagicMock()
    entity = _entity(user.id)
    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=_query([entity]))
    )
    delete = AsyncMock()
    monkeypatch.setattr(memories.MemoryService, "delete_entity", delete)
    audit = AsyncMock()
    monkeypatch.setattr(memories.AuditLogService, "log", audit)

    result = await memories.delete_entity(entity.id, request, user)
    assert result["data"]["message"]
    assert audit.await_args.kwargs["resource_name"] == "Python"

    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=_query([]))
    )
    delete.side_effect = ValueError("memory_entity_not_found")
    with pytest.raises(BusinessError) as exc:
        await memories.delete_entity(entity.id, request, user)
    _assert_error(exc, ResponseCode.NOT_FOUND, "memory_entity_not_found")

    delete.side_effect = RuntimeError("database unavailable")
    with pytest.raises(BusinessError) as exc:
        await memories.delete_entity(entity.id, request, user)
    _assert_error(exc, ResponseCode.INTERNAL_ERROR, "memory_entity_delete_failed")


@pytest.mark.asyncio
async def test_relation_list_create_and_delete_branches(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    request = MagicMock()
    relation = _relation(user.id)
    query = _query([relation], total=4)
    monkeypatch.setattr(
        memories.MemoryRelation, "filter", MagicMock(return_value=query)
    )

    result = await memories.list_relations(
        user,
        entity_id=relation.source_entity_id,
        relation_type=RelationType.USES,
        page=2,
        page_size=2,
    )
    assert result["data"]["total"] == 4
    assert result["data"]["items"][0].id == relation.id
    assert query.filter.call_count == 2
    query.offset.assert_called_once_with(2)

    unfiltered = _query([])
    monkeypatch.setattr(
        memories.MemoryRelation, "filter", MagicMock(return_value=unfiltered)
    )
    result = await memories.list_relations(
        user, entity_id=None, relation_type=None, page=1, page_size=20
    )
    assert result["data"]["items"] == []
    unfiltered.filter.assert_not_called()

    create = AsyncMock(return_value=relation)
    monkeypatch.setattr(memories.MemoryService, "create_relation", create)
    audit = AsyncMock()
    monkeypatch.setattr(memories.AuditLogService, "log", audit)
    body = CreateRelationRequest(
        source_entity_id=relation.source_entity_id,
        target_entity_id=relation.target_entity_id,
        relation_type=RelationType.USES,
    )

    result = await memories.create_relation(request, body, user)
    assert result["data"].id == relation.id
    audit.assert_awaited_once()

    for error, key in [
        (
            ValueError("memory_source_entity_not_found"),
            "memory_source_entity_not_found",
        ),
        (ValueError("invalid relation"), "memory_relation_create_failed"),
    ]:
        create.side_effect = error
        with pytest.raises(BusinessError) as exc:
            await memories.create_relation(request, body, user)
        _assert_error(exc, ResponseCode.BAD_REQUEST, key)

    create.side_effect = RuntimeError("database unavailable")
    with pytest.raises(BusinessError) as exc:
        await memories.create_relation(request, body, user)
    _assert_error(exc, ResponseCode.INTERNAL_ERROR, "memory_relation_create_failed")

    delete = AsyncMock()
    monkeypatch.setattr(memories.MemoryService, "delete_relation", delete)
    audit.reset_mock()
    result = await memories.delete_relation(relation.id, request, user)
    assert result["data"]["message"]
    audit.assert_awaited_once()

    delete.side_effect = ValueError("memory_relation_not_found")
    with pytest.raises(BusinessError) as exc:
        await memories.delete_relation(relation.id, request, user)
    _assert_error(exc, ResponseCode.NOT_FOUND, "memory_relation_not_found")

    delete.side_effect = RuntimeError("database unavailable")
    with pytest.raises(BusinessError) as exc:
        await memories.delete_relation(relation.id, request, user)
    _assert_error(exc, ResponseCode.INTERNAL_ERROR, "memory_relation_delete_failed")


@pytest.mark.asyncio
async def test_memory_graph_all_and_subgraph(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    entity = _entity(user.id)
    relation = _relation(user.id, source_entity_id=entity.id)
    entity_query = _query([entity])
    relation_query = _query([relation])
    monkeypatch.setattr(
        memories.MemoryEntity, "filter", MagicMock(return_value=entity_query)
    )
    monkeypatch.setattr(
        memories.MemoryRelation, "filter", MagicMock(return_value=relation_query)
    )

    result = await memories.get_memory_graph(user, entity_ids=None, max_depth=1)
    assert result["data"].entities[0].id == entity.id
    assert result["data"].relations[0].id == relation.id

    subgraph = AsyncMock(return_value={"entities": [entity], "relations": [relation]})
    monkeypatch.setattr(memories.MemoryService, "get_entity_subgraph", subgraph)
    result = await memories.get_memory_graph(user, entity_ids=[entity.id], max_depth=3)
    assert result["data"].entities[0].name == "Python"
    subgraph.assert_awaited_once_with(
        user_id=user.id, entity_ids=[entity.id], max_depth=3
    )
