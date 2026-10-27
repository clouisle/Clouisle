from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import tools
from app.models.tool import ToolType as DBToolType
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import ToolVisibility as DBToolVisibility
from app.schemas.response import BusinessError, error
from app.schemas.tool import (
    CodeExecuteRequest,
    McpConfigSchema,
    McpToolsListRequest,
    ToolCreateInput,
    ToolExecuteRequest,
    ToolOut,
    ToolShareInput,
    ToolSharePermission,
    ToolType,
    ToolUpdateInput,
)
from app.services.sandbox.models import SandboxExecutionMetadata


class Query:
    def __init__(self, *, first=None, items=(), exists=False, count=0):
        self.first_value = first
        self.items = list(items)
        self.exists_value = exists
        self.count_value = count
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def all(self):
        return self

    async def first(self):
        return self.first_value

    async def exists(self):
        return self.exists_value

    async def count(self):
        return self.count_value

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


class Permission:
    def __init__(self, code):
        self.code = code


class Role:
    def __init__(self, *codes):
        self.permissions = [Permission(code) for code in codes]


@pytest.fixture
def user():
    return SimpleNamespace(
        id=uuid4(),
        username="admin",
        locale="en",
        is_active=True,
        is_superuser=False,
        roles=[],
    )


@pytest.fixture
def admin_tools_client(user):
    app = FastAPI()
    app.include_router(tools.router, prefix="/api/v1/admin/tools")

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

    async def current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = current_user
    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.clear()


def db_tool(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "team": SimpleNamespace(name="Owners"),
        "name": "weather",
        "display_name": "Weather",
        "description": "Forecasts",
        "icon": None,
        "category": "other",
        "visibility": DBToolVisibility.PRIVATE,
        "type": DBToolType.CUSTOM,
        "custom_type": DBCustomToolType.HTTP,
        "parameters": [],
        "http_config": {"url": "https://example.test", "method": "GET"},
        "code_config": {},
        "mcp_config": {},
        "credentials": {},
        "is_enabled": True,
        "identity_policy": "none",
        "connection_fields": [],
        "approval_policy": {},
        "definition_version": 1,
        "created_by_id": uuid4(),
        "created_by": SimpleNamespace(username="owner"),
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def share(tool, **overrides):
    values = {
        "id": uuid4(),
        "tool_id": tool.id,
        "tool": tool,
        "shared_with_team_id": uuid4(),
        "shared_with_team": SimpleNamespace(name="Consumers"),
        "permission": "read_only",
        "shared_by_id": uuid4(),
        "shared_by": SimpleNamespace(username="admin"),
        "shared_at": datetime.now(UTC),
        "fetch_related": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def response_data(response):
    return response["data"]


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("get", "", "admin:capability:read"),
        (
            "post",
            "?team_id=00000000-0000-0000-0000-000000000001",
            "admin:capability:create",
        ),
        ("put", "/00000000-0000-0000-0000-000000000001", "admin:capability:update"),
        ("delete", "/00000000-0000-0000-0000-000000000001", "admin:capability:delete"),
        ("post", "/test", "admin:capability:execute"),
    ],
)
def test_routes_enforce_specific_permissions(
    admin_tools_client, method, path, permission
):
    client, user = admin_tools_client
    user.roles = [Role("admin:capability:unrelated")]

    response = client.request(method.upper(), f"/api/v1/admin/tools{path}", json={})

    assert response.status_code == 403
    user.roles = [Role(permission)]


def test_create_rejects_invalid_input_before_persistence(
    admin_tools_client, monkeypatch
):
    client, user = admin_tools_client
    user.roles = [Role("admin:capability:create")]
    create = AsyncMock()
    monkeypatch.setattr(tools.Tool, "create", create)

    response = client.post(
        f"/api/v1/admin/tools?team_id={uuid4()}",
        json={"name": "bad-name", "display_name": "Bad"},
    )

    assert response.status_code == 422
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_and_filter_options_cover_db_metadata(monkeypatch, user):
    first = db_tool(display_name="Zulu", category="api")
    second = db_tool(
        name="alpha",
        display_name="Alpha",
        description="Needle service",
        category="search",
        is_enabled=False,
        created_by=None,
        created_by_id=None,
        team=None,
    )
    monkeypatch.setattr(tools, "get_builtin_tools", lambda _locale: [])
    monkeypatch.setattr(tools, "get_builtin_tools_for_team", AsyncMock(return_value=[]))
    monkeypatch.setattr(tools.Tool, "all", lambda: Query(items=[first, second]))
    monkeypatch.setattr(
        tools.ToolShare,
        "filter",
        lambda **kwargs: Query(count=2 if kwargs["tool_id"] == first.id else 0),
    )

    result = await tools.list_tools(
        page=1,
        page_size=1,
        search="needle",
        type=["custom"],
        category=["search"],
        status=["disabled"],
        team_id=[second.team_id],
        creator=None,
        current_user=user,
    )

    page = response_data(result)
    assert page.total == 1
    assert page.items[0].name == "alpha"
    assert page.items[0].owner_team_name is None

    monkeypatch.setattr(
        tools.Team,
        "all",
        lambda: Query(items=[SimpleNamespace(id=first.team_id, name="Owners")]),
    )
    options = response_data(await tools.get_tool_filter_options(user))
    assert [item.value for item in options.categories] == ["api", "search"]
    assert options.teams[0].label == "Owners"
    assert options.creators[0].value == "owner"


@pytest.mark.asyncio
async def test_list_filters_nonmatching_fields_and_paginates(monkeypatch, user):
    candidates = [
        ToolOut(
            name="a",
            display_name="A",
            description="match",
            type=ToolType.CUSTOM,
            category="api",
        ),
        ToolOut(
            name="b",
            display_name="B",
            description="match",
            type=ToolType.MCP,
            category="api",
        ),
        ToolOut(
            name="c",
            display_name="C",
            description="match",
            type=ToolType.CUSTOM,
            category="web",
        ),
        ToolOut(
            name="d",
            display_name="D",
            description="match",
            type=ToolType.CUSTOM,
            category="api",
            is_enabled=False,
        ),
        ToolOut(
            name="e",
            display_name="E",
            description="other",
            type=ToolType.CUSTOM,
            category="api",
        ),
        ToolOut(
            name="f",
            display_name="F",
            description="match",
            type=ToolType.CUSTOM,
            category="api",
            created_by_name="other",
        ),
    ]
    monkeypatch.setattr(tools, "_build_admin_tools", AsyncMock(return_value=candidates))

    result = await tools.list_tools(
        page=2,
        page_size=1,
        search="match",
        type=["custom"],
        category=["api"],
        status=["enabled"],
        team_id=None,
        creator=["owner"],
        current_user=user,
    )

    assert response_data(result).total == 0
    assert response_data(result).items == []


@pytest.mark.asyncio
async def test_get_helpers_and_detail_handle_missing_and_metadata(monkeypatch, user):
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools._get_db_tool(uuid4(), detail=True)
    assert exc_info.value.msg_key == "tool_not_found"

    monkeypatch.setattr(tools.Team, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools._get_team(uuid4())
    assert exc_info.value.msg_key == "team_not_found"

    existing = db_tool()
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=existing))
    monkeypatch.setattr(tools.ToolShare, "filter", lambda **_kwargs: Query(count=3))
    detail = response_data(await tools.get_tool_by_id(existing.id, user))
    assert detail.owner_team_name == "Owners"
    assert detail.shared_with_count == 3


@pytest.mark.asyncio
async def test_create_tool_success_and_duplicate(monkeypatch, user):
    team_id = uuid4()
    tool_in = ToolCreateInput(
        name="runner",
        display_name="Runner",
        description="Runs",
        custom_type="code",
        parameters=[{"name": "value", "type": "string"}],
        code_config={"language": "python", "code": "return 1"},
    )
    monkeypatch.setattr(
        tools, "_get_team", AsyncMock(return_value=SimpleNamespace(id=team_id))
    )
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    created = db_tool(
        team_id=team_id,
        name="runner",
        display_name="Runner",
        description="Runs",
        custom_type=DBCustomToolType.CODE,
        http_config={},
        code_config={"language": "python", "code": "return 1"},
        parameters=[{"name": "value", "type": "string", "required": False}],
    )
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(tools.Tool, "create", create)

    result = await tools.create_tool(team_id, tool_in, user)

    assert response_data(result).name == "runner"
    assert create.await_args.kwargs["created_by"] is user
    assert create.await_args.kwargs["credentials"] == {}
    assert create.await_args.kwargs["parameters"][0]["name"] == "value"

    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=created))
    with pytest.raises(BusinessError) as exc_info:
        await tools.create_tool(team_id, tool_in, user)
    assert exc_info.value.msg_key == "tool_name_exists"


@pytest.mark.asyncio
async def test_update_tool_persists_all_fields_and_rejects_duplicate(monkeypatch, user):
    existing = db_tool()
    monkeypatch.setattr(tools, "_get_db_tool", AsyncMock(return_value=existing))
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    update = ToolUpdateInput(
        name="renamed",
        display_name="Renamed",
        description="Changed",
        icon="icon",
        category="api",
        visibility="team",
        custom_type="code",
        parameters=[{"name": "x", "type": "integer"}],
        http_config={"url": "https://new.test"},
        code_config={"language": "python", "code": "return 2"},
        database_config={"db_type": "postgresql", "host": "db"},
        mcp_config={"transport": "http", "url": "https://mcp.test"},
        credentials={},
        is_enabled=False,
    )

    result = await tools.update_tool(existing.id, update, user)

    assert response_data(result).name == "renamed"
    assert existing.custom_type == DBCustomToolType.CODE
    assert existing.is_enabled is False
    assert existing.credentials == {}
    existing.save.assert_awaited_once()

    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=db_tool()))
    with pytest.raises(BusinessError) as exc_info:
        await tools.update_tool(existing.id, ToolUpdateInput(name="taken"), user)
    assert exc_info.value.msg_key == "tool_name_exists"


@pytest.mark.asyncio
async def test_delete_toggle_and_duplicate_persist(monkeypatch, user):
    existing = db_tool(is_enabled=True)
    monkeypatch.setattr(tools, "_get_db_tool", AsyncMock(return_value=existing))

    await tools.delete_tool(existing.id, user)
    existing.delete.assert_awaited_once()

    result = await tools.toggle_tool(existing.id, user)
    assert response_data(result).is_enabled is False
    existing.save.assert_awaited_once()

    checks = iter([True, False])
    monkeypatch.setattr(
        tools.Tool, "filter", lambda **_kwargs: Query(exists=next(checks))
    )
    copied = db_tool(name="weather_copy_1", is_enabled=False)
    create = AsyncMock(return_value=copied)
    monkeypatch.setattr(tools.Tool, "create", create)
    result = await tools.duplicate_tool(existing.id, user)
    assert response_data(result).name == "weather_copy_1"
    assert create.await_args.kwargs["name"] == "weather_copy_1"
    assert create.await_args.kwargs["is_enabled"] is False


@pytest.mark.asyncio
async def test_mcp_discovery_maps_results_and_safe_failure(monkeypatch, user):
    request = McpToolsListRequest(
        mcp_config=McpConfigSchema(transport="http", url="https://mcp.test")
    )
    discovered = SimpleNamespace(
        name="lookup", description="Find", parameters={"type": "object"}
    )
    monkeypatch.setattr(tools, "list_mcp_tools", AsyncMock(return_value=[discovered]))

    result = await tools.get_mcp_tools(request, user)
    assert response_data(result).tools[0].name == "lookup"

    monkeypatch.setattr(
        tools, "list_mcp_tools", AsyncMock(side_effect=RuntimeError("offline"))
    )
    with pytest.raises(BusinessError) as exc_info:
        await tools.get_mcp_tools(request, user)
    assert exc_info.value.msg_key == "mcp_connection_failed"
    assert exc_info.value.__cause__.args == ("offline",)


@pytest.mark.asyncio
async def test_builtin_execution_routes_through_unified_boundary(monkeypatch, user):
    team_id = uuid4()
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: object())
    monkeypatch.setattr(
        tools, "ToolExecutor", lambda: SimpleNamespace(execute_builtin_tool=execute)
    )

    result = await tools.test_tool(
        ToolExecuteRequest(name="search", arguments={"q": "x"}), team_id, user
    )
    assert response_data(result).success is True
    assert response_data(result).result == {"ok": True}
    call_kwargs = execute.await_args.kwargs
    assert call_kwargs["tool_name"] == "search"
    assert call_kwargs["team_id"] == team_id
    assert call_kwargs["context"].entrypoint is tools.ExecutionEntrypoint.ADMIN_TEST
    assert call_kwargs["context"].team_id == team_id
    assert call_kwargs["context"].interactive is True

    with pytest.raises(BusinessError) as exc_info:
        await tools.test_tool(ToolExecuteRequest(name="search"), None, user)
    assert exc_info.value.msg_key == "team_id_required"


@pytest.mark.asyncio
async def test_custom_execution_not_found_mcp_paths_and_ambiguity(monkeypatch, user):
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.test_tool(ToolExecuteRequest(name="missing"), uuid4(), user)
    assert exc_info.value.msg_key == "tool_not_found"

    custom = db_tool(
        name="server",
        type=DBToolType.MCP,
        custom_type=None,
        mcp_config={"transport": "stdio"},
    )
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(items=[custom]))
    execute = AsyncMock(return_value={"success": True, "result": "ok", "error": None})
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.ToolExecutor",
        lambda: SimpleNamespace(execute=execute),
    )
    request = ToolExecuteRequest(
        name="server", arguments={"__tool_name__": "lookup", "q": "x"}
    )
    result = response_data(await tools.test_tool(request, custom.team_id, user))
    assert result.result == "ok"
    tool_arg, args_arg = execute.await_args.args
    assert tool_arg is custom
    assert args_arg == {"q": "x"}
    assert execute.await_args.kwargs["operation"] == "lookup"
    assert request.arguments == {"__tool_name__": "lookup", "q": "x"}

    other = db_tool(
        name="server",
        type=DBToolType.MCP,
        custom_type=None,
        mcp_config={"transport": "stdio"},
    )
    monkeypatch.setattr(
        tools.Tool, "filter", lambda **_kwargs: Query(items=[custom, other])
    )
    with pytest.raises(BusinessError) as ambiguous:
        await tools.test_tool(ToolExecuteRequest(name="server"), None, user)
    assert ambiguous.value.status_code == 400

    execute.side_effect = RuntimeError("offline")
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(items=[custom]))
    failed = response_data(
        await tools.test_tool(ToolExecuteRequest(name="server"), custom.team_id, user)
    )
    assert failed.success is False
    assert failed.error


@pytest.mark.asyncio
async def test_http_and_code_results_are_shaped(monkeypatch, user):
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    current = db_tool()
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(items=[current]))
    execute = AsyncMock(return_value={"success": True, "result": {"ok": True}})
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.ToolExecutor",
        lambda: SimpleNamespace(execute=execute),
    )
    result = response_data(
        await tools.test_tool(
            ToolExecuteRequest(name=current.name, arguments={"x": 1}), None, user
        )
    )
    assert result.result == {"ok": True}
    assert (
        execute.await_args.kwargs["context"].entrypoint
        is tools.ExecutionEntrypoint.ADMIN_TEST
    )

    current.custom_type = DBCustomToolType.CODE
    current.http_config = {}
    current.code_config = {}
    missing = response_data(
        await tools.test_tool(ToolExecuteRequest(name=current.name), None, user)
    )
    assert missing.success is False

    current.code_config = {
        "language": "python",
        "code": "return 1",
        "limits": {"timeout_seconds": 4},
    }
    execute.return_value = {
        "success": True,
        "result": 1,
        "error": None,
        "stdout": "done",
        "artifacts": [],
    }
    code = response_data(
        await tools.test_tool(ToolExecuteRequest(name=current.name), None, user)
    )
    assert code.result == 1
    assert code.logs == "done"
    assert code.duration_ms is not None

    current.custom_type = None
    execute.side_effect = ValueError("unsupported custom tool type")
    unsupported = response_data(
        await tools.test_tool(ToolExecuteRequest(name=current.name), None, user)
    )
    assert unsupported.success is False


@pytest.mark.asyncio
async def test_direct_code_rejects_language_and_uses_sandbox(monkeypatch, user):
    invalid = response_data(
        await tools.execute_code_directly(
            CodeExecuteRequest(language="ruby", code="1"), user
        )
    )
    assert invalid.success is False

    job = SimpleNamespace(limits=SimpleNamespace(timeout_seconds=3.0))
    compile_job = Mock(return_value=job)
    submit = AsyncMock(
        return_value=SimpleNamespace(
            success=False,
            result=None,
            error="failed",
            stdout="log",
            artifacts=[],
            metadata=SandboxExecutionMetadata(duration_ms=7, total_ms=7),
        )
    )
    monkeypatch.setattr(tools, "compile_code_config_job", compile_job)
    monkeypatch.setattr(tools.sandbox_gateway, "submit_and_wait", submit)
    result = response_data(
        await tools.execute_code_directly(
            CodeExecuteRequest(language="python", code="return 1", timeout=3), user
        )
    )
    assert result.success is False
    assert result.logs == "log"
    assert result.duration_ms == 7
    submit.assert_awaited_once_with(job, timeout_seconds=8.0)


@pytest.mark.asyncio
async def test_share_list_and_unshare_success(monkeypatch, user):
    existing = db_tool(visibility=DBToolVisibility.TEAM)
    target = SimpleNamespace(id=uuid4(), name="Consumers")
    record = share(existing, shared_with_team_id=target.id, shared_with_team=target)
    monkeypatch.setattr(tools, "_get_db_tool", AsyncMock(return_value=existing))
    monkeypatch.setattr(tools, "_get_team", AsyncMock(return_value=target))
    monkeypatch.setattr(
        tools.ToolShare, "filter", lambda **_kwargs: Query(first=None, items=[record])
    )
    monkeypatch.setattr(tools.ToolShare, "create", AsyncMock(return_value=record))

    created = response_data(
        await tools.share_tool(
            existing.id,
            ToolShareInput(team_id=target.id, permission=ToolSharePermission.READ_ONLY),
            user,
        )
    )
    assert created["shared_with_team_name"] == "Consumers"
    record.fetch_related.assert_awaited_once()

    listed = response_data(await tools.list_tool_shares(existing.id, user))
    assert listed["total"] == 1
    assert listed["shares"][0]["tool_name"] == existing.name

    monkeypatch.setattr(
        tools.ToolShare, "filter", lambda **_kwargs: Query(first=record)
    )
    await tools.unshare_tool(existing.id, target.id, user)
    record.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_share_validation_failures_do_not_persist(monkeypatch, user):
    existing = db_tool(visibility=DBToolVisibility.TEAM)
    monkeypatch.setattr(tools, "_get_db_tool", AsyncMock(return_value=existing))
    monkeypatch.setattr(
        tools,
        "_get_team",
        AsyncMock(return_value=SimpleNamespace(id=existing.team_id, name="Owners")),
    )
    create = AsyncMock()
    monkeypatch.setattr(tools.ToolShare, "create", create)

    with pytest.raises(BusinessError) as exc_info:
        await tools.share_tool(
            existing.id, ToolShareInput(team_id=existing.team_id), user
        )
    assert exc_info.value.msg_key == "cannot_share_to_own_team"
    create.assert_not_awaited()

    other_team = uuid4()
    monkeypatch.setattr(
        tools,
        "_get_team",
        AsyncMock(return_value=SimpleNamespace(id=other_team, name="Other")),
    )
    monkeypatch.setattr(
        tools.ToolShare, "filter", lambda **_kwargs: Query(first=share(existing))
    )
    with pytest.raises(BusinessError) as exc_info:
        await tools.share_tool(existing.id, ToolShareInput(team_id=other_team), user)
    assert exc_info.value.msg_key == "tool_already_shared"
    create.assert_not_awaited()

    monkeypatch.setattr(tools.ToolShare, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.unshare_tool(existing.id, other_team, user)
    assert exc_info.value.msg_key == "tool_share_not_found"

    existing.visibility = DBToolVisibility.PRIVATE
    with pytest.raises(BusinessError) as exc_info:
        await tools.share_tool(existing.id, ToolShareInput(team_id=other_team), user)
    assert exc_info.value.msg_key == "private_tool_cannot_be_shared"
    create.assert_not_awaited()
