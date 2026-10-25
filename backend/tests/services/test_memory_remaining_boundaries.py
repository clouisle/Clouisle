from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.llm import model_manager
from app.models.memory import RelationType
from app.services import memory
from app.services.memory import MemoryService


def _qdrant_models(*, include_range=True):
    def make(**kwargs):
        return SimpleNamespace(**kwargs)

    models = {"FieldCondition": make, "MatchValue": make, "Filter": make}
    if include_range:
        models["Range"] = make
    return SimpleNamespace(**models)


class _AllQuery:
    def __init__(self, values):
        self.values = values

    async def all(self):
        return self.values


@pytest.mark.asyncio
async def test_search_empty_qdrant_results_skip_access_updates(monkeypatch):
    user_id = uuid4()
    client = SimpleNamespace(
        query_points=AsyncMock(return_value=SimpleNamespace(points=[]))
    )
    entity_filter = MagicMock()
    monkeypatch.setattr(memory, "qmodels", _qdrant_models())
    monkeypatch.setattr(
        model_manager, "get_embedding", AsyncMock(return_value={"embedding": [0.1]})
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="memories")
    )
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))
    entity_filter = MagicMock(return_value=_AllQuery([]))
    monkeypatch.setattr(memory.MemoryEntity, "filter", entity_filter)

    assert await MemoryService.search_entities(user_id, "nothing", top_k=4) == []
    client.query_points.assert_awaited_once()
    entity_filter.assert_called_once_with(id__in=[], user_id=user_id)


@pytest.mark.asyncio
async def test_search_uses_similarity_order_when_recency_weight_is_zero(monkeypatch):
    user_id = uuid4()
    older_id, newer_id = uuid4(), uuid4()
    older = SimpleNamespace(
        id=older_id,
        updated_at=datetime.now(UTC) - timedelta(days=120),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    newer = SimpleNamespace(
        id=newer_id,
        updated_at=datetime.now(UTC),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[
                    SimpleNamespace(id=older_id, score=0.95),
                    SimpleNamespace(id=newer_id, score=0.2),
                ]
            )
        )
    )
    monkeypatch.setattr(memory, "qmodels", _qdrant_models())
    monkeypatch.setattr(
        model_manager, "get_embedding", AsyncMock(return_value={"embedding": [0.1]})
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="memories")
    )
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", lambda **kwargs: _AllQuery([newer, older])
    )

    result = await MemoryService.search_entities(
        user_id, "query", top_k=2, recency_weight=0
    )

    assert result == [older, newer]
    assert older.access_count == newer.access_count == 1
    assert [
        c.key for c in client.query_points.await_args.kwargs["query_filter"].must
    ] == ["user_id"]


@pytest.mark.asyncio
async def test_search_filters_old_entities_and_always_scopes_database_query(
    monkeypatch,
):
    user_id = uuid4()
    recent_id, stale_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    recent = SimpleNamespace(
        id=recent_id,
        updated_at=(now - timedelta(days=1)).isoformat(),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    stale = SimpleNamespace(
        id=stale_id,
        updated_at=now - timedelta(days=30),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[
                    SimpleNamespace(id=recent_id, score=0.9),
                    SimpleNamespace(id=stale_id, score=0.8),
                ]
            )
        )
    )
    entity_filter = MagicMock(return_value=_AllQuery([recent, stale]))
    monkeypatch.setattr(memory, "qmodels", _qdrant_models())
    monkeypatch.setattr(
        model_manager, "get_embedding", AsyncMock(return_value={"embedding": [0.1]})
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="memories")
    )
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))
    monkeypatch.setattr(memory.MemoryEntity, "filter", entity_filter)

    result = await MemoryService.search_entities(
        user_id, "recent", top_k=5, time_window_days=5
    )

    assert result == [recent]
    entity_filter.assert_called_once_with(id__in=[recent_id, stale_id], user_id=user_id)
    assert [
        c.key for c in client.query_points.await_args.kwargs["query_filter"].must
    ] == ["user_id", "updated_at_ts"]
    stale.save.assert_not_awaited()
    recent.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_time_filter_works_without_qdrant_range_model(monkeypatch):
    user_id = uuid4()
    client = SimpleNamespace(
        query_points=AsyncMock(return_value=SimpleNamespace(points=[]))
    )
    monkeypatch.setattr(memory, "qmodels", _qdrant_models(include_range=False))
    monkeypatch.setattr(
        model_manager, "get_embedding", AsyncMock(return_value={"embedding": [0.1]})
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="memories")
    )
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))
    monkeypatch.setattr(memory.MemoryEntity, "filter", lambda **kwargs: _AllQuery([]))

    assert (
        await MemoryService.search_entities(user_id, "recent", time_window_days=3) == []
    )
    assert [
        c.key for c in client.query_points.await_args.kwargs["query_filter"].must
    ] == ["user_id"]


@pytest.mark.asyncio
async def test_subgraph_rejects_invalid_direction_and_returns_empty_for_no_seeds():
    with pytest.raises(ValueError, match="invalid_graph_direction"):
        await MemoryService.get_entity_subgraph(uuid4(), [], direction="sideways")

    assert await MemoryService.get_entity_subgraph(uuid4(), []) == {
        "entities": [],
        "relations": [],
        "entity_depth": {},
        "truncated": False,
    }


@pytest.mark.asyncio
async def test_subgraph_incoming_traversal_filters_by_user_and_relation_type(
    monkeypatch,
):
    user_id, seed_id, source_id = uuid4(), uuid4(), uuid4()
    seed, source = SimpleNamespace(id=seed_id), SimpleNamespace(id=source_id)
    relation = SimpleNamespace(
        id=uuid4(),
        source_entity_id=source_id,
        target_entity_id=seed_id,
        relation_type=RelationType.KNOWS,
    )
    entity_filter = MagicMock(
        side_effect=[_AllQuery([seed]), _AllQuery([seed, source])]
    )
    relation_filter = MagicMock(return_value=_AllQuery([relation]))
    monkeypatch.setattr(memory.MemoryEntity, "filter", entity_filter)
    monkeypatch.setattr(memory.MemoryRelation, "filter", relation_filter)

    graph = await MemoryService.get_entity_subgraph(
        user_id, [seed_id], direction="incoming", relation_types=[RelationType.KNOWS]
    )

    assert graph["entities"] == [seed, source]
    assert graph["relations"] == [relation]
    relation_filter.assert_called_once_with(
        user_id=user_id, target_entity_id__in=[seed_id]
    )
    assert entity_filter.call_args_list[0].kwargs == {
        "user_id": user_id,
        "id__in": [seed_id],
    }
    assert set(entity_filter.call_args_list[1].kwargs["id__in"]) == {seed_id, source_id}


@pytest.mark.asyncio
async def test_subgraph_ignores_disallowed_relations_and_cross_user_endpoints(
    monkeypatch,
):
    user_id, seed_id, outsider_id, hidden_id = uuid4(), uuid4(), uuid4(), uuid4()
    seed = SimpleNamespace(id=seed_id)
    outsider = SimpleNamespace(id=outsider_id)
    blocked_type = SimpleNamespace(
        id=uuid4(),
        source_entity_id=outsider_id,
        target_entity_id=seed_id,
        relation_type=RelationType.PART_OF,
    )
    foreign_endpoint = SimpleNamespace(
        id=uuid4(),
        source_entity_id=hidden_id,
        target_entity_id=seed_id,
        relation_type=RelationType.KNOWS,
    )
    entity_filter = MagicMock(
        side_effect=[_AllQuery([seed]), _AllQuery([seed, outsider])]
    )
    relation_filter = MagicMock(
        return_value=_AllQuery([blocked_type, foreign_endpoint])
    )
    monkeypatch.setattr(memory.MemoryEntity, "filter", entity_filter)
    monkeypatch.setattr(memory.MemoryRelation, "filter", relation_filter)

    graph = await MemoryService.get_entity_subgraph(
        user_id, [seed_id], direction="outgoing", relation_types=[RelationType.KNOWS]
    )

    assert graph["entities"] == [seed]
    assert graph["relations"] == []
    assert entity_filter.call_count == 2
    assert entity_filter.call_args_list[1].kwargs["user_id"] == user_id
    assert graph["entities"] == [seed]
