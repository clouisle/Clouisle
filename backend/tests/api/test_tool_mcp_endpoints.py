"""ASGI behavior tests for the authenticated MCP operations API.

The database is real in-memory SQLite; only the MCP protocol helper functions
and the interaction-session wrapper are mocked. This keeps authorization,
consuming-team identity resolution, approval persistence and resume behavior
honest without starting any external service.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from tortoise import Tortoise

from app.api import deps
from app.api.v1.endpoints import tool_mcp
from app.llm.tools.mcp_client import (
    McpCallbacks,
    McpCapabilityUnavailable,
    McpCompletion,
    McpContentBlock,
    McpContentTooLarge,
    McpEnumeration,
    McpError,
    McpInputRequired,
    McpInputRequiredInfo,
    McpPromptArgument,
    McpPromptInfo,
    McpPromptMessage,
    McpPromptResult,
    McpResourceContents,
    McpResourceTemplateInfo,
    McpServerCapabilities,
    McpTimeout,
    McpToolInfo,
    McpToolResult,
)
from app.models.tool import (
    Tool,
    ToolShare,
    ToolSharePermission,
    ToolType,
    ToolVisibility,
)
from app.models.tool_connection import ToolConnectionScope
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, error
from app.schemas.tool_connection import ToolConnectionCreate
from app.services.tool_connections import ToolConnectionService
from app.services.tool_oauth import ToolOAuthService


def _allow_policy() -> dict:
    return {"default_decision": "allow"}


def _caller_policy() -> dict:
    return {"default_decision": "require_approval", "gates": [{"kind": "caller"}]}


async def _user(superuser: bool = True) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"mcp_{suffix}",
        email=f"mcp_{suffix}@tool-mcp.test",
        hashed_password="x",
        is_superuser=superuser,
    )


async def _team(name: str, actor: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"{name}_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=actor.id, role="owner")
    return team


async def _tool(
    team: Team,
    *,
    approval_policy: dict | None = None,
    identity_policy: str = "none",
    connection_fields: list | None = None,
    mcp_config: dict | None = None,
    visibility: ToolVisibility = ToolVisibility.TEAM,
) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="MCP tool",
        description="behavior test",
        type=ToolType.MCP,
        visibility=visibility,
        identity_policy=identity_policy,
        connection_fields=connection_fields or [],
        approval_policy=(
            approval_policy if approval_policy is not None else _allow_policy()
        ),
        mcp_config=mcp_config
        or {
            "transport": "sse",
            "url": "https://mcp.example/sse",
            "headers": {"X-Static": "static"},
        },
    )


async def _team_connection(team: Team, tool: Tool, token: str, actor: User) -> None:
    await ToolConnectionService.create_connection(
        actor=actor,
        payload=ToolConnectionCreate(
            team_id=team.id,
            scope=ToolConnectionScope.TEAM,
            tool_id=tool.id,
            name=f"conn_{uuid4().hex[:8]}",
            config={"token": token},
            is_default=True,
        ),
        declared_secret_fields={"token"},
        required_secret_fields={"token"},
    )


async def _share(tool: Tool, team: Team, actor: User) -> None:
    await ToolShare.create(
        id=uuid4(),
        tool_id=tool.id,
        shared_with_team_id=team.id,
        permission=ToolSharePermission.READ_EXECUTE,
        shared_by_id=actor.id,
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


@pytest.mark.asyncio
async def test_cross_team_shared_tool_uses_consuming_team_identity(
    mcp_app, monkeypatch
):
    owning_team = await _team("owning", mcp_app.actor)
    consuming_team = await _team("consuming", mcp_app.actor)
    other_team = await _team("other", mcp_app.actor)
    tool = await _tool(
        owning_team,
        identity_policy="team_only",
        connection_fields=[
            {"name": "token", "label": "Token", "required": True, "secret": True}
        ],
        mcp_config={
            "transport": "sse",
            "url": "https://mcp.example/sse",
            "headers": {"Authorization": "Bearer {{token}}"},
        },
    )
    await _team_connection(owning_team, tool, "owning-secret", mcp_app.actor)
    await _team_connection(consuming_team, tool, "consuming-secret", mcp_app.actor)
    await _share(tool, consuming_team, mcp_app.actor)

    enumerate_mock = AsyncMock(
        return_value=McpEnumeration(
            items=[McpToolInfo(name="search", description=None, parameters={})],
            pages_fetched=1,
        )
    )
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(consuming_team.id)}
    )

    assert response.status_code == 200
    assert response.json()["data"]["result"]["items"][0]["name"] == "search"
    config = enumerate_mock.await_args.args[0]
    assert config["headers"]["Authorization"] == "Bearer consuming-secret"
    assert "consuming-secret" not in response.text
    assert "owning-secret" not in response.text

    # The owning team keeps its own identity for the same shared definition.
    owning_response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(owning_team.id)}
    )
    assert owning_response.status_code == 200
    owning_config = enumerate_mock.await_args.args[0]
    assert owning_config["headers"]["Authorization"] == "Bearer owning-secret"

    denied = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(other_team.id)}
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 403


@pytest.mark.asyncio
async def test_metadata_listing_forwards_cursor_and_item_bounds(mcp_app, monkeypatch):
    team = await _team("cursor", mcp_app.actor)
    tool = await _tool(team)
    enumerate_mock = AsyncMock(
        return_value=McpEnumeration(
            items=[], pages_fetched=1, truncated=True, next_cursor="next-page"
        )
    )
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools",
        params={"team_id": str(team.id), "max_items": 5, "cursor": "page-2"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["result"]["next_cursor"] == "next-page"
    assert enumerate_mock.await_args.kwargs["start_cursor"] == "page-2"
    assert enumerate_mock.await_args.kwargs["limits"].max_items == 5


@pytest.mark.asyncio
async def test_direct_mcp_tool_call_executes_without_approval(mcp_app, monkeypatch):
    """Direct tool calls outside agent conversation never trigger approval."""
    team = await _team("approval", mcp_app.actor)
    tool = await _tool(team, approval_policy=_caller_policy())
    execute_mock = AsyncMock(
        return_value=McpToolResult(success=True, result={"ok": True})
    )
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", execute_mock)
    body = {"name": "ticket.close", "arguments": {"id": 7}}

    response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        params={"team_id": str(team.id)},
        json=body,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["operation"] == "tool:ticket.close"
    assert data["result"]["result"] == {"ok": True}
    execute_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_prompt_and_completion_use_distinct_operation_namespaces(
    mcp_app, monkeypatch
):
    team = await _team("namespaces", mcp_app.actor)
    tool = await _tool(team)
    read_mock = AsyncMock(
        return_value=[
            McpResourceContents(
                uri="file:///notes.txt", text="hello", mime_type="text/plain"
            )
        ]
    )
    prompt_mock = AsyncMock(
        return_value=McpPromptResult(
            messages=[
                McpPromptMessage(
                    role="user",
                    content=McpContentBlock(type="text", text="hi"),
                )
            ]
        )
    )
    complete_mock = AsyncMock(return_value=McpCompletion(values=["alpha"]))
    monkeypatch.setattr(tool_mcp, "read_mcp_resource", read_mock)
    monkeypatch.setattr(tool_mcp, "get_mcp_prompt", prompt_mock)
    monkeypatch.setattr(tool_mcp, "complete_mcp_argument", complete_mock)

    read_response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/resources/read",
        params={"team_id": str(team.id)},
        json={"uri": "file:///notes.txt"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["data"]["operation"] == "read:resource"
    assert read_response.json()["data"]["result"][0]["text"] == "hello"
    assert read_mock.await_args.args[1] == "file:///notes.txt"

    prompt_response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/prompts/get",
        params={"team_id": str(team.id)},
        json={"name": "weather", "arguments": {"city": "Paris"}},
    )
    assert prompt_response.status_code == 200
    assert prompt_response.json()["data"]["operation"] == "prompt:weather"
    assert prompt_mock.await_args.args[1] == "weather"

    completion_response = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/completion",
        params={"team_id": str(team.id)},
        json={
            "reference": {"kind": "prompt", "name": "weather"},
            "argument_name": "city",
            "argument_value": "Pa",
        },
    )
    assert completion_response.status_code == 200
    assert completion_response.json()["data"]["operation"] == "complete:prompt"
    assert completion_response.json()["data"]["result"]["values"] == ["alpha"]
    reference = complete_mock.await_args.args[1]
    assert reference.kind == "prompt"
    assert reference.name == "weather"


@pytest.mark.asyncio
async def test_oauth_authorization_overrides_static_header_for_metadata_and_calls(
    mcp_app, monkeypatch
):
    team = await _team("oauth", mcp_app.actor)
    tool = await _tool(
        team,
        identity_policy="team_only",
        connection_fields=[
            {"name": "token", "label": "Token", "required": True, "secret": True}
        ],
        mcp_config={
            "transport": "sse",
            "url": "https://mcp.example/sse",
            "oauth": {"authorization_url": "https://auth.example/authorize"},
            "headers": {
                "authorization": "Bearer static",
                "X-Static": "static",
            },
        },
    )
    await _team_connection(team, tool, "connection-secret", mcp_app.actor)
    header_mock = AsyncMock(return_value="Bearer fresh")
    monkeypatch.setattr(ToolOAuthService, "get_authorization_header", header_mock)
    enumerate_mock = AsyncMock(return_value=McpEnumeration(items=[]))
    execute_mock = AsyncMock(
        return_value=McpToolResult(success=True, result={"ok": True})
    )
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)
    monkeypatch.setattr(tool_mcp, "execute_mcp_tool", execute_mock)

    listing = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(team.id)}
    )
    assert listing.status_code == 200
    listing_headers = enumerate_mock.await_args.args[0]["headers"]
    assert "authorization" not in listing_headers
    assert listing_headers["Authorization"] == "Bearer fresh"
    header_mock.assert_awaited()

    call = await mcp_app.client.post(
        f"/tools/{tool.id}/mcp/tools/call",
        params={"team_id": str(team.id)},
        json={"name": "search", "arguments": {}},
    )
    assert call.status_code == 200
    call_headers = execute_mock.await_args.args[0]["headers"]
    assert "authorization" not in call_headers
    assert call_headers["Authorization"] == "Bearer fresh"


@pytest.mark.asyncio
async def test_oauth_requires_a_resolved_connection(mcp_app, monkeypatch):
    team = await _team("oauth-none", mcp_app.actor)
    tool = await _tool(
        team,
        mcp_config={
            "transport": "sse",
            "url": "https://mcp.example/sse",
            "oauth": {"authorization_url": "https://auth.example/authorize"},
        },
    )
    enumerate_mock = AsyncMock(return_value=McpEnumeration(items=[]))
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(team.id)}
    )

    assert response.status_code == 403
    assert response.json()["code"] == 403
    enumerate_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_listing_never_requires_approval(mcp_app, monkeypatch):
    """Listing tools and resources is discovery metadata and never requires approval."""
    team = await _team("metadata-policy", mcp_app.actor)
    enumerate_mock = AsyncMock(
        return_value=McpEnumeration(
            items=[McpToolInfo(name="search", description=None, parameters={})],
            pages_fetched=1,
        )
    )
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)
    tool = await _tool(team, approval_policy={"default_decision": "require_approval"})
    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/tools", params={"team_id": str(team.id)}
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert len(response.json()["data"]["result"]["items"]) == 1
    assert enumerate_mock.await_count == 1


@pytest.mark.asyncio
async def test_capabilities_and_tool_validation_errors(mcp_app, monkeypatch):
    team = await _team("validation", mcp_app.actor)
    tool = await _tool(team)
    probe_mock = AsyncMock(
        return_value=McpServerCapabilities(
            protocol_version="2026-07-28",
            server_name="demo",
            tools=True,
            resources=True,
            prompts=True,
        )
    )
    monkeypatch.setattr(tool_mcp, "probe_mcp_capabilities", probe_mock)

    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/capabilities", params={"team_id": str(team.id)}
    )
    assert response.status_code == 200
    assert response.json()["data"]["result"]["server_name"] == "demo"
    assert response.json()["data"]["result"]["tools"] is True

    missing = await mcp_app.client.get(
        f"/tools/{uuid4()}/mcp/capabilities", params={"team_id": str(team.id)}
    )
    assert missing.status_code == 404

    custom = await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"custom_{uuid4().hex[:8]}",
        display_name="Custom",
        description="not mcp",
        type=ToolType.CUSTOM,
        mcp_config={"transport": "sse", "url": "https://example.test"},
    )
    invalid_type = await mcp_app.client.get(
        f"/tools/{custom.id}/mcp/capabilities", params={"team_id": str(team.id)}
    )
    assert invalid_type.status_code == 400
    assert invalid_type.json()["code"] == 1002


@pytest.mark.asyncio
async def test_all_metadata_routes_surface_their_item_shapes(mcp_app, monkeypatch):
    team = await _team("metadata", mcp_app.actor)
    tool = await _tool(team)
    resource_mock = AsyncMock(
        return_value=McpEnumeration(
            items=[
                tool_mcp.McpResourceInfo(
                    uri="file:///a.txt", name="a", mime_type="text/plain"
                )
            ]
        )
    )
    template_mock = AsyncMock(
        return_value=McpEnumeration(
            items=[McpResourceTemplateInfo(uri_template="file:///{path}", name="files")]
        )
    )
    prompt_mock = AsyncMock(
        return_value=McpEnumeration(
            items=[
                McpPromptInfo(
                    name="weather",
                    arguments=[McpPromptArgument(name="city", required=True)],
                )
            ]
        )
    )
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_resources", resource_mock)
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_resource_templates", template_mock)
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_prompts", prompt_mock)

    resources = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resources", params={"team_id": str(team.id)}
    )
    assert resources.json()["data"]["result"]["items"][0]["uri"] == "file:///a.txt"

    templates = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resource-templates",
        params={"team_id": str(team.id)},
    )
    assert (
        templates.json()["data"]["result"]["items"][0]["uri_template"]
        == "file:///{path}"
    )

    prompts = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/prompts", params={"team_id": str(team.id)}
    )
    assert (
        prompts.json()["data"]["result"]["items"][0]["arguments"][0]["required"] is True
    )


def test_protocol_error_mapping_covers_every_failure_class():
    tool = SimpleNamespace(id=uuid4())

    cases = [
        (
            McpCapabilityUnavailable("resources"),
            "mcp_capability_unavailable",
            409,
            1002,
        ),
        (McpTimeout("slow", timeout_seconds=1), "mcp_request_timeout", 504, 1003),
        (
            McpContentTooLarge(
                "too big", bytes_received=20, byte_limit=10, source="test"
            ),
            "mcp_content_too_large",
            413,
            1002,
        ),
        (
            McpInputRequired(McpInputRequiredInfo(method="tools/call")),
            "mcp_input_required",
            409,
            1002,
        ),
        (McpError("transport"), "mcp_connection_failed", 502, 1003),
        (RuntimeError("boom"), "mcp_connection_failed", 502, 1003),
    ]

    for exc, msg_key, status, code in cases:
        mapped = tool_mcp._mcp_business_error(exc, operation="tool:x", tool=tool)
        assert mapped.msg_key == msg_key
        assert mapped.status_code == status
        assert int(mapped.code) == code


@pytest.mark.asyncio
async def test_protocol_failures_become_business_errors(mcp_app, monkeypatch):
    team = await _team("protocol-errors", mcp_app.actor)
    tool = await _tool(team)

    unavailable = AsyncMock(side_effect=McpCapabilityUnavailable("resources"))
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_resources", unavailable)
    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/resources", params={"team_id": str(team.id)}
    )
    assert response.status_code == 409
    assert response.json()["code"] == 1002

    timeout = AsyncMock(side_effect=McpTimeout("slow", timeout_seconds=1))
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_prompts", timeout)
    response = await mcp_app.client.get(
        f"/tools/{tool.id}/mcp/prompts", params={"team_id": str(team.id)}
    )
    assert response.status_code == 504
    assert response.json()["code"] == 1003


@pytest.mark.asyncio
async def test_missing_config_and_selectable_identity_fail_closed(mcp_app, monkeypatch):
    team = await _team("closed", mcp_app.actor)
    no_config = await _tool(team)
    await Tool.filter(id=no_config.id).update(mcp_config={})
    enumerate_mock = AsyncMock(return_value=McpEnumeration(items=[]))
    monkeypatch.setattr(tool_mcp, "enumerate_mcp_tools", enumerate_mock)

    missing = await mcp_app.client.get(
        f"/tools/{no_config.id}/mcp/tools", params={"team_id": str(team.id)}
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == 1002

    selectable = await _tool(team, identity_policy="selectable")
    no_mode = await mcp_app.client.get(
        f"/tools/{selectable.id}/mcp/tools", params={"team_id": str(team.id)}
    )
    assert no_mode.status_code == 400
    assert no_mode.json()["code"] == 400
    enumerate_mock.assert_not_awaited()
