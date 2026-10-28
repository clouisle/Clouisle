"""Request-scoped MCP resource subscriptions.

Runtime behavior is exercised with a fake MCP client/session (no network), and
the SSE endpoint over an in-memory ASGI transport with a real SQLite
authorization/approval boundary.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp import types
from tortoise import Tortoise
from tortoise.context import TortoiseContext

from app.api import deps
from app.api.v1.endpoints import tool_mcp
from app.llm.tools.mcp_client import McpCallbacks
from app.models.tool import Tool, ToolType
from app.models.tool_approval import ToolExecution
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, error
from app.services.mcp_subscriptions import open_subscription


# ---------------------------------------------------------------------------
# Runtime: fake MCP client/session
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, client: "_FakeClient") -> None:
        self.client = client

    async def subscribe_resource(self, uri: str) -> None:
        self.client.subscribed.append(uri)
        if self.client.push_on_subscribe:
            await self.client.notify(uri)

    async def unsubscribe_resource(self, uri: str) -> None:
        self.client.unsubscribed.append(uri)


class _FakeClient:
    def __init__(
        self, config, *, callbacks: McpCallbacks | None = None, **kwargs
    ) -> None:
        self.config = config
        self.callbacks = callbacks
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False
        self.push_on_subscribe = bool(config.get("_push_on_subscribe"))
        type(self).last = self

    async def get_capabilities(self, *, timeout=None):
        if self.config.get("_capability") is False:
            return SimpleNamespace(resources_subscribe=False)
        return SimpleNamespace(resources_subscribe=True)

    @asynccontextmanager
    async def connect(self, *, timeout=None):
        try:
            yield _FakeSession(self)
        finally:
            self.closed = True

    async def notify(self, uri: str) -> None:
        if self.callbacks is None or self.callbacks.notification is None:
            return
        await self.callbacks.notification(
            types.ResourceUpdatedNotification(
                params=types.ResourceUpdatedNotificationParams(uri=uri)
            )
        )


def test_subscription_runtime_requires_capability_and_cleans_up(monkeypatch):
    monkeypatch.setattr("app.services.mcp_subscriptions.McpClient", _FakeClient)

    async def scenario():
        tool = SimpleNamespace(id=uuid4())
        with pytest.raises(Exception) as unavailable:
            async with open_subscription(
                tool=tool,
                config={"_capability": False},
                uri="file:///a",
                user_id=uuid4(),
                team_id=uuid4(),
            ):
                pass
        assert "resources.subscribe" in str(unavailable.value)

        async with open_subscription(
            tool=tool,
            config={"_push_on_subscribe": True},
            uri="file:///a",
            user_id=uuid4(),
            team_id=uuid4(),
            connection_id=uuid4(),
            connection_scope="team",
            account_label="svc",
            ttl_seconds=30,
        ) as handle:
            assert handle.opened_event()["account_label"] == "svc"
            stream = handle.events()
            update = await asyncio.wait_for(stream.__anext__(), timeout=1)
            assert update is not None
            assert update["uri"] == "file:///a"
            assert update["sequence"] == 1
            await stream.aclose()
            client = _FakeClient.last
            assert client.subscribed == ["file:///a"]

        assert client.unsubscribed == ["file:///a"]
        assert client.closed is True

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Endpoint over ASGI memory transport
# ---------------------------------------------------------------------------


async def _user() -> User:
    return await User.create(
        id=uuid4(),
        username=f"user_{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@sub.test",
        hashed_password="x",
        is_superuser=True,
    )


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _tool(team: Team, *, policy: dict) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="MCP sub",
        description="sub test",
        type=ToolType.MCP,
        mcp_config={"transport": "http", "url": "https://mcp.example"},
        approval_policy=policy,
    )


class _FakeHandle(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(
            id=uuid4(),
            close_reason=None,
            opened_event=lambda: {
                "subscription_id": str(self.id),
                "uri": "file:///a",
                "connection_id": None,
            },
        )

    async def events(self):
        yield {
            "subscription_id": str(self.id),
            "uri": "file:///a",
            "sequence": 1,
            "received_at": "now",
        }


@pytest_asyncio.fixture
async def sub_app(monkeypatch, tmp_path):
    url = f"sqlite://{tmp_path / 'subscriptions.sqlite3'}"
    async with TortoiseContext() as context:
        await context.init(db_url=url, modules={"models": ["app.models"]})
        await context.generate_schemas()
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

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api"
        ) as client:
            yield SimpleNamespace(client=client, actor=actor)
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_subscribe_stream_authorizes_then_emits_scoped_events(
    sub_app, monkeypatch
):
    team = await _team(sub_app.actor)
    tool = await _tool(team, policy={"default_decision": "allow"})
    captured: dict = {}

    @asynccontextmanager
    async def fake_open(**kwargs):
        captured.update(kwargs)
        yield _FakeHandle()

    monkeypatch.setattr(tool_mcp, "open_subscription", fake_open)

    response = await sub_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={"team_id": str(team.id), "uri": "file:///a"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: subscription_opened" in response.text
    assert "event: resource_updated" in response.text
    assert "event: subscription_closed" in response.text
    assert captured["uri"] == "file:///a"
    assert captured["team_id"] == team.id
    assert (
        captured["connection_id"] is None
    )  # identity policy none, no secret reflected

    execution = await ToolExecution.all().first()
    assert execution is not None
    assert execution.operation == "subscribe:resource"


@pytest.mark.asyncio
async def test_subscribe_without_server_capability_is_rejected(sub_app, monkeypatch):
    team = await _team(sub_app.actor)
    tool = await _tool(team, policy={"default_decision": "allow"})

    class _NoSubscribeClient(_FakeClient):
        async def get_capabilities(self, *, timeout=None):
            return SimpleNamespace(resources_subscribe=False)

    monkeypatch.setattr("app.services.mcp_subscriptions.McpClient", _NoSubscribeClient)
    response = await sub_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={"team_id": str(team.id), "uri": "file:///a"},
    )
    assert response.status_code == 409
    assert "capab" in response.json()["msg"].lower()


@pytest.mark.asyncio
async def test_subscribe_rejects_other_team_without_share(sub_app, monkeypatch):
    owner_team = await _team(sub_app.actor)
    tool = await _tool(owner_team, policy={"default_decision": "allow"})
    other_team = await Team.create(id=uuid4(), name=f"other_{uuid4().hex[:8]}")

    @asynccontextmanager
    async def fake_open(**kwargs):
        yield _FakeHandle()

    monkeypatch.setattr(tool_mcp, "open_subscription", fake_open)
    response = await sub_app.client.get(
        f"/tools/{tool.id}/mcp/resources/subscribe",
        params={"team_id": str(other_team.id), "uri": "file:///a"},
    )
    assert response.status_code == 403
    assert await ToolExecution.all().count() == 0
