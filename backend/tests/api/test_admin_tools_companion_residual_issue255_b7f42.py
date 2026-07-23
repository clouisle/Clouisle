from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import tools as admin_tools
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool import ToolUpdateInput


class Query:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


@pytest.mark.anyio
async def test_update_tool_rejects_renaming_to_existing_team_tool(monkeypatch):
    tool = SimpleNamespace(id=uuid4(), name="old_name", team_id=uuid4())
    existing = SimpleNamespace(id=uuid4())
    model = SimpleNamespace(
        filter=Mock(side_effect=[Query(tool), Query(existing)]),
    )
    monkeypatch.setattr(admin_tools, "Tool", model)

    with pytest.raises(BusinessError) as exc_info:
        await admin_tools.update_tool(
            tool.id,
            ToolUpdateInput(name="taken_name"),
            current_user=SimpleNamespace(),
        )

    assert exc_info.value.code == ResponseCode.ALREADY_EXISTS
    assert model.filter.call_args_list[1].kwargs == {
        "team_id": tool.team_id,
        "name": "taken_name",
    }


@pytest.mark.anyio
async def test_delete_tool_missing_tool_raises_not_found(monkeypatch):
    model = SimpleNamespace(filter=Mock(return_value=Query(None)))
    monkeypatch.setattr(admin_tools, "Tool", model)

    with pytest.raises(BusinessError) as exc_info:
        await admin_tools.delete_tool(uuid4(), current_user=SimpleNamespace())

    assert exc_info.value.code == ResponseCode.NOT_FOUND


@pytest.mark.anyio
async def test_delete_tool_deletes_found_tool(monkeypatch):
    tool = SimpleNamespace(id=uuid4(), delete=AsyncMock())
    model = SimpleNamespace(filter=Mock(return_value=Query(tool)))
    monkeypatch.setattr(admin_tools, "Tool", model)

    result = await admin_tools.delete_tool(tool.id, current_user=SimpleNamespace())

    tool.delete.assert_awaited_once()
    assert result["code"] == ResponseCode.SUCCESS
    assert result["data"] is None
