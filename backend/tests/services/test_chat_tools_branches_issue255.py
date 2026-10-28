import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import execute_tool_call
from app.core.i18n import t


def _patch_policy_boundary(monkeypatch, user):
    """Run the real invoke resolver while stubbing approval persistence.

    Memory, knowledge and asset tools are executed through the stored-tool
    approval boundary. These cases exercise argument resolution, so the
    boundary runs the operation directly; the approval gate itself is
    covered by tests/services/test_tool_execution_stored_policy.py.
    """
    from app.services import builtin_tools, tool_execution

    async def execute(definition, operation, arguments, context, invoke, **kwargs):
        return await invoke(arguments, None)

    monkeypatch.setattr(tool_execution, "execute_stored_tool", execute)
    monkeypatch.setattr(
        builtin_tools,
        "get_builtin_definition",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="definition")),
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )


def _tool_agent(tool_id, tool_type):
    """Agent whose ``tools_config`` binds one stored tool."""
    return SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        tools_config=[{"type": tool_type, "tool_id": str(tool_id)}],
    )


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
            {
                "user_id": "user-1",
                "query": "Ada",
                "top_k": 5,
                "time_window_days": None,
                "entity_type": None,
            },
        ),
        (
            "search_memory",
            {
                "query": "Ada",
                "top_k": "3",
                "time_window_days": "14",
                "entity_type": "skill",
            },
            "handle_search_memory",
            {
                "user_id": "user-1",
                "query": "Ada",
                "top_k": 3,
                "time_window_days": 14,
                "entity_type": "skill",
            },
        ),
        (
            "get_memory_subgraph",
            {"entity_ids": ["entity-1"], "max_depth": "2", "direction": "incoming"},
            "handle_get_memory_subgraph",
            {
                "user_id": "user-1",
                "entity_ids": ["entity-1"],
                "max_depth": 2,
                "direction": "incoming",
                "relation_types": None,
            },
        ),
    ],
)
async def test_memory_tools_require_user_and_route_arguments(
    monkeypatch, tool_name, arguments, handler_name, expected_kwargs
):
    assert "error" in json.loads(await execute_tool_call(tool_name, arguments))

    user = SimpleNamespace(id="user-1")
    # A user without an agent cannot be authorized for the Agent's memory.
    missing_agent = await execute_tool_call(tool_name, arguments, user=user)
    assert json.loads(missing_agent) == {"error": t("agent_context_required")}

    _patch_policy_boundary(monkeypatch, user)
    handler = AsyncMock(return_value={"ok": True})
    with patch(f"app.services.memory.MemoryService.{handler_name}", handler):
        result = await execute_tool_call(
            tool_name,
            arguments,
            user=user,
            agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        )

    assert json.loads(result) == {"ok": True}
    handler.assert_awaited_once_with(**expected_kwargs)


@pytest.mark.anyio
async def test_get_memory_subgraph_accepts_exact_names_through_tool_route(monkeypatch):
    user_id = uuid4()
    project_id, feature_id = uuid4(), uuid4()
    project = SimpleNamespace(
        id=project_id,
        name="教智研一号开发项目",
        entity_type="project",
        description="project",
        properties={},
    )
    feature = SimpleNamespace(
        id=feature_id,
        name="教科院二期功能开发",
        entity_type="project",
        description="feature work",
        properties={},
    )
    named_query = MagicMock()
    named_query.all = AsyncMock(return_value=[project, feature])
    entity_filter = MagicMock(return_value=named_query)
    get_subgraph = AsyncMock(
        return_value={
            "entities": [project, feature],
            "relations": [],
            "entity_depth": {str(project_id): 0, str(feature_id): 0},
            "truncated": False,
        }
    )
    monkeypatch.setattr(
        "app.services.memory.MemoryEntity.filter",
        entity_filter,
    )
    monkeypatch.setattr(
        "app.services.memory.MemoryService.get_entity_subgraph",
        get_subgraph,
    )

    user = SimpleNamespace(id=user_id)
    _patch_policy_boundary(monkeypatch, user)
    result = await execute_tool_call(
        "get_memory_subgraph",
        {
            "entity_ids": ["教智研一号开发项目", "教科院二期功能开发"],
            "max_depth": 2,
        },
        user=user,
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
    )
    payload = json.loads(result)

    assert payload["success"] is True
    assert [entity["id"] for entity in payload["entities"]] == [
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


@pytest.mark.anyio
async def test_knowledge_search_aggregates_results_and_handles_provider_error(
    monkeypatch,
):
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

    user = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    _patch_policy_boundary(monkeypatch, user)

    with (
        patch("app.models.agent.AgentKnowledgeBase.filter", return_value=query),
        patch("app.services.retrieval.retrieve", retrieve),
    ):
        result = await execute_tool_call(
            "knowledge_search",
            {"query": "policy", "top_k": 2},
            agent=agent,
            user=user,
        )

    payload = json.loads(result)
    assert payload == {
        "contexts": [
            {
                "kb_id": "kb-1",
                "kb_name": "Handbook",
                "document_id": str(retrieve.return_value.results[0]["document_id"]),
                "document_name": "Guide",
                "content": "Answer",
                "score": 0.9,
                "citation_id": payload["contexts"][0]["citation_id"],
            }
        ]
    }
    assert payload["contexts"][0]["citation_id"].startswith("rag_")
    request = retrieve.await_args.args[0]
    assert request.query == "policy"
    assert request.top_k == 2
    assert len(request.targets) == 1
    assert request.targets[0].kb_id == "kb-1"
    assert request.targets[0].search_mode == "hybrid"
    assert request.targets[0].score_threshold == 0.4

    query.prefetch_related.side_effect = RuntimeError("provider unavailable")
    with patch("app.models.agent.AgentKnowledgeBase.filter", return_value=query):
        error = await execute_tool_call("knowledge_search", {}, agent=agent, user=user)
    assert "error" in json.loads(error)


@pytest.mark.anyio
async def test_mcp_tool_validates_configuration_and_executes_configured_server(
    monkeypatch,
):
    from app.services.tool import ToolExecutor

    # No runtime identity: stored tools fail closed instead of executing.
    assert json.loads(await execute_tool_call("mcp_docs_search", {})) == {
        "error": t("user_context_required")
    }

    tool_id = uuid4()
    tool = SimpleNamespace(id=tool_id, name="docs", display_name="Docs")
    agent = _tool_agent(tool_id, "mcp")
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )
    tool_lookup = AsyncMock(return_value=tool)
    monkeypatch.setattr("app.models.tool.Tool.get_or_none", tool_lookup)
    execute = AsyncMock(return_value={"answer": 42})
    monkeypatch.setattr(ToolExecutor, "execute", execute)

    result = await execute_tool_call(
        "mcp_docs_search", {"query": "answer"}, agent=agent, user=user
    )

    tool_lookup.assert_awaited_once_with(id=str(tool_id), is_enabled=True)
    assert json.loads(result) == {"answer": 42}
    called_tool, called_arguments = execute.await_args.args
    assert called_tool is tool
    assert called_arguments == {"query": "answer"}
    assert execute.await_args.kwargs["operation"] == "search"
    context = execute.await_args.kwargs["context"]
    assert context.team_id == agent.team_id
    assert context.actor is user

    # The Agent has no alias for this tool, so it never reaches the executor.
    unknown = json.loads(
        await execute_tool_call("mcp_unknown_tool", {}, agent=agent, user=user)
    )
    assert "error" in unknown
    assert execute.await_count == 1


@pytest.mark.anyio
async def test_custom_tool_requires_user_context_and_maps_policy_errors(monkeypatch):
    from app.schemas.response import BusinessError
    from app.services.tool import ToolExecutor

    missing_user = await execute_tool_call("custom_weather", {"city": "Paris"})
    assert json.loads(missing_user) == {"error": t("user_context_required")}

    tool_id = uuid4()
    tool = SimpleNamespace(id=tool_id, name="weather", display_name="Weather")
    agent = _tool_agent(tool_id, "custom")
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        "app.models.tool.Tool.get_or_none", AsyncMock(return_value=tool)
    )
    execute = AsyncMock(return_value={"status": 200})
    monkeypatch.setattr(ToolExecutor, "execute", execute)

    result = await execute_tool_call(
        "custom_weather", {"city": "Paris"}, agent=agent, user=user
    )

    assert json.loads(result) == {"status": 200}
    assert execute.await_args.kwargs["operation"] == "weather"

    execute.side_effect = BusinessError(
        code=403, msg_key="tool_access_denied", status_code=403
    )
    error = json.loads(
        await execute_tool_call("custom_weather", {}, agent=agent, user=user)
    )
    assert error == {"error": t("agent_tool_access_denied", tool_name="Weather")}


@pytest.mark.anyio
async def test_builtin_tools_execute_through_the_stored_tool_boundary(monkeypatch):
    from app.services.tool import ToolExecutor

    tool_info = SimpleNamespace(handler=AsyncMock())
    user = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), tools_config=[])
    execute_builtin = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("app.llm.tools.tool_registry.get_tool", lambda _name: tool_info)
    monkeypatch.setattr(
        "app.llm.tools.tool_registry.get_sandbox_tool_class", lambda _name: None
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(ToolExecutor, "execute_builtin_tool", execute_builtin)

    assert json.loads(await execute_tool_call("calendar", {}, agent=agent)) == {
        "error": t("user_context_required")
    }

    result = await execute_tool_call(
        "calendar",
        {"query": "today"},
        agent=agent,
        user=user,
        conversation_id="conversation-1",
    )

    assert result == {"ok": True}
    kwargs = execute_builtin.await_args.kwargs
    assert kwargs["tool_name"] == "calendar"
    assert kwargs["arguments"] == {"query": "today"}
    assert kwargs["team_id"] == agent.team_id
    assert kwargs["context"].actor is user
    assert kwargs["context"].team_id == agent.team_id
    assert kwargs["agent"] is agent
    assert kwargs["user"] is user
    assert kwargs["conversation_id"] == "conversation-1"


@pytest.mark.anyio
async def test_missing_agent_for_skill_and_unknown_tool_return_errors():
    skill_error = json.loads(await execute_tool_call("skill_demo_12345678", {}))
    missing_error = json.loads(await execute_tool_call("does_not_exist", {}))

    assert "error" in skill_error
    assert "error" in missing_error
