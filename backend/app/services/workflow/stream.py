"""
Stream manager for workflow execution events.

Handles streaming output to clients via SSE (Server-Sent Events).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, cast
import asyncio
import json
import logging

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class StreamEventType(Enum):
    """Types of stream events."""

    # Workflow lifecycle events
    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_ERROR = "workflow_error"

    # Node lifecycle events
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"
    NODE_ERROR = "node_error"
    NODE_SKIP = "node_skip"

    # Output events
    TOKEN = "token"  # LLM token streaming
    CHUNK = "chunk"  # Generic chunk output
    OUTPUT = "output"  # Final output

    # Progress events
    PROGRESS = "progress"  # Progress update
    STATUS = "status"  # Status change

    # Iteration events
    ITERATION_START = "iteration_start"
    ITERATION_COMPLETE = "iteration_complete"

    # Debug events
    DEBUG = "debug"  # Debug info (only in debug mode)


@dataclass
class StreamEvent:
    """
    A stream event to be sent to clients.

    Attributes:
        event_type: Type of the event
        data: Event data payload
        node_id: Associated node ID (if applicable)
        timestamp: Event timestamp
        sequence: Event sequence number
    """

    event_type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)
    node_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sequence: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "event": self.event_type.value,
            "data": self.data,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
        }

    def to_sse(self) -> str:
        """Convert to SSE format."""
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"event: {self.event_type.value}\ndata: {data}\n\n"


class StreamManager:
    """
    Manages streaming events for a workflow run.

    Features:
    - Publish events to Redis Pub/Sub
    - Subscribe to events for SSE streaming
    - Buffer events for late subscribers
    - Sequence numbering for ordering
    """

    def __init__(self, run_id: str):
        """
        Initialize stream manager.

        Args:
            run_id: Workflow run ID
        """
        self.run_id = run_id
        self._channel = f"workflow:run:{run_id}:stream"
        self._buffer_key = f"workflow:run:{run_id}:events"
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def publish(self, event: StreamEvent) -> None:
        """
        Publish a stream event.

        Args:
            event: Event to publish
        """
        redis = await get_redis()

        async with self._lock:
            self._sequence += 1
            event.sequence = self._sequence

        event_data = event.to_dict()
        event_json = json.dumps(event_data, ensure_ascii=False)

        # Publish to channel
        publish_result = redis.publish(self._channel, event_json)
        if asyncio.iscoroutine(publish_result):
            await publish_result

        # Also store in buffer list for late subscribers
        rpush_result = redis.rpush(self._buffer_key, event_json)
        if asyncio.iscoroutine(rpush_result):
            await rpush_result
        # Keep buffer for 1 hour
        expire_result = redis.expire(self._buffer_key, 3600)
        if asyncio.iscoroutine(expire_result):
            await expire_result

        logger.debug(
            f"Published event {event.event_type.value} "
            f"for run {self.run_id}, seq={event.sequence}"
        )

    async def publish_workflow_start(
        self,
        workflow_id: str,
        workflow_name: str,
        inputs: dict,
    ) -> None:
        """Publish workflow start event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.WORKFLOW_START,
                data={
                    "workflow_id": str(workflow_id),
                    "workflow_name": workflow_name,
                    "inputs": inputs,
                },
            )
        )

    async def publish_workflow_complete(
        self,
        outputs: dict,
        duration_ms: int,
    ) -> None:
        """Publish workflow complete event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.WORKFLOW_COMPLETE,
                data={
                    "outputs": outputs,
                    "duration_ms": duration_ms,
                },
            )
        )

    async def publish_workflow_error(
        self,
        error: str,
        node_id: str | None = None,
    ) -> None:
        """Publish workflow error event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.WORKFLOW_ERROR,
                data={"error": error},
                node_id=node_id,
            )
        )

    async def publish_node_start(
        self,
        node_id: str,
        node_type: str,
        node_label: str | None = None,
        is_streaming: bool = False,
    ) -> None:
        """Publish node start event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.NODE_START,
                node_id=node_id,
                data={
                    "node_type": node_type,
                    "node_label": node_label,
                    "is_streaming": is_streaming,
                },
            )
        )

    async def publish_node_complete(
        self,
        node_id: str,
        outputs: dict,
        duration_ms: int,
        node_type: str | None = None,
        is_streaming: bool = False,
    ) -> None:
        """Publish node complete event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.NODE_COMPLETE,
                node_id=node_id,
                data={
                    "outputs": outputs,
                    "duration_ms": duration_ms,
                    "node_type": node_type,
                    "is_streaming": is_streaming,
                },
            )
        )

    async def publish_node_error(
        self,
        node_id: str,
        error: str,
    ) -> None:
        """Publish node error event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.NODE_ERROR,
                node_id=node_id,
                data={"error": error},
            )
        )

    async def publish_node_skip(
        self,
        node_id: str,
        reason: str = "branch_not_taken",
        node_type: str | None = None,
        node_label: str | None = None,
    ) -> None:
        """Publish node skip event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.NODE_SKIP,
                node_id=node_id,
                data={
                    "reason": reason,
                    "node_type": node_type,
                    "node_label": node_label or node_id,
                },
            )
        )

    async def publish_token(
        self,
        node_id: str,
        token: str,
    ) -> None:
        """Publish LLM token event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.TOKEN,
                node_id=node_id,
                data={"token": token},
            )
        )

    async def publish_chunk(
        self,
        node_id: str,
        chunk: str,
        chunk_type: str = "text",
    ) -> None:
        """Publish chunk output event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.CHUNK,
                node_id=node_id,
                data={
                    "chunk": chunk,
                    "type": chunk_type,
                },
            )
        )

    async def publish_output(
        self,
        node_id: str,
        output: Any,
        output_name: str = "result",
    ) -> None:
        """Publish final output event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.OUTPUT,
                node_id=node_id,
                data={
                    "output": output,
                    "name": output_name,
                },
            )
        )

    async def publish_progress(
        self,
        current: int,
        total: int,
        message: str | None = None,
    ) -> None:
        """Publish progress update event."""
        await self.publish(
            StreamEvent(
                event_type=StreamEventType.PROGRESS,
                data={
                    "current": current,
                    "total": total,
                    "percentage": (current / total * 100) if total > 0 else 0,
                    "message": message,
                },
            )
        )

    async def publish_iteration(
        self,
        node_id: str,
        iteration: int,
        total: int,
        is_start: bool = True,
        item: Any = None,
    ) -> None:
        """Publish iteration event."""
        event_type = (
            StreamEventType.ITERATION_START
            if is_start
            else StreamEventType.ITERATION_COMPLETE
        )
        data = {
            "iteration": iteration,
            "total": total,
        }
        if item is not None and is_start:
            data["item"] = item

        await self.publish(
            StreamEvent(
                event_type=event_type,
                node_id=node_id,
                data=data,
            )
        )

    async def subscribe(
        self,
        from_sequence: int = 0,
    ) -> AsyncIterator[StreamEvent]:
        """
        Subscribe to stream events.

        Args:
            from_sequence: Start from this sequence number (for reconnection)

        Yields:
            StreamEvent objects
        """
        redis = await get_redis()

        # First, send buffered events
        if from_sequence > 0:
            buffered_result = redis.lrange(self._buffer_key, 0, -1)
            buffered = cast(
                list[str],
                await buffered_result
                if asyncio.iscoroutine(buffered_result)
                else buffered_result,
            )
            for event_json in buffered:
                try:
                    event_data = json.loads(event_json)
                    if event_data.get("sequence", 0) > from_sequence:
                        yield self._parse_event(event_data)
                except json.JSONDecodeError:
                    continue

        # Subscribe to live events
        pubsub = redis.pubsub()
        await pubsub.subscribe(self._channel)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    event_data = json.loads(message["data"])
                    event = self._parse_event(event_data)

                    if event.sequence <= from_sequence:
                        continue

                    yield event

                    # Stop on terminal events
                    if event.event_type in {
                        StreamEventType.WORKFLOW_COMPLETE,
                        StreamEventType.WORKFLOW_ERROR,
                    }:
                        break

                except json.JSONDecodeError:
                    continue

        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()

    def _parse_event(self, data: dict) -> StreamEvent:
        """Parse event from dictionary."""
        return StreamEvent(
            event_type=StreamEventType(data.get("event", "status")),
            data=data.get("data", {}),
            node_id=data.get("node_id"),
            timestamp=datetime.fromisoformat(
                data.get("timestamp", datetime.utcnow().isoformat())
            ),
            sequence=data.get("sequence", 0),
        )

    async def get_all_events(self) -> list[StreamEvent]:
        """
        Get all buffered events.

        Returns:
            List of all events in order
        """
        redis = await get_redis()
        buffered_result = redis.lrange(self._buffer_key, 0, -1)
        buffered = cast(
            list[str],
            await buffered_result
            if asyncio.iscoroutine(buffered_result)
            else buffered_result,
        )

        events: list[StreamEvent] = []
        for event_json in buffered:
            try:
                event_data = json.loads(event_json)
                events.append(self._parse_event(event_data))
            except json.JSONDecodeError:
                continue

        return events

    async def clear(self) -> None:
        """Clear all buffered events."""
        redis = await get_redis()
        await redis.delete(self._buffer_key)


async def stream_to_sse(
    run_id: str,
    from_sequence: int = 0,
) -> AsyncIterator[str]:
    """
    Stream workflow events as SSE.

    Args:
        run_id: Workflow run ID
        from_sequence: Start from this sequence number

    Yields:
        SSE formatted strings
    """
    manager = StreamManager(run_id)

    async for event in manager.subscribe(from_sequence):
        yield event.to_sse()
