from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
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


def test_format_entity_date_handles_various_types():
    from datetime import datetime

    assert memory._format_entity_date(None) is None
    assert memory._format_entity_date(datetime(2026, 9, 9, 10, 0)) == "2026-09-09"
    assert memory._format_entity_date("2026-09-09T10:00:00Z") == "2026-09-09"
    assert memory._format_entity_date(12345) == "12345"


def test_calculate_recency_score_handles_string_and_naive_dates():
    from datetime import UTC, datetime

    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    # No timestamp
    assert memory._calculate_recency_score(SimpleNamespace(), now) == 1.0

    # Valid ISO string
    e_str = SimpleNamespace(updated_at="2026-09-09T12:00:00+00:00")
    assert memory._calculate_recency_score(e_str, now) == 1.0

    # Invalid string
    e_bad = SimpleNamespace(updated_at="invalid-date")
    assert memory._calculate_recency_score(e_bad, now) == 1.0

    # Naive datetime
    e_naive = SimpleNamespace(updated_at=datetime(2026, 9, 9, 12, 0))
    assert memory._calculate_recency_score(e_naive, now) == 1.0


@pytest.mark.anyio
async def test_search_entities_qdrant_range_and_str_date_filtering(monkeypatch):
    from datetime import UTC, datetime, timedelta
    from app.llm import model_manager

    user_id = uuid4()
    id1, id2, id3 = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)

    e_str_recent = SimpleNamespace(
        id=id1,
        updated_at=(now - timedelta(days=1)).isoformat(),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    e_naive_old = SimpleNamespace(
        id=id2,
        updated_at=datetime.now().replace(tzinfo=None) - timedelta(days=20),
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )
    e_bad_str = SimpleNamespace(
        id=id3,
        updated_at="not-a-date",
        access_count=0,
        last_accessed_at=None,
        save=AsyncMock(),
    )

    class MockQuery:
        async def all(self):
            return [e_str_recent, e_naive_old, e_bad_str]

    def constructor(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        memory,
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
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1, 0.2], "model_id": "model"}),
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    client = SimpleNamespace(
        query_points=AsyncMock(
            return_value=SimpleNamespace(
                points=[
                    SimpleNamespace(id=id1, score=0.9),
                    SimpleNamespace(id=id2, score=0.8),
                    SimpleNamespace(id=id3, score=0.7),
                ]
            )
        )
    )
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", MagicMock(return_value=MockQuery())
    )

    results = await MemoryService.search_entities(
        user_id=user_id, query="test", time_window_days=5
    )
    # e_naive_old is 20 days old -> excluded; e_bad_str falls back to now -> kept; e_str_recent is 1 day old -> kept
    assert e_str_recent in results
    assert e_naive_old not in results


@pytest.mark.anyio
async def test_handle_search_memory_ignores_invalid_type_and_negative_days(monkeypatch):
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(MemoryService, "search_entities", search)
    monkeypatch.setattr(memory, "t", lambda key, **kwargs: key)

    # Invalid entity_type string and negative time_window_days
    res = await MemoryService.handle_search_memory(
        uuid4(), "query", time_window_days=-5, entity_type="nonexistent_type"
    )
    assert res["success"] is True
    search.assert_awaited_once_with(
        user_id=search.await_args.kwargs["user_id"],
        query="query",
        top_k=5,
        entity_type=None,
        time_window_days=None,
    )


@pytest.mark.anyio
async def test_add_entity_embedding_handles_str_and_naive_updated_at(monkeypatch):
    from datetime import datetime
    from app.llm import model_manager

    entity = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        name="Test",
        description="desc",
        entity_type=EntityType.FACT,
        updated_at="2026-09-09T10:00:00+00:00",
        embedding_id=None,
        embedding_model_id=None,
        save=AsyncMock(),
    )
    client = SimpleNamespace(upsert=AsyncMock())
    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1], "model_id": "model"}),
    )
    monkeypatch.setattr(
        memory, "_ensure_memory_collection", AsyncMock(return_value="collection")
    )
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))

    await MemoryService._add_entity_embedding(entity)
    point = client.upsert.await_args.kwargs["points"][0]
    assert "updated_at_ts" in point.payload

    # Now with naive datetime
    entity.updated_at = datetime(2026, 9, 9, 10, 0)
    await MemoryService._add_entity_embedding(entity)
    point2 = client.upsert.await_args.kwargs["points"][0]
    assert "updated_at_ts" in point2.payload
