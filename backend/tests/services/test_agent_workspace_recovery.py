"""Workspace loss stays in the durable tool protocol and the Agent can replan."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.types import (
    ChatResponse,
    FinishReason,
    FunctionCall,
    Message,
    ToolCall,
    Usage,
)
from app.services import agent_round
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn
from app.services.sandbox.recovery import record_workspace_reset


def _context(**overrides):
    values = dict(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        model_id="model",
        tokenizer_model_id=None,
        model_provider="provider",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="model",
        sandbox_session_id=str(uuid4()),
        user_message="Recreate the report if its workspace is lost.",
        max_iterations=8,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
    )
    values.update(overrides)
    return AgentLoopContext(**values)


def _call(name, call_id, arguments=None):
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments=json.dumps(arguments or {})),
    )


def _response(*, calls=None, content=""):
    return ChatResponse(
        id="response",
        model="model",
        content=content,
        tool_calls=calls,
        finish_reason=FinishReason.TOOL_CALLS if calls else FinishReason.STOP,
        usage=Usage(prompt_tokens=4, completion_tokens=2, total_tokens=6),
    )


def _notice():
    return {
        "code": "WORKSPACE_RESET",
        "generation": 1,
        "message": "Old files, paths, edit snapshots and process handles are unavailable. "
        "Rebuild required files or rematerialize authorized assets; do not replay "
        "commands whose outcome is uncertain.",
    }


@pytest.mark.asyncio
async def test_agent_replans_after_workspace_reset_and_persists_notice(monkeypatch):
    persisted = []
    files = {"report.txt": "old report"}
    calls = []
    provider_turn = 0

    async def persist_step(**kwargs):
        return kwargs["round_index"]

    async def persist_result(**kwargs):
        persisted.append(kwargs)
        return kwargs["round_index"]

    monkeypatch.setattr(agent_round, "persist_assistant_step", persist_step)
    monkeypatch.setattr(agent_round, "persist_tool_result", persist_result)

    async def tool(name, arguments, **kwargs):
        calls.append(name)
        if len(calls) == 1:
            files.clear()
            record_workspace_reset(_notice())
            # Existing tool wrappers may consume the recovery exception.
            return {"success": False, "error": "Workspace reset before execution"}
        if name == "write":
            files[arguments["path"]] = arguments["content"]
            return {"success": True}
        return {"success": True, "content": files[arguments["path"]]}

    async def provider(**kwargs):
        nonlocal provider_turn
        provider_turn += 1
        if provider_turn == 1:
            return _response(calls=[_call("read", "read-old", {"path": "report.txt"})])
        history = kwargs["messages"]
        results = [entry for entry in history if entry.get("role") == "tool"]
        if provider_turn == 2:
            result = json.loads(results[-1]["content"])
            assert result["workspace_reset"]["generation"] == 1
            assert result["success"] is False
            return _response(
                calls=[
                    _call(
                        "write",
                        "rebuild",
                        {"path": "report.txt", "content": "rebuilt report"},
                    )
                ]
            )
        if provider_turn == 3:
            return _response(calls=[_call("read", "read-new", {"path": "report.txt"})])
        assert json.loads(results[-1]["content"])["content"] == "rebuilt report"
        return _response(content="Report rebuilt in the new workspace.")

    async def build_turn(**kwargs):
        messages = []
        for entry in kwargs["history_override"]:
            tool_calls = []
            for call in entry.get("tool_calls") or []:
                arguments = call.get("arguments", {})
                tool_calls.append(
                    ToolCall(
                        id=call["id"],
                        function=FunctionCall(
                            name=call["name"],
                            arguments=arguments
                            if isinstance(arguments, str)
                            else json.dumps(arguments),
                        ),
                    )
                )
            messages.append(
                Message(
                    role=entry["role"],
                    content=entry.get("content"),
                    reasoning_content=entry.get("reasoning_content"),
                    name=entry.get("tool_name"),
                    tool_call_id=entry.get("tool_call_id"),
                    tool_calls=tool_calls or None,
                )
            )
        return ContextTurn(prepared=SimpleNamespace(messages=messages))

    context = _context(
        team_chat=provider, build_turn=build_turn, execute_tool_call=tool
    )
    loop = AgentLoop(context)
    async for _ in loop.run():
        pass

    assert calls == ["read", "write", "read"]
    assert loop.result.full_content == "Report rebuilt in the new workspace."
    assert loop.result.max_iterations_reached is False
    first = persisted[0]
    assert json.loads(first["content"])["workspace_reset"]["code"] == "WORKSPACE_RESET"
    assert "workspace_reset" not in json.loads(persisted[1]["content"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output", ["plain tool output", '["a", "b"]', {"error": "uncertain"}]
)
async def test_reset_notice_preserves_non_object_results_and_existing_error(output):
    async def tool(*args, **kwargs):
        record_workspace_reset(_notice())
        return output

    loop = AgentLoop(_context(execute_tool_call=tool))
    _, _, _, record = await loop._execute_one_tool(
        tc=_call("read", "call"), image_pool=[], image_inventory=[]
    )
    displayed = json.loads(record["display_result"])
    provider_payload = json.loads(record["llm_result"])
    assert displayed["workspace_reset"]["generation"] == 1
    assert provider_payload["workspace_reset"]["code"] == "WORKSPACE_RESET"
    if isinstance(output, dict):
        assert provider_payload["error"] == "uncertain"
    elif output.startswith("["):
        assert provider_payload["result"] == ["a", "b"]
    else:
        assert provider_payload["result"] == output


@pytest.mark.asyncio
async def test_reset_notice_survives_tool_exception_and_does_not_leak_to_siblings():
    async def tool(name, *args, **kwargs):
        if name == "lost":
            record_workspace_reset(_notice())
            raise RuntimeError("Execution outcome is uncertain")
        return {"content": "unrelated result"}

    loop = AgentLoop(_context(execute_tool_call=tool))
    _, _, _, failed = await loop._execute_one_tool(
        tc=_call("lost", "lost"), image_pool=[], image_inventory=[]
    )
    _, _, _, sibling = await loop._execute_one_tool(
        tc=_call("healthy", "healthy"), image_pool=[], image_inventory=[]
    )
    failure = json.loads(failed["llm_result"])
    assert failure["error"] == "Execution outcome is uncertain"
    assert failure["workspace_reset"]["generation"] == 1
    assert json.loads(sibling["llm_result"]) == {"content": "unrelated result"}


@pytest.mark.asyncio
async def test_concurrent_tool_reset_notice_is_isolated_from_healthy_call():
    reset_recorded = asyncio.Event()
    sibling_finished = asyncio.Event()

    async def tool(name, *args, **kwargs):
        if name == "lost":
            record_workspace_reset(_notice())
            reset_recorded.set()
            await sibling_finished.wait()
            return {"error": "old workspace unavailable"}
        await reset_recorded.wait()
        sibling_finished.set()
        return {"content": "healthy result"}

    loop = AgentLoop(_context(execute_tool_call=tool))
    failed, healthy = await asyncio.gather(
        loop._execute_one_tool(
            tc=_call("lost", "lost"), image_pool=[], image_inventory=[]
        ),
        loop._execute_one_tool(
            tc=_call("healthy", "healthy"), image_pool=[], image_inventory=[]
        ),
    )
    assert json.loads(failed[3]["llm_result"])["workspace_reset"]["generation"] == 1
    assert json.loads(healthy[3]["llm_result"]) == {"content": "healthy result"}
