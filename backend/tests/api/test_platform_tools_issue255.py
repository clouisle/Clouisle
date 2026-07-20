from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import ToolType as DBToolType
from app.models.tool_config import ToolConfig
from app.schemas.response import BusinessError
from app.schemas.tool import ToolCreateInput, ToolExecuteRequest, ToolUpdateInput


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


def user(**overrides):
    values = {
        "id": uuid4(),
        "username": "member",
        "locale": "en",
        "is_superuser": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
        "type": DBToolType.CUSTOM,
        "custom_type": DBCustomToolType.HTTP,
        "parameters": [],
        "http_config": {"url": "https://example.test", "method": "GET"},
        "code_config": {},
        "mcp_config": {},
        "credentials": {},
        "is_enabled": True,
        "created_by_id": uuid4(),
        "created_by": SimpleNamespace(username="creator"),
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def config(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "tool_name": "search",
        "team_id": uuid4(),
        "credentials": {"token": "secret"},
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def data(response):
    return response["data"]


@pytest.mark.asyncio
async def test_accessible_teams_and_write_access_enforce_membership(monkeypatch):
    current = user()
    alpha = SimpleNamespace(id=uuid4(), name="Alpha")
    zulu = SimpleNamespace(id=uuid4(), name="Zulu")
    memberships = [SimpleNamespace(team=zulu), SimpleNamespace(team=alpha)]
    monkeypatch.setattr(
        tools.TeamMember, "filter", lambda **_kwargs: Query(items=memberships)
    )

    assert await tools._get_accessible_teams(current) == [alpha, zulu]

    access = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    owned = db_tool(created_by_id=current.id)
    await tools.check_tool_write_access(owned, current)
    access.assert_awaited_once_with(owned.team_id, current)

    access.reset_mock()
    await tools.check_tool_write_access(db_tool(), current)
    assert access.await_args_list[-1].kwargs == {"require_admin": True}

    access.reset_mock()
    await tools.check_tool_write_access(db_tool(), user(is_superuser=True))
    access.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_tools_builds_owned_and_shared_results_and_filters(monkeypatch):
    current = user()
    team = SimpleNamespace(id=uuid4(), name="Owners")
    owned = db_tool(team_id=team.id, display_name="Zulu")
    shared = db_tool(display_name="Alpha", category="search")
    share = SimpleNamespace(tool=shared, permission="read_only")
    queries = iter([Query(items=[owned]), Query(items=[])])
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: next(queries))
    monkeypatch.setattr(
        tools.ToolShare,
        "filter",
        lambda **kwargs: (
            Query(items=[share]) if "shared_with_team_id" in kwargs else Query(count=2)
        ),
    )
    monkeypatch.setattr(tools, "get_builtin_tools", lambda _locale: [])
    monkeypatch.setattr(tools, "_get_accessible_teams", AsyncMock(return_value=[team]))

    result = data(
        await tools.list_tools(
            page=1,
            page_size=10,
            search="alpha",
            type=["custom"],
            category=["search"],
            status=["enabled"],
            team_id=None,
            creator=["creator"],
            current_user=current,
        )
    )

    assert result.total == 1
    assert result.items[0].is_owned is False
    assert result.items[0].owner_team_name == "Owners"
    assert result.items[0].shared_with_count == 2


@pytest.mark.asyncio
async def test_list_tools_rejects_inaccessible_team_before_build(monkeypatch):
    current = user()
    team = SimpleNamespace(id=uuid4(), name="Mine")
    build = AsyncMock()
    monkeypatch.setattr(tools, "_get_accessible_teams", AsyncMock(return_value=[team]))
    monkeypatch.setattr(tools, "_build_accessible_tools", build)

    with pytest.raises(BusinessError) as exc_info:
        await tools.list_tools(
            page=1,
            page_size=10,
            search=None,
            type=None,
            category=None,
            status=None,
            team_id=[uuid4()],
            creator=None,
            current_user=current,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.msg_key == "not_team_member"
    build.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_tool_detail_handles_not_found_and_checks_access(monkeypatch):
    current = user()
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.get_tool_by_id(uuid4(), current)
    assert exc_info.value.msg_key == "tool_not_found"

    existing = db_tool(created_by=None)
    access = AsyncMock()
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=existing))
    monkeypatch.setattr(tools, "check_team_access", access)
    result = data(await tools.get_tool_by_id(existing.id, current))
    assert result.name == existing.name
    assert result.created_by_name is None
    access.assert_awaited_once_with(existing.team_id, current)


@pytest.mark.asyncio
async def test_create_tool_validates_duplicate_and_persists_with_audit(monkeypatch):
    current = user()
    team_id = uuid4()
    request = MagicMock()
    tool_in = ToolCreateInput(
        name="runner",
        display_name="Runner",
        custom_type="code",
        code_config={"language": "python", "code": "return 1"},
    )
    access = AsyncMock()
    scoped = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.deps, "check_scoped_permission", scoped)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    created = db_tool(
        team_id=team_id,
        name="runner",
        display_name="Runner",
        custom_type=DBCustomToolType.CODE,
        http_config={},
        code_config={"language": "python", "code": "return 1"},
        created_by_id=current.id,
        created_by=current,
    )
    create = AsyncMock(return_value=created)
    audit = AsyncMock()
    monkeypatch.setattr(tools.Tool, "create", create)
    monkeypatch.setattr(tools.AuditLogService, "log", audit)

    result = data(await tools.create_tool(team_id, tool_in, request, current))

    assert result.name == "runner"
    assert create.await_args.kwargs["created_by"] is current
    access.assert_awaited_once_with(team_id, current)
    scoped.assert_awaited_once_with(current, "tool:create", "team", team_id)
    audit.assert_awaited_once()

    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=created))
    with pytest.raises(BusinessError) as exc_info:
        await tools.create_tool(team_id, tool_in, request, current)
    assert exc_info.value.msg_key == "tool_name_exists"
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_update_tool_persists_fields_and_stops_on_duplicate(monkeypatch):
    current = user()
    existing = db_tool(created_by_id=current.id)
    request = MagicMock()
    queries = iter([Query(first=existing), Query()])
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: next(queries))
    monkeypatch.setattr(tools, "check_tool_write_access", AsyncMock())
    monkeypatch.setattr(tools.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(tools.AuditLogService, "log", AsyncMock())
    update = ToolUpdateInput(
        name="renamed",
        display_name="Renamed",
        description="Changed",
        category="api",
        custom_type="code",
        parameters=[{"name": "value", "type": "string"}],
        code_config={"language": "python", "code": "return 2"},
        credentials={"token": "new"},
        is_enabled=False,
    )

    result = data(await tools.update_tool(existing.id, update, request, current))

    assert result.name == "renamed"
    assert existing.custom_type == DBCustomToolType.CODE
    assert existing.is_enabled is False
    existing.save.assert_awaited_once()

    duplicate = db_tool()
    monkeypatch.setattr(
        tools.Tool,
        "filter",
        lambda **kwargs: Query(first=existing if "id" in kwargs else duplicate),
    )
    with pytest.raises(BusinessError) as exc_info:
        await tools.update_tool(
            existing.id, ToolUpdateInput(name="taken"), request, current
        )
    assert exc_info.value.msg_key == "tool_name_exists"
    assert existing.save.await_count == 1


@pytest.mark.asyncio
async def test_delete_and_toggle_cover_not_found_access_and_persistence(monkeypatch):
    current = user()
    request = MagicMock()
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.delete_tool(uuid4(), request, current)
    assert exc_info.value.msg_key == "tool_not_found"

    existing = db_tool(is_enabled=True)
    access = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=existing))
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools, "check_tool_write_access", AsyncMock())
    monkeypatch.setattr(tools.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(tools.AuditLogService, "log", audit)

    await tools.delete_tool(existing.id, request, current)
    existing.delete.assert_awaited_once()
    access.assert_awaited_once_with(existing.team_id, current, require_admin=True)

    result = data(await tools.toggle_tool(existing.id, request, current))
    assert result.is_enabled is False
    existing.save.assert_awaited_once()
    assert audit.await_count == 2


@pytest.mark.asyncio
async def test_builtin_execution_uses_team_config_and_returns_safe_provider_failure(
    monkeypatch,
):
    current = user()
    team_id = uuid4()
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: object())
    monkeypatch.setattr(tools.tool_registry, "execute", execute)
    monkeypatch.setattr(
        ToolConfig,
        "filter",
        lambda **_kwargs: Query(first=config(team_id=team_id)),
    )

    result = data(
        await tools.test_tool(
            ToolExecuteRequest(name="search", arguments={"q": "x"}), team_id, current
        )
    )
    assert result.success is True
    assert execute.await_args.kwargs["credentials"] == {"token": "secret"}

    monkeypatch.setattr(
        tools.tool_registry,
        "execute",
        AsyncMock(side_effect=RuntimeError("provider secret")),
    )
    monkeypatch.setattr(
        tools, "resolve_user_visible_error", lambda _error: "safe error"
    )
    failed = data(
        await tools.test_tool(ToolExecuteRequest(name="search"), None, current)
    )
    assert failed.success is False
    assert failed.error == "safe error"


@pytest.mark.asyncio
async def test_custom_execution_checks_team_and_covers_http_and_missing(monkeypatch):
    current = user()
    team_id = uuid4()
    access = AsyncMock()
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as exc_info:
        await tools.test_tool(ToolExecuteRequest(name="missing"), team_id, current)
    assert exc_info.value.msg_key == "tool_not_found"
    access.assert_awaited_once_with(team_id, current)

    existing = db_tool(team_id=team_id)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=existing))
    execute = AsyncMock(return_value={"success": False, "error": "upstream"})
    monkeypatch.setattr(tools, "execute_http_tool", execute)
    result = data(
        await tools.test_tool(
            ToolExecuteRequest(name=existing.name, arguments={"city": "Paris"}),
            team_id,
            current,
        )
    )
    assert result.success is False
    assert result.error == "upstream"
    execute.assert_awaited_once_with(
        existing.http_config, {"city": "Paris"}, existing.credentials
    )


@pytest.mark.asyncio
async def test_config_access_create_update_delete_and_persistence_failures(monkeypatch):
    current = user()
    request = MagicMock()
    monkeypatch.setattr(ToolConfig, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as exc_info:
        await tools.list_tool_configs(None, current)
    assert exc_info.value.status_code == 403

    with pytest.raises(BusinessError) as exc_info:
        await tools.create_tool_config(
            {"tool_name": "search", "credentials": {}}, request, None, current
        )
    assert exc_info.value.status_code == 403

    admin = user(is_superuser=True)
    existing = config(team_id=None)
    create = AsyncMock(return_value=existing)
    audit = AsyncMock()
    monkeypatch.setattr(ToolConfig, "create", create)
    monkeypatch.setattr(tools.AuditLogService, "log", audit)
    created = data(
        await tools.create_tool_config(
            {"tool_name": "search", "credentials": {"token": "secret"}},
            request,
            None,
            admin,
        )
    )
    assert created["tool_name"] == "search"
    audit.assert_awaited_once()

    monkeypatch.setattr(ToolConfig, "filter", lambda **_kwargs: Query(first=existing))
    updated = data(
        await tools.update_tool_config(
            "search", {"credentials": {"token": "new"}}, request, None, admin
        )
    )
    assert updated["credentials"] == {"token": "new"}
    existing.save.assert_awaited_once()

    await tools.delete_tool_config("search", request, None, admin)
    existing.delete.assert_awaited_once()

    failing = config(team_id=None)
    failing.save = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(ToolConfig, "filter", lambda **_kwargs: Query(first=failing))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await tools.update_tool_config(
            "search", {"credentials": {}}, request, None, admin
        )
    assert audit.await_count == 3
