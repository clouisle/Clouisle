"""Replayable per-run event transport.

Follows the workflow ``StreamManager`` replay-before-live pattern: events are
persisted to a bounded Redis list BEFORE publication, sequences are monotonic
per run, and late subscribers replay from their last applied sequence before
switching to live Pub/Sub. Redis here is transport only; PostgreSQL remains
the terminal source of truth.

Event envelope (see ``agent_loop_events.AgentLoopEvent``):

    run_id, sequence, timestamp, round_id?, message_id?, payload
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from app.core.redis import get_redis
from app.services.agent_loop_events import AgentLoopEvent, EventSink

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "agent:run:{run_id}:events"
BUFFER_PREFIX = "agent:run:{run_id}:buffer"
BUFFER_TTL_SECONDS = 3600 * 24
TERMINAL_EVENT_TYPES = {"run_end", "error"}


class AgentRunStream(EventSink):
    """Buffers and publishes typed events for one run.

    Uses the same instance for the whole worker run so ``publish`` and
    ``subscribe`` share a monotonic sequence counter. Fresh instances created
    by resuming subscribers must call ``seed_sequence`` first so reconnects
    continue from the buffered tail.
    """

    def __init__(self, run_id: UUID) -> None:
        super().__init__()
        self.run_id = run_id
        self._channel = CHANNEL_PREFIX.format(run_id=run_id)
        self._buffer_key = BUFFER_PREFIX.format(run_id=run_id)
        self._lock = asyncio.Lock()

    async def seed_sequence(self) -> None:
        """Continue the per-run sequence from buffered events (resume passes)."""
        redis = await get_redis()
        buffered = await redis.lrange(self._buffer_key, 0, -1)
        for event_json in buffered:
            try:
                self._sequence = max(
                    self._sequence,
                    int(json.loads(event_json).get("sequence", 0)),
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        **envelope: Any,
    ) -> AgentLoopEvent:
        """Stamp, persist, then broadcast one event."""
        event = self.emit(event_type, payload, **envelope)
        redis = await get_redis()
        async with self._lock:
            if event.sequence == 0:
                self._sequence += 1
                event.sequence = self._sequence
            envelope_payload = {
                **event.envelope(),
                "type": event.type,
                "payload": event.payload,
            }
            event_json = json.dumps(envelope_payload, ensure_ascii=False, default=str)
            await redis.rpush(self._buffer_key, event_json)
            await redis.expire(self._buffer_key, BUFFER_TTL_SECONDS)
            await redis.publish(self._channel, event_json)
        return event

    async def get_all_events(self) -> list[dict[str, Any]]:
        redis = await get_redis()
        buffered = await redis.lrange(self._buffer_key, 0, -1)
        events: list[dict[str, Any]] = []
        for event_json in buffered:
            try:
                events.append(json.loads(event_json))
            except json.JSONDecodeError:
                continue
        return events

    async def subscribe(
        self,
        from_sequence: int = 0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield buffered and live events newer than ``from_sequence``.

        Sequence 0 replays the full buffered run (worker may have finished
        before the subscriber connects). Live delivery stops after a terminal
        event.
        """
        redis = await get_redis()
        buffered = await redis.lrange(self._buffer_key, 0, -1)
        buffered_events: list[dict[str, Any]] = []
        for event_json in buffered:
            try:
                buffered_events.append(json.loads(event_json))
            except json.JSONDecodeError:
                continue
        for event in buffered_events:
            if event.get("sequence", 0) > from_sequence:
                yield event
        if buffered_events and buffered_events[-1].get("type") in TERMINAL_EVENT_TYPES:
            return

        pubsub = redis.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                    if event.get("sequence", 0) <= from_sequence:
                        continue
                    yield event
                    if event.get("type") in TERMINAL_EVENT_TYPES:
                        break
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()

    async def clear(self) -> None:
        redis = await get_redis()
        await redis.delete(self._buffer_key)


async def sse_events(
    run_id: UUID,
    from_sequence: int = 0,
) -> AsyncIterator[str]:
    """Stream run events as SSE strings (replay then live, then terminal)."""
    stream = AgentRunStream(run_id)
    async for event in stream.subscribe(from_sequence):
        data = json.dumps(event, ensure_ascii=False, default=str)
        yield f"event: {event.get('type', 'message')}\ndata: {data}\n\n"
