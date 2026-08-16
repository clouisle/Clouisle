import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.workflow.stream import (
    StreamEvent,
    StreamEventType,
    StreamManager,
    stream_to_sse,
)


@pytest.mark.asyncio
async def test_publish_numbers_and_persists_events():
    redis = Mock()
    redis.publish = AsyncMock()
    redis.rpush = AsyncMock()
    redis.expire = AsyncMock()
    manager = StreamManager("run-1")
    first = StreamEvent(StreamEventType.TOKEN, {"token": "你"})
    second = StreamEvent(StreamEventType.WORKFLOW_COMPLETE, {"outputs": {}})

    with patch("app.services.workflow.stream.get_redis", AsyncMock(return_value=redis)):
        await manager.publish(first)
        await manager.publish(second)

    assert (first.sequence, second.sequence) == (1, 2)
    channel, payload = redis.publish.await_args_list[0].args
    assert channel == "workflow:run:run-1:stream"
    assert json.loads(payload) == first.to_dict()
    redis.rpush.assert_any_await("workflow:run:run-1:events", payload)
    assert redis.expire.await_args_list == [
        (("workflow:run:run-1:events", 3600),),
        (("workflow:run:run-1:events", 3600),),
    ]


@pytest.mark.asyncio
async def test_publish_accepts_synchronous_redis_clients():
    redis = Mock()
    redis.publish.return_value = 1
    redis.rpush.return_value = 1
    redis.expire.return_value = True

    with patch("app.services.workflow.stream.get_redis", AsyncMock(return_value=redis)):
        await StreamManager("run-1").publish(StreamEvent(StreamEventType.STATUS))

    redis.publish.assert_called_once()
    redis.rpush.assert_called_once()
    redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_publish_propagates_redis_errors_without_buffering():
    redis = Mock()
    redis.publish = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    redis.rpush = AsyncMock()
    redis.expire = AsyncMock()

    with (
        patch("app.services.workflow.stream.get_redis", AsyncMock(return_value=redis)),
        pytest.raises(ConnectionError, match="redis unavailable"),
    ):
        await StreamManager("run-1").publish(
            StreamEvent(StreamEventType.WORKFLOW_ERROR, {"error": "failed"})
        )

    redis.rpush.assert_not_awaited()
    redis.expire.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_helpers_publish_expected_boundaries():
    manager = StreamManager("run-1")
    manager.publish = AsyncMock()

    await manager.publish_workflow_start("workflow-1", "Workflow", {"input": 1})
    await manager.publish_workflow_waiting("pause-1")
    await manager.publish_workflow_complete({"output": 2}, 10)
    await manager.publish_workflow_error("failed", "node-1")
    await manager.publish_node_start("node-1", "llm", "LLM", True)
    await manager.publish_node_complete("node-1", {"text": "done"}, 5, "llm", True)
    await manager.publish_node_error("node-1", "failed")
    await manager.publish_node_skip("node-2", node_type="code")
    await manager.publish_token("node-1", "token")
    await manager.publish_chunk("node-1", "chunk")
    await manager.publish_output("node-1", 42)
    await manager.publish_iteration("node-1", 1, 2, item="first")
    await manager.publish_iteration("node-1", 1, 2, is_start=False, item="ignored")

    events = [call.args[0] for call in manager.publish.await_args_list]
    assert [event.event_type for event in events] == [
        StreamEventType.WORKFLOW_START,
        StreamEventType.WORKFLOW_WAITING,
        StreamEventType.WORKFLOW_COMPLETE,
        StreamEventType.WORKFLOW_ERROR,
        StreamEventType.NODE_START,
        StreamEventType.NODE_COMPLETE,
        StreamEventType.NODE_ERROR,
        StreamEventType.NODE_SKIP,
        StreamEventType.TOKEN,
        StreamEventType.CHUNK,
        StreamEventType.OUTPUT,
        StreamEventType.ITERATION_START,
        StreamEventType.ITERATION_COMPLETE,
    ]
    assert events[7].data["node_label"] == "node-2"
    assert events[11].data["item"] == "first"
    assert "item" not in events[12].data


@pytest.mark.asyncio
async def test_progress_handles_zero_total():
    manager = StreamManager("run-1")
    manager.publish = AsyncMock()

    await manager.publish_progress(current=0, total=0, message="waiting")

    event = manager.publish.await_args.args[0]
    assert event.event_type is StreamEventType.PROGRESS
    assert event.data == {
        "current": 0,
        "total": 0,
        "percentage": 0,
        "message": "waiting",
    }


class _PubSub:
    def __init__(self, messages):
        self.messages = messages
        self.subscribe = AsyncMock()
        self.unsubscribe = AsyncMock()
        self.close = AsyncMock()

    async def listen(self):
        for message in self.messages:
            yield message


@pytest.mark.asyncio
async def test_subscribe_filters_invalid_and_old_events_then_closes_on_terminal():
    timestamp = datetime(2026, 1, 2, 3, 4, 5).isoformat()
    buffered = [
        "not-json",
        json.dumps({"event": "token", "data": {"token": "old"}, "sequence": 2}),
        json.dumps({"event": "token", "data": {"token": "buffered"}, "sequence": 4}),
    ]
    pubsub = _PubSub(
        [
            {"type": "subscribe", "data": "ignored"},
            {"type": "message", "data": "not-json"},
            {
                "type": "message",
                "data": json.dumps({"event": "token", "sequence": 3}),
            },
            {
                "type": "message",
                "data": json.dumps(
                    {
                        "event": "workflow_error",
                        "data": {"error": "failed"},
                        "timestamp": timestamp,
                        "sequence": 5,
                    }
                ),
            },
            {
                "type": "message",
                "data": json.dumps({"event": "token", "sequence": 6}),
            },
        ]
    )
    redis = Mock()
    redis.lrange = AsyncMock(return_value=buffered)
    redis.pubsub.return_value = pubsub

    with patch("app.services.workflow.stream.get_redis", AsyncMock(return_value=redis)):
        events = [event async for event in StreamManager("run-1").subscribe(3)]

    assert [(event.event_type, event.sequence) for event in events] == [
        (StreamEventType.TOKEN, 4),
        (StreamEventType.WORKFLOW_ERROR, 5),
    ]
    assert events[-1].timestamp == datetime.fromisoformat(timestamp)
    pubsub.subscribe.assert_awaited_once_with("workflow:run:run-1:stream")
    pubsub.unsubscribe.assert_awaited_once_with("workflow:run:run-1:stream")
    pubsub.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscribe_replays_waiting_event_from_buffer_at_sequence_zero():
    redis = Mock()
    redis.lrange = AsyncMock(
        return_value=[
            json.dumps({"event": "token", "data": {"token": "before"}, "sequence": 1}),
            json.dumps(
                {
                    "event": "workflow_waiting",
                    "data": {"node_id": "pause-1"},
                    "sequence": 2,
                }
            ),
        ]
    )

    with patch("app.services.workflow.stream.get_redis", AsyncMock(return_value=redis)):
        events = [event async for event in StreamManager("run-1").subscribe()]

    assert [(event.event_type, event.sequence) for event in events] == [
        (StreamEventType.TOKEN, 1),
        (StreamEventType.WORKFLOW_WAITING, 2),
    ]
    redis.pubsub.assert_not_called()


@pytest.mark.asyncio
async def test_get_all_events_skips_malformed_entries_and_clear_deletes_buffer():
    redis = Mock()
    redis.lrange.return_value = [
        "broken",
        json.dumps({"event": "node_error", "data": {"error": "boom"}}),
    ]
    redis.delete = AsyncMock()
    manager = StreamManager("run-1")

    with patch("app.services.workflow.stream.get_redis", AsyncMock(return_value=redis)):
        events = await manager.get_all_events()
        await manager.clear()

    assert len(events) == 1
    assert events[0].event_type is StreamEventType.NODE_ERROR
    assert events[0].sequence == 0
    redis.delete.assert_awaited_once_with("workflow:run:run-1:events")


@pytest.mark.asyncio
async def test_stream_to_sse_preserves_event_name_and_unicode_payload():
    event = StreamEvent(StreamEventType.OUTPUT, {"output": "完成"}, sequence=7)

    async def subscribe(_self, from_sequence):
        assert from_sequence == 6
        yield event

    with patch.object(StreamManager, "subscribe", subscribe):
        chunks = [chunk async for chunk in stream_to_sse("run-1", 6)]

    assert chunks == [event.to_sse()]
    assert chunks[0].startswith("event: output\ndata: ")
    assert "完成" in chunks[0]
