import asyncio

import pytest

from app.api.v1.endpoints.chat import _is_model_stream_activity
from app.api.v1.endpoints.chat_helpers import stream_utils
from app.llm.types import ChatStreamChunk, FinishReason


class FakeRequest:
    def __init__(self, *, disconnected: bool = False):
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


@pytest.mark.anyio
async def test_send_heartbeat_continues_before_interval(monkeypatch):
    monkeypatch.setattr(stream_utils.time, "time", lambda: 10.0)

    should_continue, new_last_event_time = await stream_utils.send_heartbeat_if_needed(
        9.0,
        15.0,
        FakeRequest(),
    )

    assert should_continue is True
    assert new_last_event_time == 9.0


@pytest.mark.anyio
async def test_send_heartbeat_refreshes_after_interval(monkeypatch):
    monkeypatch.setattr(stream_utils.time, "time", lambda: 30.0)

    should_continue, new_last_event_time = await stream_utils.send_heartbeat_if_needed(
        10.0,
        15.0,
        FakeRequest(),
    )

    assert should_continue is True
    assert new_last_event_time == 30.0


@pytest.mark.anyio
async def test_send_heartbeat_stops_when_disconnected_after_interval(monkeypatch):
    monkeypatch.setattr(stream_utils.time, "time", lambda: 30.0)

    should_continue, new_last_event_time = await stream_utils.send_heartbeat_if_needed(
        10.0,
        15.0,
        FakeRequest(disconnected=True),
    )

    assert should_continue is False
    assert new_last_event_time == 10.0


async def delayed_items(*items: object, delay: float = 0):
    for item in items:
        if delay:
            await asyncio.sleep(delay)
        yield item


async def delayed_sequence(*steps: tuple[object, float]):
    for item, delay in steps:
        if delay:
            await asyncio.sleep(delay)
        yield item


def stream_chunk(**kwargs) -> ChatStreamChunk:
    return ChatStreamChunk(id="chunk-1", model="test-model", **kwargs)


def test_model_stream_activity_includes_internal_provider_activity():
    assert _is_model_stream_activity(
        stream_chunk(delta={"stream_activity": True}),
    )
    assert _is_model_stream_activity(
        stream_chunk(delta={"content": "hello"}),
    )
    assert _is_model_stream_activity(
        stream_chunk(delta={}, finish_reason=FinishReason.STOP),
    )
    assert not _is_model_stream_activity(stream_chunk(delta={}))


@pytest.mark.anyio
async def test_iter_with_idle_timeout_yields_items_before_timeout():
    received = []

    async for item in stream_utils.iter_with_idle_timeout(
        delayed_items("a", "b"),
        timeout_seconds=0.1,
    ):
        received.append(item)

    assert received == ["a", "b"]


@pytest.mark.anyio
async def test_iter_with_idle_timeout_raises_when_next_item_stalls():
    with pytest.raises(stream_utils.StreamIdleTimeoutError):
        async for _ in stream_utils.iter_with_idle_timeout(
            delayed_items("late", delay=0.05),
            timeout_seconds=0.001,
        ):
            pass


@pytest.mark.anyio
async def test_iter_with_idle_timeout_refreshes_after_activity():
    received = []

    async for item in stream_utils.iter_with_idle_timeout(
        delayed_sequence(("first", 0), ("second", 0.02), ("third", 0.02)),
        timeout_seconds=0.03,
        activity_predicate=lambda item: item != "empty",
    ):
        received.append(item)

    assert received == ["first", "second", "third"]


@pytest.mark.anyio
async def test_iter_with_idle_timeout_ignores_inactive_items():
    received = []

    with pytest.raises(stream_utils.StreamIdleTimeoutError):
        async for item in stream_utils.iter_with_idle_timeout(
            delayed_sequence(("active", 0), ("empty", 0.02), ("late", 0.02)),
            timeout_seconds=0.03,
            activity_predicate=lambda item: item != "empty",
        ):
            received.append(item)

    assert received == ["active", "empty"]
