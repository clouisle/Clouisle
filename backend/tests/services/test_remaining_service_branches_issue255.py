import builtins
import importlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.models.agent import RAGMode
from app.models.memory import EntityType, RelationType

builtins.ToolCall = object
agent_module = importlib.import_module("app.services.agent")
del builtins.ToolCall
AgentService = agent_module.AgentService

memory_module = importlib.import_module("app.services.memory")
usage_module = importlib.import_module("app.services.usage_tracker")
vector_module = importlib.import_module("app.services.vector_store")
MemoryService = memory_module.MemoryService
QuotaExceededError = usage_module.QuotaExceededError
UsageTracker = usage_module.UsageTracker


class Query:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def select_related(self, *_args):
        return self

    def using_db(self, *_args):
        return self

    def select_for_update(self):
        return self

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    async def all(self):
        return self.values


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


@pytest.fixture
def qmodels(monkeypatch):
    models = SimpleNamespace(
        Distance=SimpleNamespace(COSINE="cosine"),
        FieldCondition=Model,
        Filter=Model,
        MatchAny=Model,
        MatchValue=Model,
        PointIdsList=Model,
        PointStruct=Model,
        PayloadSchemaType=SimpleNamespace(KEYWORD="keyword"),
        VectorParams=Model,
    )
    monkeypatch.setattr(memory_module, "qmodels", models)
    monkeypatch.setattr(vector_module, "qmodels", models)
    return models


def team_model(**overrides):
    current = datetime.now(timezone.utc)
    values = {
        "team_id": "team",
        "is_enabled": True,
        "daily_reset_at": current,
        "monthly_reset_at": current,
        "daily_tokens_used": 2,
        "monthly_tokens_used": 3,
        "daily_requests_used": 1,
        "monthly_requests_used": 1,
        "daily_token_limit": None,
        "monthly_token_limit": None,
        "daily_request_limit": None,
        "monthly_request_limit": None,
        "model": SimpleNamespace(name="Model"),
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_usage_resets_and_stats_cover_expired_and_missing(monkeypatch):
    current = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    model = team_model(
        daily_reset_at=None,
        monthly_reset_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        daily_token_limit=10,
        monthly_token_limit=20,
    )
    tracker = UsageTracker()
    monkeypatch.setattr(usage_module, "now", lambda: current)
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    stats = await tracker.get_usage_stats("team", "model")

    assert stats["daily_token_percent"] == 0.0
    assert stats["monthly_token_percent"] == 0.0
    model.save.assert_awaited_once()
    tracker._get_team_model.return_value = None
    assert await tracker.get_usage_stats("team", "missing") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "quota_type"),
    [
        ({"daily_token_limit": 2}, "daily_token"),
        ({"monthly_token_limit": 3}, "monthly_token"),
        ({"daily_request_limit": 1}, "daily_request"),
        ({"monthly_request_limit": 1}, "monthly_request"),
    ],
)
async def test_usage_quota_with_model_rejects_each_limit(overrides, quota_type):
    with pytest.raises(QuotaExceededError) as exc:
        await UsageTracker().check_quota_with_model(team_model(**overrides), 1)
    assert exc.value.quota_type == quota_type


@pytest.mark.asyncio
async def test_usage_disabled_and_record_missing(monkeypatch):
    tracker = UsageTracker()
    with pytest.raises(ValueError, match="disabled"):
        await tracker.check_quota_with_model(team_model(is_enabled=False))

    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=None))
    with pytest.raises(ValueError, match="cannot record usage"):
        await tracker.record_usage("team", "model", 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "quota_type"),
    [
        ({"daily_token_limit": 2}, "daily_token"),
        ({"monthly_token_limit": 3}, "monthly_token"),
        ({"daily_request_limit": 1}, "daily_request"),
        ({"monthly_request_limit": 1}, "monthly_request"),
    ],
)
async def test_atomic_usage_rejects_each_limit(monkeypatch, overrides, quota_type):
    model = team_model(**overrides)

    @asynccontextmanager
    async def transaction():
        yield object()

    monkeypatch.setattr(usage_module, "in_transaction", transaction)
    monkeypatch.setattr(
        usage_module.TeamModel, "filter", lambda **_kwargs: Query(model)
    )

    with pytest.raises(QuotaExceededError) as exc:
        await UsageTracker().check_and_record_usage("team", "model", 1)
    assert exc.value.quota_type == quota_type


@pytest.mark.asyncio
async def test_memory_entity_create_updates_existing(monkeypatch):
    existing = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", lambda **_kwargs: Query(existing)
    )
    update = AsyncMock(return_value="updated")
    monkeypatch.setattr(MemoryService, "update_entity", update)

    result = await MemoryService.create_entity(
        uuid4(), "Ada", EntityType.PERSON.value, description="new"
    )

    assert result == "updated"
    update.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_update_merges_empty_description_and_properties(monkeypatch):
    entity = SimpleNamespace(
        name="Ada",
        description="",
        properties={"old": 1},
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", lambda **_kwargs: Query(entity)
    )
    monkeypatch.setattr(MemoryService, "_update_entity_embedding", AsyncMock())

    result = await MemoryService.update_entity(
        uuid4(), uuid4(), description="bio", properties={"new": 2}
    )

    assert result.description == "bio"
    assert result.properties == {"old": 1, "new": 2}


@pytest.mark.asyncio
async def test_memory_update_and_delete_reject_missing(monkeypatch):
    monkeypatch.setattr(memory_module.MemoryEntity, "filter", lambda **_kwargs: Query())
    with pytest.raises(ValueError, match="memory_entity_not_found"):
        await MemoryService.update_entity(uuid4(), uuid4())
    with pytest.raises(ValueError, match="memory_entity_not_found"):
        await MemoryService.delete_entity(uuid4(), uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["source", "target"])
async def test_memory_relation_rejects_missing_endpoint(monkeypatch, missing):
    source = None if missing == "source" else SimpleNamespace()
    target = None if missing == "target" else SimpleNamespace()
    responses = iter([Query(source), Query(target)])
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", lambda **_kwargs: next(responses)
    )

    with pytest.raises(ValueError, match=f"memory_{missing}_entity_not_found"):
        await MemoryService.create_relation(
            uuid4(), uuid4(), uuid4(), RelationType.RELATED_TO.value
        )


@pytest.mark.asyncio
async def test_memory_relation_returns_existing(monkeypatch):
    endpoints = iter([Query(SimpleNamespace()), Query(SimpleNamespace())])
    relation = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        memory_module.MemoryEntity, "filter", lambda **_kwargs: next(endpoints)
    )
    monkeypatch.setattr(
        memory_module.MemoryRelation, "filter", lambda **_kwargs: Query(relation)
    )

    assert (
        await MemoryService.create_relation(
            uuid4(), uuid4(), uuid4(), RelationType.RELATED_TO
        )
        is relation
    )


@pytest.mark.asyncio
async def test_memory_search_handles_embedding_and_vector_failures(monkeypatch):
    from app.llm import model_manager

    monkeypatch.setattr(
        model_manager, "get_embedding", AsyncMock(side_effect=RuntimeError("offline"))
    )
    assert await MemoryService.search_entities(uuid4(), "query") == []

    monkeypatch.setattr(
        model_manager,
        "get_embedding",
        AsyncMock(return_value={"embedding": [0.1], "model_id": "m"}),
    )
    monkeypatch.setattr(
        memory_module, "_ensure_memory_collection", AsyncMock(return_value="c")
    )
    client = SimpleNamespace(query_points=AsyncMock(side_effect=RuntimeError("down")))
    monkeypatch.setattr(
        memory_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )
    assert await MemoryService.search_entities(uuid4(), "query") == []


@pytest.mark.asyncio
async def test_agent_build_messages_covers_context_history_and_rag(monkeypatch):
    service = AgentService()
    agent = SimpleNamespace(system_prompt="rules", rag_mode=RAGMode.AUTO)
    monkeypatch.setattr(
        service, "_retrieve_rag_context", AsyncMock(return_value="knowledge")
    )

    messages = await service._build_messages(
        agent,
        "now",
        context={"tenant": "one"},
        conversation_history=[
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "system", "content": "s"},
            {"role": "ignored", "content": "x"},
        ],
    )

    contents = [message.content for message in messages]
    # Workflow mode injects Markdown/language guidance into the system prompt;
    # the base prompt still carries the appended runtime context.
    assert contents[0].startswith("rules\n\nContext:\n- tenant: one")
    assert "## Markdown Output" in contents[0]
    assert contents[1:] == ["u", "a", "s", "Relevant context:\nknowledge", "now"]


@pytest.mark.asyncio
async def test_agent_tools_cover_missing_builtin_media_mcp_and_agentic(monkeypatch):
    service = AgentService()
    tool = SimpleNamespace(function=SimpleNamespace(name="tool"))
    monkeypatch.setattr(
        service, "_get_builtin_tool", lambda name: None if name == "missing" else tool
    )
    agent = SimpleNamespace(
        tools_config=[
            {"type": "builtin", "name": "missing"},
            {"type": "mcp"},
            {"type": "other"},
        ],
        enable_image_generation=True,
        enable_video_generation=True,
        rag_mode=RAGMode.AGENTIC,
    )

    tools = await service._get_agent_tools(agent)

    assert len(tools) == 3
    assert tools[-1].function.name == "search_knowledge_base"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["search_points", "search"])
async def test_vector_search_uses_legacy_clients(monkeypatch, qmodels, method):
    point = SimpleNamespace(id="one")
    client = SimpleNamespace(**{method: AsyncMock(return_value=[point])})
    monkeypatch.setattr(
        vector_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    result = await vector_module._qdrant_search("c", [0.1], 1, Model(must=[]))

    assert result == [point]


@pytest.mark.asyncio
async def test_vector_query_points_retries_old_signature(monkeypatch, qmodels):
    point = SimpleNamespace(id="one")
    client = SimpleNamespace(
        query_points=AsyncMock(
            side_effect=[TypeError("old client"), SimpleNamespace(points=[point])]
        )
    )
    monkeypatch.setattr(
        vector_module, "_get_qdrant_client", AsyncMock(return_value=client)
    )

    assert await vector_module._qdrant_search("c", [0.1], 1, Model(must=[])) == [point]
    assert "query_vector" in client.query_points.await_args_list[1].kwargs


@pytest.mark.asyncio
async def test_vector_search_rejects_client_without_search(monkeypatch, qmodels):
    monkeypatch.setattr(
        vector_module, "_get_qdrant_client", AsyncMock(return_value=object())
    )
    with pytest.raises(AttributeError, match="no query/search method"):
        await vector_module._qdrant_search("c", [0.1], 1, Model(must=[]))


def test_vector_filter_and_score_edge_branches(monkeypatch, qmodels):
    kb_id = UUID("00000000-0000-0000-0000-000000000001")
    assert len(vector_module._build_qdrant_filter(kb_id, None).must) == 1
    assert len(vector_module._build_qdrant_filter(kb_id, [uuid4()]).must) == 2

    monkeypatch.setattr(vector_module.settings, "QDRANT_DISTANCE", "cosine")
    assert vector_module._normalize_qdrant_score(2) == 1.0
    monkeypatch.setattr(vector_module.settings, "QDRANT_DISTANCE", "euclid")
    assert vector_module._normalize_qdrant_score(1) == 0.5
    monkeypatch.setattr(vector_module.settings, "QDRANT_DISTANCE", "dot")
    assert vector_module._normalize_qdrant_score(-1) == -1
