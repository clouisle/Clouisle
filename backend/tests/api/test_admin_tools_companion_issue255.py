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

    def limit(self, *_args):
        return self

    async def first(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def __await__(self):
        async def resolve():
            if isinstance(self.result, list):
                return self.result
            return [self.result] if self.result is not None else []

        return resolve().__await__()


@pytest.fixture
def admin():
    return SimpleNamespace(id=uuid4(), username="admin", locale="en")


@pytest.mark.anyio
async def test_test_tool_mcp_routes_through_executor_with_copied_arguments(admin):
    request = ToolExecuteRequest(
        name="mcp_alias",
        arguments={"__tool_name__": "server_tool", "city": "Paris"},
    )
    custom_tool = SimpleNamespace(
        id=uuid4(),
        name="mcp_alias",
        team_id=uuid4(),
        type=DBToolType.MCP,
        custom_type=None,
        mcp_config={"transport": "stdio", "command": "server"},
    )
    execute = AsyncMock(
        return_value={"success": False, "result": None, "error": "remote failed"}
    )

    with (
        patch.object(admin_tools.tool_registry, "get_tool", return_value=None),
        patch.object(admin_tools.Tool, "filter", return_value=_Query([custom_tool])),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await admin_tools.test_tool(request, current_user=admin)

    tool_arg, args_arg = execute.await_args.args
    assert tool_arg is custom_tool
    assert args_arg == {"city": "Paris"}
    call_kwargs = execute.await_args.kwargs
    assert call_kwargs["operation"] == "server_tool"
    assert (
        call_kwargs["context"].entrypoint is admin_tools.ExecutionEntrypoint.ADMIN_TEST
    )
    assert call_kwargs["context"].interactive is True
    assert request.arguments == {"__tool_name__": "server_tool", "city": "Paris"}
    assert response["data"].success is False
    assert response["data"].error == "remote failed"


@pytest.mark.anyio
async def test_test_tool_code_without_code_returns_i18n_error_without_executor(admin):
    request = ToolExecuteRequest(name="empty_code", arguments={"x": 1})
    custom_tool = SimpleNamespace(
        id=uuid4(),
        name="empty_code",
        team_id=uuid4(),
        type=DBToolType.CUSTOM,
        custom_type=DBCustomToolType.CODE,
        code_config={"language": "python"},
    )
    execute = AsyncMock()

    with (
        patch.object(admin_tools.tool_registry, "get_tool", return_value=None),
        patch.object(admin_tools.Tool, "filter", return_value=_Query([custom_tool])),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await admin_tools.test_tool(request, current_user=admin)

    execute.assert_not_awaited()
    assert response["data"].success is False
    assert response["data"].error


@pytest.mark.anyio
async def test_test_tool_rejects_ambiguous_custom_name_without_team(admin):
    first = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        type=DBToolType.CUSTOM,
        custom_type=DBCustomToolType.HTTP,
        http_config={"url": "https://example.test"},
    )
    second = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        type=DBToolType.CUSTOM,
        custom_type=DBCustomToolType.HTTP,
        http_config={"url": "https://example.test"},
    )

    with (
        patch.object(admin_tools.tool_registry, "get_tool", return_value=None),
        patch.object(admin_tools.Tool, "filter", return_value=_Query([first, second])),
    ):
        with pytest.raises(BusinessError) as exc:
            await admin_tools.test_tool(
                ToolExecuteRequest(name="shared"), current_user=admin
            )

    assert exc.value.status_code == 400


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
