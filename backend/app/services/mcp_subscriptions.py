"""Request-scoped live MCP resource subscriptions.

MCP resource subscriptions are session-scoped: updates only arrive while the
JSON-RPC session that asked for them stays open. This module therefore ties a
subscription to the lifetime of one streaming API request:

1. the request opens one negotiated ``McpClient`` session;
2. the negotiated session is checked before anything is subscribed (fail
   closed, never a fabricated success). The negotiated *version* decides,
   because 2026-07-28 removed ``resources/subscribe`` outright:

   * 2026-07-28 sessions use ``subscriptions/listen``, even when the server
     still reports a stale ``resources.subscribe`` capability flag;
   * older sessions use ``resources/subscribe`` when the server advertises it;

3. updates are queued in memory for the owning request only;
4. the session pings the server at a fraction of the TTL budget, so a server
   that silently dropped it ends the stream as ``connection_lost`` instead of
   surfacing as a read timeout at the very end of the budget;
5. the request's TTL or client disconnect closes the session and performs a
   best-effort ``unsubscribe`` (legacy path only; ``listen`` ends with its
   stream).

Both paths filter on the exact subscribed URI, so the SSE contract does not
depend on the negotiated version.

There is deliberately no background listener, registry, daemon or durable
subscription: process death ends the stream, and reconnecting creates a new
subscription. Cleanup is read-side and never routed through the tool
approval/outcome machinery.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import mcp.types as types

try:  # mcp >= 2: the 2026-07-28 subscription stream.
    from mcp.client.subscriptions import listen as _listen
    from mcp.client.subscriptions import ResourceUpdated as _ResourceUpdated
except ImportError:  # pragma: no cover - mcp 1.x has no listen at all
    _listen = None
    _ResourceUpdated = None

from app.core.config import settings
from app.core.timezone import now_utc
from app.llm.tools.mcp_client import (
    McpCallbacks,
    McpCallbackPolicy,
    McpCapabilityUnavailable,
    McpClient,
    read_session_capabilities,
    server_logging_from_config,
)

logger = logging.getLogger(__name__)

MAX_QUEUED_UPDATES = 100
HEARTBEAT_SECONDS = 15.0
CONNECT_TIMEOUT_SECONDS = 15.0
# One ping per half of the TTL budget: a session the server silently dropped is
# noticed in half the budget rather than at the read timeout at the very end.
PING_INTERVAL_FRACTION = 0.5
MIN_PING_INTERVAL_SECONDS = 0.01
# First protocol version that removes ``resources/subscribe`` in favour of
# ``subscriptions/listen``. Versions are ISO dates, so they compare as strings.
LISTEN_MIN_PROTOCOL_VERSION = "2026-07-28"


def subscription_ttl_seconds() -> float:
    return float(settings.MCP_SUBSCRIPTION_TTL_SECONDS)


def ping_interval_seconds(ttl: float) -> float:
    """Delay between liveness pings for a subscription of ``ttl`` seconds."""
    return max(float(ttl) * PING_INTERVAL_FRACTION, MIN_PING_INTERVAL_SECONDS)


class SubscriptionClosed(str):
    """Close reasons emitted on the event stream."""

    CLIENT_DISCONNECTED = "client_disconnected"
    TTL_EXPIRED = "ttl_expired"
    CONNECTION_LOST = "connection_lost"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"


@dataclass
class SubscriptionHandle:
    """One live subscription owned by one streaming request."""

    id: UUID
    tool_id: UUID
    team_id: UUID
    user_id: UUID
    uri: str
    connection_id: UUID | None = None
    connection_scope: str | None = None
    account_label: str | None = None
    opened_at: datetime = field(default_factory=now_utc)
    expires_at: datetime = field(
        default_factory=lambda: (
            now_utc() + timedelta(seconds=subscription_ttl_seconds())
        )
    )
    close_reason: str | None = None
    _queue: asyncio.Queue[dict[str, Any] | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=MAX_QUEUED_UPDATES),
        repr=False,
    )
    _sequence: int = 0

    def opened_event(self) -> dict[str, Any]:
        return {
            "subscription_id": str(self.id),
            "tool_id": str(self.tool_id),
            "team_id": str(self.team_id),
            "uri": self.uri,
            "connection_id": str(self.connection_id) if self.connection_id else None,
            "connection_scope": self.connection_scope,
            "account_label": self.account_label,
            "expires_at": self.expires_at.isoformat(),
        }

    def _offer(self, item: dict[str, Any] | None) -> None:
        """Queue one item, dropping the oldest when a slow client fills us.

        Nothing in this queue path awaits, so a drop always frees the slot the
        second ``put_nowait`` needs; the warning is a backstop that cannot fire
        while offers stay single-task.
        """
        try:
            self._queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass
        try:
            self._queue.get_nowait()
        except asyncio.QueueEmpty:  # pragma: no cover - defensive
            pass
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:  # pragma: no cover - defensive
            logger.warning("Dropping MCP subscription event for %s", self.id)

    def enqueue_update(self, uri: str) -> None:
        self._sequence += 1
        event = {
            "subscription_id": str(self.id),
            "uri": uri,
            "sequence": self._sequence,
            "received_at": now_utc().isoformat(),
        }
        # Bounded queue: drop the oldest pending update rather than block the
        # SDK read loop for a slow HTTP client.
        self._offer(event)

    def enqueue_close(self) -> None:
        """End the consumer's stream after the server stopped delivering."""
        self._offer(None)

    async def events(self) -> AsyncIterator[dict[str, Any] | None]:
        """Yield queued updates; ``None`` is a heartbeat tick.

        Ends at the subscription deadline. Cancellation (client disconnect) is
        propagated to the owning context manager.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max((self.expires_at - now_utc()).total_seconds(), 0.0)
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                if self.close_reason is None:
                    self.close_reason = SubscriptionClosed.TTL_EXPIRED
                return
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=min(remaining, HEARTBEAT_SECONDS)
                )
            except TimeoutError:
                yield None
                continue
            if event is None:
                return
            yield event


class _NotificationCollector:
    """Filters this subscription's resource-update notifications."""

    def __init__(self, handle: SubscriptionHandle) -> None:
        self.handle = handle

    async def __call__(self, message: Any) -> None:
        payload = message
        root = getattr(payload, "root", None)
        if root is not None:
            payload = root
        method = getattr(payload, "method", None)
        if method is None and isinstance(payload, Mapping):
            method = payload.get("method")
        if method != "notifications/resources/updated":
            return
        params = getattr(payload, "params", None)
        if params is None and isinstance(payload, Mapping):
            params = payload.get("params")
        if isinstance(params, types.ResourceUpdatedNotificationParams):
            uri = params.uri
        elif isinstance(params, Mapping):
            uri = params.get("uri")
        else:
            uri = getattr(params, "uri", None)
        if not isinstance(uri, str) or uri != self.handle.uri:
            return
        self.handle.enqueue_update(uri)


def _listen_factory(protocol_version: str | None) -> Any | None:
    """Return the ``listen`` entry point for this negotiated version, if any."""
    if _listen is None:
        return None
    if not isinstance(protocol_version, str):
        return None
    if protocol_version < LISTEN_MIN_PROTOCOL_VERSION:
        return None
    return _listen


async def _pump_listen(subscription: Any, handle: SubscriptionHandle) -> None:
    """Forward one ``listen`` event stream into the handle's queue.

    The stream is filtered to the exact subscribed URI so a modern session
    delivers the same events a legacy ``resources/subscribe`` session would.
    """
    try:
        async for event in subscription:
            uri = getattr(event, "uri", None)
            if _ResourceUpdated is not None and not isinstance(event, _ResourceUpdated):
                continue
            if isinstance(uri, str) and uri == handle.uri:
                handle.enqueue_update(uri)
    except asyncio.CancelledError:  # pragma: no cover - normal teardown
        raise
    except Exception:
        logger.warning(
            "MCP listen stream ended for tool %s", handle.tool_id, exc_info=True
        )
        handle.close_reason = SubscriptionClosed.CONNECTION_LOST
    finally:
        handle.enqueue_close()


async def _ping_session(
    session: Any, handle: SubscriptionHandle, interval: float
) -> None:
    """Ping the server on ``interval``; a failure ends the subscription.

    A subscription session lives for minutes and owns no reconnection, so a
    dead server would otherwise only be noticed at the next update or the TTL
    deadline. A failing ping is the liveness signal: mark the subscription
    ``connection_lost`` and let the consumer stop waiting.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await session.send_ping()
        except Exception:
            logger.warning(
                "MCP subscription ping failed for tool %s; the session is lost",
                handle.tool_id,
                exc_info=True,
            )
            handle.close_reason = SubscriptionClosed.CONNECTION_LOST
            handle.enqueue_close()
            return


@asynccontextmanager
async def open_subscription(
    *,
    tool: Any,
    config: Mapping[str, Any],
    uri: str,
    user_id: UUID,
    team_id: UUID,
    connection_id: UUID | None = None,
    connection_scope: str | None = None,
    account_label: str | None = None,
    ttl_seconds: float | None = None,
) -> AsyncIterator[SubscriptionHandle]:
    """Open one negotiated session and subscribe by the server's own mechanism."""
    ttl = max(5.0, float(ttl_seconds or subscription_ttl_seconds()))
    handle = SubscriptionHandle(
        id=uuid4(),
        tool_id=tool.id,
        team_id=team_id,
        user_id=user_id,
        uri=uri,
        connection_id=connection_id,
        connection_scope=connection_scope,
        account_label=account_label,
        expires_at=now_utc() + timedelta(seconds=ttl),
    )
    callbacks = McpCallbacks(
        notification=_NotificationCollector(handle),
        server_logging=server_logging_from_config(config, subject=f"tool:{tool.id}"),
        policy=McpCallbackPolicy(max_callback_seconds=min(10.0, ttl)),
    )
    client = McpClient(dict(config), callbacks=callbacks)

    async with AsyncExitStack() as stack:
        session = await stack.enter_async_context(
            client.connect(timeout=min(CONNECT_TIMEOUT_SECONDS, ttl))
        )
        # Capabilities come from the session we actually subscribe on: a probe
        # on a second connection could answer for a different server instance.
        capabilities = read_session_capabilities(session)
        # Version first: 2026-07-28 removed ``resources/subscribe`` outright, so
        # a modern session must use ``listen`` even if the server still reports
        # a stale ``resources.subscribe`` capability flag (the SDK server does).
        listen = _listen_factory(capabilities.protocol_version)
        if listen is None and not capabilities.resources_subscribe:
            raise McpCapabilityUnavailable("resources.subscribe")

        ping = asyncio.create_task(
            _ping_session(session, handle, ping_interval_seconds(ttl))
        )
        stack.push_async_callback(_stop_task, ping)

        if listen is not None:
            subscription = await stack.enter_async_context(
                listen(session, resource_subscriptions=(uri,))
            )
            pump = asyncio.create_task(_pump_listen(subscription, handle))
            stack.push_async_callback(_stop_task, pump)
            yield handle
            return

        try:
            await session.subscribe_resource(uri)
        except Exception:
            logger.warning(
                "MCP resource subscribe failed for tool %s", tool.id, exc_info=True
            )
            raise
        try:
            yield handle
        finally:
            # Read-side cleanup only: never claim the subscription itself was
            # outcome-unknown, never replay a mutating tool call.
            try:
                await session.unsubscribe_resource(uri)
            except Exception:
                logger.info(
                    "Best-effort MCP unsubscribe failed for %s", uri, exc_info=True
                )


async def _stop_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


__all__ = [
    "LISTEN_MIN_PROTOCOL_VERSION",
    "MAX_QUEUED_UPDATES",
    "PING_INTERVAL_FRACTION",
    "SubscriptionClosed",
    "SubscriptionHandle",
    "open_subscription",
    "ping_interval_seconds",
    "subscription_ttl_seconds",
]
