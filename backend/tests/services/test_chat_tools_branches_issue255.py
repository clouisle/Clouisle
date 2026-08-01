import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import execute_tool_call
from app.core.i18n import t
from app.models.tool import CustomToolType


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "handler_name", "expected_kwargs"),
    [
        (
            "create_memory_entity",
            {"name": "Ada"},
            "handle_create_entity",
            {
                "user_id": "user-1",
                "name": "Ada",
                "entity_type": "fact",
                "description": None,
                "properties": None,
            },
        ),
        (
            "create_memory_relation",
            {"source_entity_name": "Ada", "target_entity_name": "Math"},
            "handle_create_relation",
            {
                "user_id": "user-1",
                "source_entity_name": "Ada",
                "target_entity_name": "Math",
                "relation_type": "related_to",
                "description": None,
            },
        ),
        (
            "update_memory_entity",
            {"entity_name": "Ada", "description": "Pioneer"},
            "handle_update_entity",
            {
                "user_id": "user-1",
                "entity_name": "Ada",
                "description": "Pioneer",
                "properties": None,
            },
        ),
        (
            "search_memory",
            {"query": "Ada"},
            "handle_search_memory",
            {"user_id": "user-1", "query": "Ada", "top_k": 5},
        ),
    ],
)
async def test_memory_tools_require_user_and_route_arguments(
    tool_name, arguments, handler_name, expected_kwargs
):
    assert "error" in json.loads(await execute_tool_call(tool_name, arguments))

    handler = AsyncMock(return_value={"ok": True})
    with patch(f"app.services.memory.MemoryService.{handler_name}", handler):
        result = await execute_tool_call(
            tool_name, arguments, user=SimpleNamespace(id="user-1")
        )

    assert json.loads(result) == {"ok": True}
    handler.assert_awaited_once_with(**expected_kwargs)


@pytest.mark.anyio
async def test_knowledge_search_aggregates_results_and_handles_provider_error():
    knowledge_base = SimpleNamespace(
        id="kb-1",
        name="Handbook",
        embedding_model_id="embedding-1",
        rerank_model_id=None,
        team_id="team-1",
        status="active",
        settings=None,
    )
    agent_kb = SimpleNamespace(
        knowledge_base=knowledge_base,
        search_mode="hybrid",
        score_threshold=0.4,
    )
    query = MagicMock()
    query.prefetch_related = AsyncMock(return_value=[agent_kb])
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {
                    "kb_id": "kb-1",
                    "kb_name": "Handbook",
                    "document_id": uuid4(),
                    "document_name": "Guide",
                    "content": "Answer",
                    "score": 0.9,
                },
            )
        )
    )

    with (
        patch("app.models.agent.AgentKnowledgeBase.filter", return_value=query),
        patch("app.services.retrieval.retrieve", retrieve),
    ):
        result = await execute_tool_call(
            "knowledge_search",
            {"query": "policy", "top_k": 2},
            agent=SimpleNamespace(id="agent-1"),
        )

    assert json.loads(result) == {
        "contexts": [
            {
                "kb_id": "kb-1",
                "kb_name": "Handbook",
                "document_id": str(retrieve.return_value.results[0]["document_id"]),
                "document_name": "Guide",
                "content": "Answer",
                "score": 0.9,
            }
        ]
    }
    request = retrieve.await_args.args[0]
    assert request.query == "policy"
    assert request.top_k == 2
    assert len(request.targets) == 1
    assert request.targets[0].kb_id == "kb-1"
    assert request.targets[0].search_mode == "hybrid"
    assert request.targets[0].score_threshold == 0.4

    query.prefetch_related.side_effect = RuntimeError("provider unavailable")
    with patch("app.models.agent.AgentKnowledgeBase.filter", return_value=query):
        error = await execute_tool_call(
            "knowledge_search", {}, agent=SimpleNamespace(id="agent-1")
        )
    assert "error" in json.loads(error)


@pytest.mark.anyio
async def test_mcp_tool_validates_configuration_and_executes_configured_server():
    query = MagicMock()
    query.first = AsyncMock(return_value=None)
    with patch("app.models.tool.Tool.filter", return_value=query):
        missing = await execute_tool_call("mcp_docs_search", {})
    assert "error" in json.loads(missing)

    query.first.return_value = SimpleNamespace(mcp_config={"url": "https://mcp.test"})
    mcp_result = SimpleNamespace(success=True, result={"answer": 42}, error=None)
    with (
        patch("app.models.tool.Tool.filter", return_value=query),
        patch(
            "app.llm.tools.mcp_client.execute_mcp_tool",
            new=AsyncMock(return_value=mcp_result),
        ) as execute_mcp,
    ):
        result = await execute_tool_call(
            "mcp_docs_search", {"query": "answer"}, tool_timeouts={"mcp": 7}
        )

    assert json.loads(result) == {
        "success": True,
        "result": {"answer": 42},
        "error": None,
    }
    execute_mcp.assert_awaited_once_with(
        mcp_config={"url": "https://mcp.test"},
        tool_name="search",
        arguments={"query": "answer"},
        timeout=7,
    )
    assert "error" in json.loads(await execute_tool_call("mcp_invalid", {}))


@pytest.mark.anyio
async def test_custom_http_tool_returns_formatted_result_and_masks_executor_error():
    tool = SimpleNamespace(
        custom_type=CustomToolType.HTTP,
        http_config={"url": "https://api.test"},
        credentials={"token": "secret"},
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=tool)
    executor = AsyncMock(return_value={"status": 200})

    with (
        patch("app.models.tool.Tool.filter", return_value=query),
        patch("app.llm.tools.executors.execute_http_tool", executor),
        patch(
            "app.llm.tools.executors.format_http_result_for_llm",
            return_value="status: 200",
        ),
    ):
        result = await execute_tool_call(
            "custom_weather", {"city": "Paris"}, tool_timeouts={"http": 4}
        )

    assert json.loads(result) == {
        "result": {"status": 200},
        "llm_result": "status: 200",
    }
    executor.assert_awaited_once_with(
        http_config={"url": "https://api.test"},
        arguments={"city": "Paris"},
        credentials={"token": "secret"},
        timeout=4,
    )

    executor.side_effect = RuntimeError("secret provider detail")
    with (
        patch("app.models.tool.Tool.filter", return_value=query),
        patch("app.llm.tools.executors.execute_http_tool", executor),
    ):
        error = await execute_tool_call("custom_weather", {})
    assert json.loads(error) == {"error": t("tool_execution_failed")}


@pytest.mark.anyio
async def test_builtin_credentials_fall_back_from_team_to_global_configuration():
    async def handler(query, credentials=None):
        return {"query": query, "credentials": credentials}

    tool_info = SimpleNamespace(handler=handler)
    team_query = MagicMock()
    team_query.first = AsyncMock(return_value=None)
    global_query = MagicMock()
    global_query.first = AsyncMock(
        return_value=SimpleNamespace(credentials={"API_KEY": "global-key"})
    )

    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=tool_info),
        patch("app.llm.tools.tool_registry.get_sandbox_tool_class", return_value=None),
        patch(
            "app.models.tool_config.ToolConfig.filter",
            side_effect=[team_query, global_query],
        ) as tool_config_filter,
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(return_value={"ok": True}),
        ) as execute,
    ):
        result = await execute_tool_call(
            "calendar", {"query": "today"}, agent=SimpleNamespace(team_id="team-1")
        )

    assert result == {"ok": True}
    assert tool_config_filter.call_args_list == [
        call(tool_name="calendar", team_id="team-1"),
        call(tool_name="calendar", team_id=None),
    ]
    execute.assert_awaited_once_with(
        "calendar",
        {"query": "today"},
        credentials={"API_KEY": "global-key"},
        session_id=None,
        agent=SimpleNamespace(team_id="team-1"),
        user=None,
        current_images=None,
    )


@pytest.mark.anyio
async def test_missing_agent_for_skill_and_unknown_tool_return_errors():
    skill_error = json.loads(await execute_tool_call("skill_demo_12345678", {}))
    missing_error = json.loads(await execute_tool_call("does_not_exist", {}))

    assert "error" in skill_error
    assert "error" in missing_error
