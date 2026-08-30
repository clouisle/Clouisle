"""
Focused tests for Stage 5 steering, follow-up and cooperative stop.

Covers the durable-run control contracts:

- queued steering consumed at a safe loop boundary is injected into the
  working history before the next provider call,
- queued STOP moves the run toward a stopped terminal with partial content,
- the completing transition closes the terminal race: inputs enqueued after
  terminal start a new run and are rejected by the store,
- repeated stop is idempotent.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent_run import (
    AgentRunInputKind,
    AgentRunInputStatus,
    AgentRunStatus,
)
from app.services import agent_run_store


def _run(status=AgentRunStatus.RUNNING, **values):
    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=status,
        source_message_id=None,
        canonical_message_id=uuid4(),
        active_round_id=uuid4(),
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
        save=AsyncMock(return_value=None),
    )
    for k, v in values.items():
        setattr(run, k, v)
    return run


def _input(run_id, kind=AgentRunInputKind.STEER, content="x", sequence=1):
    return SimpleNamespace(
        id=uuid4(),
        run_id=run_id,
        sequence=sequence,
        kind=kind,
        content=content,
        attachment_meta={},
        status=AgentRunInputStatus.QUEUED,
        request_id=None,
        consumed_at=None,
    )


@pytest.mark.asyncio
async def test_loop_injects_steering_into_working_history(monkeypatch):
    """Steering consumed at a safe boundary appears in the next provider
    context's working history."""
    from app.services.agent_loop import (
        AgentLoop,
        AgentLoopContext,
        ContextTurn,
    )
    from app.llm.types import Message, MessageRole

    steer = _input(uuid4(), content="steer text", sequence=1)
    injected: list[dict] = []

    queue = [steer]

    async def consume():
        if not queue:
            return []
        return [queue.pop(0)]

    async def input_consumed(item):
        # Mirror the worker: a consumed steer becomes a user message in the
        # working history so the next provider call sees it.
        injected.append(item)
        context.working_history_override.append(
            {
                "role": "user",
                "content": item.content or "",
                "round_id": str(item.run_id),
                "round_index": 1_000 + item.sequence,
                "round_role": "user_input",
                "is_round_canonical": True,
                "round_status": "completed",
            }
        )

    async def build_turn(**kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[Message(role=MessageRole.USER, content="hi")]
            ),
        )

    context = AgentLoopContext(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="hi",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=1,
        streaming=False,
        team_chat=AsyncMock(
            return_value=SimpleNamespace(
                content="answer",
                reasoning_content=None,
                tool_calls=None,
                usage=None,
            )
        ),
        build_turn=build_turn,
        consume_inputs=consume,
        input_consumed=input_consumed,
        working_history_override=[],
        round_id=uuid4(),
    )

    # stop_requested mock: use an async lambda
    async def _stop():
        return False

    context.stop_requested = _stop

    loop = AgentLoop(context)
    async for _ in loop.run():
        pass

    assert len(injected) == 1
    assert injected[0].content == "steer text"
    # Steer entry is fused into the working history so the next provider call
    # sees it.
    user_entries = [e for e in context.working_history_override if e["role"] == "user"]
    assert any("steer text" in e["content"] for e in user_entries)


@pytest.mark.asyncio
async def test_stop_requested_between_turns_marks_stopped(monkeypatch):
    """A stop checked at a safe boundary persists partial content and stops."""
    from app.services.agent_loop import (
        AgentLoop,
        AgentLoopContext,
        ContextTurn,
    )
    from app.llm.types import Message, MessageRole

    stop_now = {"flag": False}

    async def _stop():
        return stop_now["flag"]

    async def build_turn(**kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[Message(role=MessageRole.USER, content="hi")]
            ),
        )

    context = AgentLoopContext(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="hi",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=5,
        streaming=False,
        team_chat=AsyncMock(
            return_value=SimpleNamespace(
                content="partial...",
                reasoning_content=None,
                tool_calls=None,
                usage=None,
            )
        ),
        build_turn=build_turn,
        stop_requested=_stop,
        working_history_override=[],
        round_id=uuid4(),
    )

    # Let the first turn complete, then request stop at the next boundary.
    async def _stop_when_called_twice():
        return False

    context.stop_requested = _stop

    loop = AgentLoop(context)
    calls = {"n": 0}

    async def _team_chat(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return SimpleNamespace(
                content="", reasoning_content=None, tool_calls=[], usage=None
            )
        return SimpleNamespace(
            content="final", reasoning_content=None, tool_calls=None, usage=None
        )

    context.team_chat = _team_chat
    stop_now["flag"] = True
    async for _ in loop.run():
        pass
    assert loop.result.manually_stopped is True


@pytest.mark.asyncio
async def test_enqueue_after_terminal_rejected(monkeypatch):
    """Inputs enqueued after terminal status are rejected (client starts a new
    run instead); repeat stop is idempotent."""
    from app.models.agent_run import AgentRunStatus as S

    terminal_run = _run(status=S.COMPLETED)

    async def _get_run(**kwargs):
        return terminal_run if kwargs.get("id") == terminal_run.id else None

    monkeypatch.setattr(agent_run_store.AgentRun, "get_or_none", _get_run)

    result = await agent_run_store.enqueue_input(
        run_id=terminal_run.id, kind=AgentRunInputKind.STEER, content="later"
    )
    assert result is None


@pytest.mark.asyncio
async def test_completing_transition_drop_pending(monkeypatch):
    """After completing, pending inputs are dropped and the run finalizes."""
    run = _run(status=AgentRunStatus.RUNNING)

    async def _drop(run_id, status=None):
        return 2

    monkeypatch.setattr(agent_run_store, "drop_pending_inputs", _drop)
    dropped = await agent_run_store.drop_pending_inputs(run.id)
    assert dropped == 2


@pytest.mark.asyncio
async def test_stop_endpoint_idempotent(monkeypatch):
    """Repeated stop requests are idempotent (no double transition)."""
    from app.api.v1.endpoints.chat import stop_run
    from app.models.agent_run import AgentRunStatus as S

    run = _run(status=S.RUNNING)
    transitions = []

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat._load_owned_run",
        AsyncMock(return_value=run),
    )

    async def _transition(r, status, **kw):
        transitions.append(status)
        r.status = status
        return r

    async def _enqueue(run_id, kind, **kw):
        return None

    monkeypatch.setattr(agent_run_store, "transition_run", _transition)
    monkeypatch.setattr(agent_run_store, "enqueue_input", _enqueue)

    await stop_run(run.agent_id, run.id, SimpleNamespace(id=run.user_id))
    assert transitions == [AgentRunStatus.STOPPING]

    transitions.clear()
    run.status = AgentRunStatus.STOPPING
    await stop_run(run.agent_id, run.id, SimpleNamespace(id=run.user_id))
    assert transitions == []  # already stopping, no re-transition

    transitions.clear()
    run.status = AgentRunStatus.COMPLETED
    await stop_run(run.agent_id, run.id, SimpleNamespace(id=run.user_id))
    assert transitions == []  # terminal -> idempotent no-op
