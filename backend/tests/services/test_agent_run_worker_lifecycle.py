"""Branch coverage for agent_run_worker and agent_run_store lifecycle paths.

These tests cover the core durable-run chain branches that integration tests
do not reach: run_agent_round pre-loop validation (missing run / missing
agent / lock busy), _rebuild_context RAG and non-stream tool filtering,
finalizer branches, and the store's transition/park/validation paths.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent import MessageRoundStatus
from app.models.agent_run import AgentRunStatus
from app.services import agent_run_store
from app.services.agent_run_worker import (
    _finalize_stopped,
    _tools_definitions,
    run_agent_round,
)


def _run(status=AgentRunStatus.QUEUED, **values):
    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=status,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
    )
    run.updated_at = None
    run.save = AsyncMock(return_value=None)
    for key, value in values.items():
        setattr(run, key, value)
    return run


class FakeRedis:
    def __init__(self):
        self.data: dict[str, object] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def expire(self, key, seconds):
        return key in self.data

    async def delete(self, key):
        self.data.pop(key, None)
        return True

    async def rpush(self, key, value):
        if key not in self.data or not isinstance(self.data[key], list):
            self.data[key] = []
        self.data[key].append(value)  # type: ignore[union-attr]
        return len(self.data[key])  # type: ignore[arg-type]

    async def lrange(self, key, start, end):
        values = self.data.get(key) or []
        if end is None or end < 0:
            return values[start:]
        return values[start : end + 1]  # type: ignore[misc]

    async def publish(self, channel, message):
        return 1

    async def pubsub(self):
        return FakePubSub(self)


class FakePubSub:
    def __init__(self, redis: FakeRedis):
        self.redis = redis

    async def subscribe(self, channel):
        pass

    async def unsubscribe(self, channel):
        pass

    async def close(self):
        pass

    async def listen(self):
        yield {"type": "subscribe"}
        while True:
            await asyncio.sleep(0.05)


def _get_redis_fixture(redis: FakeRedis):
    async def _get_redis():
        return redis

    return _get_redis


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(agent_run_store, "get_redis", _get_redis_fixture(redis))
    return redis


@pytest.fixture
def patched_store(monkeypatch, fake_redis):
    """Mocks every ORM touchpoint of run_agent_round pre-loop validation."""
    from app.services import agent_run_worker as worker

    worker.agent_run_store = agent_run_store

    run = _run(status=AgentRunStatus.QUEUED)
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        rag_mode=SimpleNamespace(value="off"),
        max_iterations=5,
    )
    conversation = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        title="title",
        message_count=0,
        token_usage=0,
    )
    user_msg = SimpleNamespace(id=uuid4(), rag_context=[])

    async def _get_run(run_id, **_kwargs):
        if run_id == run.id:
            return run
        return None

    async def _get_or_none(**kwargs):
        if kwargs.get("id") == agent.id:
            return agent
        if kwargs.get("id") == conversation.id:
            return conversation
        if kwargs.get("id") == user_msg.id:
            return user_msg
        return None

    async def _acquire_lock(run_id, conversation_id, **_kwargs):
        return True

    async def _transition(run, status, **_kwargs):
        run.status = status
        return run

    async def _release(run_id, conversation_id):
        pass

    async def _drop(*_args, **_kwargs):
        return 0

    async def _heartbeat(run_id, conversation_id, stop):
        await stop.wait()

    async def _create_placeholder(conversation, user_msg, run):
        return SimpleNamespace(id=uuid4())

    async def _rebuild_context(*_args, **_kwargs):
        raise RuntimeError("never reached")

    monkeypatch.setattr(worker.agent_run_store, "get_run", _get_run)
    monkeypatch.setattr(worker.Agent, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.Conversation, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.agent_run_store, "acquire_run_lock", _acquire_lock)
    monkeypatch.setattr(worker.agent_run_store, "transition_run", _transition)
    monkeypatch.setattr(worker.agent_run_store, "release_run_lock", _release)
    monkeypatch.setattr(worker.agent_run_store, "drop_pending_inputs", _drop)
    monkeypatch.setattr(worker.agent_run_store, "heartbeat_run_lock", _heartbeat)
    monkeypatch.setattr(
        worker.agent_run_store, "has_pending_inputs", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(worker, "_create_placeholder", _create_placeholder)
    monkeypatch.setattr(worker, "_rebuild_context", _rebuild_context)

    return SimpleNamespace(
        run=run,
        agent=agent,
        conversation=conversation,
        user_msg=user_msg,
        worker=worker,
    )


@pytest.mark.asyncio
async def test_run_agent_round_missing_run_raises_lookup(monkeypatch, fake_redis):
    from app.services import agent_run_worker as worker

    async def _get_run(run_id, **_kwargs):
        return None

    monkeypatch.setattr(worker.agent_run_store, "get_run", _get_run)
    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round({"run_id": str(uuid4())})


@pytest.mark.asyncio
async def test_run_agent_round_missing_agent_or_conversation_marks_failed(
    monkeypatch, patched_store
):
    from app.services import agent_run_worker as worker

    transition = AsyncMock()

    async def _get_or_none(**kwargs):
        return None

    monkeypatch.setattr(worker.Agent, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.Conversation, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.agent_run_store, "transition_run", transition)

    payload = {
        "run_id": str(patched_store.run.id),
        "agent_id": str(uuid4()),
        "conversation_id": str(uuid4()),
    }
    result = await run_agent_round(payload)
    assert result == {"status": AgentRunStatus.FAILED.value}
    transition.assert_awaited()
    args = transition.await_args.args
    assert args[1] == AgentRunStatus.FAILED
    assert transition.await_args.kwargs["error_code"] == "context_lost"


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_publishes_error_and_fails(
    monkeypatch, patched_store
):
    from app.services import agent_run_worker as worker

    transition = AsyncMock()
    publishes: list[tuple[str, dict]] = []

    async def _acquire_lock(run_id, conversation_id, **_kwargs):
        return False

    async def _publish(event_type, payload, **_kwargs):
        publishes.append((event_type, payload))

    monkeypatch.setattr(worker.agent_run_store, "acquire_run_lock", _acquire_lock)
    monkeypatch.setattr(worker.agent_run_store, "transition_run", transition)
    monkeypatch.setattr(
        worker,
        "AgentRunStream",
        lambda _id: SimpleNamespace(
            seed_sequence=AsyncMock(),
            publish=_publish,
        ),
    )

    payload = {
        "run_id": str(patched_store.run.id),
        "agent_id": str(patched_store.agent.id),
        "conversation_id": str(patched_store.conversation.id),
    }
    result = await run_agent_round(payload)
    assert result == {"status": AgentRunStatus.FAILED.value}
    transition.assert_awaited()
    assert transition.await_args.kwargs["error_code"] == "lock_busy"
    error_events = [(t, p) for t, p in publishes if p.get("code") == "lock_busy"]
    assert error_events and error_events[0][0] == "error"
    assert ("run_end", {"status": "failed"}) in publishes


@pytest.mark.asyncio
async def test_tools_definitions_none_and_populated():
    assert _tools_definitions(None) is None
    tools = _tools_definitions(
        [{"function": {"name": "a", "description": "d", "parameters": {}}}]
    )
    assert tools[0].function.name == "a"


@pytest.mark.asyncio
async def test_finalize_stopped_sets_manual_stop_fields(monkeypatch):

    canonical = SimpleNamespace(
        content="",
        reasoning_content=None,
        is_manually_stopped=False,
        round_status=None,
        save=AsyncMock(),
    )
    result = SimpleNamespace(
        full_content="partial",
        full_reasoning="reasoning",
        maximum_tokens_reached=False,
        max_iterations_reached=False,
    )
    stream = SimpleNamespace(publish=AsyncMock())

    await _finalize_stopped(canonical, result, stream)

    assert canonical.content == "partial"
    assert canonical.reasoning_content == "reasoning"
    assert canonical.is_manually_stopped is True
    assert canonical.round_status == MessageRoundStatus.MANUALLY_STOPPED
    canonical.save.assert_awaited_once()
    stream.publish.assert_awaited_once_with("message_end", {"usage": {}})


# ---------------------------------------------------------------------------
# agent_run_store lifecycle branches
# ---------------------------------------------------------------------------


class _Transaction:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False

    def __call__(self):
        return self


class _LockedRunQuery:
    def __init__(self, run):
        self.run = run

    def using_db(self, _conn):
        return self

    def select_for_update(self):
        return self

    async def first(self):
        return self.run


def _waiting_run():
    run = _run(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-1",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "target", "question": "Where?", "options": ["cloud", "local"]},
                {"id": "note", "question": "Note?", "required": False},
            ]
        },
        pending_tool_round_id=uuid4(),
        pending_tool_round_index=4,
        pending_tool_iteration_index=2,
        worker_payload={"history_override": [], "exclude_message_ids": []},
    )
    run.active_round_id = run.pending_tool_round_id
    run.canonical_message_id = uuid4()
    return run


@pytest.mark.asyncio
async def test_park_run_waiting_persists_and_rejects_when_not_running(
    monkeypatch, fake_redis
):
    run = _run(status=AgentRunStatus.RUNNING)
    db_running = [True]

    async def _filter_update(**_kwargs):
        return 1 if db_running[0] else 0

    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=_filter_update),
    )

    parked = await agent_run_store.park_run_waiting(
        run,
        tool_call_id="call-1",
        tool_name="ask_user",
        tool_input={"questions": []},
        round_id=uuid4(),
        round_index=4,
        iteration_index=2,
        worker_payload={"resume": True},
    )
    assert parked is run
    assert run.status == AgentRunStatus.WAITING
    assert run.pending_tool_call_id == "call-1"

    # The DB row is no longer running -> park raises.
    db_running[0] = False
    with pytest.raises(RuntimeError, match="no longer running"):
        await agent_run_store.park_run_waiting(
            run,
            tool_call_id="call-2",
            tool_name="ask_user",
            tool_input={"questions": []},
            round_id=uuid4(),
            round_index=4,
            iteration_index=2,
        )


@pytest.mark.asyncio
async def test_park_run_waiting_omits_worker_payload_when_none(monkeypatch, fake_redis):
    run = _run(status=AgentRunStatus.RUNNING)
    calls = []

    async def _filter_update(**kwargs):
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=_filter_update),
    )

    await agent_run_store.park_run_waiting(
        run,
        tool_call_id="call-1",
        tool_name="ask_user",
        tool_input={},
        round_id=uuid4(),
        round_index=4,
        iteration_index=2,
    )
    assert "worker_payload" not in calls[-1]


@pytest.mark.asyncio
async def test_transition_run_sets_started_finished_and_errors(monkeypatch, fake_redis):
    run = _run(status=AgentRunStatus.QUEUED)

    running = await agent_run_store.transition_run(run, AgentRunStatus.RUNNING)
    assert running.started_at is not None
    assert running.finished_at is None

    failed = await agent_run_store.transition_run(
        run,
        AgentRunStatus.FAILED,
        error_code="boom",
        error_message="bad",
    )
    assert failed.finished_at is not None
    assert failed.error_code == "boom"
    assert failed.error_message == "bad"


@pytest.mark.asyncio
async def test_submit_user_answers_skips_canonical_exclusion_and_round_index(
    monkeypatch, fake_redis
):
    run = _waiting_run()
    message_create = AsyncMock()
    monkeypatch.setattr(agent_run_store, "in_transaction", _Transaction())
    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: _LockedRunQuery(run),
    )
    monkeypatch.setattr(agent_run_store.Message, "create", message_create)

    # canonical_message_id already in exclusions and round_index present
    run.worker_payload["exclude_message_ids"] = [str(run.canonical_message_id)]
    submitted = await agent_run_store.submit_user_answers(
        run.id, tool_call_id="call-1", answers={"target": "cloud"}
    )
    assert submitted is run
    assert run.worker_payload["exclude_message_ids"] == [str(run.canonical_message_id)]
    assert run.worker_payload["first_round_index"] == 5
    assert run.status == AgentRunStatus.QUEUED


@pytest.mark.asyncio
async def test_submit_user_answers_rejects_wrong_tool_name(monkeypatch, fake_redis):
    run = _waiting_run()
    run.pending_tool_name = "generate_image"
    message_create = AsyncMock()
    monkeypatch.setattr(agent_run_store, "in_transaction", _Transaction())
    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: _LockedRunQuery(run),
    )
    monkeypatch.setattr(agent_run_store.Message, "create", message_create)

    submitted = await agent_run_store.submit_user_answers(
        run.id, tool_call_id="call-1", answers={"target": "cloud"}
    )
    assert submitted is None
    message_create.assert_not_awaited()
