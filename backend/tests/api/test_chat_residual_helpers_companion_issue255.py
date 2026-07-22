from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import (
    MessageRole,
    MessageRoundRole,
    MessageRoundStatus,
    RAGMode,
)


class Query:
    def __init__(self, *, first=None, items=None, exists=False):
        self.first_value = first
        self.items = items or []
        self.exists_value = exists

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def exists(self):
        return self.exists_value

    def __await__(self):
        async def result():
            return self.items

        return result().__await__()


class SavedMessage(SimpleNamespace):
    async def save(self, **_kwargs):
        self.saved = True


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (Exception("plain"), "plain"),
        (Exception("prefix - not a literal"), "prefix - not a literal"),
        (
            Exception("prefix - {'error': {'message': 'provider failed'}}"),
            "provider failed",
        ),
        (
            Exception("prefix - {'error': {'message': ''}}"),
            "prefix - {'error': {'message': ''}}",
        ),
    ],
)
def test_llm_error_extraction_residual_shapes(error, expected):
    assert chat._extract_llm_error_message(error) == expected


def test_llm_error_format_uses_i18n_fallback_and_provider_message(monkeypatch):
    monkeypatch.setattr(chat, "t", lambda key, **values: (key, values))

    assert chat._format_llm_error_message(Exception()) == ("model_call_failed", {})
    assert chat._format_llm_error_message(Exception("bad")) == (
        "model_service_request_failed",
        {"message": "bad"},
    )


@pytest.mark.asyncio
async def test_partial_round_error_skips_absent_and_empty_messages(monkeypatch):
    assert not await chat.persist_partial_round_error(
        None, content="x", reasoning="", model_id=None, start_time=1
    )

    monkeypatch.setattr(
        chat, "round_has_persisted_trace", AsyncMock(return_value=False)
    )
    message = SavedMessage(round_id=uuid4())
    assert not await chat.persist_partial_round_error(
        message, content="", reasoning="", model_id=None, start_time=1
    )
    assert not hasattr(message, "saved")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "reasoning", "fallback", "expected_content", "expected_reasoning"),
    [
        ("answer", "thought", "fallback", "answer", "thought"),
        ("", "", "fallback", "fallback", None),
        ("", "thought", None, "", "thought"),
    ],
)
async def test_partial_round_error_persists_each_progress_source(
    monkeypatch, content, reasoning, fallback, expected_content, expected_reasoning
):
    monkeypatch.setattr(chat.time, "time", lambda: 3.0)
    monkeypatch.setattr(chat, "now_utc", lambda: "now")
    monkeypatch.setattr(chat, "round_has_persisted_trace", AsyncMock(return_value=True))
    message = SavedMessage(round_id=uuid4())

    assert await chat.persist_partial_round_error(
        message,
        content=content,
        reasoning=reasoning,
        model_id="provider/model",
        start_time=1.0,
        first_token_time=2.0,
        fallback_content=fallback,
    )
    assert message.content == expected_content
    assert message.reasoning_content == expected_reasoning
    assert message.first_token_ms == 1000
    assert message.duration_ms == 2000
    assert message.round_status == MessageRoundStatus.ERROR
    assert message.saved


def test_round_status_and_history_optional_fields():
    assert (
        chat.get_round_terminal_status(completed=True) == MessageRoundStatus.COMPLETED
    )
    assert chat.get_round_terminal_status(completed=False) == MessageRoundStatus.ERROR
    assert (
        chat.get_round_terminal_status(completed=True, errored=True)
        == MessageRoundStatus.ERROR
    )
    assert (
        chat.get_round_terminal_status(completed=True, max_iterations_reached=True)
        == MessageRoundStatus.MAX_ITERATIONS_REACHED
    )
    assert (
        chat.get_round_terminal_status(
            completed=True, manually_stopped=True, max_iterations_reached=True
        )
        == MessageRoundStatus.MANUALLY_STOPPED
    )

    history = []
    round_id = uuid4()
    chat.append_round_history_entry(
        history,
        role="tool",
        content="result",
        round_id=round_id,
        round_index=2,
        round_role="tool_result",
        is_round_canonical=False,
        iteration_index=1,
        round_status="error",
        reasoning_content="why",
        tool_calls=[],
        tool_call_id="call-1",
        tool_name="search",
    )
    assert history == [
        {
            "role": "tool",
            "content": "result",
            "round_id": str(round_id),
            "round_index": 2,
            "round_role": "tool_result",
            "is_round_canonical": False,
            "iteration_index": 1,
            "round_status": "error",
            "reasoning_content": "why",
            "tool_calls": [],
            "tool_call_id": "call-1",
            "tool_name": "search",
        }
    ]


@pytest.mark.asyncio
async def test_round_steps_map_groups_only_steps_with_round_ids(monkeypatch):
    conversation_id = uuid4()
    round_id = uuid4()
    canonical = SimpleNamespace(
        conversation_id=conversation_id, round_id=round_id, is_round_canonical=True
    )
    step = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation_id,
        round_id=round_id,
        is_round_canonical=False,
        role=MessageRole.TOOL,
        content="result",
        tool_calls=None,
        tool_call_id="call-1",
        tool_name="search",
        reasoning_content=None,
        model_used=None,
        token_usage=None,
        duration_ms=None,
        is_manually_stopped=False,
        rag_context=None,
        created_at="now",
        round_index=1,
        round_role=MessageRoundRole.TOOL_RESULT,
        iteration_index=1,
        round_status=None,
    )
    no_round = SimpleNamespace(**{**step.__dict__, "round_id": None})

    query = SimpleNamespace(
        order_by=lambda *_args: SimpleNamespace(
            all=AsyncMock(return_value=[step, no_round])
        )
    )
    monkeypatch.setattr(chat.Message, "filter", lambda **_kwargs: query)

    grouped = await chat.build_round_steps_map([canonical])
    assert grouped[round_id][0]["role"] == "tool"
    assert grouped[round_id][0]["round_role"] == "tool_result"
    assert grouped[round_id][0]["round_status"] is None
    assert (
        await chat.build_round_steps_map(
            [SimpleNamespace(round_id=None, is_round_canonical=True)]
        )
        == {}
    )


@pytest.mark.asyncio
async def test_get_agent_tools_covers_memory_rag_builtin_custom_skill_and_mcp(
    monkeypatch,
):
    memory_module = __import__(
        "app.llm.tools.memory_tools", fromlist=["get_memory_tools"]
    )
    monkeypatch.setattr(
        memory_module,
        "get_memory_tools",
        lambda: [
            {
                "name": "create_memory_entity",
                "description": "create",
                "input_schema": {},
            },
            {"name": "search_memory", "description": "search", "input_schema": {}},
        ],
    )
    monkeypatch.setattr(
        chat.AgentKnowledgeBase,
        "filter",
        lambda **_kwargs: Query(
            items=[
                SimpleNamespace(
                    knowledge_base=SimpleNamespace(name="Docs", description="Internal")
                ),
                SimpleNamespace(
                    knowledge_base=SimpleNamespace(name="FAQ", description=None)
                ),
            ]
        ),
    )

    custom = SimpleNamespace(
        name="weather",
        description="Weather",
        parameters=[
            {"name": "city", "required": True},
            {"name": "units", "type": "string", "description": "Units"},
        ],
    )
    mcp = SimpleNamespace(name="server", mcp_config={"url": "mcp"})
    tool_module = __import__("app.models.tool", fromlist=["Tool"])
    monkeypatch.setattr(
        tool_module.Tool,
        "filter",
        lambda **kwargs: Query(first={"custom": custom, "mcp": mcp}.get(kwargs["id"])),
    )

    skill_module = __import__("app.services.skill", fromlist=["SkillService"])
    skill_schema = {
        "type": "function",
        "function": {"name": "skill_report", "description": "Report", "parameters": {}},
    }
    skill = SimpleNamespace()
    monkeypatch.setattr(
        skill_module.SkillService,
        "get_skill_for_team",
        AsyncMock(side_effect=[skill, RuntimeError("disabled")]),
    )
    monkeypatch.setattr(
        skill_module.SkillService,
        "to_tool_info",
        lambda _skill: SimpleNamespace(to_openai_schema=lambda: skill_schema),
    )

    mcp_module = __import__("app.llm.tools.mcp_client", fromlist=["list_mcp_tools"])
    monkeypatch.setattr(
        mcp_module,
        "list_mcp_tools",
        AsyncMock(
            return_value=[
                SimpleNamespace(name="lookup", description=None, parameters=None)
            ]
        ),
    )
    monkeypatch.setattr(
        chat.tool_registry,
        "to_openai_tools",
        lambda names: [
            {
                "type": "function",
                "function": {
                    "name": names[0],
                    "description": names[0],
                    "parameters": {},
                },
            }
        ],
    )
    monkeypatch.setattr(
        chat.tool_registry,
        "to_openai_sandbox_tools",
        lambda names: [
            {
                "type": "function",
                "function": {"name": name, "description": name, "parameters": {}},
            }
            for name in names
        ],
    )

    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        enable_memory=True,
        memory_config={"auto_extract": False},
        rag_mode=RAGMode.AGENTIC,
        enable_image_generation=True,
        enable_video_generation=True,
        tools_config=[
            {"type": "builtin"},
            {"type": "builtin", "name": "clock"},
            {"type": "custom", "tool_id": "missing"},
            {"type": "custom", "tool_id": "custom"},
            {"type": "skill", "skill_id": "good"},
            {"type": "skill", "skill_id": "bad"},
            {"type": "mcp", "server_id": "mcp"},
        ],
    )

    tools = await chat.get_agent_tools(agent)
    by_name = {tool["function"]["name"]: tool for tool in tools}
    assert "create_memory_entity" not in by_name
    assert {
        "search_memory",
        "knowledge_search",
        "generate_image",
        "generate_video",
        "clock",
        "custom_weather",
        "skill_report",
        "read",
        "write",
        "bash",
        "mcp_server_lookup",
    } <= by_name.keys()
    assert by_name["custom_weather"]["function"]["parameters"]["required"] == ["city"]
    assert by_name["mcp_server_lookup"]["function"]["parameters"]["required"] == []
