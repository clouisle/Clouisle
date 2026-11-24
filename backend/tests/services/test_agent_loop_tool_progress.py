"""Tool-call progress wiring in the shared AgentLoop.

The adapter reports progress to whatever sink the executing runtime supplies.
For an Agent run that sink must land in the run event stream, using the same
formatter the tool's call/result events already use, and it must not exist at
all on the silent (non-presentation) paths.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.tools.mcp_client import McpToolProgress
from app.llm.types import (
    ChatResponse,
    FinishReason,
    FunctionCall,
    ToolCall,
    Usage,
)
from app.services.agent_loop import (
    TOOL_PROGRESS,
    AgentLoop,
    AgentLoopContext,
    ContextTurn,
)
from app.services.tool_context import current_tool_identity


def _tool(name: str, call_id: str, arguments: str = "{}") -> ToolCall:
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments=arguments))


def _context(**overrides: object) -> AgentLoopContext:
    async def build_turn(**_kwargs: object) -> ContextTurn:
        return ContextTurn(prepared=SimpleNamespace(messages=[], compression=None))

    async def team_chat(**_kwargs: object) -> ChatResponse:
        return ChatResponse(
            id="response",
            model="model",
            content="done",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="request",
        model_id="model",
        tokenizer_model_id=None,
        model_provider="provider",
        model_context_limit=100_000,
        model_max_output_tokens=1_000,
        model_used="model",
        max_iterations=3,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        build_turn=build_turn,
        team_chat=team_chat,
        formatter=None,
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


@pytest.mark.asyncio
async def test_tool_progress_reaches_the_run_event_stream():
    events: list[tuple[str, dict[str, object]]] = []

    async def tool_runner(_name, _arguments, **_kwargs):
        sink = current_tool_identity().progress
        assert sink is not None
        await sink(McpToolProgress(progress=2.0, total=4.0, message="halfway"))
        return json.dumps({"ok": True})

    loop = AgentLoop(
        _context(
            execute_tool_call=tool_runner,
            formatter=lambda name, payload: events.append((name, payload)) or "",
        )
    )
    loop._build_tool_call_sse = lambda tc: ""  # presentation is covered elsewhere

    await loop._execute_one_tool(
        tc=_tool("mcp_docs_search", "call-1"), image_pool=[], image_inventory=[]
    )

    progress_events = [payload for name, payload in events if name == TOOL_PROGRESS]
    assert len(progress_events) == 1
    event_line, data_line = progress_events[0]["sse"].strip().splitlines()
    assert event_line.removeprefix("event: ") == TOOL_PROGRESS
    assert json.loads(data_line.removeprefix("data: ")) == {
        "tool_call_id": "call-1",
        "tool_name": "mcp_docs_search",
        "progress": 2.0,
        "total": 4.0,
        "message": "halfway",
    }


@pytest.mark.asyncio
async def test_silent_paths_get_no_progress_sink():
    seen: dict[str, object] = {}

    async def tool_runner(_name, _arguments, **_kwargs):
        seen["progress"] = current_tool_identity().progress
        return json.dumps({"ok": True})

    loop = AgentLoop(_context(execute_tool_call=tool_runner))
    loop._build_tool_call_sse = lambda tc: ""

    await loop._execute_one_tool(
        tc=_tool("mcp_docs_search", "call-2"), image_pool=[], image_inventory=[]
    )

    assert seen["progress"] is None


@pytest.mark.asyncio
async def test_progress_is_attributed_to_the_calling_tool_call():
    events: list[tuple[str, dict[str, object]]] = []

    async def tool_runner(_name, _arguments, **_kwargs):
        sink = current_tool_identity().progress
        await sink(McpToolProgress(progress=1.0))
        await sink(McpToolProgress(progress=2.0))
        return json.dumps({"ok": True})

    loop = AgentLoop(
        _context(
            execute_tool_call=tool_runner,
            formatter=lambda name, payload: events.append((name, payload)) or "",
        )
    )
    loop._build_tool_call_sse = lambda tc: ""

    await loop._execute_one_tool(
        tc=_tool("mcp_docs_search", "call-9"), image_pool=[], image_inventory=[]
    )

    payloads = [
        json.loads(payload["sse"].strip().splitlines()[1].removeprefix("data: "))
        for name, payload in events
        if name == TOOL_PROGRESS
    ]
    assert [item["tool_call_id"] for item in payloads] == ["call-9", "call-9"]
    assert [item["progress"] for item in payloads] == [1.0, 2.0]
