"""AgentLoop per-turn tool list wiring for tool discovery."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.types import (
    ChatResponse,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    MessageRole,
    ToolCall,
    Usage,
)
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn


class _Discovery:
    def __init__(self):
        self.calls = 0
        self.lists = [
            ["first-turn-tool"],
            ["first-turn-tool", "loaded-tool"],
        ]

    def tools_for_turn(self):
        index = min(self.calls, len(self.lists) - 1)
        self.calls += 1
        return list(self.lists[index])


@pytest.mark.asyncio
async def test_each_model_turn_receives_the_current_tool_list(monkeypatch):
    from app.services import agent_round

    async def _persist_step(**kwargs):
        return kwargs["round_index"] + 1

    async def _persist_result(**kwargs):
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_assistant_step", _persist_step)
    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_result)

    seen: list[list[str]] = []

    async def _provider(**kwargs):
        seen.append(list(kwargs.get("tools") or []))
        if len(seen) == 1:
            return ChatResponse(
                id="r",
                model="m",
                content="",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        function=FunctionCall(name="load_tools", arguments="{}"),
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                usage=Usage(),
            )
        return ChatResponse(
            id="r",
            model="m",
            content="done",
            tool_calls=None,
            finish_reason=FinishReason.STOP,
            usage=Usage(),
        )

    async def _tool(tool_name, arguments, **kwargs):
        return json.dumps({"loaded": ["loaded-tool"]})

    async def _build_turn(**kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[LLMMessage(role=MessageRole.USER, content="go")],
                compression=None,
            )
        )

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="go",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=3,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        team_chat=_provider,
        build_turn=_build_turn,
        execute_tool_call=_tool,
        tool_discovery=_Discovery(),
        formatter=None,
    )

    loop = AgentLoop(context)
    async for _ in loop.run():
        pass

    assert seen == [
        ["first-turn-tool"],
        ["first-turn-tool", "loaded-tool"],
    ]
    assert loop.result.full_content == "done"


@pytest.mark.asyncio
async def test_pause_resume_replays_suffix_only_from_original_response_snapshot(
    monkeypatch,
):
    from app.llm.tools.interaction import ToolInteractionRequest
    from app.services import agent_round

    async def _persist_step(**kwargs):
        return kwargs["round_index"] + 1

    async def _persist_result(**kwargs):
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_assistant_step", _persist_step)
    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_result)

    class Discovery:
        core_names = ("ask_user", "safe_core")

        def __init__(self, *, visible, turn_visible):
            self.visible = set(visible)
            self.turn_visible_names = set(turn_visible)
            self.snapshots = 0

        def tools_for_turn(self):
            self.snapshots += 1
            self.turn_visible_names = set(self.visible)
            return sorted(self.visible)

        def is_visible(self, name):
            return name in self.visible

        def undiscovered_error(self, name):
            return json.dumps(
                {"success": False, "error": f"Tool '{name}' is not loaded"}
            )

    calls = [
        ToolCall(
            id="ask-1",
            function=FunctionCall(name="ask_user", arguments="{}"),
        ),
        ToolCall(
            id="call-loaded-after-response",
            function=FunctionCall(name="newly-loaded", arguments="{}"),
        ),
    ]
    executed = []
    paused = {}

    async def _provider(**_kwargs):
        return ChatResponse(
            id="r",
            model="m",
            content="",
            tool_calls=calls,
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(),
        )

    async def _build_turn(**_kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[LLMMessage(role=MessageRole.USER, content="go")]
            )
        )

    async def _runner(name, _arguments, **_kwargs):
        executed.append(name)
        if name == "ask_user":
            return ToolInteractionRequest(
                tool_name="ask_user",
                arguments={"questions": [{"id": "q", "question": "Q?"}]},
            )
        return "ok"

    async def _pause(**kwargs):
        paused.update(kwargs)

    original_discovery = Discovery(
        visible={"ask_user", "safe_core"}, turn_visible={"ask_user", "safe_core"}
    )
    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="go",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=3,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        team_chat=_provider,
        build_turn=_build_turn,
        execute_tool_call=_runner,
        pause_for_user=_pause,
        tool_discovery=original_discovery,
        formatter=None,
    )

    first = AgentLoop(context)
    async for _ in first.run():
        pass

    assert paused["resume_tool_visible_names"] == ["ask_user", "safe_core"]
    assert executed == ["ask_user"]

    # A fresh worker rebuilds with newly loaded tools, but the pending suffix
    # remains constrained to the response's original visible schemas.
    resumed_discovery = Discovery(
        visible={"ask_user", "safe_core", "newly-loaded"},
        turn_visible={"ask_user", "safe_core", "newly-loaded"},
    )
    resumed_calls = [
        calls[1],
        ToolCall(
            id="call-originally-visible",
            function=FunctionCall(name="safe_core", arguments="{}"),
        ),
    ]
    context.tool_discovery = resumed_discovery
    context.resume_tool_calls = resumed_calls
    context.resume_tool_call_ids = {call.id for call in resumed_calls}
    context.resume_tool_visible_names = set(paused["resume_tool_visible_names"])
    context.pause_for_user = None

    async def _finish(**_kwargs):
        return ChatResponse(
            id="done",
            model="m",
            content="done",
            finish_reason=FinishReason.STOP,
            usage=Usage(),
        )

    context.team_chat = _finish
    resumed = AgentLoop(context)
    async for _ in resumed.run():
        pass

    assert executed == ["ask_user", "safe_core"]
    assert resumed_discovery.snapshots == 1  # only the next request snapshot
    assert resumed.result.waiting_for_user is False
