from datetime import datetime, timedelta, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import agent_stats
from app.schemas.response import BusinessError, ResponseCode, error


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(agent_stats.router, prefix="/api/v1/agents")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
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

    return app


@pytest.fixture
def client(app):
    async def current_user():
        return SimpleNamespace(id=uuid4(), is_active=True)

    app.dependency_overrides[deps.get_current_active_user] = current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_tool_usage_requires_authentication(app):
    async def reject_unauthenticated():
        raise BusinessError(status_code=403)

    app.dependency_overrides[deps.get_current_user] = reject_unauthenticated
    response = TestClient(app).get(f"/api/v1/agents/{uuid4()}/stats/tool-usage")

    assert response.status_code == 403


def test_tool_usage_returns_not_found_for_missing_agent(client, monkeypatch):
    monkeypatch.setattr(
        agent_stats,
        "check_agent_access",
        AsyncMock(
            side_effect=BusinessError(
                code=ResponseCode.AGENT_NOT_FOUND,
                msg_key="agent_not_found",
                status_code=404,
            )
        ),
    )

    response = client.get(f"/api/v1/agents/{uuid4()}/stats/tool-usage")

    assert response.status_code == 404
    assert response.json()["code"] == ResponseCode.AGENT_NOT_FOUND


def test_tool_usage_aggregates_supported_shapes_for_24_hours(client, monkeypatch):
    agent_id = uuid4()
    fixed_now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    usage = AsyncMock(
        return_value=[
            {"name": "search", "count": 2},
            {"name": "fetch", "count": 1},
        ]
    )
    monkeypatch.setattr(agent_stats, "now", lambda: fixed_now)
    monkeypatch.setattr(
        agent_stats, "check_agent_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(agent_stats.stats_sql, "agent_tool_usage", usage)
    monkeypatch.setattr(
        agent_stats,
        "get_tool_display_names",
        AsyncMock(return_value={"search": "Search", "fetch": "Fetch"}),
    )

    response = client.get(
        f"/api/v1/agents/{agent_id}/stats/tool-usage", params={"period": "24h"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "period": "24h",
        "tools": [
            {"name": "search", "display_name": "Search", "count": 2},
            {"name": "fetch", "display_name": "Fetch", "count": 1},
        ],
        "total_calls": 3,
    }
    assert usage.await_args.args[1] == fixed_now - timedelta(hours=24)
    # MCP enumeration must stay off: it is an untimed network call.
    assert agent_stats.get_tool_display_names.await_args.kwargs == {
        "enumerate_mcp_tools": False
    }


def test_tool_usage_all_period_keeps_empty_result_unfiltered(client, monkeypatch):
    agent_id = uuid4()
    usage = AsyncMock(return_value=[])
    monkeypatch.setattr(
        agent_stats, "check_agent_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(agent_stats.stats_sql, "agent_tool_usage", usage)
    monkeypatch.setattr(
        agent_stats, "get_tool_display_names", AsyncMock(return_value={})
    )

    response = client.get(
        f"/api/v1/agents/{agent_id}/stats/tool-usage", params={"period": "all"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"period": "all", "tools": [], "total_calls": 0}
    assert usage.await_args.args[1] is None


def test_tool_usage_falls_back_to_raw_names_for_unknown_tools(client, monkeypatch):
    """A tool the agent no longer has configured must still be listed."""
    agent_id = uuid4()
    monkeypatch.setattr(
        agent_stats, "check_agent_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_tool_usage",
        AsyncMock(return_value=[{"name": "retired_tool", "count": 1}]),
    )
    monkeypatch.setattr(
        agent_stats,
        "get_tool_display_names",
        AsyncMock(return_value={"web_search": "Web Search"}),
    )

    response = client.get(
        f"/api/v1/agents/{agent_id}/stats/tool-usage", params={"period": "7d"}
    )

    assert response.json()["data"]["tools"] == [
        {"name": "retired_tool", "display_name": "retired_tool", "count": 1}
    ]


def test_tool_usage_resolves_mcp_prefix_without_listing_server(client, monkeypatch):
    agent_id = uuid4()
    monkeypatch.setattr(
        agent_stats, "check_agent_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_tool_usage",
        AsyncMock(return_value=[{"name": "mcp_github_create_issue", "count": 3}]),
    )
    # Non-enumerating mode yields prefix entries. Verify the longest prefix wins.
    monkeypatch.setattr(
        agent_stats,
        "get_tool_display_names",
        AsyncMock(
            return_value={
                "mcp_github_": "GitHub/",
                "mcp_github_create_": "GitHub Issue/",
            }
        ),
    )

    response = client.get(
        f"/api/v1/agents/{agent_id}/stats/tool-usage", params={"period": "7d"}
    )

    assert response.json()["data"]["tools"] == [
        {
            "name": "mcp_github_create_issue",
            "display_name": "GitHub Issue/issue",
            "count": 3,
        }
    ]
