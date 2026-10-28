"""Behavior coverage for MCP operation envelopes and subscription lifecycle.

The database is real in-memory SQLite; only the MCP protocol helpers and the
live subscription context manager are replaced. Approval execution rows,
authorization and subscription closing/cleanup run through their production
implementations so the assertions describe observable endpoint behavior rather
than mocks echoing their inputs.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp import types
from tortoise import Tortoise

from app.api import deps
from app.api.v1.endpoints import tool_mcp
from app.core.timezone import now_utc
from app.llm.tools.mcp_client import (
    McpCallbacks,
    McpEnumeration,
    McpError,
)
from app.models.tool import Tool, ToolType, ToolVisibility
from app.models.tool_approval import ToolExecution
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode, error
from app.schemas.tool_approval import ApprovalDecision, ToolExecutionStatus
from app.services import mcp_subscriptions
from app.services.mcp_subscriptions import (
    MAX_QUEUED_UPDATES,
    SubscriptionClosed,
    SubscriptionHandle,
    open_subscription,
)
from app.services.tool_execution import PendingToolApproval

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _user() -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"mcp_{suffix}",
        email=f"mcp_{suffix}@tool-mcp.test",
        hashed_password="x",
        is_superuser=True,
    )


async def _team(name: str, actor: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"{name}_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=actor.id, role="owner")
    return team


async def _tool(team: Team, *, approval_policy: dict | None = None) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="MCP tool",
        description="behavior test",
        type=ToolType.MCP,
        visibility=ToolVisibility.TEAM,
        identity_policy="none",
        connection_fields=[],
        approval_policy=approval_policy or {"default_decision": "allow"},
        mcp_config={
            "transport": "http",
            "url": "https://mcp.example/mcp",
            "headers": {"X-Static": "static"},
        },
    )


async def _passthrough_callbacks(
    tool: Tool,
    context: object,
    invoke: object,
    *,
    execution_id: object = None,
    call_timeout_seconds: object = None,
) -> object:
    return await invoke(McpCallbacks())  # type: ignore[operator]


@pytest_asyncio.fixture
async def mcp_app(monkeypatch):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    actor = await _user()

    app = FastAPI()
    app.include_router(tool_mcp.router, prefix="/tools")
    app.dependency_overrides[deps.get_current_active_user] = lambda: actor

    @app.exception_handler(BusinessError)
    async def handle_business_error(_request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(
                code=exc.code,
                msg=exc.msg,
                msg_key=exc.msg_key,
                data=exc.data,
                **exc.kwargs,
            ),
        )

    monkeypatch.setattr(tool_mcp, "run_with_mcp_callbacks", _passthrough_callbacks)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api"
        ) as client:
            yield SimpleNamespace(client=client, actor=actor)
    finally:
        await Tortoise.close_connections()


# ---------------------------------------------------------------------------
# Loading and approval-policy edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_tool_is_rejected_before_any_metadata_connection(
    mcp_app, monkeypatch
):
    team = await _team("disabled", mcp_app.actor)
    tool = await _tool(team)
    await Tool.filter(id=tool.id).update(is_enabled=False)
    enumerate_mock = AsyncMock(return_value=McpEnumeration(items=[]))
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(team.id)}
    )

    assert response.status_code == 403
    assert response.json()["code"] == int(ResponseCode.FORBIDDEN)
    assert response.json()["msg"]
    enumerate_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_malformed_stored_policy_blocks_metadata_with_configuration_error(
    mcp_app, monkeypatch
):
    team = await _team("bad-policy", mcp_app.actor)
    tool = await _tool(team)
    await Tool.filter(id=tool.id).update(
        approval_policy={"default_decision": "definitely-not-a-decision"}
    )
    enumerate_mock = AsyncMock(return_value=McpEnumeration(items=[]))
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(team.id)}
    )

    assert response.status_code == 409
    assert response.json()["code"] == int(
        ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
    )
    assert response.json()["msg"]
    enumerate_mock.assert_not_awaited()


def test_metadata_policy_uses_exactly_one_override_level():
    tool = SimpleNamespace(
        approval_policy={
            "default_decision": "allow",
            "operation_overrides": {
                "list:tools": {
                    "default_decision": "require_approval",
                    "gates": [{"kind": "caller"}],
                    "operation_overrides": {
                        # Same-operation nesting is deliberately not chased.
                        "list:tools": {"default_decision": "deny"}
                    },
                }
            },
        }
    )

    resolved = tool_mcp._metadata_policy(tool, "list:tools")

    assert resolved.default_decision is ApprovalDecision.REQUIRE_APPROVAL
    assert [gate.kind.value for gate in resolved.gates] == ["caller"]
    assert resolved.operation_overrides == {}

    # An operation without an explicit override stays discovery-allowed even
    # when another listing requires approval.
    other = tool_mcp._metadata_policy(tool, "list:resources")
    assert other.default_decision is ApprovalDecision.ALLOW
    assert other.operation_overrides == {}


def test_operation_envelope_serializes_pending_approval_reference():
    execution_id = uuid4()
    envelope = tool_mcp._operation_out(
        "subscribe:resource", PendingToolApproval(execution_id, "remote-tool")
    )

    assert envelope.status == "pending_approval"
    assert envelope.operation == "subscribe:resource"
    assert envelope.execution_id == execution_id
    assert envelope.result is None
    assert envelope.pending_approval is not None
    assert envelope.pending_approval.execution_id == execution_id
    assert envelope.pending_approval.tool_name == "remote-tool"


def test_business_error_mapping_preserves_already_mapped_errors():
    original = BusinessError(
        code=ResponseCode.FORBIDDEN,
        msg_key="tool_access_denied",
        status_code=403,
    )

    mapped = tool_mcp._mcp_business_error(
        original, operation="tool:x", tool=SimpleNamespace(id=uuid4())
    )

    assert mapped is original


# ---------------------------------------------------------------------------
# Operation endpoints: protocol failure and stale execution paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,payload,helper",
    [
        ("/mcp/tools/call", {"name": "search", "arguments": {}}, "execute_mcp_tool"),
        ("/mcp/resources/read", {"uri": "file:///a.txt"}, "read_mcp_resource"),
        ("/mcp/prompts/get", {"name": "weather", "arguments": {}}, "get_mcp_prompt"),
        (
            "/mcp/completion",
            {
                "reference": {"kind": "prompt", "name": "weather"},
                "argument_name": "city",
            },
            "complete_mcp_argument",
        ),
    ],
)
async def test_operation_protocol_failure_maps_to_gateway_error(
    mcp_app, monkeypatch, route, payload, helper
):
    team = await _team("op-failure", mcp_app.actor)
    tool = await _tool(team)
    failing = AsyncMock(side_effect=McpError("transport down"))
    monkeypatch.setattr(tool_mcp, helper, failing)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}{route}",
        params={"team_id": str(team.id)},
        json=payload,
    )

    assert response.status_code == 502
    assert response.json()["code"] == int(ResponseCode.INTERNAL_ERROR)
    assert response.json()["msg"]
    failing.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route,payload,helper",
    [
        ("/mcp/tools/call", {"name": "search", "arguments": {}}, "execute_mcp_tool"),
        ("/mcp/resources/read", {"uri": "file:///a.txt"}, "read_mcp_resource"),
        ("/mcp/prompts/get", {"name": "weather", "arguments": {}}, "get_mcp_prompt"),
        (
            "/mcp/completion",
            {
                "reference": {"kind": "prompt", "name": "weather"},
                "argument_name": "city",
            },
            "complete_mcp_argument",
        ),
    ],
)
async def test_operation_rejects_unknown_execution_before_contacting_server(
    mcp_app, monkeypatch, route, payload, helper
):
    team = await _team("stale-execution", mcp_app.actor)
    tool = await _tool(team)
    protocol = AsyncMock()
    monkeypatch.setattr(tool_mcp, helper, protocol)
    unknown_execution = str(uuid4())

    response = await mcp_app.client.post(
        f"/tools/{tool.id}{route}",
        params={"team_id": str(team.id)},
        json={**payload, "execution_id": unknown_execution},
    )

    assert response.status_code == 404
    assert response.json()["code"] == int(ResponseCode.TOOL_EXECUTION_NOT_FOUND)
    assert response.json()["msg"]
    protocol.assert_not_awaited()
    assert await ToolExecution.all().count() == 0


# ---------------------------------------------------------------------------
# Subscription endpoint: pending approval and stream lifecycle
# ---------------------------------------------------------------------------


class _ScriptedHandle(SimpleNamespace):
    def __init__(self, script: list, *, failure: BaseException | None = None) -> None:
        super().__init__(
            id=uuid4(),
            close_reason=None,
            opened_event=lambda: {
                "subscription_id": str(self.id),
                "uri": "file:///a",
            },
        )
        self._script = script
        self._failure = failure

    async def events(self):
        for item in self._script:
            yield item
        if self._failure is not None:
            raise self._failure


def _fake_open(handle: _ScriptedHandle):
    @asynccontextmanager
    async def fake_open(**kwargs):
        yield handle

    return fake_open


async def _subscribe(tool: Tool, team: Team, actor: User, **overrides):
    kwargs = {
        "uri": "file:///a",
        "team_id": team.id,
        "connection_mode": None,
        "connection_id": None,
        "execution_id": None,
        "current_user": actor,
    }
    kwargs.update(overrides)
    return await tool_mcp.subscribe_mcp_resource(tool.id, **kwargs)


@pytest.mark.asyncio
async def test_subscribe_returns_pending_approval_and_closes_request_scope(
    mcp_app, monkeypatch
):
    team = await _team("pending-sub", mcp_app.actor)
    tool = await _tool(team)
    monkeypatch.setattr(tool_mcp, "open_subscription", _fake_open(_ScriptedHandle([])))

    # First request records the immutable execution binding.
    opened = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={"team_id": str(team.id), "uri": "file:///a"},
    )
    assert opened.status_code == 200
    assert "event: subscription_closed" in opened.text

    execution = (
        await ToolExecution.filter(
            tool_id=tool.id, operation=tool_mcp.OP_RESOURCE_SUBSCRIBE
        )
        .order_by("-created_at")
        .first()
    )
    assert execution is not None
    await ToolExecution.filter(id=execution.id).update(
        status=ToolExecutionStatus.AWAITING_APPROVAL
    )

    # Replaying the identical operation now yields the durable pending
    # envelope instead of opening a second subscription.
    resumed = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={
            "team_id": str(team.id),
            "uri": "file:///a",
            "execution_id": str(execution.id),
        },
    )

    assert resumed.status_code == 200
    data = resumed.json()["data"]
    assert data["status"] == "pending_approval"
    assert data["operation"] == tool_mcp.OP_RESOURCE_SUBSCRIBE
    assert data["execution_id"] == str(execution.id)
    assert data["pending_approval"]["execution_id"] == str(execution.id)
    assert data["pending_approval"]["tool_name"] == tool.name


@pytest.mark.asyncio
async def test_subscribe_unknown_execution_returns_business_error(mcp_app, monkeypatch):
    team = await _team("stale-sub", mcp_app.actor)
    tool = await _tool(team)
    protocol_open = AsyncMock()
    monkeypatch.setattr(tool_mcp, "open_subscription", protocol_open)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={
            "team_id": str(team.id),
            "uri": "file:///a",
            "execution_id": str(uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == int(ResponseCode.TOOL_EXECUTION_NOT_FOUND)
    protocol_open.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscribe_connection_failure_maps_to_gateway_error(mcp_app, monkeypatch):
    team = await _team("sub-connect-failure", mcp_app.actor)
    tool = await _tool(team)

    @asynccontextmanager
    async def failing_open(**kwargs):
        raise McpError("connection refused")
        yield  # pragma: no cover - required to make this a context manager

    monkeypatch.setattr(tool_mcp, "open_subscription", failing_open)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={"team_id": str(team.id), "uri": "file:///a"},
    )

    assert response.status_code == 502
    assert response.json()["code"] == int(ResponseCode.INTERNAL_ERROR)
    assert response.json()["msg"]


@pytest.mark.asyncio
async def test_subscribe_cancellation_closes_scope_and_propagates(mcp_app, monkeypatch):
    team = await _team("sub-cancel-open", mcp_app.actor)
    tool = await _tool(team)

    @asynccontextmanager
    async def cancelled_open(**kwargs):
        raise asyncio.CancelledError()
        yield  # pragma: no cover - required to make this a context manager

    monkeypatch.setattr(tool_mcp, "open_subscription", cancelled_open)

    with pytest.raises(asyncio.CancelledError):
        await _subscribe(tool, team, mcp_app.actor)


@pytest.mark.asyncio
async def test_subscribe_stream_emits_keepalive_and_default_close_reason(
    mcp_app, monkeypatch
):
    team = await _team("stream-events", mcp_app.actor)
    tool = await _tool(team)
    handle = _ScriptedHandle(
        [None, {"subscription_id": "s", "uri": "file:///a", "sequence": 1}]
    )
    monkeypatch.setattr(tool_mcp, "open_subscription", _fake_open(handle))

    response = await _subscribe(tool, team, mcp_app.actor)
    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(chunks)

    assert "event: subscription_opened" in text
    assert ": keep-alive" in text
    assert "event: resource_updated" in text
    assert "event: subscription_closed" in text
    assert '"reason": "ttl_expired"' in text


@pytest.mark.asyncio
async def test_subscribe_stream_marks_connection_lost_without_emitting_close(
    mcp_app, monkeypatch
):
    team = await _team("stream-lost", mcp_app.actor)
    tool = await _tool(team)
    handle = _ScriptedHandle([], failure=RuntimeError("socket closed"))
    monkeypatch.setattr(tool_mcp, "open_subscription", _fake_open(handle))

    response = await _subscribe(tool, team, mcp_app.actor)
    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(chunks)

    assert "event: subscription_opened" in text
    assert "event: subscription_closed" not in text
    assert handle.close_reason == SubscriptionClosed.CONNECTION_LOST


@pytest.mark.asyncio
async def test_subscribe_stream_marks_client_disconnect_and_propagates_cancel(
    mcp_app, monkeypatch
):
    team = await _team("stream-cancel", mcp_app.actor)
    tool = await _tool(team)
    handle = _ScriptedHandle([], failure=asyncio.CancelledError())
    monkeypatch.setattr(tool_mcp, "open_subscription", _fake_open(handle))

    response = await _subscribe(tool, team, mcp_app.actor)

    with pytest.raises(asyncio.CancelledError):
        async for _chunk in response.body_iterator:
            pass
    assert handle.close_reason == SubscriptionClosed.CLIENT_DISCONNECTED


# ---------------------------------------------------------------------------
# Subscription runtime: queue, TTL, notification filtering and cleanup
# ---------------------------------------------------------------------------


def _handle(uri: str = "file:///a") -> SubscriptionHandle:
    return SubscriptionHandle(
        id=uuid4(),
        tool_id=uuid4(),
        team_id=uuid4(),
        user_id=uuid4(),
        uri=uri,
    )


def test_subscription_queue_drops_oldest_updates_when_saturated():
    handle = _handle()
    for index in range(MAX_QUEUED_UPDATES + 3):
        handle.enqueue_update(f"file:///item-{index}")

    assert handle._queue.qsize() == MAX_QUEUED_UPDATES
    queued = []
    while not handle._queue.empty():
        queued.append(handle._queue.get_nowait())

    assert [event["sequence"] for event in queued] == list(
        range(4, MAX_QUEUED_UPDATES + 4)
    )
    assert queued[0]["uri"] == "file:///item-3"
    assert queued[-1]["uri"] == f"file:///item-{MAX_QUEUED_UPDATES + 2}"


@pytest.mark.asyncio
async def test_subscription_events_end_at_ttl_without_overwriting_close_reason():
    expired = _handle()
    expired.expires_at = now_utc() - timedelta(seconds=1)
    assert [event async for event in expired.events()] == []
    assert expired.close_reason == SubscriptionClosed.TTL_EXPIRED

    already_closed = _handle()
    already_closed.expires_at = now_utc() - timedelta(seconds=1)
    already_closed.close_reason = "operator_closed"
    assert [event async for event in already_closed.events()] == []
    assert already_closed.close_reason == "operator_closed"


@pytest.mark.asyncio
async def test_subscription_events_emit_heartbeat_until_deadline(monkeypatch):
    monkeypatch.setattr(mcp_subscriptions, "HEARTBEAT_SECONDS", 0.01)
    handle = _handle()
    handle.expires_at = now_utc() + timedelta(seconds=0.05)

    events = [event async for event in handle.events()]

    assert events
    assert all(event is None for event in events)
    assert handle.close_reason == SubscriptionClosed.TTL_EXPIRED


@pytest.mark.asyncio
async def test_subscription_events_stop_on_sentinel_without_expiring():
    handle = _handle()
    handle.expires_at = now_utc() + timedelta(seconds=60)
    await handle._queue.put(None)

    with pytest.raises(StopAsyncIteration):
        await handle.events().__anext__()
    assert handle.close_reason is None


@pytest.mark.asyncio
async def test_notification_collector_unwraps_root_and_mappings():
    handle = _handle("file:///target")
    collector = mcp_subscriptions._NotificationCollector(handle)

    # SDK message wrapper (root) with an attribute-style payload.
    await collector(
        SimpleNamespace(
            root=SimpleNamespace(
                method="notifications/resources/updated",
                params=SimpleNamespace(uri="file:///target"),
            )
        )
    )
    # Plain mapping payload and mapping params.
    await collector(
        {
            "method": "notifications/resources/updated",
            "params": {"uri": "file:///target"},
        }
    )
    # Filtered out: wrong method, other URI, non-string URI.
    await collector({"method": "notifications/tools/list_changed"})
    await collector(
        {
            "method": "notifications/resources/updated",
            "params": {"uri": "file:///other"},
        }
    )
    await collector(
        {
            "method": "notifications/resources/updated",
            "params": {"uri": 42},
        }
    )
    # Only the three target updates were queued.
    await collector(
        types.ResourceUpdatedNotification(
            params=types.ResourceUpdatedNotificationParams(uri="file:///target")
        )
    )

    queued = []
    while not handle._queue.empty():
        queued.append(handle._queue.get_nowait())
    assert [event["sequence"] for event in queued] == [1, 2, 3]
    assert {event["uri"] for event in queued} == {"file:///target"}


class _FakeSession:
    def __init__(self, client: "_FakeClient") -> None:
        self.client = client

    async def subscribe_resource(self, uri: str) -> None:
        self.client.subscribed.append(uri)

    async def unsubscribe_resource(self, uri: str) -> None:
        self.client.unsubscribed.append(uri)


class _FakeClient:
    def __init__(self, config, *, callbacks=None, **kwargs) -> None:
        self.config = config
        self.callbacks = callbacks
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def get_capabilities(self, *, timeout=None):
        return SimpleNamespace(resources_subscribe=True)

    @asynccontextmanager
    async def connect(self, *, timeout=None):
        try:
            yield _FakeSession(self)
        finally:
            self.closed = True


class _FailingSubscribeClient(_FakeClient):
    last: "_FailingSubscribeClient | None" = None

    def __init__(self, config, *, callbacks=None, **kwargs) -> None:
        super().__init__(config, callbacks=callbacks, **kwargs)
        type(self).last = self

    async def get_capabilities(self, *, timeout=None):
        return SimpleNamespace(resources_subscribe=True)

    @asynccontextmanager
    async def connect(self, *, timeout=None):
        client = self

        class _Session(_FakeSession):
            async def subscribe_resource(self, uri: str) -> None:
                client.subscribed.append(uri)
                raise McpError("subscribe rejected")

        try:
            yield _Session(client)
        finally:
            client.closed = True


@pytest.mark.asyncio
async def test_open_subscription_enforces_ttl_floor(monkeypatch):
    monkeypatch.setattr(mcp_subscriptions, "McpClient", _FakeClient)

    async with open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={"transport": "http", "url": "https://mcp.example"},
        uri="file:///a",
        user_id=uuid4(),
        team_id=uuid4(),
        ttl_seconds=0.1,
    ) as handle:
        remaining = (handle.expires_at - now_utc()).total_seconds()
        assert 4.0 < remaining <= 5.0


@pytest.mark.asyncio
async def test_open_subscription_surfaces_subscribe_failure_and_skips_unsubscribe(
    monkeypatch,
):
    monkeypatch.setattr(mcp_subscriptions, "McpClient", _FailingSubscribeClient)

    with pytest.raises(McpError, match="subscribe rejected"):
        async with open_subscription(
            tool=SimpleNamespace(id=uuid4()),
            config={"transport": "http", "url": "https://mcp.example"},
            uri="file:///a",
            user_id=uuid4(),
            team_id=uuid4(),
            ttl_seconds=30,
        ):
            pass

    client = _FailingSubscribeClient.last
    assert client is not None
    assert client.subscribed == ["file:///a"]
    assert client.unsubscribed == []
    assert client.closed is True


@pytest.mark.asyncio
async def test_open_subscription_unsubscribe_failure_is_best_effort(monkeypatch):
    class _UnsubscribeFailingClient(_FakeClient):
        async def get_capabilities(self, *, timeout=None):
            return SimpleNamespace(resources_subscribe=True)

        @asynccontextmanager
        async def connect(self, *, timeout=None):
            client = self

            class _Session(_FakeSession):
                async def unsubscribe_resource(self, uri: str) -> None:
                    client.unsubscribed.append(uri)
                    raise RuntimeError("unsubscribe failed")

            try:
                yield _Session(client)
            finally:
                client.closed = True

    monkeypatch.setattr(mcp_subscriptions, "McpClient", _UnsubscribeFailingClient)

    async with open_subscription(
        tool=SimpleNamespace(id=uuid4()),
        config={"transport": "http", "url": "https://mcp.example"},
        uri="file:///a",
        user_id=uuid4(),
        team_id=uuid4(),
        ttl_seconds=30,
    ) as handle:
        assert handle.uri == "file:///a"

    assert handle.close_reason is None
