"""End-to-end MRTR behavior for the authenticated MCP operations API.

The database is real in-memory SQLite and only the MCP protocol helpers are
mocked, so approval binding, identity resolution and the wire contract between
schema, endpoint and adapter stay honest.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import mcp.types as types
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from tortoise import Tortoise

from app.api import deps
from app.api.v1.endpoints import tool_mcp
from app.llm.tools.mcp_client import (
    McpCallbacks,
    McpInputRequired,
    McpInputRequiredInfo,
    McpToolResult,
)
from app.models.tool import Tool, ToolType, ToolVisibility
from app.models.tool_connection import ToolConnectionScope
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, error
from app.schemas.tool_connection import ToolConnectionCreate
from app.services.tool_approvals import build_parameter_snapshot
from app.services.tool_connections import ToolConnectionService

ELICITATION_REQUEST = {
    "method": "elicitation/create",
    "params": {
        "mode": "form",
        "message": "Which environment?",
        "requestedSchema": {"type": "object", "properties": {}},
    },
}
ANSWERS = {"q1": {"method": "elicitation/create", "result": {"action": "accept"}}}


async def _user() -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"mrtr_{suffix}",
        email=f"mrtr_{suffix}@tool-mcp.test",
        hashed_password="x",
        is_superuser=True,
    )


async def _team(actor: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"mrtr_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=actor.id, role="owner")
    return team


async def _tool(team: Team, *, with_identity: bool = True) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="MCP tool",
        description="mrtr test",
        type=ToolType.MCP,
        visibility=ToolVisibility.TEAM,
        identity_policy="team_only" if with_identity else "none",
        connection_fields=(
            [{"name": "token", "label": "Token", "required": True, "secret": True}]
            if with_identity
            else []
        ),
        approval_policy={"default_decision": "allow"},
        mcp_config=(
            {
                "transport": "sse",
                "url": "https://mcp.example/sse",
                "headers": {"Authorization": "Bearer {{token}}"},
            }
            if with_identity
            else {"transport": "sse", "url": "https://mcp.example/sse"}
        ),
    )


async def _connection(team: Team, tool: Tool, actor: User):
    return await ToolConnectionService.create_connection(
        actor=actor,
        payload=ToolConnectionCreate(
            team_id=team.id,
            scope=ToolConnectionScope.TEAM,
            tool_id=tool.id,
            name=f"conn_{uuid4().hex[:8]}",
            config={"token": "secret-token"},
            is_default=True,
        ),
        declared_secret_fields={"token"},
        required_secret_fields={"token"},
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


def _parked(method: str) -> McpToolResult:
    return McpToolResult(
        success=False,
        error="MCP server requires additional input",
        input_required=McpInputRequiredInfo(
            method=method,
            requests={"q1": ELICITATION_REQUEST},
            request_state="state-1",
        ),
    )


# ---------------------------------------------------------------------------
# The parked leg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_returns_the_state_needed_to_resume(mcp_app, monkeypatch):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    connection = await _connection(team, tool, mcp_app.actor)
    monkeypatch.setattr(
        tool_mcp, "execute_mcp_tool", AsyncMock(return_value=_parked("tools/call"))
    )

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {"q": 1},
            "connection_id": str(connection.id),
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 200
    result = response.json()["data"]["result"]
    assert result["success"] is False
    assert result["input_required"]["request_state"] == "state-1"
    assert result["input_required"]["requests"]["q1"]["method"] == "elicitation/create"


# ---------------------------------------------------------------------------
# The resuming leg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_forwards_answers_under_the_same_identity(mcp_app, monkeypatch):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    connection = await _connection(team, tool, mcp_app.actor)
    mock = AsyncMock(return_value=McpToolResult(success=True, result="ok"))
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", mock)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {"q": 1},
            "connection_id": str(connection.id),
            "request_state": "state-1",
            "input_responses": ANSWERS,
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["result"]["success"] is True
    kwargs = mock.await_args.kwargs
    assert kwargs["request_state"] == "state-1"
    assert isinstance(kwargs["input_responses"]["q1"], types.ElicitResult)
    assert kwargs["input_responses"]["q1"].action == "accept"
    assert mock.await_args.args[0]["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_resource_read_reports_the_parked_requests(mcp_app, monkeypatch):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    connection = await _connection(team, tool, mcp_app.actor)
    monkeypatch.setattr(
        tool_mcp,
        "read_mcp_resource",
        AsyncMock(
            side_effect=McpInputRequired(
                McpInputRequiredInfo(
                    method="resources/read",
                    requests={"q1": ELICITATION_REQUEST},
                    request_state="state-1",
                )
            )
        ),
    )

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/resources/read",
        json={
            "uri": "file:///a.txt",
            "connection_id": str(connection.id),
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["data"]["input_required"]["request_state"] == "state-1"
    assert body["data"]["input_required"]["requests"]["q1"]["method"] == (
        "elicitation/create"
    )


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answers_without_an_explicit_connection_are_rejected(
    mcp_app, monkeypatch
):
    """A tool that runs under an external account must pin that account."""
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    mock = AsyncMock(return_value=McpToolResult(success=True))
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", mock)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {},
            "connection_mode": "team",
            "request_state": "state-1",
            "input_responses": ANSWERS,
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 409
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_identity_less_tools_resume_without_a_connection(mcp_app, monkeypatch):
    """No external account means nothing can drift between the two legs."""
    team = await _team(mcp_app.actor)
    tool = await _tool(team, with_identity=False)
    mock = AsyncMock(return_value=McpToolResult(success=True, result="ok"))
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", mock)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {},
            "request_state": "state-1",
            "input_responses": ANSWERS,
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 200
    assert mock.await_args.kwargs["request_state"] == "state-1"


@pytest.mark.asyncio
async def test_state_without_answers_is_rejected(mcp_app, monkeypatch):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    monkeypatch.setattr(
        tool_mcp,
        "execute_mcp_tool",
        AsyncMock(return_value=McpToolResult(success=True)),
    )

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {},
            "connection_id": str(uuid4()),
            "request_state": "state-1",
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_malformed_answers_never_reach_the_server(mcp_app, monkeypatch):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    connection = await _connection(team, tool, mcp_app.actor)
    mock = AsyncMock(return_value=McpToolResult(success=True))
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", mock)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {},
            "connection_id": str(connection.id),
            "request_state": "state-1",
            "input_responses": {
                "q1": {"method": "elicitation/create", "result": {"action": "maybe"}}
            },
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 400
    assert mock.await_count == 0


# ---------------------------------------------------------------------------
# Approval binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,payload,helper",
    [
        ("mcp/tools/call", {"name": "search", "arguments": {}}, "execute_mcp_tool"),
        ("mcp/resources/read", {"uri": "file:///a.txt"}, "read_mcp_resource"),
        ("mcp/prompts/get", {"name": "greet", "arguments": {}}, "get_mcp_prompt"),
    ],
)
async def test_malformed_answers_are_rejected_on_every_route(
    mcp_app, monkeypatch, path, payload, helper
):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    connection = await _connection(team, tool, mcp_app.actor)
    mock = AsyncMock(return_value=McpToolResult(success=True))
    monkeypatch.setattr(tool_mcp, helper, mock)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/{path}",
        json={
            **payload,
            "connection_id": str(connection.id),
            "request_state": "state-1",
            "input_responses": {
                "q1": {"method": "elicitation/create", "result": {"action": "maybe"}}
            },
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 400
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_empty_answers_are_rejected(mcp_app, monkeypatch):
    team = await _team(mcp_app.actor)
    tool = await _tool(team)
    connection = await _connection(team, tool, mcp_app.actor)
    mock = AsyncMock(return_value=McpToolResult(success=True))
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", mock)

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        json={
            "name": "search",
            "arguments": {},
            "connection_id": str(connection.id),
            "input_responses": {},
        },
        params={"team_id": str(team.id)},
    )

    assert response.status_code == 422
    assert mock.await_count == 0


def test_answers_are_part_of_the_approval_digest():
    base = {"name": "search", "arguments": {"q": 1}, "request_state": "state-1"}
    accept = build_parameter_snapshot({**base, "input_responses": ANSWERS})
    decline = build_parameter_snapshot(
        {
            **base,
            "input_responses": {
                "q1": {"method": "elicitation/create", "result": {"action": "decline"}}
            },
        }
    )

    assert accept.digest != decline.digest


def test_a_plain_call_keeps_the_legacy_digest():
    """Executions parked before this change must still resume."""
    payload = SimpleNamespace(request_state=None, input_responses=None)

    assert tool_mcp._round_trip_parameters(payload) == {}
