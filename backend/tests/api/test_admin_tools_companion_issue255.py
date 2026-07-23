from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import tools as admin_tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import ToolType as DBToolType
from app.schemas.response import BusinessError
from app.schemas.tool import (
    CodeExecuteRequest,
    McpConfigSchema,
    McpToolsListRequest,
    ToolExecuteRequest,
    ToolShareInput,
    ToolSharePermission,
)


class _Query:
    def __init__(self, result=None):
        self.result = result
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    async def first(self):
        return self.result


@pytest.fixture
def admin():
    return SimpleNamespace(id=uuid4(), username="admin", locale="en")


@pytest.mark.anyio
async def test_test_tool_mcp_uses_argument_tool_name_and_returns_executor_result(admin):
    request = ToolExecuteRequest(
        name="mcp_alias",
        arguments={"__tool_name__": "server_tool", "city": "Paris"},
    )
    custom_tool = SimpleNamespace(
        type=DBToolType.MCP,
        custom_type=None,
        mcp_config={"transport": "stdio", "command": "server"},
    )
    executor_result = SimpleNamespace(success=False, result=None, error="remote failed")

    with (
        patch.object(admin_tools.tool_registry, "get_tool", return_value=None),
        patch.object(admin_tools.Tool, "filter", return_value=_Query(custom_tool)),
        patch.object(
            admin_tools,
            "execute_mcp_tool",
            new=AsyncMock(return_value=executor_result),
        ) as execute_mcp,
    ):
        response = await admin_tools.test_tool(request, current_user=admin)

    execute_mcp.assert_awaited_once_with(
        mcp_config=custom_tool.mcp_config,
        tool_name="server_tool",
        arguments={"city": "Paris"},
        timeout=60.0,
    )
    assert request.arguments == {"city": "Paris"}
    assert response["data"].success is False
    assert response["data"].error == "remote failed"


@pytest.mark.anyio
async def test_test_tool_code_without_code_returns_i18n_error_without_sandbox(admin):
    request = ToolExecuteRequest(name="empty_code", arguments={"x": 1})
    custom_tool = SimpleNamespace(
        type=DBToolType.CUSTOM,
        custom_type=DBCustomToolType.CODE,
        code_config={"language": "python"},
    )

    with (
        patch.object(admin_tools.tool_registry, "get_tool", return_value=None),
        patch.object(admin_tools.Tool, "filter", return_value=_Query(custom_tool)),
        patch.object(admin_tools, "t", return_value="missing code"),
        patch.object(admin_tools, "compile_code_config_job") as compile_job,
        patch.object(
            admin_tools.sandbox_gateway, "submit_and_wait", new=AsyncMock()
        ) as submit,
    ):
        response = await admin_tools.test_tool(request, current_user=admin)

    compile_job.assert_not_called()
    submit.assert_not_awaited()
    assert response["data"].success is False
    assert response["data"].error == "missing code"


@pytest.mark.anyio
async def test_execute_code_directly_rejects_unsupported_language_without_sandbox(
    admin,
):
    request = CodeExecuteRequest(language="ruby", code="puts 1")

    with (
        patch.object(admin_tools, "t", return_value="bad language") as translate,
        patch.object(admin_tools, "compile_code_config_job") as compile_job,
        patch.object(
            admin_tools.sandbox_gateway, "submit_and_wait", new=AsyncMock()
        ) as submit,
    ):
        response = await admin_tools.execute_code_directly(request, current_user=admin)

    translate.assert_called_once_with(
        "unsupported_code_execution_language", language="ruby"
    )
    compile_job.assert_not_called()
    submit.assert_not_awaited()
    assert response["data"].success is False
    assert response["data"].error == "bad language"


@pytest.mark.anyio
async def test_get_mcp_tools_wraps_list_failures(admin):
    request = McpToolsListRequest(
        mcp_config=McpConfigSchema(transport="stdio", command="server")
    )

    with (
        patch.object(
            admin_tools,
            "list_mcp_tools",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await admin_tools.get_mcp_tools(request, current_user=admin)

    assert exc.value.code == admin_tools.ResponseCode.INTERNAL_ERROR
    assert exc.value.status_code == 500


@pytest.mark.anyio
async def test_share_tool_rejects_own_team_before_creating_share(admin):
    team_id = uuid4()
    tool = SimpleNamespace(team_id=team_id)
    share_data = ToolShareInput(
        team_id=team_id,
        permission=ToolSharePermission.READ_ONLY,
    )

    with (
        patch.object(admin_tools, "_get_db_tool", new=AsyncMock(return_value=tool)),
        patch.object(
            admin_tools,
            "_get_team",
            new=AsyncMock(return_value=SimpleNamespace(id=team_id, name="Ops")),
        ),
        patch.object(admin_tools.ToolShare, "create", new=AsyncMock()) as create_share,
        pytest.raises(BusinessError) as exc,
    ):
        await admin_tools.share_tool(uuid4(), share_data, current_user=admin)

    create_share.assert_not_awaited()
    assert exc.value.code == admin_tools.ResponseCode.BAD_REQUEST
