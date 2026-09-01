"""
Focused tests for durable AgentRun store, stream, and endpoints.

The Tortoise ORM is mocked at the model level (project convention), and the
Redis transport is a tiny in-memory fake so replay/lock logic is exercised
without a live Redis.

Contracts under test:

- run status transitions and terminal persistence,
- one active-run lock per conversation (second start fails to acquire;
  expired lease marks the run interrupted and releases the lock),
- replay-before-live event streaming: subscriber after sequence N receives
  exactly N+1 onward, terminal event closes the stream,
- queued input enqueue/consume ordering and request-id idempotency,
- run endpoints enforce owner/agent scope.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent_run import (
    AgentRunInputKind,
    AgentRunStatus,
)
from app.services import agent_run_store, agent_run_stream


class FakeRedis:
    """Minimal in-memory Redis for list/set/get/expire/publish/pubsub."""

    def __init__(self):
        self.data: dict[str, object] = {}
        self.channels: dict[str, list[str]] = {}
        self.subscribed: list[str] = []

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
        self.channels.setdefault(channel, []).append(message)
        return 1

    async def pubsub(self):
        return FakePubSub(self)


class FakePubSub:
    def __init__(self, redis: FakeRedis):
        self.redis = redis

    async def subscribe(self, channel):
        self.redis.subscribed.append(channel)

    async def unsubscribe(self, channel):
        if channel in self.redis.subscribed:
            self.redis.subscribed.remove(channel)

    async def close(self):
        pass

    async def listen(self):
        yield {"type": "subscribe"}
        for message in self.redis.channels.get("agent:run:stream", []):
            yield {"type": "message", "data": message}
        # End live listen.
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
    monkeypatch.setattr(agent_run_stream, "get_redis", _get_redis_fixture(redis))
    return redis


def _fake_run(status=AgentRunStatus.QUEUED, **values):
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


@pytest.mark.asyncio
async def test_lock_excludes_second_run_and_release(monkeypatch, fake_redis):
    """One active-run lock per conversation; owner refresh/release only."""
    from app.services import agent_run_store as store

    conversation_id = uuid4()
    run_a = uuid4()
    run_b = uuid4()

    assert await store.acquire_run_lock(run_a, conversation_id) is True
    assert await store.acquire_run_lock(run_b, conversation_id) is False
    assert await store.refresh_run_lock(run_a, conversation_id) is True
    assert await store.refresh_run_lock(run_b, conversation_id) is False

    # Non-owner release is a no-op; owner release works.
    await store.release_run_lock(run_b, conversation_id)
    assert await store.is_run_lock_owner(run_a, conversation_id) is True
    await store.release_run_lock(run_a, conversation_id)
    assert await store.is_run_lock_owner(run_a, conversation_id) is False


@pytest.mark.asyncio
async def test_run_transition_sets_terminal_and_caches(monkeypatch, fake_redis):
    from app.services import agent_run_store as store

    run = _fake_run()
    updated = await store.transition_run(run, AgentRunStatus.COMPLETED)
    assert updated.status == AgentRunStatus.COMPLETED
    assert updated.finished_at is not None
    run.save.assert_awaited_once()
    cached = await store.get_cached_run_status(run.id)
    assert cached == AgentRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_stream_replay_before_live_and_resume_after_sequence(
    monkeypatch, fake_redis
):
    stream = agent_run_stream.AgentRunStream(uuid4())
    await stream.publish("run_start", {"status": "running"})
    await stream.publish("tool_call", {"name": "x"})
    await stream.publish("run_end", {"status": "completed"})

    replayed = [e async for e in stream.subscribe(from_sequence=0)]
    types = [e.get("type") for e in replayed]
    assert types == ["run_start", "tool_call", "run_end"]
    sequences = [e.get("sequence") for e in replayed]
    assert sequences == [1, 2, 3]

    # A resumed subscriber uses a fresh instance seeded from the buffer,
    # mirroring how the workflow StreamManager continues sequences across
    # reconnect passes: after sequence 1 -> exactly 2 onward.
    resume_stream = agent_run_stream.AgentRunStream(stream.run_id)
    await resume_stream.seed_sequence()
    resumed = [e async for e in resume_stream.subscribe(from_sequence=1)]
    assert [e.get("sequence") for e in resumed] == [2, 3]
    assert [e.get("type") for e in resumed] == ["tool_call", "run_end"]


@pytest.mark.asyncio
async def test_stream_events_all_and_clear(monkeypatch, fake_redis):
    stream = agent_run_stream.AgentRunStream(uuid4())
    await stream.publish("message_start", {"message_id": str(uuid4())})
    events = await stream.get_all_events()
    assert len(events) == 1
    assert events[0]["type"] == "message_start"
    await stream.clear()
    assert await stream.get_all_events() == []


@pytest.mark.asyncio
async def test_enqueue_input_ordering_and_idempotency(monkeypatch, fake_redis):
    from app.services import agent_run_store as store

    run_id = uuid4()
    created: list[SimpleNamespace] = []
    run = _fake_run(status=AgentRunStatus.RUNNING)
    run.id = run_id

    async def _get_run(**kwargs):
        if kwargs.get("id") == run_id:
            return run
        return None

    async def _create(**values):
        entry = SimpleNamespace(
            id=uuid4(),
            run_id=run_id,
            sequence=values["sequence"],
            kind=values["kind"],
            content=values.get("content"),
            attachment_meta=values.get("attachment_meta", {}),
            status=values.get("status"),
            request_id=values.get("request_id"),
            consumed_at=None,
            save=AsyncMock(return_value=None),
        )
        created.append(entry)
        return entry

    async def _first_ordered(filter_qs):
        if created:
            return created[0]
        return None

    class _OrderedQS:
        def __init__(self, entries):
            self.entries = entries

        def first(self):
            return _first_ordered_coro(self.entries)

    async def _first_ordered_coro(entries):
        return entries[0] if entries else None

    monkeypatch.setattr(store.AgentRun, "get_or_none", _get_run)

    async def _first_qs(entries):
        return entries[0] if entries else None

    def _ordered_first(entries):
        async def _first():
            return entries[0] if entries else None

        return _first

    class _OrderedQS:
        def __init__(self, entries):
            self.entries = entries

        def order_by(self, _field):
            return self

        def first(self):
            return _ordered_first(self.entries)()

    def _filter_qs(*args, **kwargs):
        if kwargs.get("run_id") == run_id and "status" in kwargs:
            return _OrderedQS([e for e in created if e.status.value == "queued"])
        if kwargs.get("run_id") == run_id:
            return _OrderedQS(created)
        return _OrderedQS([])

    monkeypatch.setattr(store.AgentRunInput, "filter", _filter_qs)
    monkeypatch.setattr(
        store.AgentRunInput, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(store.AgentRunInput, "create", _create)

    await store.enqueue_input(run_id=run_id, kind=AgentRunInputKind.STEER, content="a")
    await store.enqueue_input(run_id=run_id, kind=AgentRunInputKind.STOP)
    assert created[0].sequence == 1
    assert created[1].sequence == 2

    # Same request id returns the existing row (idempotent).
    monkeypatch.setattr(
        store.AgentRunInput, "get_or_none", AsyncMock(return_value=created[0])
    )
    dup = await store.enqueue_input(
        run_id=run_id, kind=AgentRunInputKind.STEER, content="a", request_id="req-1"
    )
    assert dup is created[0]


@pytest.mark.asyncio
async def test_worker_loss_marks_interrupted(monkeypatch, fake_redis):
    from app.services import agent_run_store as store

    stale_run = _fake_run(status=AgentRunStatus.RUNNING)
    stale_run.started_at = datetime.now(UTC) - timedelta(minutes=10)
    stale_run.conversation_id = uuid4()
    transitioned = AsyncMock(return_value=stale_run)

    async def _all():
        return [stale_run]

    monkeypatch.setattr(
        store.AgentRun, "filter", lambda **_k: SimpleNamespace(all=_all)
    )
    monkeypatch.setattr(store, "transition_run", transitioned)

    # Lock key absent -> not owned -> interrupted exactly once.
    marked = await store.mark_expired_runs_interrupted(max_age_seconds=120)
    assert marked == 1
    transitioned.assert_awaited_once()
    args = transitioned.await_args.args
    assert args[1] == AgentRunStatus.INTERRUPTED


@pytest.mark.asyncio
async def test_run_endpoint_scope_checks(monkeypatch):
    """Wrong agent or non-owner cannot inspect a run."""
    from app.api.v1.endpoints import chat as chat_api
    from app.schemas.response import BusinessError, ResponseCode

    run_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    agent_id = uuid4()
    conversation = SimpleNamespace(id=uuid4(), user=user)

    async def _run_lookup(**kwargs):
        if kwargs.get("id") == run_id and kwargs.get("agent_id") == agent_id:
            return SimpleNamespace(
                id=run_id,
                agent_id=agent_id,
                conversation_id=conversation.id,
                mode=SimpleNamespace(value="send"),
                status=SimpleNamespace(value="running"),
                source_message_id=None,
                canonical_message_id=None,
                active_round_id=None,
                error_code=None,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
        return None

    async def _conv_lookup(**kwargs):
        if kwargs.get("id") == conversation.id and kwargs.get("user") is user:
            return conversation
        return None

    monkeypatch.setattr("app.models.agent_run.AgentRun.get_or_none", _run_lookup)
    monkeypatch.setattr("app.models.agent.Conversation.get_or_none", _conv_lookup)

    # Wrong agent -> not found.
    with pytest.raises(BusinessError) as exc_a:
        await chat_api._load_owned_run(uuid4(), run_id, user)
    assert exc_a.value.code == ResponseCode.NOT_FOUND

    # Right agent, unauthorized user -> forbidden.
    other_user = SimpleNamespace(id=uuid4())
    with pytest.raises(BusinessError) as exc_b:
        await chat_api._load_owned_run(agent_id, run_id, other_user)
    assert exc_b.value.code == ResponseCode.FORBIDDEN

    # Right owner -> returns run.
    run = await chat_api._load_owned_run(agent_id, run_id, user)
    assert run.id == run_id


def test_worker_formatter_queues_structured_sse_payload():
    """Loop-generated tool SSE is persisted as a typed payload, not raw text."""
    from app.services.agent_run_worker import _RunFormatter

    queue: asyncio.Queue = asyncio.Queue()
    formatter = _RunFormatter(queue, agent=SimpleNamespace())

    assert (
        formatter(
            "tool_call",
            {
                "sse": (
                    "event: tool_call"
                    + chr(10)
                    + 'data: {"tool_call_id":"call-1","tool_name":"clock"}'
                    + chr(10)
                    + chr(10)
                )
            },
        )
        is None
    )
    event_type, payload = queue.get_nowait()
    assert event_type == "tool_call"
    assert payload == {"tool_call_id": "call-1", "tool_name": "clock"}


@pytest.mark.asyncio
async def test_finalize_completed_sets_initial_conversation_title(monkeypatch):
    from app.services import agent_run_worker

    conversation = SimpleNamespace(
        id=uuid4(),
        title=None,
        message_count=0,
        token_usage=0,
    )
    agent = SimpleNamespace(
        id=uuid4(),
        message_count=0,
        total_tokens=0,
    )
    canonical = SimpleNamespace(
        id=uuid4(),
        branch_parent_id=None,
        content="",
        reasoning_content=None,
        model_used=None,
        duration_ms=10,
        first_token_ms=2,
        is_manually_stopped=False,
        round_status=None,
        round_index=0,
        token_usage=None,
        save=AsyncMock(),
    )
    result = SimpleNamespace(
        full_content="answer",
        full_reasoning="",
        max_iterations_reached=False,
        aggregate_input_tokens=3,
        aggregate_output_tokens=4,
        aggregate_cache_read_tokens=0,
        aggregate_cache_creation_tokens=0,
        aggregate_total_input_tokens=3,
        duration_ms=10,
        first_token_ms=2,
        created_message_count=2,
        final_round_index=1,
    )
    conversation_update = AsyncMock()
    agent_update = AsyncMock()
    monkeypatch.setattr(
        agent_run_worker.Conversation,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=conversation_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Agent,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=agent_update),
    )
    monkeypatch.setattr(
        agent_run_worker.Message,
        "get_or_none",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.message_branching.activate_conversation_branch",
        AsyncMock(),
    )

    await agent_run_worker._finalize_completed(
        canonical,
        result,
        conversation,
        agent,
        SimpleNamespace(publish=AsyncMock()),
        user_message=SimpleNamespace(content="x" * 51),
        model_used="model",
        locale="en",
    )

    assert conversation_update.await_args.kwargs["title"] == ("x" * 50) + "..."
