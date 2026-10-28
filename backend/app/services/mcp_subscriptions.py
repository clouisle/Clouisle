"""Request-scoped live MCP resource subscriptions.

MCP resource subscriptions are session-scoped: a server only emits
``notifications/resources/updated`` while the JSON-RPC session that called
``resources/subscribe`` stays open. This module therefore ties a subscription
to the lifetime of one streaming API request:

1. the request opens one live ``McpClient`` session;
2. the negotiated ``resources.subscribe`` capability is required before the
   subscribe call (fail closed, never a fabricated success);
3. update notifications are queued in memory for the owning request only;
4. the request's TTL or client disconnect closes the session and performs a
   best-effort ``unsubscribe_resource``.

There is deliberately no background listener, registry, daemon or durable
subscription: process death ends the stream, and reconnecting creates a new
subscription. Unsubscribe is a read-side cleanup and is never routed through
the tool approval/outcome machinery.
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

from app.core.config import settings
from app.core.timezone import now_utc
from app.llm.tools.mcp_client import (
    McpCallbacks,
    McpCallbackPolicy,
    McpCapabilityUnavailable,
    McpClient,
)

logger = logging.getLogger(__name__)

MAX_QUEUED_UPDATES = 100
HEARTBEAT_SECONDS = 15.0
CONNECT_TIMEOUT_SECONDS = 15.0


def subscription_ttl_seconds() -> float:
    return float(settings.MCP_SUBSCRIPTION_TTL_SECONDS)


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

    def enqueue_update(self, uri: str) -> None:
        self._sequence += 1
        event = {
            "subscription_id": str(self.id),
            "uri": uri,
            "sequence": self._sequence,
            "received_at": now_utc().isoformat(),
        }
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Bounded queue: drop the oldest pending update, never block the
            # SDK read loop for a slow HTTP client.
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - defensive
                pass
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - defensive
                logger.warning("Dropping MCP resource update for %s", self.uri)

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
    """Open one negotiated session, require subscribe support, then subscribe."""
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
        policy=McpCallbackPolicy(max_callback_seconds=min(10.0, ttl)),
    )
    client = McpClient(dict(config), callbacks=callbacks)

    capabilities = await client.get_capabilities(
        timeout=min(CONNECT_TIMEOUT_SECONDS, ttl)
    )
    if not capabilities.resources_subscribe:
        raise McpCapabilityUnavailable("resources.subscribe")

    async with AsyncExitStack() as stack:
        session = await stack.enter_async_context(
            client.connect(timeout=min(CONNECT_TIMEOUT_SECONDS, ttl))
        )
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


__all__ = [
    "MAX_QUEUED_UPDATES",
    "SubscriptionClosed",
    "SubscriptionHandle",
    "open_subscription",
    "subscription_ttl_seconds",
]
