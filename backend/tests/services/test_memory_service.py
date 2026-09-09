from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.llm import model_manager
from app.models.memory import EntityType, RelationType
from app.services import memory as memory_module
from app.services.memory import MemoryService


def _query(*, first=None, all=None):
    query = MagicMock()
    query.first = AsyncMock(return_value=first)
    query.all = AsyncMock(return_value=[] if all is None else all)
    query.prefetch_related.return_value = query
    return query


@pytest.fixture(autouse=True)
def qdrant_models(monkeypatch):
    def constructor(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        memory_module,
        "qmodels",
        SimpleNamespace(
            FieldCondition=constructor,
            MatchValue=constructor,
            Filter=constructor,
            PointStruct=constructor,
            PointIdsList=constructor,
            Range=constructor,
        ),
    )


@pytest.mark.asyncio
async def test_create_entity_persists_defaults_and_adds_embedding(monkeypatch):
    user_id = uuid4()
    entity = SimpleNamespace(name="Python", entity_type=EntityType.SKILL)
    create = AsyncMock(return_value=entity)
    add_embedding = AsyncMock()
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query())
    )
    monkeypatch.setattr(memory_module.MemoryEntity, "create", create)
    monkeypatch.setattr(MemoryService, "_add_entity_embedding", add_embedding)

    result = await MemoryService.create_entity(user_id, "Python", "skill")

    assert result is entity
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
        memory_module.MemoryEntity,
        "filter",
        MagicMock(return_value=_query(first=existing)),
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
    entity = SimpleNamespace(
        name="Python",
        description="uses daily",
        properties={"level": "intermediate", "kept": True},
        save=AsyncMock(),
    )
    refresh_embedding = AsyncMock()
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(return_value=_query(first=entity)),
    )
    monkeypatch.setattr(MemoryService, "_update_entity_embedding", refresh_embedding)

    result = await MemoryService.update_entity(
        uuid4(), uuid4(), "for APIs", {"level": "advanced", "years": 5}
    )

    assert result is entity
    assert entity.description == "uses daily\nfor APIs"
    assert entity.properties == {"level": "advanced", "kept": True, "years": 5}
    entity.save.assert_awaited_once()
    refresh_embedding.assert_awaited_once_with(entity)


@pytest.mark.asyncio
async def test_update_entity_rejects_entity_outside_user_scope(monkeypatch):
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query())
    )

    with pytest.raises(ValueError, match="memory_entity_not_found"):
        await MemoryService.update_entity(uuid4(), uuid4(), "ignored")


@pytest.mark.asyncio
@pytest.mark.parametrize("embedding_id", [None, "point-id"])
async def test_delete_entity_persists_and_conditionally_removes_embedding(
    monkeypatch, embedding_id
):
    entity = SimpleNamespace(
        name="Python",
        embedding_id=embedding_id,
        embedding_model_id="model-id",
        delete=AsyncMock(),
    )
    delete_embedding = AsyncMock()
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(return_value=_query(first=entity)),
    )
    monkeypatch.setattr(MemoryService, "_delete_entity_embedding", delete_embedding)

    await MemoryService.delete_entity(uuid4(), uuid4())

    entity.delete.assert_awaited_once()
    if embedding_id:
        delete_embedding.assert_awaited_once_with("point-id", "model-id")
    else:
        delete_embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_relation_validates_target_after_source(monkeypatch):
    source = SimpleNamespace(name="Python")
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(side_effect=[_query(first=source), _query()]),
    )

    with pytest.raises(ValueError, match="memory_target_entity_not_found"):
        await MemoryService.create_relation(uuid4(), uuid4(), uuid4(), "related_to")


@pytest.mark.asyncio
async def test_create_relation_returns_existing_without_duplicate_write(monkeypatch):
    source = SimpleNamespace(name="Python")
    target = SimpleNamespace(name="FastAPI")
    existing = SimpleNamespace(id=uuid4())
    create = AsyncMock()
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(side_effect=[_query(first=source), _query(first=target)]),
    )
    monkeypatch.setattr(
        memory_module.MemoryRelation,
        "filter",
        MagicMock(return_value=_query(first=existing)),
    )
    monkeypatch.setattr(memory_module.MemoryRelation, "create", create)

    result = await MemoryService.create_relation(
        uuid4(), uuid4(), uuid4(), RelationType.RELATED_TO
    )

    assert result is existing
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_relation_persists_enum_and_defaults(monkeypatch):
    user_id, source_id, target_id = uuid4(), uuid4(), uuid4()
    source = SimpleNamespace(name="Python")
    target = SimpleNamespace(name="FastAPI")
    relation = SimpleNamespace()
    create = AsyncMock(return_value=relation)
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(side_effect=[_query(first=source), _query(first=target)]),
    )
    monkeypatch.setattr(
        memory_module.MemoryRelation, "filter", MagicMock(return_value=_query())
    )
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
async def test_delete_relation_success_and_missing(monkeypatch):
    relation = SimpleNamespace(delete=AsyncMock())
    relation_filter = MagicMock(side_effect=[_query(first=relation), _query()])
    monkeypatch.setattr(memory_module.MemoryRelation, "filter", relation_filter)

    await MemoryService.delete_relation(uuid4(), uuid4())
    relation.delete.assert_awaited_once()

    with pytest.raises(ValueError, match="memory_relation_not_found"):
        await MemoryService.delete_relation(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_search_entities_filters_by_user_and_type_and_tracks_access(monkeypatch):
    user_id = uuid4()
    point_id = uuid4()
    entity = SimpleNamespace(access_count=2, last_accessed_at=None, save=AsyncMock())
    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[SimpleNamespace(id=point_id, score=0.9, payload={})]
            )
        )
    )
    entity_query = _query(all=[entity])
    entity_filter = MagicMock(return_value=entity_query)
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1, 0.2], "model_id": "embed"}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", entity_filter)

    result = await MemoryService.search_entities(
        user_id, "python", top_k=3, entity_type=EntityType.SKILL
    )

    assert result == [entity]
    client.query_points.assert_awaited_once()
    call = client.query_points.await_args.kwargs
    assert call["collection_name"] == "collection"
    assert call["limit"] == 3
    assert [condition.key for condition in call["query_filter"].must] == [
        "user_id",
        "entity_type",
    ]
    entity_filter.assert_called_once_with(id__in=[point_id], user_id=user_id)
    assert entity.access_count == 3
    assert entity.last_accessed_at is not None
    entity.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_entities_returns_empty_on_embedding_or_qdrant_failure(
    monkeypatch,
):
    embedding = AsyncMock(side_effect=RuntimeError("embedding unavailable"))
    monkeypatch.setattr(model_manager, "get_embedding", embedding)

    assert await MemoryService.search_entities(uuid4(), "query") == []

    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1]}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(
        memory_module,
        "_get_qdrant_client",
        AsyncMock(
            return_value=SimpleNamespace(
                query_points=AsyncMock(side_effect=RuntimeError("qdrant unavailable"))
            )
        ),
    )

    assert await MemoryService.search_entities(uuid4(), "query") == []


@pytest.mark.asyncio
async def test_get_entity_subgraph_fetches_bidirectional_neighbors_with_user_scope(
    monkeypatch,
):
    user_id, start_id, neighbor_id = uuid4(), uuid4(), uuid4()
    start = SimpleNamespace(id=start_id)
    neighbor = SimpleNamespace(id=neighbor_id)
    relation = SimpleNamespace(
        id=uuid4(),
        source_entity_id=start_id,
        target_entity_id=neighbor_id,
        relation_type=RelationType.RELATED_TO,
    )
    entity_filter = MagicMock(
        side_effect=[_query(all=[start]), _query(all=[start, neighbor])]
    )
    relation_filter = MagicMock(side_effect=[_query(all=[relation]), _query(all=[])])
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", entity_filter)
    monkeypatch.setattr(memory_module.MemoryRelation, "filter", relation_filter)

    result = await MemoryService.get_entity_subgraph(user_id, [start_id])

    assert result["entities"] == [start, neighbor]
    assert result["relations"] == [relation]
    assert result["entity_depth"] == {str(start_id): 0, str(neighbor_id): 1}
    assert result["truncated"] is False

    assert relation_filter.call_args_list[0].kwargs == {
        "user_id": user_id,
        "source_entity_id__in": [start_id],
    }
    assert relation_filter.call_args_list[1].kwargs == {
        "user_id": user_id,
        "target_entity_id__in": [start_id],
    }


@pytest.mark.asyncio
async def test_handle_get_memory_subgraph_formats_graph_for_tool(monkeypatch):
    user_id, start_id, neighbor_id = uuid4(), uuid4(), uuid4()
    start = SimpleNamespace(
        id=start_id,
        name="Ada",
        entity_type=EntityType.PERSON,
        description="mathematician",
        properties=None,
    )
    neighbor = SimpleNamespace(
        id=neighbor_id,
        name="Python",
        entity_type=EntityType.SKILL,
        description=None,
        properties={"level": "expert"},
    )
    relation = SimpleNamespace(
        id=uuid4(),
        source_entity_id=start_id,
        target_entity_id=neighbor_id,
        relation_type=RelationType.USES,
        description="primary language",
        properties=None,
    )
    get_subgraph = AsyncMock(
        return_value={
            "entities": [start, neighbor],
            "relations": [relation],
            "entity_depth": {str(start_id): 0, str(neighbor_id): 1},
            "truncated": True,
        }
    )
    monkeypatch.setattr(MemoryService, "get_entity_subgraph", get_subgraph)

    result = await MemoryService.handle_get_memory_subgraph(
        user_id=user_id,
        entity_ids=[str(start_id), str(neighbor_id)],
        max_depth=2,
        direction="outgoing",
        relation_types=["uses"],
    )

    assert result == {
        "success": True,
        "entities": [
            {
                "id": str(start_id),
                "name": "Ada",
                "type": "person",
                "description": "mathematician",
                "properties": {},
                "depth": 0,
            },
            {
                "id": str(neighbor_id),
                "name": "Python",
                "type": "skill",
                "description": None,
                "properties": {"level": "expert"},
                "depth": 1,
            },
        ],
        "relations": [
            {
                "id": str(relation.id),
                "source_entity_id": str(start_id),
                "source_name": "Ada",
                "relation_type": "uses",
                "target_entity_id": str(neighbor_id),
                "target_name": "Python",
                "description": "primary language",
                "properties": {},
            }
        ],
        "truncated": True,
    }
    get_subgraph.assert_awaited_once_with(
        user_id=user_id,
        entity_ids=[start_id, neighbor_id],
        max_depth=2,
        direction="outgoing",
        relation_types=["uses"],
        max_nodes=30,
        max_relations=100,
    )


@pytest.mark.asyncio
async def test_handle_get_memory_subgraph_resolves_exact_names_in_user_scope(
    monkeypatch,
):
    user_id = uuid4()
    project_id, feature_id = uuid4(), uuid4()
    project = SimpleNamespace(
        id=project_id,
        name="教智研一号开发项目",
        entity_type=EntityType.PROJECT,
        description="project",
        properties={},
    )
    feature = SimpleNamespace(
        id=feature_id,
        name="教科院二期功能开发",
        entity_type=EntityType.PROJECT,
        description="feature work",
        properties={},
    )
    entity_filter = MagicMock(return_value=_query(all=[project, feature]))
    get_subgraph = AsyncMock(
        return_value={
            "entities": [project, feature],
            "relations": [],
            "entity_depth": {str(project_id): 0, str(feature_id): 0},
            "truncated": False,
        }
    )
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", entity_filter)
    monkeypatch.setattr(MemoryService, "get_entity_subgraph", get_subgraph)

    result = await MemoryService.handle_get_memory_subgraph(
        user_id=user_id,
        entity_ids=["教智研一号开发项目", "教科院二期功能开发"],
        max_depth=2,
    )

    assert result["success"] is True
    assert [entity["id"] for entity in result["entities"]] == [
        str(project_id),
        str(feature_id),
    ]
    entity_filter.assert_called_once_with(
        user_id=user_id,
        name__in=["教智研一号开发项目", "教科院二期功能开发"],
    )
    get_subgraph.assert_awaited_once_with(
        user_id=user_id,
        entity_ids=[project_id, feature_id],
        max_depth=2,
        direction="both",
        relation_types=None,
        max_nodes=30,
        max_relations=100,
    )


@pytest.mark.asyncio
async def test_add_entity_embedding_upserts_payload_and_persists_model(monkeypatch):
    entity_id, user_id = uuid4(), uuid4()
    entity = SimpleNamespace(
        id=entity_id,
        user_id=user_id,
        name="Python",
        description="language",
        entity_type=EntityType.SKILL,
        embedding_id=None,
        embedding_model_id=None,
        save=AsyncMock(),
    )
    client = SimpleNamespace(upsert=AsyncMock())
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1, 0.2], "model_id": "model"}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    await MemoryService._add_entity_embedding(entity)

    model_manager.get_embedding.assert_awaited_once_with(
        "Python: language", user_id=user_id
    )
    point = client.upsert.await_args.kwargs["points"][0]
    assert point.id == str(entity_id)
    assert point.vector == [0.1, 0.2]
    assert point.payload["user_id"] == str(user_id)
    assert point.payload["entity_type"] == "skill"
    assert point.payload["name"] == "Python"
    assert "updated_at_ts" in point.payload
    assert isinstance(point.payload["updated_at_ts"], int)
    assert entity.embedding_id == str(entity_id)
    assert entity.embedding_model_id == "model"
    entity.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_entity_embedding_wraps_provider_failure(monkeypatch):
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(side_effect=RuntimeError("not configured")),
    )
    entity = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), name="Python", description=None
    )

    with pytest.raises(
        RuntimeError, match="Failed to generate embedding: not configured"
    ):
        await MemoryService._add_entity_embedding(entity)


@pytest.mark.asyncio
async def test_update_entity_embedding_replaces_existing_point(monkeypatch):
    entity = SimpleNamespace(embedding_id="old", embedding_model_id="model")
    delete = AsyncMock()
    add = AsyncMock()
    monkeypatch.setattr(MemoryService, "_delete_entity_embedding", delete)
    monkeypatch.setattr(MemoryService, "_add_entity_embedding", add)

    await MemoryService._update_entity_embedding(entity)

    delete.assert_awaited_once_with("old", "model")
    add.assert_awaited_once_with(entity)


@pytest.mark.asyncio
async def test_handle_create_entity_reports_similar_names_and_audits(monkeypatch):
    user_id, entity_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id)
    entity = SimpleNamespace(id=entity_id, name="Python")
    monkeypatch.setattr(memory_module.User, "get", AsyncMock(return_value=user))
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(
            return_value=_query(
                all=[SimpleNamespace(name="python"), SimpleNamespace(name="Rust")]
            )
        ),
    )
    monkeypatch.setattr(MemoryService, "create_entity", AsyncMock(return_value=entity))
    audit = AsyncMock()
    monkeypatch.setattr(memory_module.AuditLogService, "log", audit)
    monkeypatch.setattr(memory_module, "t", lambda key, **kwargs: f"<{key}>")

    result = await MemoryService.handle_create_entity(
        user_id, "Python", "skill", "language"
    )

    assert result == {
        "success": True,
        "entity_id": str(entity_id),
        "message": "<memory_entity_created_tool><memory_similar_entities_notice>",
        "similar_entities": ["python"],
    }
    assert audit.await_args.kwargs["status"] == "success"


@pytest.mark.asyncio
async def test_handle_create_entity_failure_audits_after_user_lookup(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(memory_module.User, "get", AsyncMock(return_value=user))
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(side_effect=RuntimeError("database failed")),
    )
    audit = AsyncMock()
    monkeypatch.setattr(memory_module.AuditLogService, "log", audit)
    monkeypatch.setattr(memory_module, "_memory_tool_error", lambda: "safe error")

    result = await MemoryService.handle_create_entity(uuid4(), "Python", "skill")

    assert result == {"success": False, "error": "safe error"}
    assert audit.await_args.kwargs["status"] == "failed"
    assert audit.await_args.kwargs["error_message"] == "database failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["source", "target"])
async def test_handle_create_relation_reports_missing_endpoint(monkeypatch, missing):
    source = None if missing == "source" else SimpleNamespace(name="Python")
    target = SimpleNamespace(name="FastAPI") if missing == "source" else None
    monkeypatch.setattr(memory_module.User, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(side_effect=[_query(first=source), _query(first=target)]),
    )
    audit = AsyncMock()
    monkeypatch.setattr(memory_module.AuditLogService, "log", audit)
    monkeypatch.setattr(memory_module, "t", lambda key, **kwargs: key)

    result = await MemoryService.handle_create_relation(
        uuid4(), "Python", "FastAPI", "uses"
    )

    assert result == {
        "success": False,
        "error": f"memory_{missing}_entity_not_found",
    }
    assert audit.await_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_create_relation_success_audits_persisted_relation(monkeypatch):
    relation_id = uuid4()
    source = SimpleNamespace(id=uuid4(), name="Python")
    target = SimpleNamespace(id=uuid4(), name="FastAPI")
    monkeypatch.setattr(memory_module.User, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(side_effect=[_query(first=source), _query(first=target)]),
    )
    create = AsyncMock(return_value=SimpleNamespace(id=relation_id))
    monkeypatch.setattr(MemoryService, "create_relation", create)
    audit = AsyncMock()
    monkeypatch.setattr(memory_module.AuditLogService, "log", audit)
    monkeypatch.setattr(memory_module, "t", lambda key, **kwargs: key)

    result = await MemoryService.handle_create_relation(
        uuid4(), "Python", "FastAPI", "uses", "framework"
    )

    assert result == {
        "success": True,
        "relation_id": str(relation_id),
        "message": "memory_relation_created_tool",
    }
    create.assert_awaited_once()
    assert audit.await_args.kwargs["status"] == "success"


@pytest.mark.asyncio
async def test_handle_update_entity_reports_missing_and_audits(monkeypatch):
    monkeypatch.setattr(memory_module.User, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query())
    )
    audit = AsyncMock()
    monkeypatch.setattr(memory_module.AuditLogService, "log", audit)
    monkeypatch.setattr(memory_module, "t", lambda key, **kwargs: key)

    result = await MemoryService.handle_update_entity(uuid4(), "Missing")

    assert result == {
        "success": False,
        "error": "memory_entity_named_not_found",
    }
    assert audit.await_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_handle_update_entity_records_changes_and_success(monkeypatch):
    entity_id = uuid4()
    entity = SimpleNamespace(
        id=entity_id,
        name="Python",
        description="old",
        properties={"level": 1},
        entity_type=EntityType.SKILL,
    )
    monkeypatch.setattr(memory_module.User, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(return_value=_query(first=entity)),
    )
    monkeypatch.setattr(MemoryService, "update_entity", AsyncMock(return_value=entity))
    audit = AsyncMock()
    monkeypatch.setattr(memory_module.AuditLogService, "log", audit)
    monkeypatch.setattr(memory_module, "t", lambda key, **kwargs: key)

    result = await MemoryService.handle_update_entity(
        uuid4(), "Python", "new", {"level": 2}
    )

    assert result == {
        "success": True,
        "entity_id": str(entity_id),
        "message": "memory_entity_updated_tool",
    }
    assert audit.await_args.kwargs["changes"] == {
        "description": {"before": "old", "after": "new"},
        "properties": {"before": "{'level': 1}", "after": "{'level': 2}"},
    }


@pytest.mark.asyncio
async def test_handle_search_memory_formats_results_and_empty_state(monkeypatch):
    entity = SimpleNamespace(
        id=uuid4(),
        name="Python",
        entity_type=EntityType.SKILL,
        description="language",
        properties={},
    )
    search = AsyncMock(side_effect=[[entity], []])
    monkeypatch.setattr(MemoryService, "search_entities", search)
    monkeypatch.setattr(
        memory_module, "t", lambda key, **kwargs: f"{key}:{kwargs.get('count', '')}"
    )

    found = await MemoryService.handle_search_memory(uuid4(), "python", top_k=2)
    empty = await MemoryService.handle_search_memory(uuid4(), "missing")

    assert found == {
        "success": True,
        "results": [
            {
                "id": str(entity.id),
                "name": "Python",
                "type": "skill",
                "description": "language",
                "properties": {},
                "updated_at": None,
            }
        ],
        "count": 1,
        "message": "memory_search_results_found:1",
    }
    assert empty == {
        "success": True,
        "results": [],
        "count": 0,
        "message": "memory_search_empty:",
    }


@pytest.mark.asyncio
async def test_handle_search_memory_converts_unexpected_failure(monkeypatch):
    monkeypatch.setattr(
        MemoryService,
        "search_entities",
        AsyncMock(side_effect=RuntimeError("failed")),
    )
    monkeypatch.setattr(memory_module, "_memory_tool_error", lambda: "safe error")

    assert await MemoryService.handle_search_memory(uuid4(), "query") == {
        "success": False,
        "error": "safe error",
    }


@pytest.mark.asyncio
async def test_qdrant_client_is_created_once_and_cached(monkeypatch):
    client = object()
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(memory_module, "_qdrant_client", None)
    monkeypatch.setattr(memory_module, "AsyncQdrantClient", constructor)

    assert await memory_module._get_qdrant_client() is client
    assert await memory_module._get_qdrant_client() is client
    constructor.assert_called_once_with(
        url=memory_module.settings.QDRANT_URL,
        api_key=memory_module.settings.QDRANT_API_KEY,
        prefer_grpc=False,
    )


@pytest.mark.asyncio
async def test_ensure_memory_collection_creates_and_caches_missing_collection(
    monkeypatch,
):
    client = SimpleNamespace(
        get_collection=AsyncMock(side_effect=RuntimeError("missing")),
        create_collection=AsyncMock(),
        create_payload_index=AsyncMock(),
    )
    models = SimpleNamespace(
        VectorParams=lambda **kwargs: SimpleNamespace(**kwargs),
        Distance=SimpleNamespace(COSINE="cosine"),
        PayloadSchemaType=SimpleNamespace(KEYWORD="keyword", INTEGER="integer"),
    )
    monkeypatch.setattr(memory_module, "qmodels", models)
    monkeypatch.setattr(memory_module, "_memory_collections", set())
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    assert await memory_module._ensure_memory_collection(3) == "memory_entities_dim_3"
    assert await memory_module._ensure_memory_collection(3) == "memory_entities_dim_3"
    client.get_collection.assert_awaited_once_with("memory_entities_dim_3")
    client.create_collection.assert_awaited_once()
    assert client.create_payload_index.await_count == 2
    assert client.create_payload_index.await_args_list[0].kwargs == {
        "collection_name": "memory_entities_dim_3",
        "field_name": "user_id",
        "field_schema": "keyword",
    }
    assert client.create_payload_index.await_args_list[1].kwargs == {
        "collection_name": "memory_entities_dim_3",
        "field_name": "updated_at_ts",
        "field_schema": "integer",
    }


@pytest.mark.asyncio
async def test_ensure_memory_collection_backfills_legacy_timestamps(monkeypatch):
    from datetime import UTC, datetime

    entity_id = uuid4()
    entity = SimpleNamespace(
        id=entity_id,
        updated_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        created_at=None,
    )
    point = SimpleNamespace(id=entity_id, payload={})
    client = SimpleNamespace(
        get_collection=AsyncMock(return_value=SimpleNamespace()),
        create_payload_index=AsyncMock(),
        scroll=AsyncMock(return_value=([point], None)),
        set_payload=AsyncMock(),
    )
    models = SimpleNamespace(
        PayloadSchemaType=SimpleNamespace(INTEGER="integer"),
    )
    monkeypatch.setattr(memory_module, "qmodels", models)
    monkeypatch.setattr(memory_module, "_memory_collections", set())
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        memory_module.MemoryEntity,
        "filter",
        MagicMock(return_value=_query(all=[entity])),
    )

    await memory_module._ensure_memory_collection(3)

    client.set_payload.assert_awaited_once_with(
        collection_name="memory_entities_dim_3",
        payload={"updated_at_ts": int(entity.updated_at.timestamp())},
        points=[entity_id],
    )


@pytest.mark.asyncio
async def test_delete_entity_embedding_uses_model_dimension(monkeypatch):
    client = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(
        model_manager,
        "_get_model_config",
        AsyncMock(return_value=SimpleNamespace(dimensions=768)),
    )
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    await MemoryService._delete_entity_embedding("point-id", "model-id")

    client.delete.assert_awaited_once()
    assert (
        client.delete.await_args.kwargs["collection_name"] == "memory_entities_dim_768"
    )
    assert client.delete.await_args.kwargs["points_selector"].points == ["point-id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "args"),
    [
        (MemoryService.handle_create_relation, ("source", "target", "related_to")),
        (MemoryService.handle_update_entity, ("entity",)),
    ],
)
async def test_memory_handlers_convert_unexpected_failure(monkeypatch, handler, args):
    monkeypatch.setattr(
        memory_module.User,
        "get",
        AsyncMock(side_effect=RuntimeError("database failed")),
    )
    monkeypatch.setattr(memory_module, "_memory_tool_error", lambda: "safe error")

    assert await handler(uuid4(), *args) == {
        "success": False,
        "error": "safe error",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (MemoryService.delete_entity, "memory_entity_not_found"),
        (MemoryService.create_relation, "memory_source_entity_not_found"),
    ],
)
async def test_memory_crud_rejects_missing_source_records(
    monkeypatch, operation, expected
):
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=_query())
    )

    with pytest.raises(ValueError, match=expected):
        if operation is MemoryService.delete_entity:
            await operation(uuid4(), uuid4())
        else:
            await operation(uuid4(), uuid4(), uuid4(), RelationType.RELATED_TO)


@pytest.mark.asyncio
async def test_update_entity_embedding_adds_when_no_old_point(monkeypatch):
    entity = SimpleNamespace(embedding_id=None)
    add = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(MemoryService, "_add_entity_embedding", add)
    monkeypatch.setattr(MemoryService, "_delete_entity_embedding", delete)

    await MemoryService._update_entity_embedding(entity)

    delete.assert_not_awaited()
    add.assert_awaited_once_with(entity)


@pytest.mark.asyncio
async def test_delete_entity_embedding_skips_missing_model_and_swallows_failure(
    monkeypatch,
):
    get_config = AsyncMock(side_effect=RuntimeError("model unavailable"))
    monkeypatch.setattr(model_manager, "_get_model_config", get_config)

    await MemoryService._delete_entity_embedding("point-id", None)
    get_config.assert_not_awaited()

    await MemoryService._delete_entity_embedding("point-id", "model-id")
    get_config.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["search", "add"])
async def test_vector_operations_require_qdrant_models(monkeypatch, operation):
    monkeypatch.setattr(memory_module, "qmodels", None)
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1], "model_id": "model"}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )

    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        if operation == "search":
            await MemoryService.search_entities(uuid4(), "query")
        else:
            await MemoryService._add_entity_embedding(
                SimpleNamespace(
                    id=uuid4(),
                    user_id=uuid4(),
                    name="Python",
                    description=None,
                )
            )


@pytest.mark.asyncio
async def test_search_entities_preserves_similarity_order_and_reranks_by_recency(
    monkeypatch,
):
    from datetime import UTC, datetime, timedelta

    user_id = uuid4()
    id1, id2 = uuid4(), uuid4()
    now = datetime.now(UTC)

    # Entity 1: slightly higher similarity (0.90), but updated 90 days ago
    entity1 = SimpleNamespace(
        id=id1,
        name="Older High Sim",
        updated_at=now - timedelta(days=90),
        created_at=now - timedelta(days=90),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    # Entity 2: slightly lower similarity (0.85), but updated today (fresh)
    entity2 = SimpleNamespace(
        id=id2,
        name="Newer Lower Sim",
        updated_at=now,
        created_at=now,
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )

    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[
                    SimpleNamespace(id=id1, score=0.90, payload={}),
                    SimpleNamespace(id=id2, score=0.85, payload={}),
                ]
            )
        )
    )
    # ORM returns rows in reverse/arbitrary order
    entity_query = _query(all=[entity2, entity1])
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1, 0.2], "model_id": "embed"}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=entity_query)
    )

    # With recency_weight=0, exact similarity order is preserved (entity1 first)
    res_sim_only = await MemoryService.search_entities(
        user_id, "query", top_k=2, recency_weight=0.0
    )
    assert res_sim_only == [entity1, entity2]

    # With recency_weight=0.20, entity2 gets boosted because it is brand new vs 90-day-old entity1
    res_recency = await MemoryService.search_entities(
        user_id, "query", top_k=2, recency_weight=0.20
    )
    assert res_recency == [entity2, entity1]


@pytest.mark.asyncio
async def test_search_entities_filters_by_time_window(monkeypatch):
    from datetime import UTC, datetime, timedelta

    user_id = uuid4()
    id_recent, id_old = uuid4(), uuid4()
    now = datetime.now(UTC)

    recent_entity = SimpleNamespace(
        id=id_recent,
        updated_at=now - timedelta(days=2),
        created_at=now - timedelta(days=2),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    old_entity = SimpleNamespace(
        id=id_old,
        updated_at=now - timedelta(days=40),
        created_at=now - timedelta(days=40),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )

    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[
                    SimpleNamespace(id=id_recent, score=0.9, payload={}),
                    SimpleNamespace(id=id_old, score=0.85, payload={}),
                ]
            )
        )
    )
    entity_query = _query(all=[recent_entity, old_entity])
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1, 0.2], "model_id": "embed"}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", MagicMock(return_value=entity_query)
    )

    result = await MemoryService.search_entities(
        user_id, "query", top_k=2, time_window_days=7, recency_weight=0.0
    )
    assert result == [recent_entity]
    query_filter = client.query_points.await_args.kwargs["query_filter"]
    assert any(
        condition.key == "updated_at_ts" and condition.range.gte > 0
        for condition in query_filter.must
    )


@pytest.mark.asyncio
async def test_handle_search_memory_includes_formatted_date_and_time_window(
    monkeypatch,
):
    from datetime import UTC, datetime

    user_id = uuid4()
    updated_dt = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    entity = SimpleNamespace(
        id=uuid4(),
        name="FastAPI",
        entity_type=EntityType.SKILL,
        description="web framework",
        properties={},
        updated_at=updated_dt,
    )
    search = AsyncMock(return_value=[entity])
    monkeypatch.setattr(MemoryService, "search_entities", search)
    monkeypatch.setattr(
        memory_module, "t", lambda key, **kwargs: f"{key}:{kwargs.get('count', '')}"
    )

    result = await MemoryService.handle_search_memory(
        user_id, "fastapi", top_k=3, time_window_days=14, entity_type="skill"
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["results"] == [
        {
            "id": str(entity.id),
            "name": "FastAPI",
            "type": "skill",
            "description": "web framework",
            "properties": {},
            "updated_at": "2026-09-08",
        }
    ]
    search.assert_awaited_once_with(
        user_id=user_id,
        query="fastapi",
        top_k=3,
        entity_type=EntityType.SKILL,
        time_window_days=14,
    )
