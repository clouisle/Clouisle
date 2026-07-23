from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import CustomToolType, ToolType
from app.schemas.response import BusinessError
from app.schemas.tool import ToolExecuteRequest


class QueryResult:
    def __init__(self, value):
        self.first = AsyncMock(return_value=value)

    def prefetch_related(self, *_args):
        return self


class User(SimpleNamespace):
    def __init__(self, **kwargs):
        values = {
            "id": uuid4(),
            "username": "tester",
            "locale": "en",
            "is_superuser": False,
        }
        values.update(kwargs)
        super().__init__(**values)


def tool_record(**kwargs):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "weather",
        "display_name": "Weather",
        "description": "Forecast",
        "icon": None,
        "category": "other",
        "type": ToolType.CUSTOM,
        "custom_type": CustomToolType.HTTP,
        "parameters": [],
        "http_config": {},
        "code_config": {},
        "mcp_config": {},
        "credentials": {},
        "is_enabled": True,
        "created_by_id": uuid4(),
        "created_by": None,
        "created_at": None,
        "updated_at": None,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_write_access_shortcuts_and_requires_admin_for_non_creator():
    team_id = uuid4()
    with patch.object(tools, "check_team_access", new=AsyncMock()) as access:
        await tools.check_tool_write_access(
            SimpleNamespace(team_id=team_id, created_by_id=uuid4()),
            User(is_superuser=True),
        )
        access.assert_not_awaited()

        creator = User()
        await tools.check_tool_write_access(
            SimpleNamespace(team_id=team_id, created_by_id=creator.id), creator
        )
        access.assert_awaited_once_with(team_id, creator)

        access.reset_mock()
        other = User()
        await tools.check_tool_write_access(
            SimpleNamespace(team_id=team_id, created_by_id=uuid4()), other
        )
        assert access.await_args_list[1].kwargs == {"require_admin": True}


@pytest.mark.anyio
async def test_create_tool_rejects_duplicate_and_creates_with_audit():
    team_id = uuid4()
    user = User()
    request = MagicMock()
    tool_in = SimpleNamespace(
        name="weather",
        display_name="Weather",
        description="Forecast",
        icon=None,
        category="other",
        type=SimpleNamespace(value="custom"),
        custom_type=SimpleNamespace(value="http"),
        parameters=[],
        http_config=None,
        code_config=None,
        mcp_config=None,
        credentials={"token": "secret"},
        is_enabled=True,
    )

    with (
        patch.object(tools, "check_team_access", new=AsyncMock()),
        patch.object(tools.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(tools.Tool, "filter", return_value=QueryResult(object())),
    ):
        with pytest.raises(BusinessError):
            await tools.create_tool(team_id, tool_in, request, user)

    created = tool_record(team_id=team_id, created_by_id=user.id)
    with (
        patch.object(tools, "check_team_access", new=AsyncMock()),
        patch.object(tools.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(tools.Tool, "filter", return_value=QueryResult(None)),
        patch.object(
            tools.Tool, "create", new=AsyncMock(return_value=created)
        ) as create,
        patch.object(tools.AuditLogService, "log", new=AsyncMock()) as audit,
        patch.object(tools, "db_tool_to_detail", return_value="detail"),
    ):
        response = await tools.create_tool(team_id, tool_in, request, user)

    assert response["data"] == "detail"
    assert create.await_args.kwargs["credentials"] == {"token": "secret"}
    audit.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "args"),
    [
        (tools.get_tool_by_id, lambda user: (uuid4(), user)),
        (
            tools.update_tool,
            lambda user: (uuid4(), SimpleNamespace(name=None), MagicMock(), user),
        ),
        (tools.delete_tool, lambda user: (uuid4(), MagicMock(), user)),
        (tools.toggle_tool, lambda user: (uuid4(), MagicMock(), user)),
        (tools.duplicate_tool, lambda user: (uuid4(), MagicMock(), user)),
        (
            tools.share_tool,
            lambda user: (
                uuid4(),
                SimpleNamespace(team_id=uuid4(), permission="use"),
                MagicMock(),
                user,
            ),
        ),
        (tools.list_tool_shares, lambda user: (uuid4(), user)),
        (tools.unshare_tool, lambda user: (uuid4(), uuid4(), MagicMock(), user)),
    ],
)
async def test_crud_and_share_endpoints_report_missing_tool(endpoint, args):
    with patch.object(tools.Tool, "filter", return_value=QueryResult(None)):
        with pytest.raises(BusinessError):
            await endpoint(*args(User()))


@pytest.mark.anyio
async def test_update_delete_toggle_and_duplicate_success_paths():
    user = User()
    request = MagicMock()
    existing = tool_record(created_by_id=user.id, is_enabled=False)
    update = SimpleNamespace(
        name="renamed",
        display_name="Renamed",
        description="Updated",
        icon="icon",
        category="api",
        custom_type=SimpleNamespace(value="http"),
        parameters=[],
        http_config=SimpleNamespace(model_dump=lambda: {"url": "https://example.com"}),
        code_config=None,
        mcp_config=None,
        credentials={},
        is_enabled=True,
    )
    filters = [QueryResult(existing), QueryResult(None)]
    common = (
        patch.object(tools, "check_tool_write_access", new=AsyncMock()),
        patch.object(tools.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(tools.AuditLogService, "log", new=AsyncMock()),
        patch.object(tools, "db_tool_to_detail", return_value="detail"),
    )
    with ExitStack() as stack:
        for context in common:
            stack.enter_context(context)
        stack.enter_context(patch.object(tools.Tool, "filter", side_effect=filters))
        response = await tools.update_tool(existing.id, update, request, user)
    assert response["data"] == "detail"
    assert existing.name == "renamed"
    existing.save.assert_awaited_once()

    with (
        patch.object(tools.Tool, "filter", return_value=QueryResult(existing)),
        patch.object(tools, "check_team_access", new=AsyncMock()) as access,
        patch.object(tools.AuditLogService, "log", new=AsyncMock()),
    ):
        await tools.delete_tool(existing.id, request, user)
    access.assert_awaited_once_with(existing.team_id, user, require_admin=True)
    existing.delete.assert_awaited_once()

    existing.delete.reset_mock()
    existing.save.reset_mock()
    with (
        patch.object(tools.Tool, "filter", return_value=QueryResult(existing)),
        patch.object(tools, "check_tool_write_access", new=AsyncMock()),
        patch.object(tools.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(tools.AuditLogService, "log", new=AsyncMock()),
        patch.object(tools, "db_tool_to_detail", return_value="toggled"),
    ):
        response = await tools.toggle_tool(existing.id, request, user)
    assert response["data"] == "toggled"
    existing.save.assert_awaited_once()

    duplicate = tool_record(name="renamed_copy_1", created_by_id=user.id)
    name_query = MagicMock()
    name_query.exists = AsyncMock(side_effect=[True, False])
    with (
        patch.object(
            tools.Tool,
            "filter",
            side_effect=[QueryResult(existing), name_query, name_query],
        ),
        patch.object(
            tools.Tool, "create", new=AsyncMock(return_value=duplicate)
        ) as create,
        patch.object(tools, "check_team_access", new=AsyncMock()),
        patch.object(tools.AuditLogService, "log", new=AsyncMock()),
        patch.object(tools, "db_tool_to_detail", return_value="copy"),
    ):
        response = await tools.duplicate_tool(existing.id, request, user)
    assert response["data"] == "copy"
    assert create.await_args.kwargs["name"] == "renamed_copy_1"
    assert create.await_args.kwargs["is_enabled"] is False


@pytest.mark.anyio
async def test_get_tool_name_covers_sandbox_custom_and_not_found():
    user = User()
    team_id = uuid4()
    info = SimpleNamespace(name="bash", description="Run", parameters=[])
    with (
        patch.object(tools.tool_registry, "get_tool", return_value=None),
        patch.object(
            tools.tool_registry, "get_sandbox_tool_infos", return_value=[info]
        ),
        patch.object(tools, "_tool_info_to_out", return_value="sandbox"),
    ):
        assert (await tools.get_tool_by_name("bash", None, user))["data"] == "sandbox"

    custom = tool_record(team_id=team_id)
    with (
        patch.object(tools.tool_registry, "get_tool", return_value=None),
        patch.object(tools, "check_team_access", new=AsyncMock()),
        patch.object(tools.Tool, "filter", return_value=QueryResult(custom)),
        patch.object(tools, "db_tool_to_out", return_value="custom"),
    ):
        assert (await tools.get_tool_by_name("weather", team_id, user))[
            "data"
        ] == "custom"

    with (
        patch.object(tools.tool_registry, "get_tool", return_value=None),
        pytest.raises(BusinessError),
    ):
        await tools.get_tool_by_name("missing", None, user)


@pytest.mark.anyio
async def test_mcp_list_success_and_error_are_wrapped():
    request = SimpleNamespace(
        mcp_config=SimpleNamespace(model_dump=lambda: {"url": "http://mcp"})
    )
    remote = SimpleNamespace(name="search", description="Search", parameters={})
    with patch.object(tools, "list_mcp_tools", new=AsyncMock(return_value=[remote])):
        response = await tools.get_mcp_tools(request, User())
    assert response["data"].tools[0].name == "search"

    with (
        patch.object(
            tools, "list_mcp_tools", new=AsyncMock(side_effect=RuntimeError("down"))
        ),
        pytest.raises(BusinessError),
    ):
        await tools.get_mcp_tools(request, User())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("record", "executor", "expected"),
    [
        (
            tool_record(type=ToolType.MCP, custom_type=None, mcp_config={}),
            None,
            False,
        ),
        (
            tool_record(custom_type=CustomToolType.HTTP),
            "http",
            True,
        ),
        (
            tool_record(custom_type=CustomToolType.CODE, code_config={}),
            None,
            False,
        ),
        (
            tool_record(custom_type=None),
            None,
            False,
        ),
    ],
)
async def test_tool_execute_custom_non_sandbox_branches(record, executor, expected):
    request = ToolExecuteRequest(name=record.name, arguments={})
    patches = [
        patch.object(tools.tool_registry, "get_tool", return_value=None),
        patch.object(tools, "check_team_access", new=AsyncMock()),
        patch.object(tools.Tool, "filter", return_value=QueryResult(record)),
    ]
    if executor == "http":
        patches.append(
            patch.object(
                tools,
                "execute_http_tool",
                new=AsyncMock(return_value={"success": True, "result": "ok"}),
            )
        )
    with ExitStack() as stack:
        for context in patches:
            stack.enter_context(context)
        response = await tools.test_tool(request, record.team_id, User())
    assert response["data"].success is expected


@pytest.mark.anyio
async def test_builtin_execute_uses_global_credentials_and_reports_executor_error():
    request = ToolExecuteRequest(name="search", arguments={"q": "x"})
    empty = QueryResult(None)
    configured = QueryResult(SimpleNamespace(credentials={"key": "value"}))
    with (
        patch.object(tools.tool_registry, "get_tool", return_value=object()),
        patch(
            "app.models.tool_config.ToolConfig.filter", side_effect=[empty, configured]
        ),
        patch.object(
            tools.tool_registry, "execute", new=AsyncMock(return_value="ok")
        ) as execute,
    ):
        response = await tools.test_tool(request, uuid4(), User())
    assert response["data"].success is True
    assert execute.await_args.kwargs["credentials"] == {"key": "value"}

    with (
        patch.object(tools.tool_registry, "get_tool", return_value=object()),
        patch("app.models.tool_config.ToolConfig.filter", side_effect=[empty, empty]),
        patch.object(
            tools.tool_registry,
            "execute",
            new=AsyncMock(side_effect=RuntimeError("secret failure")),
        ),
        patch.object(
            tools, "resolve_user_visible_error", return_value="safe"
        ) as resolve,
    ):
        response = await tools.test_tool(request, uuid4(), User())
    assert response["data"].success is False
    assert response["data"].error == "safe"
    resolve.assert_called_once_with("secret failure")
