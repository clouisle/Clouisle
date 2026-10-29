"""Authorized on-demand tool discovery (tiered tool schemas)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.types import ToolDefinition
from app.services.tool_discovery import (
    DISCOVER_TOOLS_TOOL,
    LOAD_TOOLS_TOOL,
    UNLOAD_TOOLS_TOOL,
    _search_terms,
    build_tool_discovery,
    estimate_tool_schema_tokens,
)


def _schema(name: str, description: str = "", required: list[str] | None = None):
    properties = {
        key: {"type": "string", "description": " ".join(["detail"] * 30)}
        for key in (required or [])
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def _mcp_catalog(count: int) -> list[dict]:
    tools = [
        _schema("ask_user", "Ask the user a question"),
        _schema("knowledge_search", "Search the knowledge base"),
        _schema("read_tool_result", "Read a previously stored tool result"),
        _schema("list_assets", "List assets"),
    ]
    for index in range(count):
        tools.append(
            _schema(
                f"mcp_calendar_server_tool_{index}",
                "Calendar event management " + ("x" * 400),
                required=["title"],
            )
        )
    return tools


@pytest.mark.asyncio
async def test_small_catalog_is_not_tiered():
    tools = _mcp_catalog(3)
    state = await build_tool_discovery(tools)
    assert state is None


@pytest.mark.asyncio
async def test_large_catalog_keeps_core_and_adds_discovery_tools():
    # Production loaders hand the loop native ToolDefinition objects; the
    # catalog keeps those objects and builds meta tools with the same factory.
    tools = [ToolDefinition.model_validate(schema) for schema in _mcp_catalog(30)]
    state = await build_tool_discovery(tools, factory=ToolDefinition.model_validate)
    assert state is not None

    visible = state.tools_for_turn()
    assert all(isinstance(tool, ToolDefinition) for tool in visible)
    names = [tool.function.name for tool in visible]
    assert names[:2] == [DISCOVER_TOOLS_TOOL, LOAD_TOOLS_TOOL]
    # Always-visible set survives discovery.
    assert "ask_user" in names
    assert "knowledge_search" in names
    assert "read_tool_result" in names
    # No discoverable schema occupies the first request.
    assert not any(name.startswith("mcp_") for name in names)
    assert len(visible) < len(tools)

    visible_tokens = estimate_tool_schema_tokens(visible)
    assert visible_tokens < estimate_tool_schema_tokens(tools) // 2


@pytest.mark.asyncio
async def test_only_configured_sandbox_tools_are_visible_in_large_catalog():
    tools = [
        *_mcp_catalog(30),
        _schema("bash", "Run commands in the sandbox"),
        _schema("read", "Read a sandbox file"),
    ]
    state = await build_tool_discovery(tools)
    assert state is not None
    visible = {tool["function"]["name"] for tool in state.tools_for_turn()}
    assert {"bash", "read"} <= visible
    assert "edit" not in visible and "write" not in visible
    assert not any(name.startswith("mcp_") for name in visible)


@pytest.mark.asyncio
async def test_discover_then_load_makes_tool_visible_and_persists():
    persisted: list[list[str]] = []

    async def _remember(names):
        persisted.append(names)

    tools = _mcp_catalog(25)
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None
    state.on_loaded_change = _remember

    found = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"query": "calendar event"})
    )
    matches = [item["name"] for item in found["tools"]]
    assert "mcp_calendar_server_tool_0" in matches
    # Compact metadata: no full parameter schema is echoed back.
    assert "parameters" in found["tools"][0]
    assert isinstance(found["tools"][0]["parameters"], list)
    assert found["tools"][0]["loaded"] is False

    loaded = json.loads(
        await state.execute(LOAD_TOOLS_TOOL, {"names": ["mcp_calendar_server_tool_0"]})
    )
    assert loaded["loaded"] == ["mcp_calendar_server_tool_0"]
    assert persisted == [["mcp_calendar_server_tool_0"]]

    visible = [tool["function"]["name"] for tool in state.tools_for_turn()]
    assert "mcp_calendar_server_tool_0" in visible

    # A second search still finds it and reports the loaded state.
    again = json.loads(await state.execute(DISCOVER_TOOLS_TOOL, {"query": "calendar"}))
    loaded_entry = next(
        item for item in again["tools"] if item["name"] == "mcp_calendar_server_tool_0"
    )
    assert loaded_entry["loaded"] is True


@pytest.mark.asyncio
async def test_unknown_names_are_never_loaded():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None
    result = json.loads(
        await state.execute(
            LOAD_TOOLS_TOOL,
            {"names": ["mcp_not_configured", "mcp_calendar_server_tool_1"]},
        )
    )
    assert result["loaded"] == ["mcp_calendar_server_tool_1"]
    assert result["unknown"] == ["mcp_not_configured"]
    assert "mcp_not_configured" not in state.loaded


@pytest.mark.asyncio
async def test_loaded_names_are_revalidated_against_authorized_catalog():
    state = await build_tool_discovery(
        _mcp_catalog(25),
        min_discoverable=5,
        loaded_names=["mcp_calendar_server_tool_2", "mcp_revoked_server_tool"],
    )
    assert state is not None
    assert state.loaded == ["mcp_calendar_server_tool_2"]
    visible = [tool["function"]["name"] for tool in state.tools_for_turn()]
    assert "mcp_revoked_server_tool" not in visible


@pytest.mark.asyncio
async def test_custom_tool_denied_by_execution_authorization_is_not_exposed(
    monkeypatch,
):
    from app.models.tool import Tool
    from app.models.user import User
    from app.schemas.response import BusinessError
    from app.services import tool_execution as tool_execution_module

    class _CustomTool:
        id = "tool-1"
        name = "payroll"
        team_id = "team-1"

    class _Actor:
        id = "user-1"

    monkeypatch.setattr(Tool, "get_or_none", AsyncMock(return_value=_CustomTool()))
    monkeypatch.setattr(User, "get_or_none", AsyncMock(return_value=_Actor()))

    async def _deny(*args, **kwargs):
        raise BusinessError(code=403, msg_key="tool_access_denied", status_code=403)

    monkeypatch.setattr(tool_execution_module, "authorize_tool_context", _deny)

    tools = [
        _schema("custom_payroll", "Run payroll"),
        _schema("custom_approved", "Approved tool"),
        *[_schema(f"mcp_server_tool_{i}", "MCP action") for i in range(25)],
    ]
    agent = SimpleNamespace(
        team_id="team-1",
        tools_config=[
            {"type": "custom", "tool_id": "tool-1"},
        ],
    )
    state = await build_tool_discovery(
        tools,
        agent=agent,
        user_id="user-1",
        min_discoverable=5,
    )
    assert state is not None
    assert "custom_payroll" not in state.catalog
    assert "custom_approved" in state.catalog


@pytest.mark.asyncio
async def test_large_schema_footprint_activates_discovery_below_count_threshold():
    tools = [
        _schema("ask_user", "Ask the user"),
        *[_schema(f"custom_tool_{index}", "y" * 5000) for index in range(6)],
    ]
    assert (
        await build_tool_discovery(
            tools, min_discoverable=100, schema_token_budget=4096
        )
        is not None
    )


@pytest.mark.asyncio
async def test_workflow_agent_service_routes_discovery_before_execution():
    from app.llm.types import FunctionCall, ToolCall
    from app.services.agent import AgentService

    definitions = [ToolDefinition.model_validate(schema) for schema in _mcp_catalog(25)]
    state = await build_tool_discovery(
        definitions,
        factory=ToolDefinition.model_validate,
        min_discoverable=5,
    )
    assert state is not None

    call = ToolCall(
        id="c1",
        function=FunctionCall(
            name=LOAD_TOOLS_TOOL,
            arguments=json.dumps({"names": ["mcp_calendar_server_tool_0"]}),
        ),
    )
    result = json.loads(
        await AgentService()._dispatch_tool_call(
            SimpleNamespace(id="agent-1", team_id="team-1"),
            call,
            tool_discovery=state,
        )
    )
    assert result["loaded"] == ["mcp_calendar_server_tool_0"]

    hidden = json.loads(
        await AgentService()._dispatch_tool_call(
            SimpleNamespace(id="agent-1", team_id="team-1"),
            ToolCall(
                id="c2",
                function=FunctionCall(
                    name="mcp_calendar_server_tool_1", arguments="{}"
                ),
            ),
            tool_discovery=state,
        )
    )
    assert hidden["success"] is False
    assert "load_tools" in hidden["error"]


@pytest.mark.asyncio
async def test_protocol_tools_stay_deduped_when_loading():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None
    result = json.loads(
        await state.execute(
            LOAD_TOOLS_TOOL,
            {"names": ["read_tool_result", "ask_user"]},
        )
    )
    assert result["loaded"] == []
    assert result["already_visible"] == ["read_tool_result", "ask_user"]
    visible = [tool["function"]["name"] for tool in state.tools_for_turn()]
    assert visible.count("read_tool_result") == 1
    assert visible.count("ask_user") == 1


@pytest.mark.asyncio
async def test_chinese_query_matches_names_and_descriptions():
    tools = [
        _schema("ask_user", "Ask the user"),
        _schema(
            "mcp_calendar_server_create_event",
            "创建日历事件并邀请参会人",
        ),
        _schema("mcp_oa_server_查询报销单", "Query expense status"),
        *[
            _schema(f"mcp_misc_server_item_{index}", "Unrelated capability")
            for index in range(25)
        ],
    ]
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None

    # Description substring: a short Chinese keyword finds the calendar tool.
    by_description = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"query": "日历"})
    )
    assert [item["name"] for item in by_description["tools"]] == [
        "mcp_calendar_server_create_event"
    ]

    # Natural-language CJK query expands to bigrams and still matches.
    by_phrase = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"query": "创建日历事件"})
    )
    assert "mcp_calendar_server_create_event" in [
        item["name"] for item in by_phrase["tools"]
    ]

    # Name substring (CJK inside the tool name).
    by_name = json.loads(await state.execute(DISCOVER_TOOLS_TOOL, {"query": "报销单"}))
    assert [item["name"] for item in by_name["tools"]] == ["mcp_oa_server_查询报销单"]

    # A single CJK character still matches a description substring.
    by_char = json.loads(await state.execute(DISCOVER_TOOLS_TOOL, {"query": "历"}))
    assert [item["name"] for item in by_char["tools"]] == [
        "mcp_calendar_server_create_event"
    ]

    # English search behavior is unchanged (25 filler matches, default page 8).
    by_english = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"query": "unrelated capability"})
    )
    assert by_english["total_matches"] == 25
    assert len(by_english["tools"]) == 8


@pytest.mark.asyncio
async def test_discover_tools_pages_through_the_full_catalog():
    state = await build_tool_discovery(_mcp_catalog(30), min_discoverable=5)
    assert state is not None

    seen: list[str] = []
    offset = 0
    pages = 0
    while True:
        result = json.loads(
            await state.execute(DISCOVER_TOOLS_TOOL, {"limit": 7, "offset": offset})
        )
        assert result["total_matches"] == 30
        assert result["discoverable_tools"] == 30
        assert result["offset"] == offset
        assert result["limit"] == 7
        seen.extend(item["name"] for item in result["tools"])
        pages += 1
        if result["next_offset"] is None:
            break
        offset = result["next_offset"]

    # Every discoverable tool is listable exactly once across bounded pages.
    assert pages == 5
    assert len(seen) == 30
    assert len(set(seen)) == 30
    assert all(name.startswith("mcp_") for name in seen)

    beyond = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"limit": 7, "offset": 5000})
    )
    assert beyond["tools"] == []
    assert beyond["next_offset"] is None
    # The offset is clamped to the result size, not an arbitrary constant.
    assert beyond["offset"] == 30


@pytest.mark.asyncio
async def test_catalogs_beyond_one_thousand_tools_stay_traversable():
    tools = _mcp_catalog(1005)
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None

    seen: list[str] = []
    offset = 0
    while True:
        result = json.loads(
            await state.execute(DISCOVER_TOOLS_TOOL, {"limit": 20, "offset": offset})
        )
        assert result["total_matches"] == 1005
        seen.extend(item["name"] for item in result["tools"])
        if result["next_offset"] is None:
            break
        offset = result["next_offset"]

    assert len(seen) == 1005
    assert len(set(seen)) == 1005
    # Tools past the old fixed 1000-tool cap are reachable.
    assert "mcp_calendar_server_tool_1004" in seen

    tail = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"limit": 20, "offset": 1000})
    )
    assert len(tail["tools"]) == 5
    assert tail["next_offset"] is None


@pytest.mark.asyncio
async def test_collision_with_discovery_tool_name_fails_closed():
    tools = _mcp_catalog(25)
    tools.append(_schema(DISCOVER_TOOLS_TOOL, "A user tool with the same name"))
    assert await build_tool_discovery(tools, min_discoverable=5) is None


@pytest.mark.asyncio
async def test_batch_over_cap_defers_tail_and_execution_refreshes_eviction():
    tools = _mcp_catalog(30)
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None
    state.max_loaded = 2
    names = [f"mcp_calendar_server_tool_{i}" for i in range(5)]
    first_batch = names[:4]

    # A batch larger than the cap keeps its order and defers the tail instead
    # of silently loading more than allowed.
    state.tools_for_turn()
    result = json.loads(await state.execute(LOAD_TOOLS_TOOL, {"names": first_batch}))
    assert result["loaded"] == first_batch[:2]
    assert result["not_loaded_limit_reached"] == first_batch[2:]
    assert "evicted" not in result
    assert state.loaded == first_batch[:2]
    # The model schemas were snapshotted before this response loaded the tools.
    assert state.is_visible(names[0]) is False
    assert state.is_visible(names[2]) is False

    state.tools_for_turn()
    assert state.is_visible(names[0]) is True
    assert state.is_visible(names[2]) is False
    # The tool loaded during this response is not callable until next turn.
    result = json.loads(await state.execute(LOAD_TOOLS_TOOL, {"names": [names[4]]}))
    assert result["evicted"] == [names[0]]
    assert state.loaded == [names[1], names[4]]
    assert state.is_visible(names[4]) is False

    state.tools_for_turn()
    assert state.is_visible(names[4]) is True


@pytest.mark.asyncio
async def test_unload_tools_frees_slots_and_protects_core_tools():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None
    await state.execute(
        LOAD_TOOLS_TOOL,
        {"names": ["mcp_calendar_server_tool_0", "mcp_calendar_server_tool_1"]},
    )
    # The model already has these schemas in its current turn.
    state.tools_for_turn()
    result = json.loads(
        await state.execute(
            UNLOAD_TOOLS_TOOL,
            {
                "names": [
                    "mcp_calendar_server_tool_0",
                    "ask_user",
                    "mcp_not_loaded",
                ]
            },
        )
    )
    assert result["unloaded"] == ["mcp_calendar_server_tool_0"]
    assert result["not_loaded"] == ["mcp_not_loaded"]
    assert result["always_visible"] == ["ask_user"]
    # The current response still follows its declared snapshot.
    assert state.is_visible("mcp_calendar_server_tool_0") is True
    assert state.is_visible("mcp_calendar_server_tool_1") is True
    # The next model turn reflects the unloaded selection.
    state.tools_for_turn()
    assert state.is_visible("mcp_calendar_server_tool_0") is False
    assert state.is_visible("mcp_calendar_server_tool_1") is True


@pytest.mark.asyncio
async def test_discovery_requires_a_catalog_and_can_be_disabled():
    assert await build_tool_discovery(None) is None
    assert await build_tool_discovery([]) is None
    assert await build_tool_discovery(_mcp_catalog(30), enabled=False) is None
    # Duplicate and nameless entries still form a valid catalog.
    tools = _mcp_catalog(25)
    tools.extend([{}, {"type": "function", "function": {}}])
    tools.append(_schema("mcp_calendar_server_tool_0", "duplicate name"))
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None
    assert "mcp_calendar_server_tool_0" in state.catalog


@pytest.mark.asyncio
async def test_exact_name_ranks_first_and_unknown_terms_return_nothing():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None

    exact = json.loads(
        await state.execute(
            DISCOVER_TOOLS_TOOL, {"query": "mcp_calendar_server_tool_3"}
        )
    )
    assert exact["tools"][0]["name"] == "mcp_calendar_server_tool_3"

    missing = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"query": "zzzzqqqxyz"})
    )
    assert missing["tools"] == []
    assert missing["total_matches"] == 0
    assert missing["next_offset"] is None


@pytest.mark.asyncio
async def test_last_page_and_zero_result_pages_have_no_next_offset():
    state = await build_tool_discovery(_mcp_catalog(30), min_discoverable=5)
    assert state is not None

    last = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"limit": 7, "offset": 29})
    )
    assert len(last["tools"]) == 1
    assert last["next_offset"] is None

    exactly_done = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"limit": 7, "offset": 30})
    )
    assert exactly_done["tools"] == []
    assert exactly_done["next_offset"] is None


@pytest.mark.asyncio
async def test_load_reports_already_visible_core_meta_and_duplicate_names():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None
    tool_name = "mcp_calendar_server_tool_0"

    result = json.loads(
        await state.execute(
            LOAD_TOOLS_TOOL,
            {
                "names": [
                    "ask_user",
                    DISCOVER_TOOLS_TOOL,
                    UNLOAD_TOOLS_TOOL,
                    tool_name,
                    tool_name,
                ]
            },
        )
    )
    assert result["loaded"] == [tool_name]
    assert result["already_visible"] == [
        "ask_user",
        DISCOVER_TOOLS_TOOL,
        UNLOAD_TOOLS_TOOL,
    ]
    assert state.loaded == [tool_name]

    again = json.loads(await state.execute(LOAD_TOOLS_TOOL, {"names": tool_name}))
    assert again["loaded"] == []
    assert again["already_visible"] == [tool_name]


@pytest.mark.asyncio
async def test_loading_a_skill_loads_its_sandbox_companions():
    tools = [
        _schema("ask_user", "Ask the user"),
        _schema("skill_data_analyst", "Analyze data in the sandbox"),
        _schema("read", "Read a sandbox file"),
        _schema("edit", "Edit a sandbox file"),
        _schema("write", "Write a sandbox file"),
        _schema("bash", "Run a sandbox command"),
        *[_schema(f"mcp_misc_server_item_{index}", "Unrelated") for index in range(25)],
    ]
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None

    result = json.loads(
        await state.execute(LOAD_TOOLS_TOOL, {"names": ["skill_data_analyst"]})
    )
    assert result["loaded"] == ["skill_data_analyst"]
    state.tools_for_turn()
    for name in ("skill_data_analyst", "read", "edit", "write", "bash"):
        assert state.is_visible(name) is True


@pytest.mark.asyncio
async def test_custom_authorization_lookup_failure_hides_only_custom_tools(
    monkeypatch,
):
    from app.models.tool import Tool

    monkeypatch.setattr(
        Tool,
        "get_or_none",
        AsyncMock(side_effect=RuntimeError("authorization unavailable")),
    )
    tools = [
        _schema("ask_user", "Ask the user"),
        _schema("custom_payroll", "Run payroll"),
        *[_schema(f"mcp_server_tool_{i}", "MCP action") for i in range(25)],
    ]
    agent = SimpleNamespace(
        team_id="team-1",
        tools_config=[{"type": "custom", "tool_id": "tool-1"}],
    )
    state = await build_tool_discovery(
        tools, agent=agent, user_id="user-1", min_discoverable=5
    )
    assert state is not None
    assert "custom_payroll" not in state.catalog
    assert state.is_visible("custom_payroll") is False
    assert "mcp_server_tool_0" in state.catalog


@pytest.mark.asyncio
async def test_custom_tool_without_resolvable_actor_is_hidden(monkeypatch):
    from app.models.tool import Tool
    from app.models.user import User

    class _CustomTool:
        id = "tool-1"
        name = "payroll"
        team_id = "team-1"

    monkeypatch.setattr(Tool, "get_or_none", AsyncMock(return_value=_CustomTool()))
    monkeypatch.setattr(User, "get_or_none", AsyncMock(return_value=None))

    tools = [
        _schema("ask_user", "Ask the user"),
        _schema("custom_payroll", "Run payroll"),
        *[_schema(f"mcp_server_tool_{i}", "MCP action") for i in range(25)],
    ]
    state = await build_tool_discovery(
        tools,
        agent=SimpleNamespace(
            team_id="team-1",
            tools_config=[{"type": "custom", "tool_id": "tool-1"}],
        ),
        user_id="deleted-user",
        min_discoverable=5,
    )
    assert state is not None
    assert "custom_payroll" not in state.catalog


@pytest.mark.asyncio
async def test_restored_selection_drops_duplicates_core_unknown_and_excess():
    tools = _mcp_catalog(30)
    names = ["mcp_calendar_server_tool_0", "mcp_calendar_server_tool_0"]
    names.append("ask_user")
    names.append("mcp_revoked_tool")
    names.extend(f"mcp_calendar_server_tool_{i}" for i in range(30))
    state = await build_tool_discovery(tools, loaded_names=names, min_discoverable=5)
    assert state is not None
    assert "ask_user" not in state.loaded
    assert "mcp_revoked_tool" not in state.loaded
    assert len(state.loaded) == len(set(state.loaded)) == 24
    assert state.loaded[0] == "mcp_calendar_server_tool_0"


@pytest.mark.asyncio
async def test_compact_results_truncate_description_and_order_parameters():
    tools = [
        _schema("ask_user", "Ask the user"),
        {
            "type": "function",
            "function": {
                "name": "mcp_ops_server_long_description",
                "description": "  " + " ".join(["detail"] * 80) + "  ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "optional": {"type": "string"},
                        "required_b": {"type": "string"},
                        "required_a": {"type": "string"},
                    },
                    "required": ["required_b", "required_a"],
                },
            },
        },
        *[_schema(f"mcp_misc_server_item_{i}", "Unrelated") for i in range(25)],
    ]
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None
    found = json.loads(
        await state.execute(
            DISCOVER_TOOLS_TOOL, {"query": "mcp_ops_server_long_description"}
        )
    )
    entry = found["tools"][0]
    assert entry["description"].endswith("…")
    assert len(entry["description"]) <= 180
    assert entry["parameters"][:2] == ["required_b", "required_a"]
    assert "optional" in entry["parameters"]


@pytest.mark.asyncio
async def test_unsupported_discovery_tool_and_undiscovered_guidance():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None

    unsupported = json.loads(await state.execute("not_a_discovery_tool", {}))
    assert "unsupported" in unsupported["error"]

    guidance = json.loads(state.undiscovered_error("mcp_calendar_server_tool_9"))
    assert guidance["success"] is False
    assert guidance["tool_name"] == "mcp_calendar_server_tool_9"
    assert "load_tools" in guidance["error"]


@pytest.mark.asyncio
async def test_agent_service_builds_discovery_only_for_large_catalogs():
    from app.services.agent import AgentService

    service = AgentService()
    small = [ToolDefinition.model_validate(schema) for schema in _mcp_catalog(3)]
    assert (
        await service._build_tool_discovery(
            small, SimpleNamespace(team_id=None, tools_config=[]), None
        )
        is None
    )

    large = [ToolDefinition.model_validate(schema) for schema in _mcp_catalog(30)]
    state = await service._build_tool_discovery(
        large, SimpleNamespace(team_id=None, tools_config=[]), None
    )
    assert state is not None
    assert all(isinstance(tool, ToolDefinition) for tool in state.meta_tools)


@pytest.mark.asyncio
async def test_workflow_dispatch_touches_called_loaded_tool(monkeypatch):
    from app.llm.types import FunctionCall, ToolCall
    from app.services import agent_tool_execution
    from app.services.agent import AgentService

    executed = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(agent_tool_execution, "execute_agent_stored_tool", executed)
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None
    state.max_loaded = 2
    first = "mcp_calendar_server_tool_0"
    second = "mcp_calendar_server_tool_1"
    third = "mcp_calendar_server_tool_2"
    await state.execute(LOAD_TOOLS_TOOL, {"names": [first, second]})

    result = await AgentService()._dispatch_tool_call(
        SimpleNamespace(id="agent-1", team_id="team-1"),
        ToolCall(id="c1", function=FunctionCall(name=first, arguments="{}")),
        tool_discovery=state,
    )
    assert result == {"ok": True}

    loaded = json.loads(await state.execute(LOAD_TOOLS_TOOL, {"names": [third]}))
    assert loaded["evicted"] == [second]
    assert state.loaded == [first, third]


@pytest.mark.asyncio
async def test_malformed_schemas_are_ignored_without_breaking_the_catalog():
    tools = [
        object(),
        {"type": "function", "function": "not-a-mapping"},
        {
            "type": "function",
            "function": {
                "name": "mcp_odd_server_tool",
                "description": None,
                "parameters": "not-a-schema",
            },
        },
        *[_schema(f"mcp_misc_server_item_{index}", "Unrelated") for index in range(25)],
    ]
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None
    assert "mcp_odd_server_tool" in state.catalog
    found = json.loads(
        await state.execute(DISCOVER_TOOLS_TOOL, {"query": "mcp_odd_server_tool"})
    )
    assert found["tools"][0]["parameters"] == []
    assert found["tools"][0]["description"] == ""


@pytest.mark.asyncio
async def test_persistence_failure_never_blocks_loading_or_unloading():
    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None

    async def _boom(names):
        raise RuntimeError("payload write failed")

    state.on_loaded_change = _boom
    loaded = json.loads(
        await state.execute(LOAD_TOOLS_TOOL, {"names": ["mcp_calendar_server_tool_0"]})
    )
    assert loaded["loaded"] == ["mcp_calendar_server_tool_0"]
    state.tools_for_turn()
    assert state.is_visible("mcp_calendar_server_tool_0") is True

    unloaded = json.loads(
        await state.execute(
            UNLOAD_TOOLS_TOOL, {"names": ["mcp_calendar_server_tool_0"]}
        )
    )
    assert unloaded["unloaded"] == ["mcp_calendar_server_tool_0"]
    state.tools_for_turn()
    assert state.is_visible("mcp_calendar_server_tool_0") is False


@pytest.mark.asyncio
async def test_single_oversized_load_keeps_the_requested_order():
    state = await build_tool_discovery(_mcp_catalog(60), min_discoverable=5)
    assert state is not None
    state.max_loaded = 24
    names = [f"mcp_calendar_server_tool_{i}" for i in range(50)]
    result = json.loads(await state.execute(LOAD_TOOLS_TOOL, {"names": names}))
    assert result["loaded"] == names[:24]
    assert result["not_loaded_limit_reached"] == names[24:]
    assert "evicted" not in result
    assert state.loaded == names[:24]
    state.tools_for_turn()
    assert state.is_visible(names[0]) is True
    assert state.is_visible(names[24]) is False


@pytest.mark.asyncio
async def test_loading_a_skill_evicts_old_tools_not_its_companions():
    tools = [
        _schema("ask_user", "Ask the user"),
        _schema("skill_data_analyst", "Analyze data in the sandbox"),
        _schema("read", "Read a sandbox file"),
        _schema("edit", "Edit a sandbox file"),
        _schema("write", "Write a sandbox file"),
        _schema("bash", "Run a sandbox command"),
        *[_schema(f"mcp_misc_server_item_{index}", "Unrelated") for index in range(25)],
    ]
    state = await build_tool_discovery(tools, min_discoverable=5)
    assert state is not None
    state.max_loaded = 5
    old = [f"mcp_misc_server_item_{index}" for index in range(5)]
    await state.execute(LOAD_TOOLS_TOOL, {"names": old})
    assert state.loaded == old

    result = json.loads(
        await state.execute(LOAD_TOOLS_TOOL, {"names": ["skill_data_analyst"]})
    )
    assert result["evicted"] == old[:1]
    assert result["loaded"] == ["skill_data_analyst"]
    state.tools_for_turn()
    for name in ("skill_data_analyst", "read", "edit", "write", "bash"):
        assert state.is_visible(name) is True


@pytest.mark.asyncio
async def test_retry_reduction_sheds_loaded_tools_and_reports_removed_names():
    persisted: list[list[str]] = []

    async def _remember(names):
        persisted.append(names)

    state = await build_tool_discovery(_mcp_catalog(25), min_discoverable=5)
    assert state is not None
    state.on_loaded_change = _remember
    loaded = [f"mcp_calendar_server_tool_{i}" for i in range(3)]
    await state.execute(LOAD_TOOLS_TOOL, {"names": loaded})
    persisted.clear()

    state.tools_for_turn()
    removed = await state.reduce_for_retry()
    assert removed == loaded
    assert state.loaded == []
    visible = [tool["function"]["name"] for tool in state.tools_for_turn()]
    assert not any(name.startswith("mcp_") for name in visible)
    # Core and discovery tools survive a retry reduction.
    assert "ask_user" in visible
    assert DISCOVER_TOOLS_TOOL in visible
    assert state.is_visible("ask_user") is True

    # Nothing left to shed: no fake reduction and no extra persistence write.
    assert persisted == [[]]


@pytest.mark.asyncio
async def test_search_bounds_primary_terms_and_matches_full_description():
    query = " ".join(f"term{index}" for index in range(30))
    expanded, primary = _search_terms(query)
    assert len(primary) == 12
    assert len(expanded) <= 24

    keyword = "distinctivecapability"
    description = "prefix " + ("ordinary description " * 20) + keyword
    state = await build_tool_discovery(
        [
            _schema(f"mcp_long_description_tool_{index}", description)
            for index in range(25)
        ],
        min_discoverable=5,
    )
    assert state is not None
    result = json.loads(await state.execute(DISCOVER_TOOLS_TOOL, {"query": keyword}))
    assert result["tools"][0]["name"] == "mcp_long_description_tool_0"
    assert len(result["tools"][0]["description"]) <= 180
