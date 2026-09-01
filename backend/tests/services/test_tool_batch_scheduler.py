"""
Focused tests for Stage 7 shared/exclusive tool batch scheduling.

Contracts:

- consecutive shared tool calls overlap in wall-clock execution,
- shared -> exclusive -> shared has no overlap across the exclusive barrier,
- persistence/provider order matches the model's original tool-call order
  even when completion order differs,
- one shared sibling failure does not discard the other's result,
- default classification is exclusive (unknown tools never run concurrently).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import FunctionCall, ToolCall
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn


def _tool_call(call_id, name):
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments="{}"))


def _prepared():
    from app.llm.types import Message as LM, MessageRole

    return SimpleNamespace(messages=[LM(role=MessageRole.USER, content="hi")])


def _base_ctx(concurrency_map, *, max_iterations=2):
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    conversation = SimpleNamespace(id=uuid4())
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
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        formatter=None,
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
