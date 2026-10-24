"""Boundary coverage for agent-loop trajectory, pause and steering edges.

Each test targets a consumer-visible invariant of one round:

* a tool that returns the wrong interaction name must degrade to an error
  result instead of pausing the run;
* asset-view results persist a replayable marker envelope;
* dependency metrics stop growing at the per-pass cap and flag truncation;
* cache-token telemetry is only attached when the provider reported it;
* trajectory telemetry failures never change the model turn or tool output;
* an ask_user pause without a durable callback is a hard protocol error, and
  without a formatter still waits for the user;
* consumed steering inputs replay the partial assistant turn, and a stop that
  lands after queued inputs remains cooperative.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.tools.interaction import ToolInteractionRequest
from app.llm.types import (
    ChatResponse,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    MessageRole,
    ToolCall,
    Usage,
)
from app.services import agent_round
from app.services.agent_loop import (
    MAX_DEPENDENCY_METRICS_PER_PASS,
    AgentLoop,
    AgentLoopContext,
    AssetViewResult,
    ContextTurn,
)


def _tool(name: str, call_id: str, arguments: str = "{}") -> ToolCall:
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments=arguments))


def _prepared(content: str = "request") -> SimpleNamespace:
    return SimpleNamespace(
        messages=[LLMMessage(role=MessageRole.USER, content=content)],
        compression=None,
        compacted_messages=0,
    )


def _response(
    *,
    content: str = "done",
    tool_calls: list[ToolCall] | None = None,
    usage: Usage | None = None,
) -> ChatResponse:
    return ChatResponse(
        id="response",
        model="model",
        content=content,
        tool_calls=tool_calls,
        finish_reason=FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP,
        usage=usage or Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _context(**overrides: object) -> AgentLoopContext:
    async def build_turn(**_kwargs: object) -> ContextTurn:
        return ContextTurn(prepared=_prepared())

    async def team_chat(**_kwargs: object) -> ChatResponse:
        return _response()

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


class _RoundPatches:
    """Stub durable round persistence so the loop can run without a database."""

    def __enter__(self):
        self._step = agent_round.persist_assistant_step
        self._result = agent_round.persist_tool_result

        async def no_op(**_kwargs):
            return 0

        agent_round.persist_assistant_step = no_op
        agent_round.persist_tool_result = no_op
        return self

    def __exit__(self, *_args):
        agent_round.persist_assistant_step = self._step
        agent_round.persist_tool_result = self._result
        return False


async def _consume_loop(loop: AgentLoop) -> list[str | None]:
    return [event async for event in loop.run()]


async def _consume_loop_with_round_patches(loop: AgentLoop) -> list[str | None]:
    with _RoundPatches():
        return await _consume_loop(loop)


@pytest.mark.asyncio
async def test_interaction_name_mismatch_degrades_to_tool_error():
    """A tool answering for a different call must not pause the run."""

    async def tool_runner(_name, _arguments, **_kwargs):
        return ToolInteractionRequest(
            tool_name="other_tool", arguments={"question": "Where?"}
        )

    loop = AgentLoop(
        _context(execute_tool_call=tool_runner, collect_dependency_metrics=True)
    )
    call_sse, result_sse, media_sse, record = await loop._execute_one_tool(
        tc=_tool("read_asset", "call-mismatch"),
        image_pool=[],
        image_inventory=[],
    )

    assert "call-mismatch" in call_sse
    assert "read_asset" in call_sse
    assert "mismatch" in result_sse
    assert media_sse is None
    assert "interaction" not in record
    assert record["persist_result"] is None
    assert "mismatch" in json.loads(record["display_result"])["error"]
    assert record["llm_result"] == record["display_result"]

    metric = loop.result.dependency_metrics[-1]
    assert metric["name"] == "read_asset"
    assert metric["tool_call_id"] == "call-mismatch"
    assert metric["status"] == "failed"
    assert metric["error_category"] == "ValueError"


@pytest.mark.asyncio
async def test_asset_view_result_persists_replay_marker_envelope():
    """Asset views keep their display payload and marker for ref replay."""
    display = {"kind": "asset.view", "ref": "asset-9", "content": "preview"}
    marker = "[asset:asset-9]"

    async def tool_runner(_name, _arguments, **_kwargs):
        return AssetViewResult(display_result=display, llm_result=marker)

    loop = AgentLoop(_context(execute_tool_call=tool_runner))
    call_sse, result_sse, media_sse, record = await loop._execute_one_tool(
        tc=_tool("view_asset", "call-view", '{"ref": "asset-9"}'),
        image_pool=[],
        image_inventory=[],
    )

    assert media_sse is None
    assert record["llm_result"] == marker
    assert json.loads(record["display_result"]) == display
    envelope = json.loads(record["persist_result"])
    assert envelope["kind"] == "asset.view.persisted"
    assert envelope["version"] == 1
    assert envelope["display"] == display
    assert envelope["marker"] == marker
    # Both streamed events stay usable by the client for this call.
    assert "asset-9" in call_sse
    assert "asset-9" in result_sse


@pytest.mark.asyncio
async def test_dependency_metrics_cap_flags_truncation_without_growing():
    """Beyond the per-pass cap the result is flagged, not silently appended."""

    async def tool_runner(_name, _arguments, **_kwargs):
        return {"ok": True}

    loop = AgentLoop(
        _context(execute_tool_call=tool_runner, collect_dependency_metrics=True)
    )
    loop.result.dependency_metrics = [
        {"span_id": str(index)} for index in range(MAX_DEPENDENCY_METRICS_PER_PASS)
    ]

    await loop._execute_one_tool(
        tc=_tool("knowledge_search", "call-overflow"),
        image_pool=[],
        image_inventory=[],
    )

    assert loop.result.dependency_metrics_truncated is True
    assert len(loop.result.dependency_metrics) == MAX_DEPENDENCY_METRICS_PER_PASS
    assert loop.result.dependency_metrics[-1]["span_id"] == str(
        MAX_DEPENDENCY_METRICS_PER_PASS - 1
    )


@pytest.mark.asyncio
async def test_finish_model_trajectory_only_attaches_reported_cache_tokens(
    monkeypatch,
):
    """Cache telemetry reflects provider-reported values, never zero padding."""
    from app.services import observability_trajectory

    captured: list[dict] = []

    async def capture(handle, **kwargs):
        captured.append({"handle": handle, "kwargs": kwargs})

    monkeypatch.setattr(observability_trajectory, "finish_model_call", capture)
    loop = AgentLoop(_context())
    handle = SimpleNamespace(entry_id=uuid4())

    await loop._finish_model_trajectory(
        handle,
        status="completed",
        content="answer",
        reasoning="thinking",
        tool_calls=[],
        finish_reason="stop",
        usage=Usage(
            prompt_tokens=11,
            completion_tokens=5,
            total_tokens=16,
            cache_read_tokens=7,
            cache_creation_tokens=3,
        ),
    )
    assert captured[0]["kwargs"]["token_usage"] == {
        "prompt": 11,
        "completion": 5,
        "total": 16,
        "cache_read": 7,
        "cache_creation": 3,
    }
    assert captured[0]["kwargs"]["status"] == "completed"
    assert captured[0]["kwargs"]["content"] == "answer"

    await loop._finish_model_trajectory(
        handle,
        status="empty",
        content="",
        reasoning="",
        tool_calls=[],
        finish_reason=None,
        usage=Usage(prompt_tokens=2, completion_tokens=0, total_tokens=2),
    )
    # Unreported cache counters are omitted so consumers can tell "unknown"
    # from a real zero.
    assert captured[1]["kwargs"]["token_usage"] == {
        "prompt": 2,
        "completion": 0,
        "total": 2,
    }

    await loop._finish_model_trajectory(
        None,
        status="cancelled",
        content="",
        reasoning="",
        tool_calls=[],
        finish_reason=None,
        usage=None,
    )
    assert len(captured) == 2


@pytest.mark.asyncio
async def test_trajectory_telemetry_failures_do_not_alter_the_run(monkeypatch):
    """Broken observability storage must not change model or tool outcomes."""
    from app.services import observability_trajectory

    async def broken_request(**_kwargs):
        raise RuntimeError("trajectory request store down")

    async def broken_finish(*_args, **_kwargs):
        raise RuntimeError("trajectory response store down")

    monkeypatch.setattr(
        observability_trajectory, "record_model_request", broken_request
    )
    monkeypatch.setattr(observability_trajectory, "finish_model_call", broken_finish)
    monkeypatch.setattr(
        observability_trajectory, "record_tool_call", AsyncMock(return_value=None)
    )
    from app.services import observability_payload

    monkeypatch.setattr(
        observability_payload, "record_tool_payload", AsyncMock(return_value=None)
    )

    executed: list[tuple[str, dict]] = []

    async def tool_runner(name, arguments, **_kwargs):
        executed.append((name, arguments))
        return {"ok": True}

    responses = [
        _response(
            content="",
            tool_calls=[_tool("read_asset", "call-1", json.dumps({"ref": "asset-9"}))],
        ),
        _response(content="final answer"),
    ]

    async def team_chat(**_kwargs):
        return responses.pop(0)

    loop = AgentLoop(
        _context(
            team_chat=team_chat,
            execute_tool_call=tool_runner,
            collect_dependency_metrics=True,
            observability_run_id=uuid4(),
            formatter=lambda name, _payload: name,
        )
    )
    output = await _consume_loop_with_round_patches(loop)

    assert loop.result.full_content == "final answer"
    assert loop.result.manually_stopped is False
    assert executed == [("read_asset", {"ref": "asset-9"})]
    # Tool output still reached provider history and the client.
    assert loop.context.working_history_override[-1]["role"] == "tool"
    assert "tool_call" in output
    assert "tool_result" in output


@pytest.mark.asyncio
async def test_finalize_active_model_swallows_telemetry_errors_and_clears_state():
    """Cancellation finalizers cannot break the loop's error path."""
    loop = AgentLoop(_context())
    seen: list[tuple[str, str | None]] = []

    async def failing_finalizer(status, error):
        seen.append((status, error))
        raise RuntimeError("finalizer down")

    loop._active_model_finalizer = failing_finalizer
    await loop._finalize_active_model("failed", "boom")
    assert seen == [("failed", "boom")]
    assert loop._active_model_finalizer is None

    async def cancelled_finalizer(_status, _error):
        raise asyncio.CancelledError

    loop._active_model_finalizer = cancelled_finalizer
    with pytest.raises(asyncio.CancelledError):
        await loop._finalize_active_model("cancelled", "cancelled")
    assert loop._active_model_finalizer is None

    # No in-flight model turn: a no-op rather than an error.
    await loop._finalize_active_model("cancelled", None)


@pytest.mark.asyncio
async def test_ask_user_pause_requires_durable_callback():
    """Pausing without a durable callback is a protocol error, not a silent stop."""

    async def tool_runner(_name, _arguments, **_kwargs):
        return ToolInteractionRequest(
            tool_name="ask_user",
            arguments={"questions": [{"id": "target", "question": "Where?"}]},
        )

    async def team_chat(**_kwargs):
        return _response(
            content="",
            tool_calls=[
                _tool(
                    "ask_user",
                    "call-ask",
                    json.dumps({"questions": [{"id": "target", "question": "Where?"}]}),
                )
            ],
        )

    loop = AgentLoop(
        _context(
            team_chat=team_chat,
            execute_tool_call=tool_runner,
            formatter=lambda name, _payload: name,
        )
    )

    with pytest.raises(RuntimeError, match="ask_user"):
        await _consume_loop_with_round_patches(loop)
    assert loop.result.waiting_for_user is False


@pytest.mark.asyncio
async def test_ask_user_pause_without_formatter_still_waits_for_user():
    """A suppressed call event must not suppress the durable pause itself."""
    paused: dict = {}

    async def tool_runner(_name, _arguments, **_kwargs):
        return ToolInteractionRequest(
            tool_name="ask_user",
            arguments={
                "questions": [{"id": "target", "question": "Where?", "required": True}]
            },
        )

    async def pause_for_user(**kwargs):
        paused.update(kwargs)

    async def team_chat(**_kwargs):
        return _response(
            content="Choosing",
            tool_calls=[
                _tool(
                    "ask_user",
                    "call-ask",
                    json.dumps({"questions": [{"id": "target", "question": "Where?"}]}),
                )
            ],
        )

    loop = AgentLoop(
        _context(
            team_chat=team_chat,
            execute_tool_call=tool_runner,
            pause_for_user=pause_for_user,
            formatter=None,
        )
    )

    output = await _consume_loop_with_round_patches(loop)

    assert output == []
    assert loop.result.waiting_for_user is True
    assert loop.result.full_content == "Choosing"
    assert paused["tool_call_id"] == "call-ask"
    assert paused["tool_name"] == "ask_user"
    assert paused["arguments"]["questions"][0]["id"] == "target"


@pytest.mark.asyncio
async def test_consumed_steering_inputs_replay_turns_then_stop_wins():
    """Queued inputs replay each partial turn; a later stop stays cooperative."""
    responses = [
        _response(content=""),
        _response(content="partial one"),
        _response(content="partial two"),
        _response(content="final answer"),
    ]
    model_calls = 0

    async def team_chat(**_kwargs):
        nonlocal model_calls
        model_calls += 1
        return responses.pop(0)

    pending_inputs: list[list[SimpleNamespace]] = [
        [],
        [SimpleNamespace(content="steer empty")],
        [],
        [SimpleNamespace(content="steer one")],
        [],
        [SimpleNamespace(content="steer two")],
        [],
    ]
    stop_flag = False
    consumed: list[str] = []

    async def consume_inputs():
        if pending_inputs:
            return pending_inputs.pop(0)
        if model_calls >= 4:
            # The final post-model drain flips the cooperative stop.
            nonlocal stop_flag
            stop_flag = True
        return []

    async def input_consumed(item):
        consumed.append(item.content)

    async def stop_requested():
        return stop_flag

    loop = AgentLoop(
        _context(
            team_chat=team_chat,
            consume_inputs=consume_inputs,
            input_consumed=input_consumed,
            stop_requested=stop_requested,
            working_history_override=None,
            max_iterations=5,
        )
    )
    await _consume_loop(loop)

    assert model_calls == 4
    assert consumed == ["steer empty", "steer one", "steer two"]
    assert loop.result.manually_stopped is True
    assert loop.result.full_content == "final answer"

    history = loop.context.working_history_override
    assert history is not None
    assistant_turns = [entry for entry in history if entry["role"] == "assistant"]
    assert [entry["content"] for entry in assistant_turns] == [
        "partial one",
        "partial two",
    ]
    # Both replays are non-canonical round steps, not terminal answers.
    assert all(entry["round_role"] == "assistant_step" for entry in assistant_turns)
    assert all(entry["is_round_canonical"] is False for entry in assistant_turns)
