import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.api.v1.endpoints import tools
from app.models.tool import ToolVisibility as DBToolVisibility
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool import ToolShareInput


def _user(user_id=None, is_superuser=False):
    return SimpleNamespace(
        id=user_id or uuid4(),
        username="tester",
        locale="en",
        is_superuser=is_superuser,
    )


def _tool(creator_id=None, team_id=None, visibility=DBToolVisibility.PRIVATE):
    return SimpleNamespace(
        id=uuid4(),
        name="custom_tool",
        display_name="Custom Tool",
        description="Custom tool description",
        icon=None,
        category="api",
        type=SimpleNamespace(value="custom"),
        custom_type=SimpleNamespace(value="http"),
        visibility=visibility,
        parameters=[],
        credentials={},
        http_config={},
        code_config={},
        database_config={},
        mcp_config={},
        team_id=team_id or uuid4(),
        created_by_id=creator_id or uuid4(),
        created_by=SimpleNamespace(username="owner", id=creator_id or uuid4()),
        is_enabled=True,
        created_at=None,
        updated_at=None,
        save=AsyncMock(),
        delete=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_check_tool_access_grants_owner_for_private_tool():
    user = _user()
    tool = _tool(creator_id=user.id, visibility=DBToolVisibility.PRIVATE)
    result = await tools.check_tool_access(tool, user)
    assert result is tool


@pytest.mark.asyncio
async def test_check_tool_access_blocks_non_owner_for_private_tool():
    user = _user()
    tool = _tool(creator_id=uuid4(), visibility=DBToolVisibility.PRIVATE)
    with pytest.raises(BusinessError) as exc_info:
        await tools.check_tool_access(tool, user)
    assert exc_info.value.code == ResponseCode.PERMISSION_DENIED
    assert exc_info.value.msg_key == "tool_access_denied"


@pytest.mark.asyncio
async def test_check_tool_access_allows_superuser_for_private_tool():
    user = _user(is_superuser=True)
    tool = _tool(creator_id=uuid4(), visibility=DBToolVisibility.PRIVATE)
    result = await tools.check_tool_access(tool, user)
    assert result is tool


@pytest.mark.asyncio
async def test_share_tool_rejects_private_tool(monkeypatch):
    user = _user()
    team_id = uuid4()
    tool = _tool(
        creator_id=user.id, team_id=team_id, visibility=DBToolVisibility.PRIVATE
    )

    monkeypatch.setattr(
        tools.Tool,
        "filter",
        MagicMock(
            return_value=SimpleNamespace(
                prefetch_related=MagicMock(
                    return_value=SimpleNamespace(first=AsyncMock(return_value=tool))
                )
            )
        ),
    )
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await tools.share_tool(
            tool_id=tool.id,
            share_data=ToolShareInput(team_id=uuid4()),
            request=SimpleNamespace(),
            current_user=user,
        )
    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "private_tool_cannot_be_shared"
