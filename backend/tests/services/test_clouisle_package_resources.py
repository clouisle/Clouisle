import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.tool import Tool
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallRequest,
)
from app.schemas.response import BusinessError
from app.services.clouisle_package_resources import (
    AgentPackageAdapter,
    KnowledgeBasePackageAdapter,
    ToolPackageAdapter,
    WorkflowPackageAdapter,
)


class Query:
    def __init__(self, *, first=None, exists=False):
        self._first = first
        self._exists = exists

    async def first(self):
        return self._first

    async def exists(self):
        return self._exists


@asynccontextmanager
async def transaction():
    yield


def stub_tools_endpoint(monkeypatch, check_team_access=None):
    module = ModuleType("app.api.v1.endpoints.tools")
    module.check_team_access = check_team_access or AsyncMock()
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module.check_team_access


def tool(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "weather",
        "display_name": "Weather",
        "description": "Forecasts",
        "icon": None,
        "category": "other",
        "type": "custom",
        "custom_type": None,
        "parameters": [{"name": "city"}],
        "http_config": {"url": "https://example.test", "api_key": "secret"},
        "code_config": {"nested": {"password": "secret", "safe": True}},
        "mcp_config": {"headers": [{"Authorization": "Bearer secret"}]},
        "is_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_tool_export_sanitizes_secrets_and_checks_scope(monkeypatch):
    existing = tool()
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(first=existing),
    )
    check_scope = stub_tools_endpoint(monkeypatch)

    payload, dependencies, name = await ToolPackageAdapter().export(
        existing.id, SimpleNamespace(is_superuser=True)
    )

    assert name == "weather"
    assert dependencies == []
    assert payload["http_config"] == {"url": "https://example.test"}
    assert payload["code_config"] == {"nested": {"safe": True}}
    assert payload["mcp_config"] == {"headers": [{}]}
    check_scope.assert_awaited_once()
    assert check_scope.await_args.args[0] == existing.team_id


@pytest.mark.asyncio
async def test_tool_export_rejects_missing_tool(monkeypatch):
    stub_tools_endpoint(monkeypatch)
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(),
    )

    with pytest.raises(BusinessError) as exc_info:
        await ToolPackageAdapter().export(uuid4(), SimpleNamespace(is_superuser=True))

    assert exc_info.value.msg_key == "tool_not_found"


def test_tool_export_permission_is_required():
    user = SimpleNamespace(is_superuser=False, roles=[])

    with pytest.raises(BusinessError) as exc_info:
        ToolPackageAdapter().ensure_export_permission(user)

    assert exc_info.value.msg_key == "operation_not_permitted"


@pytest.mark.asyncio
async def test_tool_asset_round_trip_uses_only_safe_existing_files(
    tmp_path, monkeypatch
):
    source = tmp_path / "logo.png"
    source.write_bytes(b"logo")
    monkeypatch.setattr(
        "app.services.clouisle_package_resources._asset_source_path",
        lambda _path: source,
    )
    payload = {
        "icon": "/api/v1/upload/files/avatar/2026/07/logo.png",
        "assets": {"other": "assets/other/existing"},
    }
    adapter = ToolPackageAdapter()

    files = await adapter.export_files(payload)

    asset_path = "assets/icon/avatar/2026/07/logo.png"
    assert files == {asset_path: b"logo"}
    assert payload["assets"] == {"other": "assets/other/existing", "icon": asset_path}

    package_dir = tmp_path / "package"
    packaged = package_dir / asset_path
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes(b"logo")
    save_upload = AsyncMock(return_value={"url": "/uploaded/logo.png"})
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.save_generated_upload", save_upload
    )

    restored = await adapter.materialize_files(payload, package_dir)

    assert restored["icon"] == "/uploaded/logo.png"
    assert payload["icon"].startswith("/api/v1/upload/files/")
    save_upload.assert_awaited_once_with(
        content=b"logo",
        category="clouisle-assets",
        content_type="image/png",
        filename="logo.png",
    )


@pytest.mark.asyncio
async def test_tool_materialize_files_ignores_path_traversal(tmp_path, monkeypatch):
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    payload = {"icon": "original", "assets": {"icon": "../outside.png"}}
    save_upload = AsyncMock()
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.save_generated_upload", save_upload
    )

    restored = await ToolPackageAdapter().materialize_files(
        payload, tmp_path / "package"
    )

    assert restored["icon"] == "original"
    save_upload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [None, tool(name="taken")])
async def test_tool_conflict_reports_presence(monkeypatch, existing):
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(first=existing),
    )

    conflict = await ToolPackageAdapter().detect_conflict({"name": "taken"}, uuid4())

    if existing:
        assert conflict.type == "name_exists"
        assert conflict.existing_id == existing.id
    else:
        assert conflict.type == "none"


@pytest.mark.asyncio
async def test_tool_install_creates_disabled_tool(monkeypatch):
    created = tool(name="imported", is_enabled=False)
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.in_transaction", transaction
    )
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(exists=False),
    )
    monkeypatch.setattr("app.services.clouisle_package_resources.Tool.create", create)
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(is_superuser=True)

    result = await ToolPackageAdapter().install(
        manifest=None,
        resource_payload={"name": "imported", "display_name": "Imported"},
        team=team,
        user=user,
        install_in=ClouisleImportInstallRequest(),
    )

    assert result.installed == created.id
    assert create.await_args.kwargs["credentials"] == {}
    assert create.await_args.kwargs["is_enabled"] is False
    assert create.await_args.kwargs["name"] == "imported"


@pytest.mark.asyncio
async def test_tool_install_update_saves_fields(monkeypatch):
    existing = tool(display_name="Old")
    existing.save = AsyncMock()
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.in_transaction", transaction
    )
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(first=existing),
    )

    result = await ToolPackageAdapter().install(
        manifest=None,
        resource_payload={"name": existing.name, "display_name": "New"},
        team=SimpleNamespace(id=existing.team_id),
        user=SimpleNamespace(is_superuser=True),
        install_in=ClouisleImportInstallRequest(action=ClouisleConflictAction.UPDATE),
    )

    assert result.updated == existing.id
    assert existing.display_name == "New"
    existing.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_tool_install_rejects_duplicate_name(monkeypatch):
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.in_transaction", transaction
    )
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(exists=True),
    )

    with pytest.raises(BusinessError) as exc_info:
        await ToolPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "taken"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True),
            install_in=ClouisleImportInstallRequest(),
        )

    assert exc_info.value.msg_key == "clouisle_name_conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "model_path"),
    [
        (AgentPackageAdapter(), "Agent"),
        (WorkflowPackageAdapter(), "Workflow"),
        (KnowledgeBasePackageAdapter(), "KnowledgeBase"),
    ],
)
async def test_other_adapters_report_name_conflicts(monkeypatch, adapter, model_path):
    existing = SimpleNamespace(id=uuid4(), name="taken")
    monkeypatch.setattr(
        f"app.services.clouisle_package_resources.{model_path}.filter",
        lambda **_kwargs: Query(first=existing),
    )

    conflict = await adapter.detect_conflict({"name": "taken"}, uuid4())

    assert conflict.type == "name_exists"
    assert conflict.existing_id == existing.id


@pytest.mark.asyncio
async def test_rename_advances_to_first_available_name(monkeypatch):
    attempts = iter([True, True, False])
    monkeypatch.setattr(
        "app.services.clouisle_package_resources.Tool.filter",
        lambda **_kwargs: Query(exists=next(attempts)),
    )

    name = await ToolPackageAdapter()._target_name(
        {"name": "weather"},
        uuid4(),
        ClouisleImportInstallRequest(action=ClouisleConflictAction.RENAME),
        Tool,
    )

    assert name == "weather_import_2"
