import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.agent import MessageRole
from app.tasks.memory import (
    _extract_memories_for_conversation,
    _get_event_loop,
    _parse_extraction_json,
    _run_async,
    extract_conversation_memories_task,
    resolve_extraction_model,
    schedule_background_memory_extraction,
)


def test_get_event_loop_reuses_open_loop():
    loop = MagicMock()
    loop.is_closed.return_value = False
    policy = MagicMock()
    policy.get_event_loop.return_value = loop
    with patch("asyncio.get_event_loop_policy", return_value=policy):
        assert _get_event_loop() is loop


def test_get_event_loop_replaces_closed_loop():
    closed_loop = MagicMock()
    closed_loop.is_closed.return_value = True
    new_loop = MagicMock()
    policy = MagicMock()
    policy.get_event_loop.return_value = closed_loop

    with (
        patch("asyncio.get_event_loop_policy", return_value=policy),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert _get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_get_event_loop_creates_loop_when_none_exists():
    new_loop = MagicMock()
    with (
        patch("asyncio.get_event_loop_policy", side_effect=RuntimeError),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert _get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_run_async_executes_coro():
    async def sample():
        return 42

    assert _run_async(sample()) == 42


def test_parse_extraction_json_variants():
    assert _parse_extraction_json("") == {"entities": [], "relations": []}
    assert _parse_extraction_json("invalid json") == {"entities": [], "relations": []}

    # Clean JSON
    clean = '{"entities": [{"name": "Python"}], "relations": [{"source_entity_name": "A", "target_entity_name": "B"}]}'
    parsed = _parse_extraction_json(clean)
    assert len(parsed["entities"]) == 1
    assert len(parsed["relations"]) == 1

    # Markdown wrapped
    md_wrapped = f"```json\n{clean}\n```"
    parsed_md = _parse_extraction_json(md_wrapped)
    assert len(parsed_md["entities"]) == 1


@pytest.mark.asyncio
async def test_resolve_extraction_model_level1_configured(monkeypatch):
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    model_id = str(uuid4())
    mock_model = SimpleNamespace(id=model_id)

    monkeypatch.setattr(
        SiteSetting,
        "get_value",
        AsyncMock(return_value=model_id),
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=mock_model)
    monkeypatch.setattr(Model, "filter", MagicMock(return_value=query))

    resolved = await resolve_extraction_model()
    assert resolved == model_id


@pytest.mark.asyncio
async def test_resolve_extraction_model_level2_agent_model(monkeypatch):
    from app.models.agent import Agent
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    agent_id = uuid4()
    agent_model_id = str(uuid4())
    mock_agent = SimpleNamespace(id=agent_id, model_id=agent_model_id)
    mock_model = SimpleNamespace(id=agent_model_id)

    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=""))
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=mock_agent))

    query = MagicMock()
    query.first = AsyncMock(return_value=mock_model)
    monkeypatch.setattr(Model, "filter", MagicMock(return_value=query))

    resolved = await resolve_extraction_model(agent_id)
    assert resolved == agent_model_id


@pytest.mark.asyncio
async def test_resolve_extraction_model_level3_default_chat(monkeypatch):
    from app.models.agent import Agent
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    default_model_id = str(uuid4())
    mock_model = SimpleNamespace(id=default_model_id)

    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=""))
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=None))

    query = MagicMock()
    query.first = AsyncMock(return_value=mock_model)
    monkeypatch.setattr(Model, "filter", MagicMock(return_value=query))

    resolved = await resolve_extraction_model(None)
    assert resolved == default_model_id


@pytest.mark.asyncio
async def test_resolve_extraction_model_fallback_any_and_none(monkeypatch):
    from app.models.agent import Agent
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=""))
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=None))

    # None found
    query = MagicMock()
    query.first = AsyncMock(return_value=None)
    query.order_by = MagicMock(return_value=query)
    monkeypatch.setattr(Model, "filter", MagicMock(return_value=query))

    resolved = await resolve_extraction_model(None)
    assert resolved is None


@pytest.mark.asyncio
async def test_extract_memories_debounced(monkeypatch):
    redis = SimpleNamespace(
        get=AsyncMock(return_value="100.0"),
        set=AsyncMock(),
        delete=AsyncMock(),
    )
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))

    result = await _extract_memories_for_conversation(
        conversation_id_str=str(uuid4()),
        agent_id_str=str(uuid4()),
        user_id_str=str(uuid4()),
        scheduled_ts=50.0,
    )
    assert result == {"status": "debounced"}


@pytest.mark.asyncio
async def test_extract_memories_disabled_or_locked(monkeypatch):
    from app.models.site_setting import SiteSetting

    redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=False),  # lock not acquired
        delete=AsyncMock(),
    )
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=False))

    # Disabled
    res_disabled = await _extract_memories_for_conversation(
        str(uuid4()), str(uuid4()), str(uuid4()), scheduled_ts=None
    )
    assert res_disabled == {"status": "skipped", "reason": "disabled"}

    # Locked
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))
    res_locked = await _extract_memories_for_conversation(
        str(uuid4()), str(uuid4()), str(uuid4()), scheduled_ts=None
    )
    assert res_locked == {"status": "locked"}


@pytest.mark.asyncio
async def test_extract_memories_success_creates_entities_and_advances_watermark(
    monkeypatch,
):
    from app.llm import model_manager
    from app.models.agent import Agent, Conversation
    from app.models.site_setting import SiteSetting
    from app.services.memory import MemoryService

    conv_id = uuid4()
    agent_id = uuid4()
    user_id = uuid4()
    msg1_id = uuid4()

    redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
        delete=AsyncMock(),
    )
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))

    mock_conv = SimpleNamespace(id=conv_id, memory_extracted_watermark_id=None)
    mock_agent = SimpleNamespace(id=agent_id, enable_memory=True)
    msg = SimpleNamespace(
        id=msg1_id,
        role=MessageRole.USER,
        content="I use FastAPI and live in Hangzhou",
    )

    monkeypatch.setattr(Conversation, "get_or_none", AsyncMock(return_value=mock_conv))
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=mock_agent))
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[msg]),
    )
    monkeypatch.setattr(
        "app.tasks.memory.resolve_extraction_model",
        AsyncMock(return_value="model-1"),
    )

    llm_output = json.dumps(
        {
            "entities": [
                {
                    "name": "FastAPI",
                    "entity_type": "skill",
                    "description": "Uses FastAPI",
                    "properties": {},
                }
            ],
            "relations": [
                {
                    "source_entity_name": "User",
                    "target_entity_name": "FastAPI",
                    "relation_type": "uses",
                    "description": "User uses FastAPI",
                }
            ],
        }
    )
    monkeypatch.setattr(
        model_manager,
        "chat",
        AsyncMock(return_value=SimpleNamespace(content=llm_output)),
    )

    create_entity = AsyncMock(return_value={"success": True})
    create_relation = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(MemoryService, "handle_create_entity", create_entity)
    monkeypatch.setattr(MemoryService, "handle_create_relation", create_relation)

    update_query = MagicMock()
    update_query.update = AsyncMock()
    monkeypatch.setattr(Conversation, "filter", MagicMock(return_value=update_query))

    result = await _extract_memories_for_conversation(
        str(conv_id), str(agent_id), str(user_id)
    )

    assert result["status"] == "completed"
    assert result["entities_created"] == 1
    assert result["relations_created"] == 1
    assert result["watermark_id"] == str(msg1_id)
    create_entity.assert_awaited_once()
    create_relation.assert_awaited_once()
    update_query.update.assert_awaited_once_with(memory_extracted_watermark_id=msg1_id)


@pytest.mark.asyncio
async def test_schedule_background_memory_extraction_branches(monkeypatch):
    from app.models.agent import Agent, Conversation
    from app.models.site_setting import SiteSetting
    from app.tasks.memory import extract_conversation_memories_task

    conv_id, agent_id, user_id = uuid4(), uuid4(), uuid4()

    # 1. Disabled globally
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=False))
    assert (
        await schedule_background_memory_extraction(conv_id, agent_id, user_id) is False
    )

    # 2. Enabled, but agent memory disabled
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))
    mock_agent = SimpleNamespace(id=agent_id, enable_memory=False)
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=mock_agent))
    assert (
        await schedule_background_memory_extraction(conv_id, agent_id, user_id) is False
    )

    # 3. Enabled, agent enabled, 0 pending messages
    mock_agent.enable_memory = True
    mock_conv = SimpleNamespace(id=conv_id, memory_extracted_watermark_id=None)
    monkeypatch.setattr(Conversation, "get_or_none", AsyncMock(return_value=mock_conv))
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[]),
    )
    assert (
        await schedule_background_memory_extraction(conv_id, agent_id, user_id) is False
    )

    # 4. Debounced scheduling (< max_turns)
    user_msg = SimpleNamespace(role=MessageRole.USER)
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[user_msg]),
    )
    redis = SimpleNamespace(set=AsyncMock(), delete=AsyncMock())
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))
    apply_async = MagicMock()
    monkeypatch.setattr(extract_conversation_memories_task, "apply_async", apply_async)

    # Setting returns for max_turns=6, cooldown=180
    async def get_setting(key, default=None):
        if key == "memory_async_extraction_enabled":
            return True
        if key == "memory_extraction_max_pending_turns":
            return 6
        if key == "memory_extraction_cooldown_seconds":
            return 180
        return default

    monkeypatch.setattr(SiteSetting, "get_value", get_setting)

    res_debounced = await schedule_background_memory_extraction(
        conv_id, agent_id, user_id
    )
    assert res_debounced is True
    redis.set.assert_awaited_once()
    assert apply_async.call_args.kwargs["countdown"] == 180

    # 5. Immediate scheduling when >= max_turns (e.g. 7 user messages)
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[user_msg] * 7),
    )
    res_immediate = await schedule_background_memory_extraction(
        conv_id, agent_id, user_id
    )
    assert res_immediate is True
    redis.delete.assert_awaited_once()
    assert apply_async.call_args.kwargs["countdown"] == 0


@pytest.mark.asyncio
async def test_resolve_extraction_model_by_model_id_and_fallback_chat(monkeypatch):
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    # Level 1 matches model_id instead of id
    monkeypatch.setattr(
        SiteSetting, "get_value", AsyncMock(return_value="deepseek-chat")
    )
    query_id = MagicMock(first=AsyncMock(return_value=None))
    mock_model = SimpleNamespace(id="deepseek-uuid")
    query_model_id = MagicMock(first=AsyncMock(return_value=mock_model))

    def mock_filter(**kwargs):
        if "model_id" in kwargs:
            return query_model_id
        return query_id

    monkeypatch.setattr(Model, "filter", mock_filter)
    assert await resolve_extraction_model() == "deepseek-uuid"

    # Fallback to any enabled chat model
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=""))
    fallback_query = MagicMock()
    fallback_query.first = AsyncMock(return_value=None)
    fallback_ordered = MagicMock()
    fallback_ordered.first = AsyncMock(return_value=SimpleNamespace(id="fallback-uuid"))
    fallback_query.order_by = MagicMock(return_value=fallback_ordered)

    def mock_fallback_filter(**kwargs):
        if kwargs.get("is_default") is True:
            return fallback_query
        return fallback_query

    monkeypatch.setattr(Model, "filter", mock_fallback_filter)
    assert await resolve_extraction_model() == "fallback-uuid"


@pytest.mark.asyncio
async def test_extract_memories_edge_skips(monkeypatch):
    from app.models.agent import Agent, Conversation
    from app.models.site_setting import SiteSetting

    conv_id = uuid4()
    redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
        delete=AsyncMock(),
    )
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))

    # Conversation not found
    monkeypatch.setattr(Conversation, "get_or_none", AsyncMock(return_value=None))
    assert (
        await _extract_memories_for_conversation(
            str(conv_id), str(uuid4()), str(uuid4())
        )
    ) == {"status": "error", "error": "conversation_not_found"}

    # Agent disabled
    conv = SimpleNamespace(id=conv_id, memory_extracted_watermark_id=None)
    agent = SimpleNamespace(id=uuid4(), enable_memory=False)
    monkeypatch.setattr(Conversation, "get_or_none", AsyncMock(return_value=conv))
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=agent))
    assert (
        await _extract_memories_for_conversation(
            str(conv_id), str(agent.id), str(uuid4())
        )
    ) == {"status": "skipped", "reason": "agent_memory_disabled"}

    # No messages
    agent.enable_memory = True
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[]),
    )
    assert (
        await _extract_memories_for_conversation(
            str(conv_id), str(agent.id), str(uuid4())
        )
    ) == {"status": "skipped", "reason": "no_messages"}

    # No dialogue messages (e.g. system message only)
    sys_msg = SimpleNamespace(role=MessageRole.SYSTEM, content="sys")
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[sys_msg]),
    )
    assert (
        await _extract_memories_for_conversation(
            str(conv_id), str(agent.id), str(uuid4())
        )
    ) == {"status": "skipped", "reason": "no_dialogue"}

    # No model available
    user_msg = SimpleNamespace(role=MessageRole.USER, content="hello")
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[user_msg]),
    )
    monkeypatch.setattr(
        "app.tasks.memory.resolve_extraction_model",
        AsyncMock(return_value=None),
    )
    assert (
        await _extract_memories_for_conversation(
            str(conv_id), str(agent.id), str(uuid4())
        )
    ) == {"status": "skipped", "reason": "no_model_available"}


@pytest.mark.asyncio
async def test_extract_memories_swallows_creation_exceptions_and_runs_celery_task(
    monkeypatch,
):
    from app.llm import model_manager
    from app.models.agent import Agent, Conversation
    from app.models.site_setting import SiteSetting
    from app.services.memory import MemoryService

    conv_id = uuid4()
    agent_id = uuid4()
    user_id = uuid4()

    redis = SimpleNamespace(
        get=AsyncMock(return_value="bad_ts"),  # invalid float triggers fallback
        set=AsyncMock(return_value=True),
        delete=AsyncMock(),
    )
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))

    watermark_msg_id = uuid4()
    conv = SimpleNamespace(id=conv_id, memory_extracted_watermark_id=watermark_msg_id)
    agent = SimpleNamespace(id=agent_id, enable_memory=True)
    user_msg = SimpleNamespace(id=uuid4(), role=MessageRole.USER, content="Hello")

    monkeypatch.setattr(Conversation, "get_or_none", AsyncMock(return_value=conv))
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages_after",
        AsyncMock(
            return_value=None
        ),  # triggers fallback to get_visible_conversation_messages
    )
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[user_msg]),
    )
    monkeypatch.setattr(
        "app.tasks.memory.resolve_extraction_model",
        AsyncMock(return_value="model-1"),
    )

    payload = json.dumps(
        {
            "entities": [
                {"name": "BadEnt", "entity_type": "fact", "description": "d"},
                {"name": "", "entity_type": "fact"},  # empty name skipped
            ],
            "relations": [
                {
                    "source_entity_name": "A",
                    "target_entity_name": "B",
                    "relation_type": "rel",
                },
                {
                    "source_entity_name": "",
                    "target_entity_name": "B",
                },  # empty source skipped
            ],
        }
    )
    monkeypatch.setattr(
        model_manager, "chat", AsyncMock(return_value=SimpleNamespace(content=payload))
    )
    monkeypatch.setattr(
        MemoryService,
        "handle_create_entity",
        AsyncMock(side_effect=RuntimeError("create failed")),
    )
    monkeypatch.setattr(
        MemoryService,
        "handle_create_relation",
        AsyncMock(side_effect=RuntimeError("create rel failed")),
    )
    update_query = MagicMock(update=AsyncMock())
    monkeypatch.setattr(Conversation, "filter", MagicMock(return_value=update_query))

    res = await _extract_memories_for_conversation(
        str(conv_id), str(agent_id), str(user_id), scheduled_ts=10.0
    )
    assert res["status"] == "completed"
    assert res["entities_created"] == 0
    assert res["relations_created"] == 0


def test_extract_conversation_memories_task_sync_run(monkeypatch):
    monkeypatch.setattr(
        "app.tasks.memory._extract_memories_for_conversation",
        AsyncMock(return_value={"status": "completed"}),
    )
    res = extract_conversation_memories_task.run("c1", "a1", "u1", scheduled_ts=None)
    assert res == {"status": "completed"}


@pytest.mark.asyncio
async def test_schedule_background_memory_extraction_watermark_paths(monkeypatch):
    from app.models.agent import Agent, Conversation
    from app.models.site_setting import SiteSetting
    from app.tasks.memory import extract_conversation_memories_task

    conv_id = uuid4()
    agent_id = uuid4()
    user_id = uuid4()
    watermark_id = uuid4()

    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))
    agent = SimpleNamespace(id=agent_id, enable_memory=True)
    conv = SimpleNamespace(id=conv_id, memory_extracted_watermark_id=watermark_id)
    monkeypatch.setattr(Agent, "get_or_none", AsyncMock(return_value=agent))
    monkeypatch.setattr(Conversation, "get_or_none", AsyncMock(return_value=conv))

    user_msg = SimpleNamespace(role=MessageRole.USER)
    # 1. after_message_id returns None -> falls back to get_visible_conversation_messages
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages_after",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages",
        AsyncMock(return_value=[user_msg]),
    )
    redis = SimpleNamespace(set=AsyncMock(), delete=AsyncMock())
    monkeypatch.setattr("app.tasks.memory.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(extract_conversation_memories_task, "apply_async", MagicMock())

    res = await schedule_background_memory_extraction(conv_id, agent_id, user_id)
    assert res is True

    # 2. after_message_id returns valid list
    monkeypatch.setattr(
        "app.tasks.memory.get_visible_conversation_messages_after",
        AsyncMock(return_value=[user_msg]),
    )
    res2 = await schedule_background_memory_extraction(conv_id, agent_id, user_id)
    assert res2 is True
