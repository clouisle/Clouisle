"""Durable worker wiring for authorized tool discovery."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.services.agent_run_worker import (
    _bind_execute_tool_call,
    _build_tool_discovery_state,
    _tools_definitions,
)


def _schema(name: str, description: str = ""):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _large_tools(count: int = 25):
    tools = [
        _schema("ask_user", "Ask the user"),
        _schema("knowledge_search", "Search knowledge"),
        _schema("read_tool_result", "Read a stored tool result"),
    ]
    tools.extend(
        _schema(f"mcp_ops_server_action_{index}", "Operations action")
        for index in range(count)
    )
    return tools


@pytest.mark.asyncio
async def test_build_state_restores_and_persists_selection(monkeypatch):
    from app.services import agent_run_store

    persisted = AsyncMock()
    monkeypatch.setattr(agent_run_store, "remember_discovered_tools", persisted)
    run_id = uuid4()
    definitions = _tools_definitions(_large_tools())
    assert definitions is not None

    state = await _build_tool_discovery_state(
        definitions,
        payload={
            "run_id": str(run_id),
            "discovered_tools": ["mcp_ops_server_action_1"],
        },
        agent=SimpleNamespace(team_id=None, tools_config=[]),
        user_id=None,
    )
    assert state is not None
    assert state.loaded == ["mcp_ops_server_action_1"]

    result = json.loads(
        await state.execute("load_tools", {"names": ["mcp_ops_server_action_2"]})
    )
    assert result["loaded"] == ["mcp_ops_server_action_2"]
    persisted.assert_awaited_once_with(
        run_id, ["mcp_ops_server_action_1", "mcp_ops_server_action_2"]
    )


@pytest.mark.asyncio
async def test_discovery_tools_are_routed_before_execution(monkeypatch):
    from app.api.v1.endpoints import chat_tools

    base = AsyncMock(return_value="base-result")
    monkeypatch.setattr(chat_tools, "execute_tool_call", base)

    discovery = SimpleNamespace(
        handles=lambda name: name in {"discover_tools", "load_tools"},
        is_visible=lambda name: True,
        touch=lambda name: None,
        execute=AsyncMock(return_value="discovery-result"),
    )
    runner = _bind_execute_tool_call(discovery)

    assert await runner("discover_tools", {"query": "x"}) == "discovery-result"
    discovery.execute.assert_awaited_once_with("discover_tools", {"query": "x"})
    base.assert_not_awaited()

    # Every normal tool keeps the original execution boundary, arguments and
    # keyword context untouched (approval/authorization behavior unchanged).
    assert await runner("read_tool_result", {"ref": "tr1:a:b"}, agent="a") == (
        "base-result"
    )
    base.assert_awaited_once_with("read_tool_result", {"ref": "tr1:a:b"}, agent="a")


@pytest.mark.asyncio
async def test_undiscovered_authorized_tool_is_rejected_until_loaded(monkeypatch):
    from app.api.v1.endpoints import chat_tools
    from app.services import agent_run_store

    monkeypatch.setattr(agent_run_store, "remember_discovered_tools", AsyncMock())

    base = AsyncMock(return_value="base-result")
    monkeypatch.setattr(chat_tools, "execute_tool_call", base)

    definitions = _tools_definitions(_large_tools())
    state = await _build_tool_discovery_state(
        definitions,
        payload={"run_id": str(uuid4())},
        agent=SimpleNamespace(team_id=None, tools_config=[]),
        user_id=None,
    )
    assert state is not None
    runner = _bind_execute_tool_call(state)

    blocked = json.loads(await runner("mcp_ops_server_action_0", {}))
    assert blocked["success"] is False
    assert "discover_tools" in blocked["error"]
    base.assert_not_awaited()

    await state.execute("load_tools", {"names": ["mcp_ops_server_action_0"]})
    assert await runner("mcp_ops_server_action_0", {}) == "base-result"
    base.assert_awaited_once_with("mcp_ops_server_action_0", {})


@pytest.mark.asyncio
async def test_load_tools_only_exposes_tool_to_the_next_model_turn(monkeypatch):
    from app.api.v1.endpoints import chat_tools
    from app.services import agent_run_store

    monkeypatch.setattr(agent_run_store, "remember_discovered_tools", AsyncMock())
    base = AsyncMock(return_value="base-result")
    monkeypatch.setattr(chat_tools, "execute_tool_call", base)
    state = await _build_tool_discovery_state(
        _tools_definitions(_large_tools()),
        payload={"run_id": str(uuid4())},
        agent=SimpleNamespace(team_id=None, tools_config=[]),
        user_id=None,
    )
    assert state is not None
    runner = _bind_execute_tool_call(state)

    # Model response schemas are fixed for this turn, even after load_tools.
    state.tools_for_turn()
    loaded_name = "mcp_ops_server_action_0"
    await state.execute("load_tools", {"names": [loaded_name]})
    rejected = json.loads(await runner(loaded_name, {}))
    assert rejected["success"] is False
    base.assert_not_awaited()

    # The next model request snapshots the updated selection and can call it.
    state.tools_for_turn()
    assert await runner(loaded_name, {}) == "base-result"
    base.assert_awaited_once_with(loaded_name, {})


def test_approval_history_with_result_reference_restores_readback_tool():
    from app.services.agent_run_worker import _history_override_has_tool_result_ref

    history = [
        {"role": "user", "content": "continue"},
        {
            "role": "tool",
            "content": (
                "Earlier tool result omitted; use read_tool_result "
                f"ref=tr1:{uuid4()}:call-1"
            ),
        },
    ]
    assert _history_override_has_tool_result_ref(history) is True
    assert (
        _history_override_has_tool_result_ref(
            [{"role": "user", "content": "no prior result"}]
        )
        is False
    )
    assert _history_override_has_tool_result_ref([]) is False
    assert (
        _history_override_has_tool_result_ref(
            [{"role": "tool", "content": "malformed tr1:not-a-ref"}]
        )
        is False
    )


@pytest.mark.asyncio
async def test_result_reference_restores_readback_when_agent_has_no_tools(monkeypatch):
    from app.services import agent_run_worker as worker

    async def no_tools(agent, user_id=None):
        return []

    async def no_discovery(tools, *, payload, agent, user_id):
        assert tools is not None and [tool.function.name for tool in tools] == [
            "read_tool_result"
        ]
        return None

    monkeypatch.setattr(worker, "_load_tools", no_tools)
    monkeypatch.setattr(worker, "_build_tool_discovery_state", no_discovery)
    tools_openai, tools, _ = await worker._load_authorized_tools(
        {
            "run_id": str(uuid4()),
            "history_override": [
                {"role": "tool", "content": f"ref=tr1:{uuid4()}:call-1"}
            ],
        },
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=False,
    )
    assert [tool["function"]["name"] for tool in tools_openai] == ["read_tool_result"]
    assert tools is not None and [tool.function.name for tool in tools] == [
        "read_tool_result"
    ]


@pytest.mark.asyncio
async def test_readback_schema_is_available_for_markers_created_during_recovery(
    monkeypatch,
):
    from app.services import agent_run_worker as worker

    async def no_tools(agent, user_id=None):
        return []

    async def no_discovery(tools, *, payload, agent, user_id):
        assert tools is not None
        return None

    monkeypatch.setattr(worker, "_load_tools", no_tools)
    monkeypatch.setattr(worker, "_build_tool_discovery_state", no_discovery)
    tools_openai, tools, _ = await worker._load_authorized_tools(
        {
            "run_id": str(uuid4()),
            "history_override": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "clock", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "result"},
            ],
        },
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=False,
    )
    # A complete exchange can be compacted into a new marker during recovery.
    assert [tool["function"]["name"] for tool in tools_openai] == ["read_tool_result"]
    assert tools is not None and [tool.function.name for tool in tools] == [
        "read_tool_result"
    ]


def test_without_discovery_the_boundary_is_unchanged(monkeypatch):
    from app.api.v1.endpoints import chat_tools

    original = chat_tools.execute_tool_call
    assert _bind_execute_tool_call(None) is original


@pytest.mark.asyncio
async def test_executing_a_loaded_tool_refreshes_eviction_order(monkeypatch):
    from app.api.v1.endpoints import chat_tools
    from app.services import agent_run_store

    monkeypatch.setattr(agent_run_store, "remember_discovered_tools", AsyncMock())
    base = AsyncMock(return_value="base-result")
    monkeypatch.setattr(chat_tools, "execute_tool_call", base)

    state = await _build_tool_discovery_state(
        _tools_definitions(_large_tools()),
        payload={"run_id": str(uuid4())},
        agent=SimpleNamespace(team_id=None, tools_config=[]),
        user_id=None,
    )
    assert state is not None
    state.max_loaded = 2
    first = "mcp_ops_server_action_0"
    second = "mcp_ops_server_action_1"
    third = "mcp_ops_server_action_2"
    await state.execute("load_tools", {"names": [first, second]})
    runner = _bind_execute_tool_call(state)
    assert state.loaded == [first, second]

    # Calling the oldest loaded tool refreshes its recency, so eviction takes
    # the other tool instead of the one the run just used.
    assert await runner(first, {}) == "base-result"
    result = json.loads(await state.execute("load_tools", {"names": [third]}))
    assert result["evicted"] == [second]
    assert state.loaded == [first, third]


@pytest.mark.asyncio
async def test_discovery_build_reuses_the_run_tool_identity_scope(monkeypatch):
    from app.services import agent_run_worker as worker
    from app.services.tool_context import current_tool_identity

    run_id = uuid4()
    api_key_id = uuid4()
    payload = {
        "run_id": str(run_id),
        "tool_entrypoint": "api_key",
        "tool_entrypoint_id": "key-1",
        "api_key_id": str(api_key_id),
    }
    captured: dict[str, Any] = {}

    async def _load_tools(agent, user_id=None):
        captured["listing"] = current_tool_identity()
        return [
            _schema("ask_user", "Ask the user"),
            _schema("mcp_server_tool", "A tool"),
        ]

    async def _build(tools, *, payload, agent, user_id):
        captured["discovery"] = current_tool_identity()
        return None

    monkeypatch.setattr(worker, "_load_tools", _load_tools)
    monkeypatch.setattr(worker, "_build_tool_discovery_state", _build)

    tools_openai, tools, discovery = await worker._load_authorized_tools(
        payload,
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=True,
    )

    assert discovery is None
    assert current_tool_identity() is None
    for identity in (captured["listing"], captured["discovery"]):
        assert identity is not None
        assert identity.run_id == run_id
        assert identity.api_key_id == api_key_id
        assert identity.entrypoint == "api_key"
        assert identity.entrypoint_id == "key-1"
        assert identity.interactive is False
    # Non-stream filtering still applies before discovery is built.
    assert [tool["function"]["name"] for tool in tools_openai] == ["mcp_server_tool"]
    assert tools is not None and len(tools) == 1

    # A reference in approval history restores readback; ordinary history does not.
    resumed, _, _ = await worker._load_authorized_tools(
        dict(
            payload,
            history_override=[{"role": "tool", "content": f"ref=tr1:{uuid4()}:call-1"}],
        ),
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=False,
    )
    assert [tool["function"]["name"] for tool in resumed] == [
        "ask_user",
        "mcp_server_tool",
        "read_tool_result",
    ]
    no_reference, _, _ = await worker._load_authorized_tools(
        dict(payload, history_override=[{"role": "tool", "content": "plain result"}]),
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=False,
    )
    assert [tool["function"]["name"] for tool in no_reference] == [
        "ask_user",
        "mcp_server_tool",
    ]
    assert [tool["function"]["name"] for tool in tools_openai] == ["mcp_server_tool"]
    assert tools is not None and len(tools) == 1
    # A streaming run keeps ask_user in the same identity scope.
    streaming_openai, _, _ = await worker._load_authorized_tools(
        payload,
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=False,
    )
    assert [tool["function"]["name"] for tool in streaming_openai] == [
        "ask_user",
        "mcp_server_tool",
    ]
    assert current_tool_identity() is None


@pytest.mark.asyncio
async def test_no_tools_and_no_result_reference_keeps_tool_list_empty(monkeypatch):
    from app.services import agent_run_worker as worker

    async def no_tools(agent, user_id=None):
        return []

    async def no_discovery(tools, *, payload, agent, user_id):
        assert tools is None
        return None

    monkeypatch.setattr(worker, "_load_tools", no_tools)
    monkeypatch.setattr(worker, "_build_tool_discovery_state", no_discovery)
    tools_openai, tools, discovery = await worker._load_authorized_tools(
        {
            "run_id": str(uuid4()),
            "history_override": [{"role": "user", "content": "ordinary"}],
        },
        SimpleNamespace(team_id="team-1"),
        user_id="user-1",
        non_stream=False,
    )
    assert tools_openai == []
    assert tools is None
    assert discovery is None


@pytest.mark.asyncio
async def test_build_state_without_a_run_id_has_no_persistence_callback(monkeypatch):
    state = await _build_tool_discovery_state(
        _tools_definitions(_large_tools()),
        payload={},
        agent=SimpleNamespace(team_id=None, tools_config=[]),
        user_id=None,
    )
    assert state is not None
    assert state.on_loaded_change is None
    result = json.loads(
        await state.execute("load_tools", {"names": ["mcp_ops_server_action_0"]})
    )
    assert result["loaded"] == ["mcp_ops_server_action_0"]
    assert state.loaded == ["mcp_ops_server_action_0"]


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


async def _seed_run(payload: dict[str, Any]) -> Any:
    from app.models.agent import Agent, Conversation
    from app.models.agent_run import AgentRunMode
    from app.models.user import Team, User

    team = await Team.create(id=uuid4(), name=f"team-{uuid4()}")
    owner = await User.create(
        id=uuid4(),
        username=f"owner-{uuid4()}",
        email=f"{uuid4()}@example.test",
        hashed_password="unused",
    )
    agent = await Agent.create(id=uuid4(), team_id=team.id, name="discovery-agent")
    conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    from app.models.agent_run import AgentRun

    return await AgentRun.create(
        id=uuid4(),
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=owner.id,
        mode=AgentRunMode.SEND,
        worker_payload=payload,
    )


@pytest.mark.asyncio
async def test_remember_discovered_tools_merges_without_losing_resume_state(database):
    """Real persistence: only ``discovered_tools`` changes in the payload."""
    from app.models.agent_run import AgentRun
    from app.services import agent_run_store

    run = await _seed_run(
        {
            "run_id": str(uuid4()),
            "history_override": [{"role": "user", "content": "keep me"}],
            "discovered_tools": ["mcp_ops_server_action_0"],
        }
    )
    await agent_run_store.remember_discovered_tools(
        run.id, ["mcp_ops_server_action_1", "mcp_ops_server_action_2"]
    )
    refreshed = await AgentRun.get(id=run.id)
    assert refreshed.worker_payload["discovered_tools"] == [
        "mcp_ops_server_action_1",
        "mcp_ops_server_action_2",
    ]
    assert refreshed.worker_payload["history_override"] == [
        {"role": "user", "content": "keep me"}
    ]
    assert refreshed.worker_payload["run_id"] == run.worker_payload["run_id"]

    # An empty selection removes only the discovery key.
    await agent_run_store.remember_discovered_tools(run.id, [])
    refreshed = await AgentRun.get(id=run.id)
    assert "discovered_tools" not in refreshed.worker_payload
    assert refreshed.worker_payload["history_override"]

    # A missing run is a no-op, never an exception.
    await agent_run_store.remember_discovered_tools(uuid4(), ["x"])


@pytest.mark.asyncio
async def test_discovery_load_survives_a_failed_payload_save(monkeypatch):
    from app.services import agent_run_store

    async def _failed_save(run_id, names):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(agent_run_store, "remember_discovered_tools", _failed_save)
    state = await _build_tool_discovery_state(
        _tools_definitions(_large_tools()),
        payload={"run_id": str(uuid4())},
        agent=SimpleNamespace(team_id=None, tools_config=[]),
        user_id=None,
    )
    assert state is not None
    result = json.loads(
        await state.execute("load_tools", {"names": ["mcp_ops_server_action_0"]})
    )
    # The tool remains usable for this run; a later rebuild revalidates it.
    assert result["loaded"] == ["mcp_ops_server_action_0"]
    assert state.loaded == ["mcp_ops_server_action_0"]
    assert state.is_visible("mcp_ops_server_action_0") is True
