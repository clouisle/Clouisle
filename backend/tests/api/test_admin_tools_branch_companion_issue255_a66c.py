from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import tools
from app.schemas.tool import ToolExecuteRequest


@pytest.mark.anyio
async def test_builtin_tool_routes_through_unified_boundary():
    team_id = uuid4()
    execute = AsyncMock(return_value={"ok": True})

    with (
        patch.object(tools.tool_registry, "get_tool", return_value=object()),
        patch.object(
            tools,
            "ToolExecutor",
            return_value=SimpleNamespace(execute_builtin_tool=execute),
        ),
    ):
        response = await tools.test_tool(
            ToolExecuteRequest(name="builtin", arguments={"x": 1}),
            team_id=team_id,
            current_user=SimpleNamespace(id=uuid4()),
        )

    call_kwargs = execute.await_args.kwargs
    assert call_kwargs["tool_name"] == "builtin"
    assert call_kwargs["arguments"] == {"x": 1}
    assert call_kwargs["team_id"] == team_id
    assert call_kwargs["context"].entrypoint is tools.ExecutionEntrypoint.ADMIN_TEST
    assert call_kwargs["context"].interactive is True
    assert response["data"].success is True


@pytest.mark.anyio
async def test_builtin_tool_failure_is_returned_as_shaped_result():
    execute = AsyncMock(return_value={"success": False, "error": "safe failure"})

    with (
        patch.object(tools.tool_registry, "get_tool", return_value=object()),
        patch.object(
            tools,
            "ToolExecutor",
            return_value=SimpleNamespace(execute_builtin_tool=execute),
        ),
    ):
        response = await tools.test_tool(
            ToolExecuteRequest(name="builtin", arguments={}),
            team_id=uuid4(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert response["data"].success is False
    assert response["data"].error == "safe failure"
