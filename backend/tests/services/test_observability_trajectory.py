"""Behavioral coverage for bounded execution-trajectory capture."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.llm.types import (
    ChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    ToolCall,
    Usage,
)
from app.models.observability import ObservabilityRun
from app.models.observability_payload import ObservabilityTrajectoryEntry
from app.models.workflow import (
    NodeExecution,
    NodeStatus,
    RunStatus,
    TriggerType,
    WorkflowRun,
)
from app.services import agent_round
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn
from app.services.observability_trajectory import (
    MAX_ENTRY_BYTES,
    entry_payload,
    load_entry,
    trajectory_entries,
)
from app.services.observability_v2 import run_detail, trajectory_detail


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


class _Message:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self, **_kwargs):
        return dict(self._payload)


class _BuildTurn:
    """Returns a distinct immutable message snapshot for each round."""

    def __init__(self):
        self.round = 0

    async def __call__(self, **_kwargs):
        self.round += 1
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[_Message({"role": "user", "content": f"round-{self.round}"})],
                compression=None,
                compacted_messages=0,
            )
        )


class _HistoryBuildTurn:
    """Builds provider messages from the loop's appended working history."""

    async def __call__(self, history_override=None, **_kwargs):
        messages = [{"role": "user", "content": "call the http tool"}]
        for entry in history_override or []:
            role = entry.get("role")
            if role == "assistant":
                message = {
                    "role": "assistant",
                    "content": entry.get("content") or "",
                }
                if entry.get("tool_calls"):
                    message["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            },
                        }
                        for call in entry["tool_calls"]
                    ]
                messages.append(message)
            elif role == "tool":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": entry.get("tool_call_id"),
                        "content": entry.get("content"),
                    }
                )
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[_Message(message) for message in messages],
                compression=None,
                compacted_messages=0,
            )
        )


class _RoundPatches:
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


def _context(
    *,
    run_id,
    chat,
    build_turn=None,
    execute_tool_call=None,
    model_config=None,
    tools=None,
    streaming=False,
    team_chat_stream=None,
    max_iterations=4,
):
    return AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=None),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        model_id="model-uuid",
        tokenizer_model_id="provider/model",
        model_provider="provider",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="model-uuid",
        model_config=model_config,
        max_iterations=max_iterations,
        streaming=streaming,
        working_history_override=[],
        round_id=uuid4(),
        team_chat=chat,
        team_chat_stream=team_chat_stream,
        build_turn=build_turn or _BuildTurn(),
        tools=tools,
        execute_tool_call=execute_tool_call,
        formatter=None,
        collect_dependency_metrics=True,
        observability_run_id=run_id,
    )


async def _run_loop(context):
    loop = AgentLoop(context)
    with _RoundPatches():
        async for _ in loop.run():
            pass


@pytest.mark.asyncio
async def test_capture_correlates_tool_request_to_its_model_round(database):
    run_id = uuid4()
    seen_messages = []

    async def tool_runner(name, arguments, **_kwargs):
        assert name == "read_asset"
        assert arguments == {"ref": "a1b2"}
        return {"ok": True}

    responses = [
        ChatResponse(
            id="r1",
            model="m",
            content="",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(
                        name="read_asset", arguments=json.dumps({"ref": "a1b2"})
                    ),
                )
            ],
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        ),
        ChatResponse(
            id="r2",
            model="m",
            content="done",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=4, completion_tokens=1, total_tokens=5),
        ),
    ]

    async def chat(**kwargs):
        # Simulate a transport mutating the caller's list; the stored snapshot
        # must remain the request that was actually sent.
        seen_messages.append([dict(item) for item in kwargs["messages"]])
        kwargs["messages"].append({"role": "tool", "content": "late mutation"})
        return responses.pop(0)

    await _run_loop(_context(run_id=run_id, chat=chat, execute_tool_call=tool_runner))

    entries = await trajectory_entries(run_id, 20)
    assert [entry["kind"] for entry in entries] == ["model", "tool", "model"]
    first_model, tool_entry, second_model = entries
    assert tool_entry["parent_id"] == first_model["id"]
    assert tool_entry["tool_call_ids"] == ["call-1"]
    assert tool_entry["status"] == "completed"
    assert first_model["status"] == "completed"
    assert first_model["token_usage"] == {
        "prompt": 3,
        "completion": 2,
        "total": 5,
    }
    assert first_model["started_at"] is not None
    assert first_model["duration_ms"] is not None
    assert first_model["payload_state"] == "recorded"
    # Tool-call turns have no content; the summary must still explain the
    # response with the requested tool name/arguments.
    assert "read_asset" in first_model["preview"]
    assert "a1b2" in first_model["preview"]

    first_payload = await load_entry(run_id, first_model["id"])
    first_input, first_output, first_partial, first_recorded = entry_payload(
        first_payload
    )
    assert first_recorded is True
    assert first_partial is False
    assert first_input["messages"] == [{"role": "user", "content": "round-1"}]
    assert first_input["model"] == "provider/model"
    assert first_output["tool_calls"][0]["id"] == "call-1"
    assert first_output["finish_reason"] == "tool_calls"

    second_payload = await load_entry(run_id, second_model["id"])
    second_input, second_output, _, _ = entry_payload(second_payload)
    assert second_input["messages"] == [{"role": "user", "content": "round-2"}]
    assert second_output["content"] == "done"
    # The transport mutation after the snapshot is not represented.
    assert all(
        message.get("content") != "late mutation"
        for message in first_input["messages"] + second_input["messages"]
    )
    assert len(seen_messages) == 2


@pytest.mark.asyncio
async def test_run_detail_and_detail_api_promote_existing_tool_payloads(database):
    run_id = uuid4()
    await ObservabilityRun.create(
        id=run_id,
        source="agent",
        status="completed",
        submitted_at=datetime.now(UTC),
    )

    async def tool_runner(_name, _arguments, **_kwargs):
        return {"ok": True}

    async def chat(**_kwargs):
        return ChatResponse(
            id="r1",
            model="m",
            content="",
            tool_calls=[
                ToolCall(
                    id="call-9",
                    function=FunctionCall(
                        name="read_asset", arguments=json.dumps({"ref": "x"})
                    ),
                )
            ],
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    context = _context(
        run_id=run_id, chat=chat, execute_tool_call=tool_runner, max_iterations=1
    )
    await _run_loop(context)

    detail = await run_detail("agent", run_id)
    kinds = [entry["kind"] for entry in detail["trajectory"]]
    assert kinds == ["model", "tool"]
    tool_summary = detail["trajectory"][1]
    assert tool_summary["payload_state"] == "recorded"
    assert tool_summary["tool_call_ids"] == ["call-9"]

    model_entry = detail["trajectory"][0]
    model_payload = await trajectory_detail("agent", run_id, model_entry["id"])
    assert model_payload["recorded"] is True
    assert model_payload["kind"] == "model"
    assert model_payload["input"]["messages"] == [
        {"role": "user", "content": "round-1"}
    ]

    tool_payload = await trajectory_detail("agent", run_id, tool_summary["id"])
    assert tool_payload["recorded"] is True
    assert tool_payload["input"]["arguments"] == {"ref": "x"}
    assert tool_payload["output"]["model_input"]

    assert await trajectory_detail("agent", uuid4(), model_entry["id"]) is None
    assert await trajectory_detail("workflow", run_id, model_entry["id"]) is None


@pytest.mark.asyncio
async def test_second_model_snapshot_contains_appended_model_facing_tool_result(
    database,
):
    run_id = uuid4()

    async def tool_runner(_name, _arguments, **_kwargs):
        return {"ok": True, "value": "tool-output-1"}

    responses = [
        ChatResponse(
            id="r1",
            model="m",
            content="",
            tool_calls=[
                ToolCall(
                    id="call-h",
                    function=FunctionCall(
                        name="http",
                        arguments=json.dumps({"url": "https://example.test"}),
                    ),
                )
            ],
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ),
        ChatResponse(
            id="r2",
            model="m",
            content="finished",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=3, completion_tokens=1, total_tokens=4),
        ),
    ]

    async def chat(**_kwargs):
        return responses.pop(0)

    await _run_loop(
        _context(
            run_id=run_id,
            chat=chat,
            build_turn=_HistoryBuildTurn(),
            execute_tool_call=tool_runner,
        )
    )

    entries = await trajectory_entries(run_id, 10)
    assert [entry["kind"] for entry in entries] == ["model", "tool", "model"]
    first_input = json.loads((await load_entry(run_id, entries[0]["id"])).input_text)
    # The first request predates the tool result.
    assert first_input["messages"] == [
        {"role": "user", "content": "call the http tool"}
    ]

    second_input = json.loads((await load_entry(run_id, entries[2]["id"])).input_text)
    messages = second_input["messages"]
    assistant = next(
        message
        for message in messages
        if message["role"] == "assistant" and message.get("tool_calls")
    )
    assert assistant["tool_calls"][0]["id"] == "call-h"
    assert assistant["tool_calls"][0]["function"]["name"] == "http"
    tool_message = next(message for message in messages if message["role"] == "tool")
    assert tool_message["tool_call_id"] == "call-h"
    # The actual model-facing rendering of the tool result, not the display JSON.
    assert json.loads(tool_message["content"]) == {
        "ok": True,
        "value": "tool-output-1",
    }
    assert entries[2]["token_usage"] == {
        "prompt": 3,
        "completion": 1,
        "total": 4,
    }


@pytest.mark.asyncio
async def test_streaming_capture_records_content_tool_call_and_usage(database):
    run_id = uuid4()

    async def tool_runner(_name, _arguments, **_kwargs):
        return {"ok": True}

    stream_round = {"n": 0}

    async def stream(**_kwargs):
        stream_round["n"] += 1
        if stream_round["n"] == 1:
            yield ChatStreamChunk(
                id="s1",
                model="m",
                delta=ChatStreamDelta(content="thinking out loud"),
            )
            yield ChatStreamChunk(
                id="s1",
                model="m",
                delta=ChatStreamDelta(
                    tool_calls=[
                        ToolCall(
                            id="call-s",
                            function=FunctionCall(
                                name="http", arguments=json.dumps({"url": "u"})
                            ),
                        )
                    ]
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=Usage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
            )
            return
        yield ChatStreamChunk(
            id="s2",
            model="m",
            delta=ChatStreamDelta(content="finished"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=4, completion_tokens=1, total_tokens=5),
        )

    async def chat(**_kwargs):
        raise AssertionError("stream fallback must not run")

    await _run_loop(
        _context(
            run_id=run_id,
            chat=chat,
            streaming=True,
            team_chat_stream=stream,
            execute_tool_call=tool_runner,
        )
    )

    entries = await trajectory_entries(run_id, 10)
    assert [entry["kind"] for entry in entries] == ["model", "tool", "model"]
    first = await load_entry(run_id, entries[0]["id"])
    first_input, first_output, _, first_recorded = entry_payload(first)
    assert first_recorded is True
    assert first_input["streaming"] is True
    assert first_output["content"] == "thinking out loud"
    assert first_output["tool_calls"][0]["id"] == "call-s"
    assert first_output["finish_reason"] == "tool_calls"
    assert entries[0]["token_usage"] == {
        "prompt": 2,
        "completion": 3,
        "total": 5,
    }
    assert entries[1]["parent_id"] == entries[0]["id"]
    assert entries[1]["tool_call_ids"] == ["call-s"]

    second_output = entry_payload(await load_entry(run_id, entries[2]["id"]))[1]
    assert second_output["content"] == "finished"
    assert second_output["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_cancelled_stream_preserves_partial_output(database):
    run_id = uuid4()

    async def stream(**_kwargs):
        yield ChatStreamChunk(
            id="s1",
            model="m",
            delta=ChatStreamDelta(content="partial output"),
        )
        raise asyncio.CancelledError()

    async def chat(**_kwargs):
        raise AssertionError("cancelled stream must not fall back")

    with pytest.raises(asyncio.CancelledError):
        await _run_loop(
            _context(
                run_id=run_id,
                chat=chat,
                streaming=True,
                team_chat_stream=stream,
            )
        )

    entries = await trajectory_entries(run_id, 10)
    assert len(entries) == 1
    assert entries[0]["status"] == "cancelled"
    assert entries[0]["preview"] == "partial output"
    _, output, _, _ = entry_payload(await load_entry(run_id, entries[0]["id"]))
    assert output["content"] == "partial output"


@pytest.mark.asyncio
async def test_model_failure_is_recorded_with_the_raised_error(database):
    run_id = uuid4()

    async def chat(**_kwargs):
        raise RuntimeError("provider exploded")

    with pytest.raises(RuntimeError):
        await _run_loop(_context(run_id=run_id, chat=chat))

    entries = await trajectory_entries(run_id, 10)
    assert len(entries) == 1
    assert entries[0]["kind"] == "model"
    assert entries[0]["status"] == "failed"
    stored = await load_entry(run_id, entries[0]["id"])
    _, output, _, recorded = entry_payload(stored)
    assert recorded is True
    assert output["error"] == "RuntimeError: provider exploded"
    assert entries[0]["preview"] == "RuntimeError: provider exploded"


@pytest.mark.asyncio
async def test_cancellation_is_preserved_and_recorded(database):
    run_id = uuid4()

    async def chat(**_kwargs):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _run_loop(_context(run_id=run_id, chat=chat))

    entries = await trajectory_entries(run_id, 10)
    assert len(entries) == 1
    assert entries[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_oversized_request_is_bounded_and_marked_partial(database):
    run_id = uuid4()
    await ObservabilityRun.create(
        id=run_id,
        source="agent",
        status="completed",
        submitted_at=datetime.now(UTC),
    )

    class _OversizedTurn:
        async def __call__(self, **_kwargs):
            return ContextTurn(
                prepared=SimpleNamespace(
                    messages=[
                        _Message(
                            {"role": "user", "content": "x" * (MAX_ENTRY_BYTES + 1)}
                        )
                    ],
                    compression=None,
                    compacted_messages=0,
                )
            )

    async def chat(**_kwargs):
        return ChatResponse(
            id="r1",
            model="m",
            content="ok",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    await _run_loop(
        _context(
            run_id=run_id,
            chat=chat,
            build_turn=_OversizedTurn(),
            max_iterations=1,
        )
    )

    entries = await trajectory_entries(run_id, 10)
    assert entries[0]["payload_state"] == "partial"
    stored = await load_entry(run_id, entries[0]["id"])
    assert stored.input_text is None
    assert stored.partial is True
    detail = await trajectory_detail("agent", run_id, entries[0]["id"])
    assert detail["recorded"] is False
    assert detail["partial"] is True
    assert detail["input"] is None


@pytest.mark.asyncio
async def test_request_options_exclude_transport_credentials(database):
    run_id = uuid4()

    async def chat(**_kwargs):
        return ChatResponse(
            id="r1",
            model="m",
            content="ok",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    model_config = SimpleNamespace(
        default_params={
            "temperature": 0.2,
            "top_p": 0.9,
            "api_key": "sk-secret",
            "base_url": "https://internal.example",
        },
        api_key="sk-secret",
    )

    await _run_loop(
        _context(
            run_id=run_id,
            chat=chat,
            model_config=model_config,
            max_iterations=1,
        )
    )

    entries = await trajectory_entries(run_id, 10)
    stored = await load_entry(run_id, entries[0]["id"])
    input_value = json.loads(stored.input_text)
    assert input_value["options"]["temperature"] == 0.2
    assert input_value["options"]["top_p"] == 0.9
    # Configured budgets are labeled separately, not as effective options.
    assert input_value["limits"] == {
        "context_limit": 100_000,
        "configured_max_output_tokens": 1000,
    }
    assert "max_output_tokens" not in input_value["options"]
    serialized = stored.input_text
    assert "sk-secret" not in serialized
    assert "internal.example" not in serialized


def test_option_overrides_are_allowlisted():
    from app.services.observability_trajectory import safe_model_options

    options = safe_model_options(
        SimpleNamespace(default_params={"temperature": 0.3}),
        api_key="sk-leak",
        base_url="https://internal.example",
        max_tokens=256,
        context_limit=1000,
    )
    assert options == {"temperature": 0.3, "max_tokens": 256}


@pytest.mark.asyncio
async def test_request_captures_full_tool_definitions(database):
    from app.llm.types import FunctionDefinition, ToolDefinition

    run_id = uuid4()
    parameters = {
        "type": "object",
        "properties": {"ref": {"type": "string", "description": "Asset ref"}},
        "required": ["ref"],
    }
    tool = ToolDefinition(
        type="function",
        function=FunctionDefinition(
            name="read_asset",
            description="Read one document by reference",
            parameters=parameters,
        ),
    )

    async def chat(**_kwargs):
        return ChatResponse(
            id="r1",
            model="m",
            content="ok",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    await _run_loop(
        _context(
            run_id=run_id,
            chat=chat,
            tools=[tool],
            max_iterations=1,
        )
    )

    entries = await trajectory_entries(run_id, 10)
    stored = await load_entry(run_id, entries[0]["id"])
    captured = json.loads(stored.input_text)["tools"]
    assert captured == [
        {
            "type": "function",
            "function": {
                "name": "read_asset",
                "description": "Read one document by reference",
                "parameters": parameters,
            },
        }
    ]
    # The schema, not just the name, is present.
    assert (
        captured[0]["function"]["parameters"]["properties"]["ref"]["type"] == "string"
    )


@pytest.mark.asyncio
async def test_legacy_spans_merge_under_captured_entries(monkeypatch, database):
    from app.services import observability_v2

    run_id = uuid4()
    model_entry = {
        "id": str(uuid4()),
        "parent_id": None,
        "kind": "model",
        "name": "provider/model",
        "status": "completed",
        "started_at": "2026-10-08T12:00:02+00:00",
        "finished_at": "2026-10-08T12:00:03+00:00",
        "duration_ms": 1000,
        "model": "provider/model",
        "token_usage": None,
        "tool_call_ids": ["call-1"],
        "payload_state": "recorded",
        "preview": None,
    }
    tool_entry = dict(
        model_entry,
        id=str(uuid4()),
        kind="tool",
        name="read_asset",
        started_at="2026-10-08T12:00:04+00:00",
        tool_call_ids=["call-1"],
        payload_state="recorded",
        _input_recorded=True,
    )
    span_id = uuid4()
    legacy_metric = {
        "span_id": str(span_id),
        "kind": "tool",
        "name": "http",
        "tool_call_id": "call-2",
        "status": "completed",
        "started_at": "2026-10-08T12:00:01+00:00",
    }

    async def fake_entries(_run_id, _limit):
        # Fresh copies: run_detail mutates the loaded summaries in place.
        return [dict(model_entry), dict(tool_entry)]

    monkeypatch.setattr(
        "app.services.observability_trajectory.trajectory_entries",
        fake_entries,
    )
    monkeypatch.setattr(observability_v2, "TRAJECTORY_ENTRY_LIMIT", 3)
    entries, truncated = await observability_v2._agent_trajectory(
        run_id,
        {"call-1": {"partial": False}},
        [legacy_metric, {"kind": "tool", "name": "malformed"}],
    )

    # The model entry references call-1 but only the tool entry covers it; the
    # uncaptured call-2 span is still merged. Malformed metrics are dropped.
    assert truncated is False
    assert [entry["id"] for entry in entries] == [
        str(span_id),
        str(model_entry["id"]),
        str(tool_entry["id"]),
    ]
    # Legacy span has output-only context; captured tool has both sides.
    assert entries[0]["payload_state"] == "unrecorded"
    assert entries[1]["payload_state"] == "recorded"
    assert entries[2]["payload_state"] == "recorded"
    assert all("_input_recorded" not in entry for entry in entries)

    monkeypatch.setattr(observability_v2, "TRAJECTORY_ENTRY_LIMIT", 2)
    entries, truncated = await observability_v2._agent_trajectory(
        run_id, {}, [legacy_metric]
    )
    assert truncated is True
    assert [entry["id"] for entry in entries] == [
        str(model_entry["id"]),
        str(tool_entry["id"]),
    ]
    # Input was captured but the tool payload row is missing.
    assert entries[1]["payload_state"] == "partial"


def test_combined_payload_state_requires_both_sides():
    from app.services.observability_v2 import _combined_payload_state

    assert _combined_payload_state(False, "recorded") == "partial", (
        "oversized/missing input must not be promoted to recorded"
    )
    assert _combined_payload_state(True, "unrecorded") == "partial"
    assert _combined_payload_state(True, "recorded") == "recorded"
    assert _combined_payload_state(False, "unrecorded") == "unrecorded"


@pytest.mark.asyncio
async def test_workflow_nodes_expose_real_inputs_config_and_outputs(database):
    run_id = uuid4()
    other_run_id = uuid4()
    await ObservabilityRun.create(
        id=run_id,
        source="workflow",
        status="completed",
        submitted_at=datetime.now(UTC),
    )
    await WorkflowRun.create(
        id=run_id, trigger_type=TriggerType.MANUAL, status=RunStatus.SUCCESS
    )
    node = await NodeExecution.create(
        id=uuid4(),
        run_id=run_id,
        node_id="node-1",
        node_type="llm",
        node_name="Answer",
        execution_order=1,
        status=NodeStatus.SUCCESS,
        inputs={"question": "why"},
        config_snapshot={"prompt": "be brief"},
        outputs={"answer": "because"},
        model_used="provider/model",
        prompt_tokens=2,
        completion_tokens=3,
        total_tokens=5,
    )

    detail = await run_detail("workflow", run_id)
    assert detail["trajectory"][0]["id"] == str(node.id)
    assert detail["trajectory"][0]["kind"] == "workflow_node"
    # Summaries do not load node bodies; only the detail call can claim
    # completeness.
    assert detail["trajectory"][0]["payload_state"] == "partial"
    assert detail["trajectory"][0]["token_usage"] == {
        "prompt": 2,
        "completion": 3,
        "total": 5,
    }

    payload = await trajectory_detail("workflow", run_id, str(node.id))
    assert payload["recorded"] is True
    assert payload["partial"] is False
    assert payload["input"]["inputs"] == {"question": "why"}
    assert payload["input"]["config"] == {"prompt": "be brief"}
    assert payload["output"]["outputs"] == {"answer": "because"}

    # Cross-run access cannot read the node through another run id.
    await ObservabilityRun.create(
        id=other_run_id,
        source="workflow",
        status="completed",
        submitted_at=datetime.now(UTC),
    )
    assert await trajectory_detail("workflow", other_run_id, str(node.id)) is None


@pytest.mark.asyncio
async def test_retention_removes_expired_trajectory_rows_in_batches(database):
    from app.services.observability_v2 import retain

    cutoff = datetime.now(UTC) - timedelta(days=40)
    expired_run_id = uuid4()
    await ObservabilityTrajectoryEntry.create(
        id=uuid4(),
        run_id=expired_run_id,
        sequence=1,
        kind="model",
        name="m",
        status="completed",
        payload_state="recorded",
    )
    await ObservabilityTrajectoryEntry.filter(run_id=expired_run_id).update(
        created_at=cutoff
    )
    recent_run_id = uuid4()
    await ObservabilityRun.create(
        id=recent_run_id,
        source="agent",
        status="completed",
        submitted_at=datetime.now(UTC),
    )
    await ObservabilityTrajectoryEntry.create(
        id=uuid4(),
        run_id=recent_run_id,
        sequence=1,
        kind="model",
        name="m",
        status="completed",
        payload_state="recorded",
    )

    await retain()

    # Rows past the retention window expire independently of their summary
    # (including summaries that never persisted); recent rows stay.
    assert (
        await ObservabilityTrajectoryEntry.filter(run_id=expired_run_id).exists()
        is False
    )
    assert (
        await ObservabilityTrajectoryEntry.filter(run_id=recent_run_id).exists() is True
    )
