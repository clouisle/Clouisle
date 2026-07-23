from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import tools
from app.schemas.tool import ToolOut, ToolType, ToolUpdateInput


class _Query:
    def __init__(self, result):
        self.result = result

    async def first(self):
        return self.result


@pytest.mark.anyio
async def test_get_team_returns_existing_team():
    team = SimpleNamespace(id=uuid4(), name="Operations")

    with patch.object(tools.Team, "filter", return_value=_Query(team)) as filter_team:
        assert await tools._get_team(team.id) is team

    filter_team.assert_called_once_with(id=team.id)


@pytest.mark.anyio
async def test_update_tool_with_no_fields_only_saves_existing_values():
    tool = SimpleNamespace(
        id=uuid4(),
        name="weather",
        team_id=uuid4(),
        created_by=None,
        save=AsyncMock(),
    )
    detail = SimpleNamespace(name=tool.name)

    with (
        patch.object(tools, "_get_db_tool", AsyncMock(return_value=tool)),
        patch.object(
            tools, "db_tool_to_detail", Mock(return_value=detail)
        ) as serialize,
    ):
        response = await tools.update_tool(
            tool.id, ToolUpdateInput(), current_user=SimpleNamespace()
        )

    tool.save.assert_awaited_once_with()
    serialize.assert_called_once_with(tool, None)
    assert response["data"] is detail


@pytest.mark.anyio
async def test_list_tools_rejects_tool_without_matching_team():
    candidate = ToolOut(
        name="builtin",
        display_name="Builtin",
        description="No owning team",
        type=ToolType.BUILTIN,
        category="other",
        team_id=None,
    )

    with patch.object(tools, "_build_admin_tools", AsyncMock(return_value=[candidate])):
        response = await tools.list_tools(
            page=1,
            page_size=10,
            search=None,
            type=None,
            category=None,
            status=None,
            team_id=[uuid4()],
            creator=None,
            current_user=SimpleNamespace(),
        )

    assert response["data"].total == 0
    assert response["data"].items == []
