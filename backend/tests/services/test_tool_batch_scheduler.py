"""
Focused tests for Stage 7 shared/exclusive tool batch scheduling.

Contracts:

- consecutive shared tool calls overlap in wall-clock execution,
- shared -> exclusive -> shared has no overlap across the exclusive barrier,
- persistence/provider order matches the model's original tool-call order
  even when completion order differs,
- one shared sibling failure does not discard the other's result,
- default classification is exclusive (unknown tools never run concurrently),
- an approval pause reports every unstarted call in model order with its
  original arguments; a resumed loop executes those saved calls before the
  next model turn, exactly once, and a later approval pauses again with only
  the still-unstarted suffix.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.tools.interaction import ToolInteractionRequest
from app.llm.types import FunctionCall, ToolCall
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn


def _tool_call(call_id, name, arguments="{}"):
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments=arguments))


def _prepared():
    from app.llm.types import Message as LM, MessageRole

    return SimpleNamespace(messages=[LM(role=MessageRole.USER, content="hi")])


def _base_ctx(
    concurrency_map,
    *,
    max_iterations=2,
    resume_tool_calls=None,
    agent=None,
    conversation=None,
    round_id=None,
    iteration_offset=0,
    working_history_override=None,
):
    agent = agent or SimpleNamespace(id=uuid4(), team_id=uuid4())
    conversation = conversation or SimpleNamespace(id=uuid4())
    ctx = AgentLoopContext(
        agent=agent,
        conversation=conversation,
        user=SimpleNamespace(id=uuid4()),
        user_message="hi",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=max_iterations,
        iteration_offset=iteration_offset,
        streaming=False,
        working_history_override=(
            [] if working_history_override is None else working_history_override
        ),
        round_id=round_id or uuid4(),
        formatter=None,
        resume_tool_calls=resume_tool_calls,
        tool_concurrency=lambda name: concurrency_map.get(name, "exclusive"),
    )

    async def build_turn(**kwargs):
        return ContextTurn(prepared=_prepared())

    ctx.build_turn = build_turn
    return ctx


class _Clock:
    """Tracks overlapping execution windows per tool."""

    def __init__(self):
        self.windows: dict[str, tuple[float, float]] = {}

    def begin(self, name):
        self.windows.setdefault(name, [None, None])
        self.windows[name][0] = asyncio.get_event_loop().time()

    def end(self, name):
        self.windows[name][1] = asyncio.get_event_loop().time()


def _overlaps(a, b):
    return not (a[1] < b[0] or b[1] < a[0])


def _turn(tool_calls, content=""):
    return SimpleNamespace(
        content=content, reasoning_content=None, tool_calls=tool_calls, usage=None
    )


def _final(content="done"):
    return SimpleNamespace(
        content=content, reasoning_content=None, tool_calls=None, usage=None
    )


class _ToolScript:
    """Tool runner that turns approval-gated names into interaction requests."""

    def __init__(self, log, *, approvals=()):
        self.log = log
        self.approvals = set(approvals)
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, name, arguments, **_kwargs):
        self.log.append(("tool", name))
        self.calls.append((name, arguments))
        if name in self.approvals:
            return ToolInteractionRequest(
                tool_name=name,
                arguments={
                    "interaction_kind": "tool_approval",
                    "execution_id": f"exec-{name}",
                },
            )
        return {"result": name}


class _Pauses:
    def __init__(self):
        self.items: list[dict] = []

    async def __call__(self, **kwargs):
        self.items.append(kwargs)


def _chat_script(responses, log):
    pending = list(responses)
    calls: list[dict] = []

    async def _chat(**kwargs):
        log.append(("model", len(calls)))
        calls.append(kwargs)
        assert pending, "model called more times than scripted"
        return pending.pop(0)

    _chat.calls = calls
    return _chat


def _patch_persistence(monkeypatch):
    from app.services import agent_round

    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )


async def _drain(loop):
    async for _event in loop.run():
        pass


def _signature(calls):
    return [(call.id, call.function.name, call.function.arguments) for call in calls]


async def _pause_on_first_call(calls, *, concurrency=None, approvals=("write_a",)):
    """Run one loop that pauses on its first tool call and capture the pause."""
    log: list[tuple[str, object]] = []
    tools = _ToolScript(log, approvals=approvals)
    pauses = _Pauses()
    ctx = _base_ctx(concurrency or {}, max_iterations=2)
    ctx.team_chat = _chat_script([_turn(calls)], log)
    ctx.execute_tool_call = tools
    ctx.pause_for_user = pauses
    loop = AgentLoop(ctx)
    await _drain(loop)
    return ctx, loop, pauses, tools, log


def _resumed_ctx(base_ctx, pause, *, concurrency=None, max_iterations=2):
    """Rebuild the loop context the way the worker does after a decision.

    Carries the persisted history, the pause's iteration index, and the next
    round index so the saved calls continue the same round before the next
    provider turn.
    """
    ctx = _base_ctx(
        concurrency if concurrency is not None else {},
        max_iterations=max_iterations,
        resume_tool_calls=list(pause["remaining_tool_calls"]),
        agent=base_ctx.agent,
        conversation=base_ctx.conversation,
        round_id=base_ctx.round_id,
        iteration_offset=int(pause["iteration_index"]),
        working_history_override=list(base_ctx.working_history_override or []),
    )
    ctx.first_round_index = int(pause["round_index"]) + 1
    ctx.created_message_count = base_ctx.created_message_count
    return ctx


@pytest.mark.asyncio
async def test_shared_calls_overlap_in_time(monkeypatch):
    """Two consecutive shared calls execute concurrently."""
    from app.services import agent_round

    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    clock = _Clock()
    started = set()
    lock = asyncio.Lock()

    async def _runner(name, args, **kwargs):
        clock.begin(name)
        async with lock:
            started.add(name)
            await asyncio.sleep(0.08)
        clock.end(name)
        return {"result": name}

    async def _team_chat(**kwargs):
        return SimpleNamespace(
            content="",
            reasoning_content=None,
            tool_calls=[
                _tool_call("a", "read_a"),
                _tool_call("b", "read_b"),
            ],
            usage=None,
        )

    ctx = _base_ctx({"read_a": "shared", "read_b": "shared"})
    ctx.team_chat = _team_chat
    ctx.execute_tool_call = _runner
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    a = clock.windows["read_a"]
    b = clock.windows["read_b"]
    assert a[0] is not None and b[0] is not None
    assert _overlaps(a, b), f"windows {a} {b} did not overlap"


@pytest.mark.asyncio
async def test_exclusive_barrier_prevents_overlap(monkeypatch):
    """shared -> exclusive -> shared: no overlap across the exclusive call."""
    from app.services import agent_round

    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    clock = _Clock()

    async def _runner(name, args, **kwargs):
        clock.begin(name)
        await asyncio.sleep(0.05)
        clock.end(name)
        return {"result": name}

    async def _team_chat(**kwargs):
        return SimpleNamespace(
            content="",
            reasoning_content=None,
            tool_calls=[
                _tool_call("a", "read_a"),
                _tool_call("x", "mutate_x"),
                _tool_call("b", "read_b"),
            ],
            usage=None,
        )

    ctx = _base_ctx({"read_a": "shared", "read_b": "shared", "mutate_x": "exclusive"})
    ctx.team_chat = _team_chat
    ctx.execute_tool_call = _runner
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    a = clock.windows["read_a"]
    x = clock.windows["mutate_x"]
    b = clock.windows["read_b"]
    # exclusive waits for earlier shared, blocks later shared
    assert x[1] <= a[1] or _overlaps(a, x) is False
    assert not _overlaps(a, x)
    assert not _overlaps(x, b)


@pytest.mark.asyncio
async def test_persistence_order_matches_model_order(monkeypatch):
    """Even though results complete out of order, the emitted/persisted order
    matches the model's original tool-call order."""
    from app.services import agent_round

    persisted_calls: list[str] = []

    async def _persist_tool_result(**kwargs):
        persisted_calls.append(kwargs["tool_name"])
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_tool_result)
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    async def _runner(name, args, **kwargs):
        if name == "read_b":
            await asyncio.sleep(0.05)  # later model call finishes first
        return {"result": name}

    def _team_chat(_call={"n": 0}):
        async def _inner(**kwargs):
            _call["n"] += 1
            if _call["n"] == 1:
                return SimpleNamespace(
                    content="",
                    reasoning_content=None,
                    tool_calls=[
                        _tool_call("a", "read_a"),
                        _tool_call("b", "read_b"),
                    ],
                    usage=None,
                )
            return SimpleNamespace(
                content="done", reasoning_content=None, tool_calls=None, usage=None
            )

        return _inner

    ctx = _base_ctx({"read_a": "shared", "read_b": "shared"})
    ctx.team_chat = _team_chat()
    ctx.execute_tool_call = _runner
    ctx.persist_step_per_tool = True
    ctx.step_branch_parent_id = None
    ctx.first_round_index = 1
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    assert persisted_calls == ["read_a", "read_b"]


@pytest.mark.asyncio
async def test_shared_sibling_failure_keeps_other_result(monkeypatch):
    """One shared call failing does not discard the sibling's result."""
    from app.services import agent_round

    persisted: list[str] = []

    async def _persist_tool_result(**kwargs):
        persisted.append(kwargs["tool_name"])
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_tool_result)
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    async def _runner(name, args, **kwargs):
        if name == "read_b":
            raise RuntimeError("boom")
        return {"result": name}

    async def _team_chat(**kwargs):
        return SimpleNamespace(
            content="",
            reasoning_content=None,
            tool_calls=[
                _tool_call("a", "read_a"),
                _tool_call("b", "read_b"),
            ],
            usage=None,
        )

    ctx = _base_ctx({"read_a": "shared", "read_b": "shared"}, max_iterations=1)
    ctx.team_chat = _team_chat
    ctx.execute_tool_call = _runner
    ctx.persist_step_per_tool = True
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    assert persisted == ["read_a", "read_b"]


@pytest.mark.asyncio
async def test_unknown_tool_is_exclusive(monkeypatch):
    """Unknown tools default to exclusive (no concurrency)."""
    from app.services import agent_round

    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def _runner(name, args, **kwargs):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        async with lock:
            active -= 1
        return {"result": name}

    async def _team_chat(**kwargs):
        return SimpleNamespace(
            content="",
            reasoning_content=None,
            tool_calls=[
                _tool_call("a", "custom_a"),
                _tool_call("b", "custom_b"),
            ],
            usage=None,
        )

    # concurrency map is empty -> both unknown -> exclusive
    ctx = _base_ctx({})
    ctx.team_chat = _team_chat
    ctx.execute_tool_call = _runner
    ctx.persist_step_per_tool = True
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    assert max_active == 1


@pytest.mark.asyncio
async def test_pause_reports_unstarted_calls_in_model_order(monkeypatch):
    """An approval pause hands over every later call, unexecuted, in order."""
    _patch_persistence(monkeypatch)

    calls = [
        _tool_call("call-a", "write_a", '{"step": "a"}'),
        _tool_call("call-b", "read_b", '{"step": "b"}'),
        _tool_call("call-c", "read_c", '{"step": "c"}'),
    ]
    _ctx, loop, pauses, tools, log = await _pause_on_first_call(calls)

    assert len(pauses.items) == 1
    pause = pauses.items[0]
    assert pause["tool_call_id"] == "call-a"
    assert pause["tool_name"] == "write_a"
    assert _signature(pause["remaining_tool_calls"]) == [
        ("call-b", "read_b", '{"step": "b"}'),
        ("call-c", "read_c", '{"step": "c"}'),
    ]
    # Only the gated call reached the runner; the suffix stayed untouched.
    assert tools.calls == [("write_a", {"step": "a"})]
    assert log == [("model", 0), ("tool", "write_a")]
    assert loop.result.waiting_for_user is True


@pytest.mark.asyncio
async def test_resume_after_approval_runs_remaining_calls_before_model(monkeypatch):
    """After an approval, the saved suffix executes in order, once each,
    and the model is only called afterwards."""
    _patch_persistence(monkeypatch)

    calls = [
        _tool_call("call-a", "write_a", '{"step": "a"}'),
        _tool_call("call-b", "read_b", '{"step": "b"}'),
        _tool_call("call-c", "read_c", '{"step": "c"}'),
    ]
    ctx, _loop, pauses, _tools, _log = await _pause_on_first_call(calls)
    pause = pauses.items[0]

    log: list[tuple[str, object]] = []
    resumed_tools = _ToolScript(log)
    resumed_pauses = _Pauses()
    resumed_ctx = _resumed_ctx(ctx, pause)
    # The worker rebuilds with the pause's iteration offset, the persisted
    # history, and the next round index.
    assert resumed_ctx.iteration_offset == pause["iteration_index"] == 1
    assert resumed_ctx.first_round_index == pause["round_index"] + 1
    assert resumed_ctx.working_history_override == ctx.working_history_override
    assert resumed_ctx.working_history_override  # assistant step survived
    resumed_ctx.team_chat = _chat_script([_final("done")], log)
    resumed_ctx.execute_tool_call = resumed_tools
    resumed_ctx.pause_for_user = resumed_pauses
    resumed_loop = AgentLoop(resumed_ctx)
    await _drain(resumed_loop)

    # Original order and arguments survive the round trip; each runs once.
    assert resumed_tools.calls == [
        ("read_b", {"step": "b"}),
        ("read_c", {"step": "c"}),
    ]
    # The provider is not consulted until the saved calls have executed.
    assert log == [("tool", "read_b"), ("tool", "read_c"), ("model", 0)]
    assert resumed_pauses.items == []
    assert resumed_loop.result.waiting_for_user is False
    assert resumed_loop.result.full_content == "done"
    # The saved calls cannot leak into the following model iteration.
    assert resumed_ctx.resume_tool_calls is None


@pytest.mark.asyncio
async def test_resume_after_rejection_skips_rejected_call_and_continues(monkeypatch):
    """A rejected call is never executed by the resumed loop; the remainder
    still runs in order before the next model turn."""
    _patch_persistence(monkeypatch)

    calls = [
        _tool_call("call-a", "write_a", '{"step": "a"}'),
        _tool_call("call-b", "read_b", '{"step": "b"}'),
        _tool_call("call-c", "read_c", '{"step": "c"}'),
    ]
    ctx, _loop, pauses, _tools, _log = await _pause_on_first_call(calls)
    pause = pauses.items[0]

    # The worker records the rejection for call-a and resumes with the suffix.
    remaining = pause["remaining_tool_calls"]
    assert "call-a" not in [call.id for call in remaining]

    log: list[tuple[str, object]] = []
    resumed_tools = _ToolScript(log)
    resumed_pauses = _Pauses()
    resumed_ctx = _resumed_ctx(ctx, pause)
    assert resumed_ctx.iteration_offset == pause["iteration_index"]
    assert resumed_ctx.working_history_override == ctx.working_history_override
    model_calls = _chat_script([_final("done")], log)
    resumed_ctx.team_chat = model_calls
    resumed_ctx.execute_tool_call = resumed_tools
    resumed_ctx.pause_for_user = resumed_pauses
    resumed_loop = AgentLoop(resumed_ctx)
    await _drain(resumed_loop)

    assert "write_a" not in [name for name, _ in resumed_tools.calls]
    assert resumed_tools.calls == [
        ("read_b", {"step": "b"}),
        ("read_c", {"step": "c"}),
    ]
    assert log == [("tool", "read_b"), ("tool", "read_c"), ("model", 0)]
    assert len(model_calls.calls) == 1
    assert resumed_pauses.items == []
    assert resumed_loop.result.full_content == "done"


@pytest.mark.asyncio
async def test_resumed_loop_pauses_again_with_only_the_remaining_suffix(monkeypatch):
    """A second approval inside the saved calls suspends again, saving only
    the calls that have not started yet."""
    _patch_persistence(monkeypatch)

    calls = [
        _tool_call("call-a", "write_a", '{"step": "a"}'),
        _tool_call("call-b", "read_b", '{"step": "b"}'),
        _tool_call("call-c", "write_c", '{"step": "c"}'),
        _tool_call("call-d", "read_d", '{"step": "d"}'),
    ]
    ctx, _loop, pauses, _tools, _log = await _pause_on_first_call(
        calls, approvals=("write_a", "write_c")
    )
    first_pause = pauses.items[0]
    first_remaining = first_pause["remaining_tool_calls"]
    assert [call.id for call in first_remaining] == ["call-b", "call-c", "call-d"]

    log: list[tuple[str, object]] = []
    tools = _ToolScript(log, approvals=("write_c",))
    second_pauses = _Pauses()
    resumed_ctx = _resumed_ctx(ctx, first_pause)
    assert resumed_ctx.iteration_offset == first_pause["iteration_index"]
    assert resumed_ctx.first_round_index == first_pause["round_index"] + 1
    assert resumed_ctx.working_history_override == ctx.working_history_override
    resumed_ctx.team_chat = _chat_script([_final("done")], log)
    resumed_ctx.execute_tool_call = tools
    resumed_ctx.pause_for_user = second_pauses
    resumed_loop = AgentLoop(resumed_ctx)
    await _drain(resumed_loop)

    assert tools.calls == [
        ("read_b", {"step": "b"}),
        ("write_c", {"step": "c"}),
    ]
    assert len(second_pauses.items) == 1
    second_pause = second_pauses.items[0]
    assert second_pause["tool_call_id"] == "call-c"
    assert _signature(second_pause["remaining_tool_calls"]) == [
        ("call-d", "read_d", '{"step": "d"}'),
    ]
    # Paused again before any provider turn after the resumed calls.
    assert [tag for tag, _ in log] == ["tool", "tool"]
    assert resumed_loop.result.waiting_for_user is True

    # A third loop with the final suffix runs it and only then calls the model.
    third_log: list[tuple[str, object]] = []
    third_tools = _ToolScript(third_log)
    final_ctx = _resumed_ctx(resumed_ctx, second_pause)
    assert final_ctx.iteration_offset == second_pause["iteration_index"]
    assert final_ctx.first_round_index == second_pause["round_index"] + 1
    assert final_ctx.working_history_override == resumed_ctx.working_history_override
    final_ctx.team_chat = _chat_script([_final("done")], third_log)
    final_ctx.execute_tool_call = third_tools
    final_ctx.pause_for_user = _Pauses()
    final_loop = AgentLoop(final_ctx)
    await _drain(final_loop)

    assert third_tools.calls == [("read_d", {"step": "d"})]
    assert third_log == [("tool", "read_d"), ("model", 0)]
    assert final_loop.result.full_content == "done"


@pytest.mark.asyncio
async def test_resumed_shared_calls_keep_concurrent_scheduling(monkeypatch):
    """The resumed scheduler is the ordinary one: saved shared calls still
    overlap and their persistence stays in model order."""
    from app.services import agent_round

    persisted: list[str] = []

    async def _persist_tool_result(**kwargs):
        persisted.append(kwargs["tool_name"])
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_tool_result)
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    concurrency = {"read_b": "shared", "read_c": "shared"}
    calls = [
        _tool_call("call-a", "write_a", '{"step": "a"}'),
        _tool_call("call-b", "read_b", '{"step": "b"}'),
        _tool_call("call-c", "read_c", '{"step": "c"}'),
    ]
    ctx, _loop, pauses, _tools, _log = await _pause_on_first_call(
        calls, concurrency=concurrency
    )
    pause = pauses.items[0]

    clock = _Clock()
    log: list[tuple[str, object]] = []
    model_started: list[float] = []

    async def _runner(name, _arguments, **_kwargs):
        clock.begin(name)
        await asyncio.sleep(0.06)
        clock.end(name)
        log.append(("tool", name))
        return {"result": name}

    async def _team_chat(**_kwargs):
        model_started.append(asyncio.get_event_loop().time())
        log.append(("model", 0))
        return _final("done")

    resumed_ctx = _resumed_ctx(ctx, pause, concurrency=concurrency)
    assert resumed_ctx.iteration_offset == pause["iteration_index"]
    assert resumed_ctx.working_history_override == ctx.working_history_override
    resumed_ctx.team_chat = _team_chat
    resumed_ctx.execute_tool_call = _runner
    resumed_ctx.pause_for_user = _Pauses()
    resumed_loop = AgentLoop(resumed_ctx)
    await _drain(resumed_loop)

    assert _overlaps(clock.windows["read_b"], clock.windows["read_c"])
    assert persisted == ["read_b", "read_c"]
    assert log[-1] == ("model", 0)
    assert len(model_started) == 1
    assert (
        max(clock.windows["read_b"][1], clock.windows["read_c"][1]) <= model_started[0]
    )
    assert resumed_loop.result.full_content == "done"
