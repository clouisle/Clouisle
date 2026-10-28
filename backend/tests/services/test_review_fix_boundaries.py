"""Boundaries introduced by the PR-480 review fixes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.services.tool_oauth import ToolOAuthService


@pytest.mark.asyncio
async def test_team_access_rejects_private_cross_team_tool(monkeypatch):
    monkeypatch.setattr("app.api.team_access.check_team_access", AsyncMock())
    tool = SimpleNamespace(team_id=uuid4(), visibility="private", id=uuid4())

    with pytest.raises(BusinessError) as error:
        await ToolOAuthService._assert_tool_access_for_team(
            tool, uuid4(), SimpleNamespace(id=uuid4())
        )

    assert error.value.msg_key == "tool_access_denied"


@pytest.mark.asyncio
async def test_team_access_rejects_unshared_cross_team_tool(monkeypatch):
    monkeypatch.setattr("app.api.team_access.check_team_access", AsyncMock())
    monkeypatch.setattr(
        "app.models.tool.ToolShare.filter",
        lambda **_kwargs: SimpleNamespace(exists=AsyncMock(return_value=False)),
    )
    tool = SimpleNamespace(team_id=uuid4(), visibility="team", id=uuid4())

    with pytest.raises(BusinessError):
        await ToolOAuthService._assert_tool_access_for_team(
            tool, uuid4(), SimpleNamespace(id=uuid4())
        )
