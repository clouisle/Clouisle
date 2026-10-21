from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import memory
from app.services.memory import MemoryService


class _Query:
    def __init__(self, values=(), first=None):
        self.values = values
        self.first_value = first

    async def all(self):
        return self.values

    async def first(self):
        return self.first_value


@pytest.mark.anyio
async def test_backfill_uses_entity_timestamp_when_legacy_payload_has_none(monkeypatch):
    entity_id = uuid4()
    entity = SimpleNamespace(
        id=entity_id, updated_at=None, created_at="2025-03-04T00:00:00"
    )
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", lambda **_kwargs: _Query([entity])
    )
    point = SimpleNamespace(id=entity_id, payload={})
    client = SimpleNamespace(
        scroll=AsyncMock(return_value=([point], None)), set_payload=AsyncMock()
    )

    await memory._backfill_memory_timestamps(client, "memories")

    client.set_payload.assert_awaited_once_with(
        collection_name="memories",
        payload={"updated_at_ts": memory._coerce_timestamp(entity.created_at)},
        points=[entity_id],
    )


@pytest.mark.anyio
async def test_get_entity_subgraph_marks_missing_seed_as_truncated(monkeypatch):
    seed_id = uuid4()
    monkeypatch.setattr(memory.MemoryEntity, "filter", lambda **_kwargs: _Query())

    graph = await MemoryService.get_entity_subgraph(uuid4(), [seed_id], max_depth=1)

    assert graph["entities"] == []
    assert graph["truncated"] is True


@pytest.mark.anyio
async def test_get_entity_subgraph_truncates_relation_that_exceeds_node_cap(
    monkeypatch,
):
    seed_id, left_id, right_id = uuid4(), uuid4(), uuid4()
    seed = SimpleNamespace(id=seed_id)
    left, right = SimpleNamespace(id=left_id), SimpleNamespace(id=right_id)
    relation = SimpleNamespace(
        id=uuid4(),
        source_entity_id=left_id,
        target_entity_id=right_id,
        relation_type="knows",
    )
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **kwargs: _Query(
            [seed] if kwargs["id__in"] == [seed_id] else [left, right]
        ),
    )
    monkeypatch.setattr(
        memory.MemoryRelation, "filter", lambda **_kwargs: _Query([relation])
    )

    graph = await MemoryService.get_entity_subgraph(
        uuid4(), [seed_id], direction="outgoing", max_nodes=2
    )

    assert graph["entities"] == [seed]
    assert graph["relations"] == []
    assert graph["truncated"] is True


@pytest.mark.anyio
async def test_get_entity_subgraph_stops_when_relation_limit_is_reached(monkeypatch):
    source_id, target_id, another_id = uuid4(), uuid4(), uuid4()
    source = SimpleNamespace(id=source_id)
    target, another = SimpleNamespace(id=target_id), SimpleNamespace(id=another_id)
    relations = [
        SimpleNamespace(
            id=uuid4(),
            source_entity_id=source_id,
            target_entity_id=target_id,
            relation_type="knows",
        ),
        SimpleNamespace(
            id=uuid4(),
            source_entity_id=source_id,
            target_entity_id=another_id,
            relation_type="knows",
        ),
    ]
    call_count = 0

    def entities(**_kwargs):
        nonlocal call_count
        call_count += 1
        return _Query([source] if call_count == 1 else [source, target, another])

    monkeypatch.setattr(memory.MemoryEntity, "filter", entities)
    monkeypatch.setattr(
        memory.MemoryRelation, "filter", lambda **_kwargs: _Query(relations)
    )

    graph = await MemoryService.get_entity_subgraph(
        uuid4(), [source_id], direction="outgoing", max_relations=1
    )

    assert len(graph["relations"]) == 1
    assert graph["truncated"] is True


@pytest.mark.anyio
async def test_get_entity_subgraph_deduplicates_bidirectional_relation(monkeypatch):
    source_id, target_id = uuid4(), uuid4()
    source, target = SimpleNamespace(id=source_id), SimpleNamespace(id=target_id)
    relation = SimpleNamespace(
        id=uuid4(),
        source_entity_id=source_id,
        target_entity_id=target_id,
        relation_type="knows",
    )
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **kwargs: _Query(
            [source] if kwargs["id__in"] == [source_id] else [source, target]
        ),
    )
    monkeypatch.setattr(
        memory.MemoryRelation, "filter", lambda **_kwargs: _Query([relation])
    )

    graph = await MemoryService.get_entity_subgraph(uuid4(), [source_id], max_depth=1)

    assert graph["entities"] == [source, target]
    assert graph["relations"] == [relation]
    assert graph["entity_depth"][str(target_id)] == 1


@pytest.mark.anyio
async def test_delete_embedding_skips_when_qdrant_models_are_unavailable(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(memory, "qmodels", None)
    monkeypatch.setattr(memory, "_get_qdrant_client", client)

    await MemoryService._delete_entity_embedding("embedding-id")

    client.assert_not_awaited()


@pytest.mark.anyio
async def test_handle_create_entity_returns_similar_name_notice(monkeypatch):
    user_id = uuid4()
    existing = SimpleNamespace(name="Ada Lovelace")
    entity = SimpleNamespace(id=uuid4(), name="Ada", entity_type="person")
    monkeypatch.setattr(memory.User, "get", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        memory.MemoryEntity, "filter", lambda **_kwargs: _Query([existing])
    )
    monkeypatch.setattr(MemoryService, "create_entity", AsyncMock(return_value=entity))
    monkeypatch.setattr(memory.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(memory, "t", lambda key, **kwargs: key + str(kwargs))

    result = await MemoryService.handle_create_entity(user_id, "Ada", "person")

    assert result["success"] is True
    assert result["similar_entities"] == ["Ada Lovelace"]
    assert "memory_similar_entities_notice" in result["message"]


@pytest.mark.anyio
async def test_handle_create_entity_audits_failure_after_user_loaded(monkeypatch):
    user_id = uuid4()
    user = object()
    audit = AsyncMock()
    monkeypatch.setattr(memory.User, "get", AsyncMock(return_value=user))
    monkeypatch.setattr(memory.MemoryEntity, "filter", lambda **_kwargs: _Query())
    monkeypatch.setattr(
        MemoryService,
        "create_entity",
        AsyncMock(side_effect=RuntimeError("db unavailable")),
    )
    monkeypatch.setattr(memory.AuditLogService, "log", audit)
    monkeypatch.setattr(memory, "_memory_tool_error", lambda: "failed")

    result = await MemoryService.handle_create_entity(user_id, "Ada", "person")

    assert result == {"success": False, "error": "failed"}
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["status"] == "failed"
