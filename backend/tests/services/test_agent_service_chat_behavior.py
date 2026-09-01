import builtins
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.types import FunctionCall, MessageRole, ToolCall, ToolDefinition
from app.models.agent import RAGMode

# ToolCall is currently evaluated from a TYPE_CHECKING-only import in agent.py.
builtins.ToolCall = ToolCall
AgentService = importlib.import_module("app.services.agent").AgentService
del builtins.ToolCall


@pytest.mark.anyio
async def test_chat_executes_tool_then_aggregates_final_response_usage():
    agent = SimpleNamespace(team_id=None, model_id=None)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="search", arguments="{}"),
    )
    first_response = SimpleNamespace(
        content="I will search.",
        tool_calls=[tool_call],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )
    final_response = SimpleNamespace(
        content="The answer.",
        tool_calls=[],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=4, total_tokens=11),
    )
    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])
    service._execute_tool = AsyncMock(return_value={"results": ["match"]})

    with patch(
        "app.services.agent.model_manager.chat",
        new=AsyncMock(side_effect=[first_response, final_response]),
    ) as chat:
        result = await service.chat(agent, "Find it", user_id="user-1")

    assert result == {
        "response": "The answer.",
        "tool_calls": [tool_call.model_dump()],
        "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
        "dialogue": [
            {
                "role": "assistant",
                "content": "I will search.",
                "reasoning_content": None,
                "tool_calls": [tool_call.model_dump()],
                "iteration": 1,
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "tool_name": "search",
                "content": "{'results': ['match']}",
                "iteration": 1,
            },
            {
                "role": "assistant",
                "content": "The answer.",
                "reasoning_content": None,
                "iteration": 2,
            },
        ],
        "artifacts": [],
    }
    assert chat.await_count == 2
    second_messages = chat.await_args_list[1].kwargs["messages"]
    assert [(message.role, message.content) for message in second_messages] == [
        ("assistant", "I will search."),
        ("tool", "{'results': ['match']}"),
    ]
    service._execute_tool.assert_awaited_once_with(agent=agent, tool_call=tool_call)


@pytest.mark.anyio
async def test_chat_resolves_configured_team_model_before_invocation():
    agent = SimpleNamespace(team_id="team-1", model_id="team-model")
    response = SimpleNamespace(content="Done", tool_calls=[], usage=None)
    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])

    with (
        patch(
            "app.models.model.TeamModel.filter",
            return_value=SimpleNamespace(
                first=AsyncMock(return_value=SimpleNamespace(model_id="model-1"))
            ),
        ),
        patch(
            "app.services.agent.model_manager.team_chat",
            new=AsyncMock(return_value=response),
        ) as team_chat,
    ):
        result = await service.chat(agent, "Find it", user_id="user-1")

    assert result["response"] == "Done"
    team_chat.assert_awaited_once_with(
        team_id="team-1", messages=[], tools=None, model_id="model-1", user_id="user-1"
    )


@pytest.mark.anyio
async def test_build_messages_uses_images_and_parsed_files_for_enabled_agent():
    agent = SimpleNamespace(
        system_prompt="",
        rag_mode=RAGMode.OFF,
        enable_attachments=True,
        attachment_config={},
        model_id=None,
    )
    service = AgentService()
    service._parse_workflow_files = AsyncMock(return_value="file contents")

    messages = await service._build_messages(
        agent,
        "Summarize",
        images=[{"url": "https://example.test/image.png", "asset_ref": "image-ref"}],
        files=[{"url": "https://example.test/report.pdf"}],
    )

    content = messages[-1].content
    assert isinstance(content, list)
    assert content[0].text == "Summarize"
    assert content[1].image.url == "https://example.test/image.png"
    assert content[1].image.asset_ref == "image-ref"
    assert content[2].text == "<uploaded_files>\nfile contents\n</uploaded_files>"
    service._parse_workflow_files.assert_awaited_once_with(
        agent, [{"url": "https://example.test/report.pdf"}]
    )


@pytest.mark.anyio
async def test_chat_stream_yields_content_tool_calls_usage_and_final_response():
    agent = SimpleNamespace(team_id=None, model_id=None)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="search", arguments="{}"),
    )
    usage = SimpleNamespace(model_dump=lambda: {"total_tokens": 5})
    turns = [
        [
            SimpleNamespace(
                delta=SimpleNamespace(content="Searching", tool_calls=[tool_call]),
                usage=usage,
            )
        ],
        [
            SimpleNamespace(
                delta=SimpleNamespace(content="Done", tool_calls=[]), usage=None
            )
        ],
    ]

    async def chat_stream(**kwargs):
        for chunk in turns.pop(0):
            yield chunk

    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])
    service._execute_tool = AsyncMock(return_value={"results": ["match"]})

    with patch("app.services.agent.model_manager.chat_stream", new=chat_stream):
        events = [event async for event in service.chat_stream(agent, "Find it")]

    assert events == [
        "Searching",
        {"tool_call": tool_call.model_dump()},
        {"usage": {"total_tokens": 5}},
        {
            "tool_result": {
                "tool_call_id": "call-1",
                "tool_name": "search",
                "result": {"results": ["match"]},
            }
        },
        "Done",
        {
            "dialogue": [
                {
                    "role": "assistant",
                    "content": "Searching",
                    "reasoning_content": None,
                    "tool_calls": [tool_call.model_dump()],
                    "iteration": 1,
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "tool_name": "search",
                    "content": "{'results': ['match']}",
                    "iteration": 1,
                },
                {
                    "role": "assistant",
                    "content": "Done",
                    "reasoning_content": None,
                    "iteration": 2,
                },
            ],
            "artifacts": [],
        },
    ]
    service._execute_tool.assert_awaited_once_with(agent=agent, tool_call=tool_call)


@pytest.mark.anyio
async def test_chat_stream_emits_dialogue_when_tool_limit_is_reached():
    agent = SimpleNamespace(team_id=None, model_id=None)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="search", arguments="{}"),
    )

    async def chat_stream(**_kwargs):
        yield SimpleNamespace(
            delta=SimpleNamespace(content="", tool_calls=[tool_call]), usage=None
        )

    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])
    service._execute_tool = AsyncMock(return_value={"files": [{"url": "output.csv"}]})

    with patch("app.services.agent.model_manager.chat_stream", new=chat_stream):
        events = [
            event async for event in service.chat_stream(agent, "Find it", max_turns=1)
        ]

    assert events[-1] == {
        "dialogue": [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": None,
                "tool_calls": [tool_call.model_dump()],
                "iteration": 1,
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "tool_name": "search",
                "content": "{'files': [{'url': 'output.csv'}]}",
                "iteration": 1,
            },
        ],
        "artifacts": [{"url": "output.csv"}],
    }


@pytest.mark.anyio
async def test_build_messages_adds_context_history_and_rag_before_current_message():
    agent = SimpleNamespace(system_prompt="Be concise", rag_mode=RAGMode.AUTO)
    service = AgentService()
    service._retrieve_rag_context = AsyncMock(return_value="Trusted context")

    messages = await service._build_messages(
        agent,
        "Current question",
        context={"region": "EU"},
        conversation_history=[
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "system", "content": "Additional rule"},
            {"role": "ignored", "content": "Do not include"},
        ],
    )

    pairs = [(message.role, message.content) for message in messages]
    # Workflow mode injects Markdown/language guidance into the system prompt.
    assert pairs[0][0] is MessageRole.SYSTEM
    assert pairs[0][1].startswith("Be concise\n\nContext:\n- region: EU")
    assert "## Markdown Output" in pairs[0][1]
    assert pairs[1:] == [
        (MessageRole.USER, "Earlier question"),
        (MessageRole.ASSISTANT, "Earlier answer"),
        (MessageRole.SYSTEM, "Additional rule"),
        (MessageRole.SYSTEM, "Relevant context:\nTrusted context"),
        (MessageRole.USER, "Current question"),
    ]
    service._retrieve_rag_context.assert_awaited_once_with(agent, "Current question")


@pytest.mark.anyio
async def test_execute_tool_rejects_invalid_arguments_and_unknown_tools():
    service = AgentService()
    agent = SimpleNamespace(id="agent-1", team_id=None)
    invalid = ToolCall(
        id="call-invalid",
        function=FunctionCall(name="search", arguments="not-json"),
    )
    missing = ToolCall(
        id="call-missing",
        function=FunctionCall(name="missing", arguments="{}"),
    )

    invalid_result = await service._execute_tool(agent, invalid)
    with patch("app.llm.tools.tool_registry.get_tool", return_value=None):
        missing_result = await service._execute_tool(agent, missing)

    assert invalid_result == {"error": "Invalid tool arguments"}
    assert missing_result == {
        "error": "Tool not found",
        "tool_name": "missing",
        "success": False,
    }


@pytest.mark.anyio
async def test_execute_tool_uses_team_credentials_and_reports_execution_errors():
    service = AgentService()
    agent = SimpleNamespace(id="agent-1", team_id="team-1")
    tool_call = ToolCall(
        id="call-search",
        function=FunctionCall(name="search", arguments='{"query": "docs"}'),
    )
    config_query = SimpleNamespace(
        first=AsyncMock(
            return_value=SimpleNamespace(credentials={"TEST_API_KEY": "mock-key"})
        )
    )

    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=object()),
        patch("app.models.tool_config.ToolConfig.filter", return_value=config_query),
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(side_effect=[{"results": ["match"]}, RuntimeError("failed")]),
        ) as execute,
    ):
        success = await service._execute_tool(agent, tool_call)
        failure = await service._execute_tool(agent, tool_call)

    assert success == {"results": ["match"]}
    assert failure == {"error": "failed", "success": False}
    assert execute.await_args_list[0].kwargs == {
        "name": "search",
        "arguments": {"query": "docs"},
        "credentials": {"TEST_API_KEY": "mock-key"},
        "agent": agent,
        "team_id": "team-1",
    }


@pytest.mark.anyio
async def test_execute_skill_tool_returns_results_and_safe_errors():
    service = AgentService()
    agent = SimpleNamespace(id="agent-1", team_id="team-1")
    tool_call = ToolCall(
        id="call-skill",
        function=FunctionCall(name="skill_summarize", arguments='{"text": "docs"}'),
    )
    skill = SimpleNamespace(id="skill-1")
    config = SimpleNamespace()

    with (
        patch(
            "app.services.skill.SkillService.resolve_agent_skill_tool",
            new=AsyncMock(side_effect=[(skill, config), RuntimeError("unavailable")]),
        ),
        patch(
            "app.services.skill_executor.SkillExecutor.execute",
            new=AsyncMock(
                return_value=SimpleNamespace(to_dict=lambda: {"summary": "done"})
            ),
        ) as execute,
    ):
        success = await service._execute_tool(agent, tool_call)
        failure = await service._execute_tool(agent, tool_call)

    assert success == {"summary": "done"}
    assert failure == {"error": "unavailable"}
    execute.assert_awaited_once_with(
        skill=skill,
        arguments={"text": "docs"},
        config=config,
        tenant_id="team-1",
    )


@pytest.mark.anyio
async def test_retrieve_rag_context_sorts_results_and_tolerates_failures():
    class Query:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return [
                    SimpleNamespace(knowledge_base=None),
                    SimpleNamespace(
                        knowledge_base=SimpleNamespace(
                            id="kb-1",
                            name="Guides",
                            embedding_model_id=None,
                            rerank_model_id=None,
                            team_id="team-1",
                            status="active",
                            settings=None,
                        ),
                        search_mode="hybrid",
                        retrieval_top_k=2,
                        score_threshold=0.5,
                    ),
                ]

            return resolve().__await__()

    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {"kb_name": "Guides", "content": "Higher", "score": 0.9},
                {"kb_name": "Guides", "content": "Lower", "score": 0.6},
            )
        )
    )
    service = AgentService()
    agent = SimpleNamespace(id="agent-1")

    with (
        patch("app.services.agent.AgentKnowledgeBase.filter", return_value=Query()),
        patch("app.services.retrieval.retrieve", retrieve),
    ):
        result = await service._retrieve_rag_context(agent, "setup")

    assert result == "[Guides] Higher\n\n[Guides] Lower"
    request = retrieve.await_args.args[0]
    assert request.query == "setup"
    assert request.targets[0].search_mode == "hybrid"
    assert request.targets[0].top_k == 2
    assert request.targets[0].score_threshold == 0.5

    with patch(
        "app.services.agent.AgentKnowledgeBase.filter",
        side_effect=RuntimeError("unavailable"),
    ):
        assert await service._retrieve_rag_context(agent, "setup") is None


@pytest.mark.anyio
async def test_agent_tools_include_available_builtin_media_and_agentic_search():
    agent = SimpleNamespace(
        tools_config=[
            {"type": "builtin", "name": "web_search"},
            {"type": "builtin", "name": "missing"},
            {"type": "mcp", "name": "future"},
        ],
        enable_image_generation=True,
        enable_video_generation=False,
        rag_mode=RAGMode.AGENTIC,
    )
    builtin = ToolDefinition(
        type="function",
        function={
            "name": "web_search",
            "description": "Search",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    service = AgentService()
    service._get_builtin_tool = lambda name: (
        builtin if name in {"web_search", "generate_image"} else None
    )

    tools = await service._get_agent_tools(agent)

    assert [tool.function.name for tool in tools] == [
        "web_search",
        "web_search",
        "search_knowledge_base",
    ]


@pytest.mark.anyio
async def test_chat_stream_emits_reasoning_deltas():
    agent = SimpleNamespace(team_id=None, model_id=None)

    async def chat_stream(**_kwargs):
        yield SimpleNamespace(
            delta=SimpleNamespace(
                content="", reasoning_content="thinking", tool_calls=[]
            ),
            usage=None,
        )

    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])

    with patch("app.services.agent.model_manager.chat_stream", new=chat_stream):
        events = [event async for event in service.chat_stream(agent, "Question")]

    assert events == [
        {"reasoning": "thinking"},
        {
            "dialogue": [
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "thinking",
                    "iteration": 1,
                }
            ],
            "artifacts": [],
        },
    ]


@pytest.mark.anyio
async def test_build_messages_handles_image_only_content_and_empty_rag_context():
    agent = SimpleNamespace(
        system_prompt="",
        rag_mode=RAGMode.AUTO,
        enable_attachments=False,
    )
    service = AgentService()
    service._retrieve_rag_context = AsyncMock(return_value=None)

    with patch("app.services.agent.build_system_prompt", return_value=""):
        messages = await service._build_messages(
            agent,
            "Question",
            images=[{"url": ""}, "https://example.test/image"],
        )

    assert len(messages) == 1
    assert messages[0].role is MessageRole.USER
    assert [part.image.url for part in messages[0].content[1:]] == [
        "https://example.test/image"
    ]
    service._retrieve_rag_context.assert_awaited_once_with(agent, "Question")


@pytest.mark.anyio
async def test_parse_workflow_files_handles_urls_and_empty_inputs():
    disabled_agent = SimpleNamespace(enable_attachments=False)
    assert (
        await AgentService._parse_workflow_files(
            disabled_agent, [{"url": "https://example.test/ignored"}]
        )
        == ""
    )

    enabled_agent = SimpleNamespace(
        enable_attachments=True,
        attachment_config={"max_content_length": "42", "truncate_strategy": "start"},
    )
    parse_files = AsyncMock(return_value="parsed")
    with patch("app.llm.tools.builtin.file_parser.parse_files", parse_files):
        parsed = await AgentService._parse_workflow_files(
            enabled_agent,
            [
                {"url": "https://example.test/one"},
                {"name": "missing-url"},
                "",
                {"url": "https://example.test/two"},
            ],
        )
        empty = await AgentService._parse_workflow_files(enabled_agent, [None, ""])

    assert parsed == "parsed"
    assert empty == ""
    parse_files.assert_awaited_once_with(
        [
            "https://example.test/one",
            "{'name': 'missing-url'}",
            "https://example.test/two",
        ],
        max_content_length=42,
        truncate_strategy="start",
    )


@pytest.mark.anyio
async def test_agent_tools_skip_missing_skill_and_add_video_tool():
    builtin = ToolDefinition(
        type="function",
        function={
            "name": "generate_video",
            "description": "Generate video",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    agent = SimpleNamespace(
        team_id="team-1",
        tools_config=[
            {"type": "skill"},
            {"type": "skill", "skill_id": "skill-1"},
            {"type": "builtin", "name": "missing"},
        ],
        enable_image_generation=False,
        enable_video_generation=True,
        rag_mode=RAGMode.OFF,
    )
    service = AgentService()
    service._get_builtin_tool = lambda name: (
        builtin if name == "generate_video" else None
    )

    with patch(
        "app.services.skill.SkillService.get_skill_for_team",
        new=AsyncMock(side_effect=RuntimeError("unavailable")),
    ):
        tools = await service._get_agent_tools(agent)

    assert tools == [builtin]


@pytest.mark.anyio
async def test_execute_tool_falls_back_to_empty_global_credentials():
    service = AgentService()
    agent = SimpleNamespace(id="agent-1", team_id=None)
    tool_call = ToolCall(
        id="call-search",
        function=FunctionCall(name="search", arguments="{}"),
    )
    config_query = SimpleNamespace(first=AsyncMock(return_value=None))

    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=object()),
        patch("app.models.tool_config.ToolConfig.filter", return_value=config_query),
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(return_value={"ok": True}),
        ) as execute,
    ):
        result = await service._execute_tool(agent, tool_call)

    assert result == {"ok": True}
    execute.assert_awaited_once_with(
        name="search",
        arguments={},
        credentials={},
        agent=agent,
        team_id=None,
    )


def test_extract_artifacts_handles_nested_and_non_mapping_values():
    assert AgentService._extract_artifacts("plain") == []
    assert AgentService._extract_artifacts(
        {
            "artifacts": [{"name": "top"}, "ignored"],
            "display_result": {"files": [{"name": "nested"}]},
        }
    ) == [{"name": "top"}, {"name": "nested"}]


def test_get_builtin_tool_handles_empty_and_valid_registry_results():
    service = AgentService()
    with patch("app.llm.tools.tool_registry.to_openai_tools", return_value=[]):
        assert service._get_builtin_tool("missing") is None

    definition = {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    with patch(
        "app.llm.tools.tool_registry.to_openai_tools", return_value=[definition]
    ):
        tool = service._get_builtin_tool("search")

    assert tool is not None
    assert tool.function.name == "search"
