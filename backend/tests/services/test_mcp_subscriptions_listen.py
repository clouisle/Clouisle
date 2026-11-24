"""Behavior of the ``subscriptions/listen`` subscription path.

2026-07-28 removed ``resources/subscribe``, so the same SSE contract has to be
served by a typed listen stream. These tests drive the adapter with a fake
session and a fake ``listen`` entry point: no network, no SDK internals.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mcp.client.subscriptions import ResourceUpdated, ToolsListChanged

from app.core.config import settings
from app.services import mcp_subscriptions as subs


def _caps(protocol_version: str | None, *, subscribe: bool = False):
    return SimpleNamespace(
        resources_subscribe=subscribe, protocol_version=protocol_version
    )


class _Session:
    """Negotiated view of a modern session; rejects the legacy calls."""

    def __init__(self, config) -> None:
        self.protocol_version = config.get("_version")
        self.server_capabilities = (
            {"resources": {"subscribe": True}} if config.get("_subscribe") else {}
        )
        self.pings = 0

    async def send_ping(self) -> None:
        self.pings += 1

    async def subscribe_resource(self, uri: str) -> None:
        raise AssertionError("legacy subscribe_resource used on a modern session")

    async def unsubscribe_resource(self, uri: str) -> None:
        raise AssertionError("legacy unsubscribe_resource used on a modern session")


class _Client:
    def __init__(self, config, *, callbacks=None, **kwargs):
        self.config = config
        self.callbacks = callbacks
        type(self).last = self

    @asynccontextmanager
    async def connect(self, *, timeout=None):
        self.session = _Session(self.config)
        yield self.session


class _Stream:
    """Minimal async iterator over scripted events, including failures."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _SilentStream:
    """A ``listen`` stream that never delivers: only the ping can wake us."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()


def _fake_listen(items=None):
    @asynccontextmanager
    async def listen(session, *, resource_subscriptions=(), on_event=None):
        assert tuple(resource_subscriptions)  # the caller must name a URI
        yield _SilentStream() if items is None else _Stream(items)

    return listen


async def _open(monkeypatch, items=None, **config):
    monkeypatch.setattr(subs, "McpClient", _Client)
    monkeypatch.setattr(subs, "_listen", _fake_listen(items))
    return subs.open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config=config,
        uri="file:///a",
        user_id=uuid4(),
        team_id=uuid4(),
    )


async def _drain(handle, timeout: float = 2.0):
    async def collect():
        uris: list[str] = []
        async for event in handle.events():
            if event is not None:
                uris.append(event["uri"])
        return uris

    return await asyncio.wait_for(collect(), timeout)


@pytest.mark.asyncio
async def test_listen_stream_delivers_only_the_subscribed_uri(monkeypatch):
    items = [
        ResourceUpdated("file:///a"),
        ResourceUpdated("file:///other"),
        ToolsListChanged(),
        ResourceUpdated("file:///a"),
    ]

    async with await _open(monkeypatch, items, _version="2026-07-28") as handle:
        assert await _drain(handle) == ["file:///a", "file:///a"]


@pytest.mark.asyncio
async def test_a_lost_listen_stream_marks_the_subscription_connection_lost(monkeypatch):
    items = [RuntimeError("stream dropped")]

    async with await _open(monkeypatch, items, _version="2026-07-28") as handle:
        assert await _drain(handle) == []
        assert handle.close_reason == subs.SubscriptionClosed.CONNECTION_LOST


@pytest.mark.asyncio
async def test_a_legacy_server_without_subscribe_capability_fails_closed(monkeypatch):
    monkeypatch.setattr(subs, "McpClient", _Client)
    monkeypatch.setattr(subs, "_listen", _fake_listen([]))

    with pytest.raises(Exception) as unavailable:
        async with subs.open_subscription(
            tool=SimpleNamespace(id=uuid4()),
            config={},
            uri="file:///a",
            user_id=uuid4(),
            team_id=uuid4(),
        ):
            pass

    assert "resources.subscribe" in str(unavailable.value)


def test_listen_is_only_offered_on_modern_versions(monkeypatch):
    monkeypatch.setattr(subs, "_listen", object())

    assert subs._listen_factory("2026-07-28") is not None
    assert subs._listen_factory("2025-11-25") is None
    assert subs._listen_factory(None) is None

    monkeypatch.setattr(subs, "_listen", None)
    assert subs._listen_factory("2026-07-28") is None


@pytest.mark.asyncio
async def test_a_modern_session_uses_listen_even_with_a_stale_subscribe_flag(
    monkeypatch,
):
    """2026-07-28 removed resources/subscribe; a stale flag must not win.

    The SDK server still reports ``resources.subscribe`` on modern sessions,
    and calling the removed method fails with "Method not found".
    """
    monkeypatch.setattr(subs, "McpClient", _Client)
    monkeypatch.setattr(subs, "_listen", _fake_listen([ResourceUpdated("memo://a")]))

    async with subs.open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={"_version": "2026-07-28", "_subscribe": True},
        uri="memo://a",
        user_id=uuid4(),
        team_id=uuid4(),
    ) as handle:
        # The fake session rejects subscribe_resource outright, so reaching the
        # queue proves the listen path ran.
        assert await _drain(handle) == ["memo://a"]


@pytest.mark.asyncio
async def test_a_legacy_session_still_uses_subscribe(monkeypatch):
    calls = []

    class _LegacySession:
        protocol_version = "2025-11-25"
        server_capabilities = {"resources": {"subscribe": True}}

        async def subscribe_resource(self, uri: str) -> None:
            calls.append(uri)

        async def unsubscribe_resource(self, uri: str) -> None:
            calls.append(f"unsubscribe:{uri}")

    class _LegacyClient(_Client):
        @asynccontextmanager
        async def connect(self, *, timeout=None):
            yield _LegacySession()

    monkeypatch.setattr(subs, "McpClient", _LegacyClient)

    async with subs.open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={},
        uri="memo://a",
        user_id=uuid4(),
        team_id=uuid4(),
    ) as handle:
        assert handle.uri == "memo://a"

    assert calls == ["memo://a", "unsubscribe:memo://a"]


def test_subscription_ttl_uses_the_configured_setting(monkeypatch):
    monkeypatch.setattr(settings, "MCP_SUBSCRIPTION_TTL_SECONDS", 42, raising=False)

    assert subs.subscription_ttl_seconds() == 42.0


@pytest.mark.asyncio
async def test_a_full_queue_drops_updates_but_still_takes_the_close(monkeypatch):
    """A slow client must never block the SDK read loop."""
    monkeypatch.setattr(settings, "MCP_SUBSCRIPTION_TTL_SECONDS", 30, raising=False)
    handle = subs.SubscriptionHandle(
        id=uuid4(),
        tool_id=uuid4(),
        team_id=uuid4(),
        user_id=uuid4(),
        uri="file:///a",
    )
    for _ in range(subs.MAX_QUEUED_UPDATES + 5):
        handle.enqueue_update("file:///a")
    handle.enqueue_close()

    drained = 0
    async for event in handle.events():
        if event is not None:
            drained += 1

    # The close signal made room by dropping the oldest pending update.
    assert drained == subs.MAX_QUEUED_UPDATES - 1


# ---------------------------------------------------------------------------
# Liveness pings (#499)
# ---------------------------------------------------------------------------


def test_ping_interval_is_a_fraction_of_the_ttl_budget():
    assert subs.ping_interval_seconds(300.0) == 300.0 * subs.PING_INTERVAL_FRACTION
    assert subs.ping_interval_seconds(300.0) < 300.0
    # A rounded-to-zero budget must still yield a usable delay.
    assert subs.ping_interval_seconds(0.0) == subs.MIN_PING_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_a_long_lived_subscription_pings_at_the_ttl_fraction(monkeypatch):
    monkeypatch.setattr(subs, "PING_INTERVAL_FRACTION", 0.004)  # 5s TTL -> 20ms
    monkeypatch.setattr(subs, "McpClient", _Client)
    monkeypatch.setattr(subs, "_listen", _fake_listen())

    async with subs.open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={"_version": "2026-07-28"},
        uri="file:///a",
        user_id=uuid4(),
        team_id=uuid4(),
        ttl_seconds=5.0,
    ) as handle:
        await asyncio.sleep(0.15)
        assert handle.close_reason is None

    assert _Client.last.session.pings >= 2
    assert _Client.last.session.protocol_version == "2026-07-28"


@pytest.mark.asyncio
async def test_a_failed_ping_marks_the_subscription_connection_lost(monkeypatch):
    monkeypatch.setattr(subs, "PING_INTERVAL_FRACTION", 0.004)

    class _DeadSession(_Session):
        async def send_ping(self) -> None:
            raise RuntimeError("server stopped answering")

    class _DeadClient(_Client):
        @asynccontextmanager
        async def connect(self, *, timeout=None):
            self.session = _DeadSession(self.config)
            yield self.session

    monkeypatch.setattr(subs, "McpClient", _DeadClient)
    monkeypatch.setattr(subs, "_listen", _fake_listen())

    async with subs.open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={"_version": "2026-07-28"},
        uri="file:///a",
        user_id=uuid4(),
        team_id=uuid4(),
        ttl_seconds=5.0,
    ) as handle:
        # No resource update is ever delivered, so only the failed ping can end
        # the stream; it must not wait for the TTL or a read timeout.
        assert await _drain(handle) == []
        assert handle.close_reason == subs.SubscriptionClosed.CONNECTION_LOST


@pytest.mark.asyncio
async def test_the_subscription_session_opts_into_server_logs_from_its_config(
    monkeypatch,
):
    monkeypatch.setattr(subs, "McpClient", _Client)
    monkeypatch.setattr(subs, "_listen", _fake_listen())

    async with subs.open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={"_version": "2026-07-28", "server_log_level": "debug"},
        uri="file:///a",
        user_id=uuid4(),
        team_id=uuid4(),
    ) as handle:
        assert handle.close_reason is None

    assert _Client.last.callbacks.server_logging.level == "debug"
    assert _Client.last.callbacks.server_logging.subject.startswith("tool:")
